"""Query-quality gate for the free-text Technology tool (#67).

The old gate was a single absolute embedding distance (``OFF_TOPIC_DIST = 0.55``
in ``scripts/tech_analyze.py``). In a 1024-dim space *every* phrase has a nearest
CPC class, and the nearest-distance distributions of real technologies and
nonsense overlap ("recipe for pancakes" → A21D13/44 at 0.228, closer than
"quantum error correction" at 0.304). This module replaces it with GPU-free
signals measured on the nearest-neighbour list and the patent title index,
combined into a three-way verdict:

    ok         → run the analysis on the default selection (unchanged fast path)
    ambiguous  → the phrase is technical but the words point to a different
                 patent field than the embedding; the user picks one BEFORE any
                 number is produced
    off_topic  → no technology signature; answer honestly with 2–3 nearest real
                 fields as clickable suggestions instead of a number

Measured basis (docs/tech_query_gate_2026-09-04.md; 26 technologies, 25
nonsense/everyday phrases, 8 grey phrases; live Qwen3-Embedding-8B vectors and
all raw signals cached in tests/fixtures/tech_query_gate.json so the regression
tests/test_query_gate.py runs without GPU or DB):

    d1 (nearest distance)   does NOT separate: tech 0.145–0.304, nonsense
                            0.228–0.573 (pancakes 0.228, weather 0.262 inside
                            the tech band).
    margin20 = d20 − d1     does NOT separate: tech 0.025–0.141, nonsense
                            0.021–0.212 ("best pizza in berlin" 0.155). The
                            "flat shelf" hypothesis of the issue is refuted —
                            nonsense can have ONE coincidentally close class.
    sections12              does NOT separate: tech 1–4 sections, nonsense 1–5.
    d20 (20th neighbour)    SEPARATES with a clear gap: tech max 0.343 ("quantum
                            error correction"), nonsense min 0.381 ("recipe for
                            pancakes"), 2nd 0.395 ("unicorn breeding"). A real
                            technology has ≥ 20 sibling classes within ~0.34; a
                            nonsense phrase has at most a few coincidental
                            neighbours and then nothing.
    and_hits (title index)  second, independent signal: 14/25 nonsense phrases
                            have 0 patent titles containing all their terms; every
                            technology has ≥ 4 (min "perovskite tandem
                            photovoltaics", 2nd 12). Kept as a hedge against
                            embedding-level drift (a model swap shifts all
                            distances; tech_query.py:218).
    lexical field mismatch  the subclass distribution of the title hits vs. the
                            embedding's top-12 subclasses. "quantum error
                            correction" embeds into H03M13 (classical channel
                            codes, 92 % of the top-12) while 55 % of its title
                            hits carry G06N (quantum computing) → AMBIGUOUS.
                            Y-section cross-tags are excluded (Y02E dominates
                            every battery/solar title, it is not a field).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

# ---------------------------------------------------------------------------
# Thresholds — each sits in the measured gap between the two sets.
# ---------------------------------------------------------------------------
# 20th-neighbour distance: tech max 0.343, nonsense min 0.381 → midpoint. The old
# nearest-distance cap (0.55) is kept only as a sanity bound far outside the data.
D20_MAX = 0.36
D1_HARD_CAP = 0.55
# Title-index evidence: 0 filings whose title carries ALL the terms → no patent
# language basis (tech min = 4). Counting is clamped so the GIN scan stops early.
FT_CLAMP = 5001
FT_SAMPLE = 300     # filings sampled for the lexical field estimate
# Lexical-vs-embedding field mismatch → ambiguous. Needs enough title evidence to
# estimate a field (≥ FT_FIELD_MIN_HITS filings) and a dominant lexical subclass
# (≥ FT_FIELD_MIN_SHARE of the sample) that the embedding's top-12 do not contain.
# Measured shares (non-Y): "quantum error correction" G06N 0.55 (mismatch);
# technologies whose lexical top field differs from the embedding's stay below
# 0.13 ("metal powder 3D printing" B33Y 0.12, "heat pump" D06F 0.06) — see the
# doc table. 0.40 leaves room on both sides.
FT_FIELD_MIN_HITS = 20
FT_FIELD_MIN_SHARE = 0.40

TOP_K = 20          # neighbours fetched (d20)
COHERENCE_K = 12    # the toggleable candidates the tool shows (MAX_CANDIDATES)
SUGGESTIONS = 3

_STOP = {
    "the", "a", "an", "of", "for", "in", "on", "at", "to", "and", "or", "with",
    "my", "is", "are", "how", "what", "why", "who", "when", "where", "be", "it",
    "this", "that", "best", "top", "new", "into", "from", "by", "vs", "versus",
}


# ---------------------------------------------------------------------------
# Signal collection (DB) — one pgvector query + two GIN lookups
# ---------------------------------------------------------------------------
def nearest_classes(vec1024: list[float], k: int = TOP_K, min_patents: int = 50) -> list[dict]:
    """Top-k fine CPC classes by cosine distance, with title + hierarchy path, NOT
    truncated by any distance gate (the gate is the point of this module)."""
    from pipeline.db import get_connection
    vlit = "[" + ",".join(f"{x:.6f}" for x in vec1024) + "]"
    with get_connection() as c:
        rows = c.execute(
            "SELECT symbol, title, title_path, n_patents, "
            f"       (embedding_1024 <=> '{vlit}'::vector) AS dist "
            "FROM cpc_fine WHERE embedding_1024 IS NOT NULL "
            f"  AND n_patents >= {int(min_patents)} "
            f"ORDER BY embedding_1024 <=> '{vlit}'::vector LIMIT {int(k)}"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        out.append({"symbol": d["symbol"], "title": (d.get("title") or "").strip(),
                    "title_path": (d.get("title_path") or "").strip(),
                    "n_patents": int(d.get("n_patents") or 0),
                    "dist": round(float(d["dist"]), 4)})
    return out


def query_terms(query: str) -> list[str]:
    """Content words of the phrase (≥ 3 letters, no stopwords) — for diagnostics."""
    toks = re.findall(r"[a-z0-9][a-z0-9\-]+", query.lower())
    return [t for t in toks if len(t) >= 3 and t not in _STOP]


def fulltext_hits(query: str, clamp: int = FT_CLAMP, sample: int = FT_SAMPLE) -> dict:
    """Title-level full-text evidence on patent_search (19.8M filings, GIN index
    idx_patent_search_tsv):

        and_hits   filings matching ALL terms (websearch_to_tsquery), count clamped
                   at `clamp` so the GIN scan stops early (0.1–0.4 s worst case)
        fields     CPC subclass distribution of up to `sample` of those filings
                   (Y-section cross-tags excluded — they are not fields), plus the
                   leading subclass's top fine codes. This is the LEXICAL field
                   estimate that the verdict compares with the embedding's field.
    """
    import time
    from pipeline.db import get_connection
    t0 = time.time()
    with get_connection() as c:
        c.execute("SET statement_timeout = '5s'")
        row = c.execute(
            "SELECT count(*) AS n FROM (SELECT 1 FROM patent_search "
            "  WHERE tsv @@ websearch_to_tsquery('english', ?) LIMIT ?) x",
            (query, int(clamp))).fetchone()
        n = int(dict(row)["n"]) if row is not None else 0
        fields: list[dict] = []
        top_codes: list[dict] = []
        if n > 0:
            rows = c.execute(
                "WITH hit AS (SELECT pub_number FROM patent_search "
                "             WHERE tsv @@ websearch_to_tsquery('english', ?) LIMIT ?) "
                "SELECT left(pc.cpc, 4) AS sub, count(DISTINCT pc.pub_number) AS n "
                "FROM hit JOIN patent_cpc_full pc ON pc.pub_number = hit.pub_number "
                "WHERE left(pc.cpc, 1) <> 'Y' GROUP BY 1 ORDER BY 2 DESC LIMIT 5",
                (query, int(sample))).fetchall()
            fields = [{"subclass": dict(r)["sub"], "n": int(dict(r)["n"])} for r in rows]
            if fields:
                rows = c.execute(
                    "WITH hit AS (SELECT pub_number FROM patent_search "
                    "             WHERE tsv @@ websearch_to_tsquery('english', ?) LIMIT ?) "
                    "SELECT pc.cpc, count(DISTINCT pc.pub_number) AS n "
                    "FROM hit JOIN patent_cpc_full pc ON pc.pub_number = hit.pub_number "
                    "WHERE left(pc.cpc, 4) = ? GROUP BY 1 ORDER BY 2 DESC LIMIT 4",
                    (query, int(sample), fields[0]["subclass"])).fetchall()
                top_codes = [{"symbol": dict(r)["cpc"], "n": int(dict(r)["n"])} for r in rows]
                syms = [t["symbol"] for t in top_codes] + [fields[0]["subclass"]]
                titles = {dict(r)["symbol"]: (dict(r)["title"] or "").strip() for r in c.execute(
                    "SELECT symbol, title FROM cpc_fine WHERE symbol = ANY(?)", (syms,)).fetchall()}
                for t in top_codes:
                    t["title"] = titles.get(t["symbol"], "")
                fields[0]["title"] = titles.get(fields[0]["subclass"], "")
    return {"and_hits": n, "sample": min(n, sample), "fields": fields,
            "top_codes": top_codes, "ms": round((time.time() - t0) * 1000)}


def collect_signals(vec1024: list[float], query: str, min_patents: int = 50) -> dict:
    """Everything the verdict needs, from the DB. Returned dict is JSON-safe and
    is exactly what the fixture caches (so the regression runs GPU-/DB-free)."""
    nb = nearest_classes(vec1024, k=TOP_K, min_patents=min_patents)
    ft = fulltext_hits(query)
    return {"neighbours": nb, "fulltext": ft}


# ---------------------------------------------------------------------------
# Pure functions — signals → derived features → verdict (no I/O; tested)
# ---------------------------------------------------------------------------
def subclass_of(symbol: str) -> str:
    return symbol[:4]


def main_group_of(symbol: str) -> str:
    return symbol.split("/")[0]


def derive(signals: dict) -> dict:
    """Derived features from the raw neighbour list + title-index counts."""
    nb: list[dict] = signals.get("neighbours") or []
    ft: dict = signals.get("fulltext") or {}
    dists = [float(n["dist"]) for n in nb]
    last = dists[-1] if dists else 1.0
    d1 = dists[0] if dists else 1.0
    d5 = dists[4] if len(dists) >= 5 else last
    d12 = dists[11] if len(dists) >= 12 else last
    d20 = dists[19] if len(dists) >= 20 else last
    top = nb[:COHERENCE_K]
    sub = Counter(subclass_of(n["symbol"]) for n in top)
    sec = Counter(n["symbol"][:1] for n in top)
    grp = Counter(main_group_of(n["symbol"]) for n in top)
    top_share = (sub.most_common(1)[0][1] / len(top)) if top else 0.0
    fields = ft.get("fields") or []
    sample = int(ft.get("sample") or 0)
    ft_top = fields[0]["subclass"] if fields else None
    ft_share = (fields[0]["n"] / sample) if (fields and sample) else 0.0
    return {
        "d1": round(d1, 4), "d5": round(d5, 4), "d12": round(d12, 4), "d20": round(d20, 4),
        "margin20": round(d20 - d1, 4),
        "sections12": len(sec), "subclasses12": len(sub), "groups12": len(grp),
        "top_subclass_share12": round(top_share, 3),
        "emb_subclasses": [s for s, _ in sub.most_common()],
        "and_hits": int(ft.get("and_hits", 0)),
        "ft_top_subclass": ft_top, "ft_top_share": round(ft_share, 3),
        "ft_mismatch": bool(ft_top and ft_top not in sub
                            and int(ft.get("and_hits", 0)) >= FT_FIELD_MIN_HITS
                            and ft_share >= FT_FIELD_MIN_SHARE),
    }


_CPC_REF = re.compile(r"\b[A-HY]\d{2}[A-Z]\s?\d+(?:/\d+)?\b")


def _clean_title(t: str) -> str:
    """CPC titles as UI labels: drop parenthesised notes, cross-references
    ('H03M13/31 and H03M13/33 take precedence') and dangling connectors."""
    t = re.sub(r"\s+", " ", t or "").strip(" ;,")
    t = re.sub(r"\s*\(.*?\)\s*", " ", t)
    t = re.sub(r"\b(?:and|or|,)?\s*" + _CPC_REF.pattern + r"(?:\s*(?:and|or|,)\s*" + _CPC_REF.pattern + r")*"
               r"\s*(?:takes? precedence)?", " ", t)
    t = re.sub(r"\s*\btakes? precedence\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" ;,-")
    return t


def _field_label(n: dict) -> str:
    """Human-readable field name for a neighbour: its own title if it is a
    sentence-like title, else the last complete element of the hierarchy path
    (sub-group fragments like 'of plastic materials' are useless as a search
    suggestion)."""
    title = _clean_title(n.get("title", ""))
    path = [p.strip() for p in (n.get("title_path") or "").split(">") if p.strip()]
    if title and title[0].isupper() and len(title) >= 12:
        return title
    for p in reversed(path):
        p = _clean_title(p)
        if p and p[0].isupper() and len(p) >= 12 and not p.isupper():
            return p
    return title or n.get("symbol", "")


def suggestions(signals: dict, k: int = SUGGESTIONS) -> list[dict]:
    """The nearest DISTINCT real fields (one per CPC main group) as clickable
    suggestions: {symbol, label, dist}. Label = short plain-language field name."""
    seen: set[str] = set()
    out: list[dict] = []
    for n in signals.get("neighbours") or []:
        g = main_group_of(n["symbol"])
        if g in seen:
            continue
        label = _field_label(n)
        if not label or label.lower() in {o["label"].lower() for o in out}:
            continue
        seen.add(g)
        out.append({"symbol": n["symbol"], "label": label[:90], "dist": round(float(n["dist"]), 3)})
        if len(out) >= k:
            break
    return out


def _subclass_label(n: dict) -> str:
    path = [p.strip() for p in (n.get("title_path") or "").split(">") if p.strip()]
    caps = [p for p in path if p.isupper() and len(p) >= 4]
    label = _clean_title(caps[-1]).capitalize() if caps else _field_label(n)
    return label[:90]


def clusters(signals: dict, k: int = COHERENCE_K) -> list[dict]:
    """The choice list for an AMBIGUOUS verdict: the lexical field (from the
    title hits) first, then the embedding's top-k neighbours grouped by CPC
    subclass — {subclass, label, symbols[], n, source}."""
    out: list[dict] = []
    ft = signals.get("fulltext") or {}
    fields = ft.get("fields") or []
    if fields and ft.get("top_codes"):
        f0 = fields[0]
        codes = [t["symbol"] for t in ft["top_codes"]]
        label = _clean_title(f0.get("title") or "").capitalize() or f0["subclass"]
        detail = "; ".join(_clean_title(t.get("title") or "") for t in ft["top_codes"]
                           if t.get("title"))
        out.append({"subclass": f0["subclass"], "label": label[:90], "detail": detail[:160],
                    "symbols": codes, "n": int(f0["n"]), "source": "words"})
    groups: dict[str, dict] = {}
    for n in (signals.get("neighbours") or [])[:k]:
        s = subclass_of(n["symbol"])
        g = groups.setdefault(s, {"subclass": s, "label": _subclass_label(n), "detail": "",
                                  "symbols": [], "n": 0, "source": "embedding"})
        g["symbols"].append(n["symbol"])
        g["n"] += int(n.get("n_patents") or 0)
        if not g["detail"]:
            g["detail"] = _field_label(n)[:160]
    out.extend(g for g in groups.values() if g["subclass"] != (out[0]["subclass"] if out else None))
    return out


def verdict(signals: dict) -> dict:
    """Combined rule → {"verdict", "reason", "features", "suggestions", "clusters"}.

        off_topic  if d20 > D20_MAX (no technology neighbourhood)
                   or and_hits == 0 (no patent title carries these terms)
                   or d1 > D1_HARD_CAP (sanity bound)
        ambiguous  if the title hits' dominant subclass (≥ FT_FIELD_MIN_SHARE of
                   ≥ FT_FIELD_MIN_HITS filings, Y excluded) is absent from the
                   embedding's top-12 subclasses
        ok         otherwise
    """
    f = derive(signals)
    sugg = suggestions(signals)
    if f["d1"] > D1_HARD_CAP or f["d20"] > D20_MAX:
        return {"verdict": "off_topic", "features": f, "suggestions": sugg, "clusters": [],
                "reason": (f"no technology neighbourhood — the 20 nearest patent classes "
                           f"reach {f['d20']:.2f} (technologies stay under {D20_MAX})")}
    if f["and_hits"] == 0:
        return {"verdict": "off_topic", "features": f, "suggestions": sugg, "clusters": [],
                "reason": "no patent title contains these terms together"}
    if f["ft_mismatch"]:
        return {"verdict": "ambiguous", "features": f, "suggestions": sugg,
                "clusters": clusters(signals),
                "reason": (f"the words point to {f['ft_top_subclass']} "
                           f"({f['ft_top_share']:.0%} of matching patent titles) but the "
                           f"closest classes are in {', '.join(f['emb_subclasses'][:3])}")}
    return {"verdict": "ok", "features": f, "suggestions": [], "clusters": [],
            "reason": "technology neighbourhood with patent-title evidence"}


def gate(vec1024: list[float], query: str, min_patents: int = 50) -> dict:
    """DB-backed convenience: collect the signals and judge them."""
    sig = collect_signals(vec1024, query, min_patents=min_patents)
    out = verdict(sig)
    out["signals"] = sig
    return out


def summarize(items: list[dict[str, Any]]) -> str:
    """Markdown table of derived features + verdicts for a measured test set
    (items: {"query", "group", "signals"})."""
    rows = ["| group | query | d1 | d20 | margin20 | sect12 | subcl12 | emb top | and_hits | words top (share) | verdict |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for it in items:
        v = verdict(it["signals"])
        f = v["features"]
        ft_top = f"{f['ft_top_subclass']} ({f['ft_top_share']:.2f})" if f["ft_top_subclass"] else "—"
        rows.append(f"| {it['group']} | {it['query']} | {f['d1']:.3f} | {f['d20']:.3f} | "
                    f"{f['margin20']:.3f} | {f['sections12']} | {f['subclasses12']} | "
                    f"{f['emb_subclasses'][0] if f['emb_subclasses'] else '—'} | {f['and_hits']} | "
                    f"{ft_top} | **{v['verdict']}** |")
    return "\n".join(rows)
