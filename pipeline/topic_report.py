"""Topic engine — a term in, the data situation out (Stufe 1, 2026-09-17).

Owner decision 2026-09-16: the user names a topic and gets the trend data for
it; cluster and nest discovery become suppliers of suggestions. Plan and the
measurements every rule below rests on: docs/plan_topic_search_2026-09-16.md.

What one call does, in order:

1. Embed the query on the CPU embedder (:8091, same space as
   trends.embedding_1024, Matryoshka prefix). No other model is involved.
2. Ask each requested lead-time tier SEPARATELY for its 1,000 nearest rows.
   The embedding follows the register a text is written in, so a query finds
   the tier it is phrased like; pooling the tiers would date the loudest one
   and call it the topic (Owner 2026-09-15). Each tier needs its own HNSW index
   (pipeline.topic_vectors): through the global index, a filter keeps 0-8
   patent rows where the tier's own index finds 14-58.
3. Cut each tier relative to its own head. A fixed threshold fails: patents
   speak a register the query does not, so their best match sits 0.08-0.10
   below the science head for the same topic. head - 0.08, floored, and the
   applied cut is part of the answer. A head below the tier's HEAD_MIN means
   "nothing close" — calibrated on 2026-09-17 against three control topics
   (falconry, pottery, harpsichord: heads 0.52-0.63) and seven known ones
   (0.68-0.91).
4. Count the rows above the cut per month, per tier, and hand the curves to
   the same scorer the nest layer uses (emerging.score_nests): first month per
   tier, tier order, science-to-market lag, novelty lift normalised by the
   corpus, acceleration, the established-source guard, market actors.
5. Look for the topic's PAST by full text: the oldest lexical hits, gated by
   the vector so "milk" in 1992 does not count, and a one-round vocabulary
   walk — distinctive word pairs of the oldest hits, each embedded and kept
   only if it stays close to the query, then dated by full text. A topic is a
   sequence of words, not one word; the vector alone misses the early ones.
6. Store the report (topic_reports) so the same question is answered from
   cache, and the list of questions asked feeds the suggestion stage later.

Honesty rules the report carries: a tier whose hits fill the neighbour window
is CAPPED (the curve is a floor, not a count); a tier with fewer than MIN_HITS
rows is THIN; a short query whose neighbours spread over several verticals is
returned as a question, not a curve; per-source months far above that source's
own median are damped in a second total so a back-ingest cannot pass for a
trend; and the share of hits from sources we already read two years ago says
whether an early date is about the world or about our subscriptions.

Nothing here writes to trends. CLI: python -m pipeline.topic_report "term".
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np

from pipeline import db as db_mod
from pipeline.config import RESEARCH_EMBED_HOST
from pipeline.db import get_connection
from pipeline.emerging import score_nests
from pipeline.foresight import _norm_tag, month_key
from pipeline.tiers import TIERS

logger = logging.getLogger("topic_report")

# --- calibration (2026-09-17, see module docstring) ---------------------------
#: A tier answers only if the mean of its five best similarities reaches this.
HEAD_MIN = {"science": 0.68, "patent": 0.64, "funding": 0.66, "market": 0.68}
#: The cut is head - DROP, never below FLOOR. Controls never exceeded 0.62.
#: 0.08, not 0.12: at 0.12 the science tier of a known topic admitted the whole
#: field (sustained since 2001-02, 616 rows); at 0.08 it dated the topic itself
#: (2020-01, 155 rows) and the market's first hit fell on the month the owner
#: had noted independently.
DROP = float(os.getenv("TOPIC_DROP", "0.08"))
FLOOR = float(os.getenv("TOPIC_FLOOR", "0.62"))
#: pgvector 0.6 caps hnsw.ef_search at 1,000 — the neighbour window per tier.
NEIGHBOURS = 1000
MIN_HITS = 5
#: Hits above the cut at or above this share of the window: the curve is a floor.
CAPPED_SHARE = 0.9
STATUS_FILTER = ("signal", "published")

#: Short query + neighbours spread over verticals → ask back instead of answering.
AMBIG_MAX_TOKENS = 2
AMBIG_TOP_SHARE = 0.40
AMBIG_SAMPLE = 60
#: A short query whose best tier head stays below this is a word, not a topic:
#: "rag" embedded as cloth and answered with 134 science rows at head 0.686.
AMBIG_HEAD = 0.75

#: Actor windows (market tier): early = up to 24 months before the last month,
#: late = the last 12 months.
EARLY_BEFORE_MONTHS = 24
LATE_MONTHS = 12
#: Per-source damping only when a source has this many active months in the hits.
DAMP_MIN_MONTHS = 6

WALK_CANDIDATES = 8
WALK_GATE = float(os.getenv("TOPIC_WALK_GATE", "0.72"))
WALK_SEED_ROWS = 40
FULLTEXT_OLDEST = 8

CACHE_DAYS = 7
CORPUS_CACHE_HOURS = 24

# Must match idx_trends_fts textually (scripts/corpus_research.FTS_VECTOR,
# frontend/src/lib/db.ts) or the GIN index is not used.
FTS_VECTOR = ("to_tsvector('english', coalesce(title_en,'') || ' ' || "
              "coalesce(summary_en,'') || ' ' || coalesce(tags::text,''))")

STOPWORDS = {
    "a", "an", "and", "the", "of", "for", "in", "on", "to", "with", "by", "from",
    "at", "as", "is", "are", "be", "or", "its", "into", "than", "that", "this",
    "new", "how", "why", "what", "using", "based", "via", "vs", "after", "over",
    "under", "between", "about", "more", "most", "first", "next", "your", "our",
    "their", "his", "her", "it", "up", "out", "not", "no", "can", "will", "may",
    "could", "should", "has", "have", "had", "was", "were", "been", "being",
    "we", "you", "they", "i", "he", "she", "one", "two", "three", "year", "years",
    "study", "studies", "review", "analysis", "effect", "effects", "role",
    "method", "methods", "system", "systems", "approach", "towards", "toward",
}


class EmbedderUnavailable(RuntimeError):
    pass


# --- pure helpers (tested without a DB) ---------------------------------------

def normalise_query(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower())


def query_tokens(q: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-]*", (q or "").lower())
            if t not in STOPWORDS and len(t) > 1]


def vec_literal(v) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in v) + "]"


def assess_tier(rows: list[dict], tier: str) -> dict:
    """Head, cut and status of one tier's neighbour list (rows sorted by sim desc).

    status: 'none' (head below HEAD_MIN — nothing close), 'thin' (fewer than
    MIN_HITS above the cut), 'ok'. `capped` says the hits filled the window."""
    sims = [float(r["sim"]) for r in rows]
    head = float(np.mean(sims[:5])) if sims else 0.0
    head_min = HEAD_MIN.get(tier, 0.68)
    cut = round(max(head - DROP, FLOOR), 3)
    if head < head_min:
        hits: list[dict] = []
        status = "none"
    else:
        hits = [r for r in rows if float(r["sim"]) >= cut]
        status = "thin" if len(hits) < MIN_HITS else "ok"
    capped = bool(rows) and len(rows) >= NEIGHBOURS and len(hits) >= CAPPED_SHARE * len(rows)
    return {"status": status, "head": round(head, 3), "head_min": head_min,
            "cut": cut, "found": len(rows), "hits": hits, "capped": capped}


def month_series(rows: list[dict], months: list[str]) -> list[int]:
    idx = {m: i for i, m in enumerate(months)}
    out = [0] * len(months)
    for r in rows:
        mk = month_key(r.get("published_date"))
        if mk in idx:
            out[idx[mk]] += 1
    return out


def damped_total(rows: list[dict], months: list[str]) -> int:
    """Total after capping each source's month at that source's own median
    over its active months — a back-ingest of one outlet is not a trend.
    Sources with fewer than DAMP_MIN_MONTHS active months are left alone."""
    per: dict[str, Counter] = defaultdict(Counter)
    valid = set(months)
    for r in rows:
        mk = month_key(r.get("published_date"))
        if mk in valid:
            per[r.get("source_name") or ""][mk] += 1
    total = 0
    for src, cnt in per.items():
        vals = list(cnt.values())
        if len(vals) >= DAMP_MIN_MONTHS:
            med = float(np.median(vals))
            total += int(sum(min(v, med) for v in vals))
        else:
            total += sum(vals)
    return total


def ambiguity(query: str, pooled: list[dict], best_head: float | None = None) -> dict | None:
    """A one- or two-word query is a question, not an answer, when its nearest
    rows spread across verticals OR its best tier head stays below AMBIG_HEAD
    (pattern of the technology query gate, #67)."""
    if len(query_tokens(query)) > AMBIG_MAX_TOKENS or len(pooled) < 10:
        return None
    top = sorted(pooled, key=lambda r: -float(r["sim"]))[:AMBIG_SAMPLE]
    verts = Counter((r.get("primary_vertical") or "?") for r in top)
    lead, n = verts.most_common(1)[0]
    spread = n / len(top) < AMBIG_TOP_SHARE
    weak = best_head is not None and best_head < AMBIG_HEAD
    if not spread and not weak:
        return None
    fields = []
    for v, c in verts.most_common(3):
        titles = [r.get("title_en") or "" for r in top if (r.get("primary_vertical") or "?") == v][:3]
        fields.append({"vertical": v, "share": round(c / len(top), 2), "titles": titles})
    why = (f"its nearest rows spread over {len(verts)} verticals (largest {lead} at {round(100 * n / len(top))} %)"
           if spread else f"its best match is weak (head {best_head:.2f} < {AMBIG_HEAD})")
    return {"reason": f"'{query}' is short and {why}", "fields": fields}


def chain_candidates(titles: list[str], query: str, top: int = WALK_CANDIDATES) -> list[str]:
    """Distinctive word pairs of old titles — the vocabulary the topic used to
    wear. Pairs that are already in the query are not a discovery."""
    qtoks = set(query_tokens(query))
    qnorm = normalise_query(query)
    pairs: Counter = Counter()
    for t in titles:
        toks = [w for w in re.findall(r"[a-z][a-z0-9\-]+", (t or "").lower())
                if w not in STOPWORDS and len(w) > 2]
        seen = set()
        for a, b in zip(toks, toks[1:]):
            if a == b or (a in qtoks and b in qtoks):
                continue
            pair = f"{a} {b}"
            if pair in qnorm or pair in seen:
                continue
            seen.add(pair)
            pairs[pair] += 1
    return [p for p, n in pairs.most_common(top * 2) if n >= 2][:top]


def actor_windows(months: list[str]) -> tuple[str, str] | None:
    if len(months) < EARLY_BEFORE_MONTHS + 1:
        return None
    return months[-EARLY_BEFORE_MONTHS - 1], months[-LATE_MONTHS]


def actor_sets(rows: list[dict], windows: tuple[str, str] | None) -> dict[str, int]:
    if not windows:
        return {"early": 0, "late": 0}
    early, late = set(), set()
    for r in rows:
        mk = month_key(r.get("published_date"))
        if not mk:
            continue
        names = [str(n).strip().lower() for n in (list(r.get("brands") or []) + list(r.get("companies") or [])) if n]
        if not names:
            continue
        if mk <= windows[0]:
            early.update(names[:6])
        elif mk >= windows[1]:
            late.update(names[:6])
    return {"early": len(early), "late": len(late)}


def spread_by_source(rows: list[dict], limit: int, max_per_source: int = 1) -> list[dict]:
    """Take `limit` rows in their incoming order, at most `max_per_source` from
    one source; a source's surplus fills up only if the list would be short."""
    picked, spare, seen = [], [], Counter()
    for r in rows:
        key = r.get("source_name") or ""
        if key and seen[key] >= max_per_source:
            spare.append(r)
            continue
        seen[key] += 1
        picked.append(r)
        if len(picked) >= limit:
            return picked
    return picked + spare[: max(0, limit - len(picked))]


def _compact(row: dict) -> dict:
    d = row.get("published_date")
    return {"id": row.get("id"), "title": (row.get("title_en") or "")[:140],
            "source": row.get("source_name"), "url": row.get("source_url"),
            "slug": row.get("slug") if row.get("status") == "published" else None,
            "date": (d.isoformat()[:10] if hasattr(d, "isoformat") else (str(d)[:10] if d else None)),
            "sim": round(float(row.get("sim") or 0), 3)}


# --- DB access ----------------------------------------------------------------

def embed_query(text: str, host: str | None = None) -> np.ndarray:
    """Query vector in the space of trends.embedding_1024 (unit length)."""
    from pipeline import llamacpp_client
    host = host or RESEARCH_EMBED_HOST
    vec = llamacpp_client.generate_embedding(text, host=host) if host else None
    if not vec:
        raise EmbedderUnavailable(
            "no embedding returned — start the CPU embedder "
            "(systemctl --user start catandary-embed-cpu) or set RESEARCH_EMBED_HOST")
    if len(vec) < 1024:
        raise EmbedderUnavailable(
            f"embedding endpoint returned {len(vec)} dimensions — a chat model "
            "answered /v1/embeddings, not the embedding model")
    v = np.asarray(vec[:1024], dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n else v


_ROW_COLS = ("t.id, t.title_en, t.source_name, t.source_url, t.slug, t.status, v.tier, "
             "t.trend_signal_type, t.primary_vertical, t.tags, t.brands, t.companies, r.published_date")


def search_tier(vec: np.ndarray, tier: str, exact: bool = False) -> list[dict]:
    """The tier's NEIGHBOURS nearest rows, similarity descending.

    Index path: the tier's partial HNSW index on topic_vectors answers
    `WHERE tier = ?` with ef_search = NEIGHBOURS. Without that index the
    planner scans the tier's rows — correct, slow — and the report says which
    index answered. `exact=True` forces the scan (for recounts, never for a
    page request)."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}")
    lit = vec_literal(vec)
    sts = ",".join("?" * len(STATUS_FILTER))
    sql = (
        f"SELECT {_ROW_COLS}, 1 - (v.embedding_1024 <=> ?::vector) AS sim "
        "FROM (SELECT trend_id, tier, embedding_1024 FROM topic_vectors v WHERE v.tier = ? "
        "      ORDER BY v.embedding_1024 <=> ?::vector LIMIT ?) v "
        "JOIN trends t ON t.id = v.trend_id JOIN raw_entries r ON t.raw_entry_id = r.id "
        f"WHERE t.status IN ({sts}) AND (r.published_date IS NULL OR r.published_date <= CURRENT_TIMESTAMP) "
        "ORDER BY sim DESC"
    )
    params = [lit, tier, lit, NEIGHBOURS, *STATUS_FILTER]
    with get_connection() as conn:
        if db_mod.USE_POSTGRES:
            if exact:
                conn.execute("SET LOCAL enable_indexscan = off")
                conn.execute("SET LOCAL enable_bitmapscan = off")
            else:
                conn.execute(f"SET LOCAL hnsw.ef_search = {NEIGHBOURS}")
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    for r in rows:
        for k in ("tags", "brands", "companies"):
            v = r.get(k)
            if isinstance(v, str):
                try:
                    r[k] = json.loads(v)
                except ValueError:
                    r[k] = []
    return rows


def fulltext_oldest(query: str, vec: np.ndarray, limit: int = FULLTEXT_OLDEST) -> list[dict]:
    """Oldest lexical hits, gated by the vector (sim >= FLOOR) so a shared word
    does not pass for the topic. `websearch_to_tsquery` takes the query as
    typed (quotes for phrases, OR, -)."""
    if not db_mod.USE_POSTGRES:
        return []
    sts = ",".join("?" * len(STATUS_FILTER))
    sql = (
        f"SELECT {_ROW_COLS}, 1 - (t.embedding_1024 <=> ?::vector) AS sim "
        "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
        "LEFT JOIN topic_vectors v ON v.trend_id = t.id "
        f"WHERE {FTS_VECTOR} @@ websearch_to_tsquery('english', ?) "
        f"AND t.status IN ({sts}) AND t.embedding_1024 IS NOT NULL "
        "AND r.published_date <= CURRENT_TIMESTAMP "
        "ORDER BY r.published_date ASC LIMIT ?"
    )
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(sql, [vec_literal(vec), query, *STATUS_FILTER, limit * 5]).fetchall()]
    return [r for r in rows if float(r["sim"]) >= FLOOR][:limit]


def phrase_first_seen(phrase: str) -> tuple[str | None, int]:
    """(first month, hit count) of an exact phrase in the full-text index."""
    if not db_mod.USE_POSTGRES:
        return None, 0
    sts = ",".join("?" * len(STATUS_FILTER))
    sql = (
        "SELECT MIN(r.published_date) AS first, COUNT(*) AS n "
        "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
        f"WHERE {FTS_VECTOR} @@ phraseto_tsquery('english', ?) "
        f"AND t.status IN ({sts}) AND r.published_date <= CURRENT_TIMESTAMP"
    )
    with get_connection() as conn:
        row = conn.execute(sql, [phrase, *STATUS_FILTER]).fetchone()
    first = month_key(row["first"]) if row and row["first"] else None
    return first, int(row["n"] or 0) if row else 0


def vocabulary_walk(query: str, vec: np.ndarray, seed_rows: list[dict], host: str | None = None) -> list[dict]:
    """One round: word pairs of the oldest hits → embedded → kept if close to
    the query → dated by full text. Sorted oldest first."""
    seeds = sorted(seed_rows, key=lambda r: str(r.get("published_date") or "9999"))[:WALK_SEED_ROWS]
    cands = chain_candidates([r.get("title_en") or "" for r in seeds], query)
    out = []
    for phrase in cands:
        try:
            pv = embed_query(phrase, host)
        except EmbedderUnavailable:
            break
        sim = float(pv @ vec)
        if sim < WALK_GATE:
            continue
        first, n = phrase_first_seen(phrase)
        if first and n:
            out.append({"term": phrase, "first_month": first, "hits": n, "sim": round(sim, 3)})
    return sorted(out, key=lambda d: d["first_month"])


# --- corpus statistics (query-independent, cached) ----------------------------

def _cache_get(key: str, max_age_hours: float) -> dict | None:
    try:
        with get_connection() as conn:
            row = conn.execute("SELECT value, computed_at FROM topic_cache WHERE key = ?", [key]).fetchone()
    except Exception:
        return None
    if not row:
        return None
    at = row["computed_at"]
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - at > timedelta(hours=max_age_hours):
        return None
    return json.loads(row["value"])


def _cache_put(key: str, value: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        if db_mod.USE_POSTGRES:
            conn.execute("INSERT INTO topic_cache (key, value, computed_at) VALUES (?, ?, ?) "
                         "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, computed_at = EXCLUDED.computed_at",
                         [key, json.dumps(value), now])
        else:
            conn.execute("INSERT OR REPLACE INTO topic_cache (key, value, computed_at) VALUES (?, ?, ?)",
                         [key, json.dumps(value), now])


def corpus_stats(fresh: bool = False) -> dict:
    """Months axis, totals per month and per tier, first month per source.
    The running month is dropped (it would end every curve on a half month).
    ~6 s on the live DB, cached for CORPUS_CACHE_HOURS."""
    if not fresh:
        cached = _cache_get("corpus_stats", CORPUS_CACHE_HOURS)
        if cached:
            return cached
    sts = ",".join("?" * len(STATUS_FILTER))
    ym = "to_char(r.published_date, 'YYYY-MM')" if db_mod.USE_POSTGRES else "strftime('%Y-%m', r.published_date)"
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT {ym} AS m, v.tier AS tier, COUNT(*) AS n "
            "FROM topic_vectors v JOIN trends t ON t.id = v.trend_id "
            "JOIN raw_entries r ON t.raw_entry_id = r.id "
            f"WHERE t.status IN ({sts}) "
            "AND r.published_date IS NOT NULL AND r.published_date <= CURRENT_TIMESTAMP "
            "GROUP BY 1, 2", list(STATUS_FILTER)).fetchall()
        src = conn.execute(
            f"SELECT t.source_name AS s, MIN({ym}) AS m FROM trends t "
            "JOIN raw_entries r ON t.raw_entry_id = r.id "
            "WHERE r.published_date IS NOT NULL AND r.published_date <= CURRENT_TIMESTAMP "
            "GROUP BY 1", []).fetchall()
    running = datetime.now(timezone.utc).strftime("%Y-%m")
    totals: Counter = Counter()
    tier_totals: dict[str, Counter] = {t: Counter() for t in TIERS}
    for r in rows:
        if not r["m"] or r["m"] >= running:
            continue
        totals[r["m"]] += r["n"]
        if r["tier"] in tier_totals:
            tier_totals[r["tier"]][r["m"]] += r["n"]
    months = sorted(totals)
    stats = {
        "months": months,
        "totals": [totals[m] for m in months],
        "tier_totals": {t: [tier_totals[t][m] for m in months] for t in TIERS},
        "source_first": {r["s"]: r["m"] for r in src if r["s"] and r["m"]},
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _cache_put("corpus_stats", stats)
    except Exception as e:  # cache is a convenience, never a blocker
        logger.warning("corpus_stats not cached: %s", e)
    return stats


# --- assembling the answer ----------------------------------------------------

def _tiers_key(tiers) -> str:
    return ",".join(t for t in TIERS if t in set(tiers))


def load_cached(query_norm: str, tiers_key: str, max_age_days: float = CACHE_DAYS) -> dict | None:
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id, report, created_at FROM topic_reports WHERE query_norm = ? AND tiers = ? "
                "ORDER BY id DESC LIMIT 1", [query_norm, tiers_key]).fetchone()
    except Exception:
        return None
    if not row:
        return None
    at = row["created_at"]
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - at > timedelta(days=max_age_days):
        return None
    rep = json.loads(row["report"])
    rep["cached"] = True
    rep["report_id"] = row["id"]
    return rep


def save_report(report: dict) -> int | None:
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO topic_reports (query, query_norm, tiers, params, report, duration_s) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [report["query"], report["query_norm"], report["tiers_key"],
                 json.dumps(report.get("params")), json.dumps(report), report.get("duration_s")])
            row = conn.execute("SELECT MAX(id) AS id FROM topic_reports").fetchone()
        return row["id"] if row else None
    except Exception as e:
        logger.warning("report not cached: %s", e)
        return None


def build_report(query: str, tiers: list[str], results: dict[str, dict],
                 corpus: dict, ft_oldest: list[dict], vocab: list[dict],
                 index_status: dict[str, bool], ambiguous: dict | None,
                 exact: bool = False) -> dict:
    """Pure assembly: tier assessments + corpus axis → scored report dict."""
    months: list[str] = corpus["months"]
    n = len(months)
    hits_all: list[dict] = []
    tier_hits = {}
    tiers_out: dict[str, dict] = {}
    for t in tiers:
        a = results[t]
        series = month_series(a["hits"], months) if a["hits"] else [0] * n
        tier_hits[t] = np.asarray([series], dtype=np.int32)
        hits_all += a["hits"]
        src = Counter((r.get("source_name") or "?") for r in a["hits"])
        top_src = src.most_common(1)[0] if src else (None, 0)
        tiers_out[t] = {
            "status": a["status"], "head": a["head"], "head_min": a["head_min"],
            "cut": a["cut"], "found": a["found"], "hits": len(a["hits"]),
            "capped": a["capped"], "index": "tier" if index_status.get(t) else "scan",
            "hits_damped": damped_total(a["hits"], months),
            "sources": len(src), "top_source": top_src[0],
            "top_source_share": round(top_src[1] / len(a["hits"]), 3) if a["hits"] else None,
            "series": [[m, c] for m, c in zip(months, series) if c],
            # first_hit = the oldest row above the cut; first_month (set below by
            # the scorer) = the first month with TIER_MIN_HITS rows, i.e. the
            # first SUSTAINED month. A topic the market mentions once a quarter
            # has a first hit and no sustained month — both are said.
            "first_hit": next((m for m, c in zip(months, series) if c), None),
            "oldest": [_compact(r) for r in sorted(a["hits"], key=lambda r: str(r.get("published_date") or "9999"))[:3]],
            "newest": [_compact(r) for r in spread_by_source(
                sorted([r for r in a["hits"] if r.get("published_date")],
                       key=lambda r: str(r.get("published_date")), reverse=True), 5)],
            "sample": [_compact(r) for r in a["hits"][:5]],
            # share of hits that passed the classification stages (carry tags):
            # signals straight from an ingester never did, so a low value says
            # the tier's rows were never looked at by the pipeline.
            "tagged_share": (round(sum(1 for r in a["hits"] if r.get("tags")) / len(a["hits"]), 3)
                             if a["hits"] else None),
        }
    for t in TIERS:
        tier_hits.setdefault(t, np.zeros((1, n), dtype=np.int32))
    overall_series = sum(tier_hits[t][0] for t in tiers) if tiers else np.zeros(n, dtype=np.int32)
    nest = {"source_counts": Counter((r.get("source_name") or "?") for r in hits_all), "top_tags": []}
    windows = actor_windows(months)
    market_rows = results.get("market", {}).get("hits", []) if "market" in results else []
    acts = actor_sets(market_rows, windows)
    history = {
        "months": months, "totals": corpus["totals"],
        "hits": np.asarray([overall_series], dtype=np.int32),
        "tier_hits": tier_hits,
        "tier_totals": corpus["tier_totals"],
        "actors": [acts], "old_tags": Counter(), "recent_tags": Counter(),
        "source_first": corpus.get("source_first", {}),
    }
    score_nests([nest], history)
    for t, info in nest.get("tiers", {}).items():
        if t in tiers_out:
            tiers_out[t].update(first_month=info["first_month"], age_months=info["age_months"],
                                hits_recent=info["hits_recent"])
    overall = {
        "first_month": nest.get("first_month"), "age_months": nest.get("age_months"),
        "hits_total": nest.get("hits_total"), "hits_recent": nest.get("hits_recent"),
        "novelty_lift": nest.get("novelty_lift"), "accel": nest.get("accel"),
        "established_share": nest.get("established_share"),
        "tier_order": nest.get("tier_order"), "science_to_market_months": nest.get("science_to_market_months"),
        "actors_early": acts["early"], "actors_late": acts["late"], "actor_growth": nest.get("actor_growth"),
    }
    answered = [t for t in tiers if tiers_out[t]["status"] != "none"]
    status = "ambiguous" if ambiguous else ("nothing" if not answered else "ok")
    return {
        "query": query, "query_norm": normalise_query(query), "tiers_key": _tiers_key(tiers),
        "tiers_requested": list(tiers), "status": status, "ambiguity": ambiguous,
        "params": {"head_min": {t: HEAD_MIN[t] for t in tiers}, "drop": DROP, "floor": FLOOR,
                   "neighbours": NEIGHBOURS, "walk_gate": WALK_GATE, "exact": exact},
        "corpus": {"first_month": months[0] if months else None, "last_month": months[-1] if months else None,
                   "months": n, "computed_at": corpus.get("computed_at")},
        "tiers": tiers_out, "overall": overall,
        "fulltext_oldest": [_compact(r) for r in ft_oldest],
        "vocabulary": vocab,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def topic_report(query: str, tiers: list[str] | None = None, walk: bool = True,
                 fresh: bool = False, exact: bool = False, host: str | None = None,
                 save: bool = True) -> dict:
    """The whole answer for one query. Cached per (query, tiers) for CACHE_DAYS."""
    from pipeline.topic_vectors import index_status, topup
    tiers = [t for t in TIERS if t in set(tiers or TIERS)]
    if not tiers:
        raise ValueError("no tier selected")
    qn = normalise_query(query)
    tk = _tiers_key(tiers)
    if not fresh:
        cached = load_cached(qn, tk)
        if cached:
            return cached
    t0 = time.time()
    timing: dict[str, float] = {}
    vec = embed_query(query, host)
    timing["embed"] = round(time.time() - t0, 2)
    try:
        filled = topup()
        if filled:
            logger.info("topic_vectors topped up with %d new rows", filled)
    except Exception as e:
        logger.warning("topic_vectors top-up skipped: %s", e)
    idx = index_status()
    corpus = corpus_stats()
    timing["corpus"] = round(time.time() - t0, 2)
    results: dict[str, dict] = {}
    for t in tiers:
        s = time.time()
        rows = search_tier(vec, t, exact=exact)
        results[t] = assess_tier(rows, t)
        results[t]["_rows"] = rows
        timing[f"search_{t}"] = round(time.time() - s, 2)
    pooled = [r for t in tiers for r in results[t]["hits"]]
    best_head = max((results[t]["head"] for t in tiers), default=None)
    amb = ambiguity(query, pooled, best_head)
    ft_oldest: list[dict] = []
    vocab: list[dict] = []
    if not amb:
        s = time.time()
        ft_oldest = fulltext_oldest(query, vec)
        timing["fulltext"] = round(time.time() - s, 2)
        if walk:
            s = time.time()
            seeds = pooled + ft_oldest
            vocab = vocabulary_walk(query, vec, seeds, host) if seeds else []
            timing["walk"] = round(time.time() - s, 2)
    report = build_report(query, tiers, results, corpus, ft_oldest, vocab, idx, amb, exact=exact)
    report["duration_s"] = round(time.time() - t0, 2)
    report["timing"] = timing
    report["cached"] = False
    if save:
        report["report_id"] = save_report(report)
    return report


# --- rendering ------------------------------------------------------------------

def _age(months: int | None) -> str:
    if months is None:
        return "—"
    y, m = divmod(months, 12)
    return f"{y} y {m} m" if y else f"{m} m"


def render_text(rep: dict) -> str:
    L = [f"Topic: {rep['query']}", ""]
    if rep["status"] == "ambiguous":
        a = rep["ambiguity"]
        L.append(f"Which field? {a['reason']}.")
        for f in a["fields"]:
            L.append(f"  {f['vertical']:10s} {round(f['share'] * 100):3d} %  e.g. " + " | ".join(t[:60] for t in f["titles"]))
        return "\n".join(L)
    c = rep["corpus"]
    L.append(f"Corpus axis {c['first_month']} … {c['last_month']} ({c['months']} months); "
             f"cut = max(head − {rep['params']['drop']}, {rep['params']['floor']}), window {rep['params']['neighbours']} per tier.")
    L.append("")
    L.append(f"{'tier':8s} {'status':7s} {'head':>5s} {'cut':>5s} {'hits':>5s} {'damped':>6s} {'1st hit':>7s} {'sustain':>7s} {'age':>8s} {'recent':>6s}  index  largest source")
    for t, d in rep["tiers"].items():
        cap = " (capped)" if d["capped"] else ""
        src = f"{d['top_source']} {round(100 * d['top_source_share'])} %" if d.get("top_source") else "—"
        L.append(f"{t:8s} {d['status']:7s} {d['head']:5.3f} {d['cut']:5.3f} {d['hits']:5d} {d['hits_damped']:6d} "
                 f"{d.get('first_hit') or '—':>7s} {d.get('first_month') or '—':>7s} {_age(d.get('age_months')):>8s} {d.get('hits_recent', 0):6d}  "
                 f"{d['index']:6s} {src}{cap}")
    o = rep["overall"]
    L.append("")
    if rep["status"] == "nothing":
        L.append("Nothing close in any requested tier — we have too little on this, or it is phrased in a register the corpus does not use.")
    else:
        order = " → ".join(o["tier_order"] or []) or "—"
        lag = o["science_to_market_months"]
        L.append(f"Order of appearance: {order}" + (f"; science → market {lag:+d} months" if lag is not None else ""))
        L.append(f"Novelty lift {o['novelty_lift'] if o['novelty_lift'] is not None else '—'} (1.0 = spread like the corpus), "
                 f"acceleration {o['accel'] if o['accel'] is not None else '—'}, "
                 f"established-source share {round(100 * (o['established_share'] or 0))} %, "
                 f"market actors early {o['actors_early']} → late {o['actors_late']}.")
    if rep["fulltext_oldest"]:
        L += ["", "Oldest by full text (vector-gated):"]
        for r in rep["fulltext_oldest"]:
            L.append(f"  {r['date'] or '?':10s} {r['sim']:.2f} {r['source'] or '':22.22s} {r['title'][:70]}")
    if rep["vocabulary"]:
        L += ["", "Earlier vocabulary (embedded and kept only if close to the query):"]
        for v in rep["vocabulary"]:
            L.append(f"  {v['first_month']}  {v['term']:32.32s} {v['hits']:6d} hits  sim {v['sim']:.2f}")
    for t, d in rep["tiers"].items():
        if d["status"] != "none" and d["oldest"]:
            L += ["", f"Oldest {t} hits:"]
            for r in d["oldest"]:
                L.append(f"  {r['date'] or '?':10s} {r['sim']:.2f} {r['source'] or '':22.22s} {r['title'][:70]}")
    L += ["", f"{'cached' if rep.get('cached') else 'computed'} in {rep.get('duration_s', 0)} s; "
          f"report {rep.get('report_id') or '—'}; generated {rep['generated_at'][:16]}"]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Topic engine: the data situation for one term.")
    ap.add_argument("query")
    ap.add_argument("--tiers", default="", help="comma list of science,patent,funding,market (default all)")
    ap.add_argument("--no-walk", action="store_true", help="skip the vocabulary walk")
    ap.add_argument("--fresh", action="store_true", help="ignore the cache")
    ap.add_argument("--exact", action="store_true", help="sequential scan instead of the index (minutes)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    tiers = [t.strip() for t in args.tiers.split(",") if t.strip()] or None
    rep = topic_report(args.query, tiers=tiers, walk=not args.no_walk, fresh=args.fresh,
                       exact=args.exact, save=not args.no_save)
    print(json.dumps(rep, indent=2, default=str) if args.json else render_text(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
