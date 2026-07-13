"""Foresight core — shared signal-space clustering + trajectory analysis.

Extracted from scripts/cluster_trajectory_demo.py and scripts/propose_mega_trends.py
so the same engine drives three consumers (see issue #2):

  1. foresight_snapshot.py  — persists cluster/trajectory artifacts for the frontend
  2. the scoped discoverers — per-vertical / per-lead-time-tier proposal runs
  3. the distillation discovery loop — periodic LLM pass over cluster centers

The two original scripts remain unchanged for now (they are exercised by ongoing
production analysis); they migrate onto this core in a later step.

Design constraints (measured on the 455k-signal pool):
  - Embeddings are read as raw float32 BLOBs and decoded straight into a
    preallocated numpy matrix via np.frombuffer — never into Python float lists
    (the Stage-5 OOM pattern: ~46 GB at 400k signals).
  - Above ~100k points KMeans switches to MiniBatchKMeans (rows are
    L2-normalized, so Euclidean k-means ≈ spherical/cosine k-means).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

import numpy as np
from sklearn.cluster import KMeans, MiniBatchKMeans
from sklearn.metrics import silhouette_score

from pipeline import db as db_mod
from pipeline.db import get_connection

# Tags that make bad cluster labels (geographies, signal types, generic terms).
GENERIC_TAGS = {
    "germany", "usa", "china", "europe", "uk", "us", "eu", "france", "india",
    "regulation", "government regulation", "government policy", "economic_policy",
    "product_launch", "product launch", "consumer_behavior", "consumer behavior",
    "funding", "research", "market_shift", "partnership", "innovation",
    "sustainability", "policy", "data_privacy", "data privacy",
}

# SoV-delta thresholds (percentage points early→late) for the momentum tag.
MOMENTUM_RISING_PP = 1.0
MOMENTUM_DECLINING_PP = -1.0

# Momentum is judged inside the most recent N months only. The corpus mixes
# acquisition eras (patent/research back-file dominates 2002-2020, RSS the
# recent years); an all-history SoV window measures that source-composition
# shift, not the trend (validation 2026-07-02 caught -60pp "declines" that
# were just the patent ingest window ending). Within a recent window the
# composition is near-stable, so share-of-voice means what it claims.
MOMENTUM_WINDOW_MONTHS = 36

MINIBATCH_ABOVE = 100_000  # switch to MiniBatchKMeans above this many points


# ---------------------------------------------------------------- data loading

# Canonical lead-time tier → source mapping (issue #2/#3). Preprint servers are
# source_type='api' but belong to the science tier; patents and funding share
# 'api' and are told apart by source name. LIKE patterns are bound params —
# literal % in the SQL breaks under the ?→%s psycopg2 wrapper.
TIER_FILTERS: dict[str, tuple[str, list[str]]] = {
    "science": ("(s.source_type = 'research' OR t.source_name LIKE ?)",
                ["%Preprints%"]),
    "patent": ("(t.source_name LIKE ? OR t.source_name LIKE ?)",
               ["Google Patents%", "EPO %"]),
    "funding": ("(" + " OR ".join(["t.source_name LIKE ?"] * 5) + ")",
                ["NIH RePORTER%", "NSF %", "OpenAIRE%", "UKRI%", "SEC Form D%"]),
    "market": ("s.source_type IN ('trade_media', 'press_wire', 'brand')", []),
}


def load_signals(status: str = "signal,published", vertical: str | None = None,
                 source_like: str | None = None, limit: int = 0,
                 since: str | None = None, until: str | None = None,
                 dim1024: bool = False, tier: str | None = None) -> list[dict]:
    """Load embedded trends joined to their raw entry's published_date.

    status: comma list or 'all'. vertical: primary_vertical or None/'ALL' for no
    filter. source_like: comma-separated substrings OR-matched against
    source_name (e.g. 'NSF,NIH,OpenAIRE,UKRI' = the funding pool).
    tier: canonical lead-time tier scope (TIER_FILTERS key) — the maintained
    replacement for hand-rolled source_like tier pools.
    since/until: ISO date bounds on published_date (for time-window runs).
    dim1024: load the Matryoshka 1024-dim column instead of the full 4096 —
    4× less text to parse/hold, which is what makes the full 1.1M-signal space
    tractable in memory; KMeans centroids are ~identical on the truncation.
    Embeddings are kept as raw bytes in row['_emb'] for build_matrix().
    """
    where: list[str] = []
    params: list = []
    if tier:
        if tier not in TIER_FILTERS:
            raise ValueError(f"unknown tier {tier!r} (known: {sorted(TIER_FILTERS)})")
        cond, tier_params = TIER_FILTERS[tier]
        where.append(cond)
        params += tier_params
    if status and status.lower() != "all":
        sts = [s.strip() for s in status.split(",")]
        where.append(f"t.status IN ({','.join('?' * len(sts))})")
        params += sts
    if vertical and vertical.upper() != "ALL":
        where.append("t.primary_vertical = ?")
        params.append(vertical)
    emb_field = "embedding_1024" if dim1024 else "embedding"
    where.append(f"t.{emb_field} IS NOT NULL")
    if source_like:
        pats = [p.strip() for p in source_like.split(",") if p.strip()]
        if pats:
            where.append("(" + " OR ".join(["t.source_name LIKE ?"] * len(pats)) + ")")
            params += [f"%{p}%" for p in pats]
    if since:
        where.append("r.published_date >= ?")
        params.append(since)
    if until:
        where.append("r.published_date < ?")
        params.append(until)
    # Bogus future dates from malformed RSS/API records (observed up to 2029)
    # would stretch the month axis and hollow out the recent-window analysis.
    # Rows with NULL dates stay in (they cluster; they just carry no trajectory).
    # CURRENT_TIMESTAMP is portable (SQLite + Postgres); datetime('now') is not.
    where.append("(r.published_date IS NULL OR r.published_date <= CURRENT_TIMESTAMP)")
    # Under Postgres the embedding is a pgvector — cast to text and parse; under
    # SQLite it is the raw float32 blob.
    emb_col = f"t.{emb_field}::text" if db_mod.USE_POSTGRES else f"t.{emb_field}"
    src_join = (" LEFT JOIN sources s ON r.source_id = s.id" if tier else "")
    sql = ("SELECT t.id, t.title_en, t.mega_trend, t.tags, t.source_name, "
           "       t.primary_vertical, t.status, t.source_url, "
           f"       r.published_date, {emb_col} AS embedding "
           f"FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id{src_join} "
           f"WHERE {' AND '.join(where)}")
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
    out = []
    for r in rows:
        emb = db_mod._vector_to_bytes(r["embedding"])
        if not isinstance(emb, (bytes, bytearray)) or len(emb) < 4:
            continue
        r["_emb"] = bytes(emb)
        r["embedding"] = None  # drop duplicate blob reference, keep memory flat
        if isinstance(r["published_date"], datetime):
            r["published_date"] = r["published_date"].isoformat()
        try:
            tags = r["tags"]
            r["tags"] = tags if isinstance(tags, list) else (json.loads(tags) if tags else [])
        except Exception:
            r["tags"] = []
        out.append(r)
    return out


def build_matrix(rows: list[dict]) -> np.ndarray:
    """Raw float32 bytes → L2-row-normalized matrix; frees each row's bytes."""
    dim = len(rows[0]["_emb"]) // 4
    X = np.empty((len(rows), dim), dtype=np.float32)
    for i, r in enumerate(rows):
        X[i] = np.frombuffer(r["_emb"], dtype=np.float32)
        r["_emb"] = None
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    return X


# ------------------------------------------------------------------ clustering

def pick_k(X: np.ndarray, lo: int, hi: int) -> int:
    """Silhouette-picked k on a sample (deterministic seeds)."""
    n = X.shape[0]
    if n < 60:
        return max(2, min(lo, n // 8))
    sample = X if n <= 4000 else X[np.random.default_rng(42).choice(n, 4000, replace=False)]
    best_k, best_s = lo, -1.0
    for k in range(lo, min(hi, max(lo, n // 10)) + 1):
        labels = KMeans(n_clusters=k, n_init=4, random_state=42).fit_predict(sample)
        s = silhouette_score(sample, labels, sample_size=min(2000, len(sample)), random_state=42)
        if s > best_s:
            best_k, best_s = k, s
    return best_k


def cluster_signals(X: np.ndarray, k: int | None = None,
                    k_range: tuple[int, int] = (6, 14)) -> tuple[np.ndarray, np.ndarray, int]:
    """Spherical k-means (rows pre-normalized). Returns (labels, centroids, k)."""
    k = k or pick_k(X, *k_range)
    n = X.shape[0]
    if n > MINIBATCH_ABOVE:
        km = MiniBatchKMeans(n_clusters=k, batch_size=4096, n_init=3,
                             random_state=42).fit(X)
    else:
        km = KMeans(n_clusters=k, n_init=8 if n <= 50_000 else 3, random_state=42).fit(X)
    return km.labels_, km.cluster_centers_, k


# ------------------------------------------------------------------- analysis

def month_key(d) -> str | None:
    if not d:
        return None
    s = str(d)[:7]
    return s if len(s) == 7 and s[4] == "-" else None


# Acronyms that .title() would mangle ("AI" -> "Ai"). Display form per token.
ACRONYM_DISPLAY = {
    "ai": "AI", "ml": "ML", "ar": "AR", "vr": "VR", "xr": "XR", "llm": "LLM",
    "llms": "LLMs", "ev": "EV", "evs": "EVs", "iot": "IoT", "api": "API",
    "apis": "APIs", "ux": "UX", "ui": "UI", "5g": "5G", "6g": "6G",
    "mrna": "mRNA", "dna": "DNA", "rna": "RNA", "crispr": "CRISPR", "co2": "CO2",
    "esg": "ESG", "b2b": "B2B", "d2c": "D2C", "saas": "SaaS", "nlp": "NLP",
    "gpu": "GPU", "suv": "SUV", "hvac": "HVAC", "3d": "3D", "usa": "USA",
}


def _norm_tag(t: str) -> str:
    """Normalize a tag for dedup/comparison: lowercase, and unify the underscore/
    hyphen/space variants ('plant_based' == 'plant-based' == 'plant based') so
    they don't produce separate labels for the same concept."""
    return (t or "").lower().replace("_", " ").replace("-", " ").strip()


def _pretty(tag_norm: str) -> str:
    """Title-case a normalized tag, keeping known acronyms uppercase."""
    return " ".join(ACRONYM_DISPLAY.get(w, w.capitalize()) for w in tag_norm.split())


def _distinct_thematic(tags: list[str]) -> list[str]:
    """Normalized, generic-filtered, variant-deduped thematic tags, in order."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        if not t:
            continue
        norm = _norm_tag(t)
        if norm in GENERIC_TAGS or t.lower() in GENERIC_TAGS or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def derive_label(tags: list[str], fallback: str = "Unlabelled cluster") -> str:
    """Human-readable label from the top thematic tags (geo/generic filtered,
    acronym-aware, variant-deduped). Frequency-ordered; see `distinctive_label`
    for the cross-cluster distinctiveness variant used by analyze()."""
    themal = _distinct_thematic(tags)
    picked = themal[:2] if themal else [tags[0].lower().replace("_", " ")] if tags else []
    if not picked:
        return fallback
    return " · ".join(_pretty(p) for p in picked)


def distinctive_label(tag_counter: Counter, size: int, tag_df: dict[str, int],
                      n_clusters: int, fallback: str = "Unlabelled cluster") -> str:
    """Label a cluster by its most DISTINCTIVE tags (tf-idf across clusters), not
    just its most frequent. Fixes the 'every FOOD cluster is Plant-Based' problem:
    a tag common to many clusters (df high) is downweighted, so each cluster
    surfaces what sets it apart (cultivated meat vs plant-based milk vs …).
    `tag_df` = number of clusters each normalized tag appears in."""
    # Sum counts of tag variants that normalize to the same concept
    # ('plant-based' + 'plant based' → one entry) before scoring.
    norm_counts: Counter = Counter()
    for tag, cnt in tag_counter.items():
        norm = _norm_tag(tag)
        if norm and norm not in GENERIC_TAGS:
            norm_counts[norm] += cnt
    scored: list[tuple[float, str]] = []
    for norm, cnt in norm_counts.items():
        tf = cnt / max(size, 1)
        idf = np.log(n_clusters / (1 + tag_df.get(norm, 0))) + 1.0  # +1 keeps it positive
        scored.append((tf * idf, norm))
    scored.sort(key=lambda x: -x[0])
    picked = [norm for _, norm in scored[:2]]
    if not picked:
        return derive_label([t for t, _ in tag_counter.most_common(6)], fallback)
    return " · ".join(_pretty(p) for p in picked)


def analyze(rows: list[dict], X: np.ndarray, labels: np.ndarray,
            centroids: np.ndarray) -> dict:
    """Per-cluster analysis + global month axis.

    Returns {"months": [...], "totals": [...], "clusters": [cluster-dict, ...]}
    with each cluster carrying size, cohesion, dominant mega-trend + purity,
    verticals, top tags, source corroboration, representatives, a monthly
    series (count + share of the scope's monthly volume) and SoV momentum
    (Δ share between the early and late thirds of the sufficiently-dense
    months — share-of-voice removes the source-onboarding growth bias).
    """
    months = sorted({m for r in rows if (m := month_key(r["published_date"]))})
    midx = {m: i for i, m in enumerate(months)}
    totals = [0] * len(months)
    for r in rows:
        mk = month_key(r["published_date"])
        if mk in midx:
            totals[midx[mk]] += 1

    # SoV windows: only the most recent MOMENTUM_WINDOW_MONTHS with enough
    # volume (source composition is near-stable there), early/late thirds.
    window_start = max(0, len(months) - MOMENTUM_WINDOW_MONTHS)
    meaningful = [i for i in range(window_start, len(months)) if totals[i] >= 5]
    third = max(1, len(meaningful) // 3) if meaningful else 0
    early_idx = set(meaningful[:third])
    late_idx = set(meaningful[-third:]) if third else set()

    def share(series: list[int], idxs: set[int]) -> float:
        num = sum(series[i] for i in idxs)
        den = sum(totals[i] for i in idxs)
        return num / den if den else 0.0

    idx_by_cluster: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        idx_by_cluster.setdefault(int(lab), []).append(i)

    clusters = []
    for cid, idxs in sorted(idx_by_cluster.items(), key=lambda kv: -len(kv[1])):
        members = [rows[i] for i in idxs]
        cen = centroids[cid]
        cen = cen / max(np.linalg.norm(cen), 1e-9)
        sims = X[idxs] @ cen
        cohesion = float(np.mean(sims))
        reps = [members[j] for j in np.argsort(-sims)[:5]]
        megas = Counter(m["mega_trend"] for m in members if m["mega_trend"])
        dom, dom_n = (megas.most_common(1)[0] if megas else (None, 0))
        tags = Counter(t for m in members for t in (m["tags"] or []))
        verts = [v for v, _ in Counter(
            m["primary_vertical"] for m in members if m["primary_vertical"]).most_common(3)]
        sources = {m["source_name"] for m in members if m["source_name"]}

        series = [0] * len(months)
        for m in members:
            mk = month_key(m["published_date"])
            if mk in midx:
                series[midx[mk]] += 1
        se, sl = share(series, early_idx), share(series, late_idx)
        delta_pp = (sl - se) * 100
        momentum = ("rising" if delta_pp > MOMENTUM_RISING_PP
                    else "declining" if delta_pp < MOMENTUM_DECLINING_PP
                    else "stable")
        if len(meaningful) < 6:
            momentum, delta_pp = "unknown", 0.0

        top_tags = [t for t, _ in tags.most_common(12)]
        clusters.append({
            "cluster_idx": cid,
            "_tag_counter": tags,           # kept for the distinctiveness pass below
            "label": derive_label(top_tags, fallback=f"Cluster {cid}"),  # provisional
            "size": len(members),
            "cohesion": round(cohesion, 4),
            "mega_trend": dom,
            "mega_purity": round(dom_n / len(members), 4) if members else 0.0,
            "verticals": verts,
            "top_tags": top_tags,
            "n_sources": len(sources),
            "momentum": momentum,
            "sov_delta_pp": round(delta_pp, 2),
            "rep_trend_ids": [r["id"] for r in reps],
            "rep_titles": [(r["title_en"] or "")[:120] for r in reps],
            "monthly_series": [
                {"m": months[i], "n": series[i],
                 "share": round(series[i] / totals[i], 4) if totals[i] else 0.0}
                for i in range(len(months))
            ],
        })

    # Second pass: relabel each cluster by tag distinctiveness across clusters, so
    # near-identical clusters (e.g. the plant-based cluster of FOOD) surface what
    # sets them apart rather than repeating the vertical's dominant tag. tag_df =
    # in how many clusters each normalized tag ranks in the top 20.
    tag_df: Counter = Counter()
    for c in clusters:
        top20 = [t for t, _ in c["_tag_counter"].most_common(20)]
        for norm in {_norm_tag(t) for t in top20}:
            if norm:
                tag_df[norm] += 1
    n_c = len(clusters)
    for c in clusters:
        c["label"] = distinctive_label(c["_tag_counter"], c["size"], tag_df, n_c,
                                       fallback=c["label"])
        del c["_tag_counter"]
    return {"months": months, "totals": totals, "clusters": clusters}


# -------------------------------------------------------------------- lineage
# Cross-window cluster evolution (issue #2 phase 1): cluster each rolling time
# window independently, then match clusters across consecutive windows by
# centroid cosine. The resulting graph carries emergence / continuation /
# split / merge / decline plus semantic drift — the "where is this trend
# going" substrate the single-window snapshots cannot express.

MATCH_SIM = 0.80          # centroid cosine >= this = same theme across windows
LINEAGE_MIN_SIGNALS = 300  # windows below this are recorded as gaps, not clustered


def _add_months(d: datetime, months: int) -> datetime:
    y, m = divmod(d.year * 12 + (d.month - 1) + months, 12)
    return d.replace(year=y, month=m + 1, day=1)


def window_bounds(since: str, until: str, step_months: int = 3,
                  span_months: int = 12) -> list[tuple[str, str]]:
    """Rolling (start, end) ISO-date windows covering [since, until).

    Windows overlap when span > step (default: quarterly step, 12-month span —
    9 months of shared data makes cross-window matches stable). The last
    window is the first one whose end reaches `until`.
    """
    start = datetime.fromisoformat(since).replace(day=1)
    stop = datetime.fromisoformat(until)
    out: list[tuple[str, str]] = []
    while True:
        end = _add_months(start, span_months)
        out.append((start.date().isoformat(), end.date().isoformat()))
        if end >= stop:
            break
        start = _add_months(start, step_months)
    return out


def _relation(out_deg: int, in_deg: int) -> str:
    if out_deg > 1 and in_deg > 1:
        return "split_merge"
    if out_deg > 1:
        return "split"
    if in_deg > 1:
        return "merge"
    return "continue"


def build_lineage(status: str = "signal,published", vertical: str | None = None,
                  since: str = "2016-01-01", until: str | None = None,
                  step_months: int = 3, span_months: int = 12,
                  k_range: tuple[int, int] = (6, 14), dim1024: bool = False,
                  min_signals: int = LINEAGE_MIN_SIGNALS,
                  match_sim: float = MATCH_SIM,
                  progress=None) -> dict:
    """Cluster every window, then match consecutive windows by centroid cosine.

    Returns {"windows": [...], "nodes": [...], "edges": [...]}.
    nodes: one per (window, cluster) with label/size/sov_share/cohesion/top_tags,
      a `status` of "emerged" / "declined" / "" (relative to the neighbouring
      computed windows) and the L2-normalized centroid as float32 bytes.
    edges: between consecutive computed windows with cosine `sim`, a
      relation (continue/split/merge/split_merge) and drift = 1 - sim.
    Windows with fewer than `min_signals` dated signals become gaps
    ({"computed": False}) and break lineage chains deliberately — matching
    across a data hole would fabricate continuity.
    """
    until = until or datetime.now().date().isoformat()
    bounds = window_bounds(since, until, step_months, span_months)
    windows: list[dict] = []
    per_win: list[dict | None] = []
    for ws, we in bounds:
        rows = load_signals(status=status, vertical=vertical, since=ws, until=we,
                            dim1024=dim1024)
        info = {"start": ws, "end": we, "n": len(rows), "computed": False}
        if len(rows) < min_signals:
            windows.append(info)
            per_win.append(None)
            continue
        X = build_matrix(rows)
        labels, centroids, k = cluster_signals(X, k_range=k_range)
        res = analyze(rows, X, labels, centroids)
        cn = centroids / np.clip(np.linalg.norm(centroids, axis=1, keepdims=True),
                                 1e-9, None)
        info.update(computed=True, k=k)
        windows.append(info)
        per_win.append({"clusters": res["clusters"], "centroids": cn.astype(np.float32),
                        "total": len(rows)})
        del X, rows
        if progress:
            progress(f"window {ws}..{we}: n={info['n']} k={k}")

    nodes: list[dict] = []
    node_at: dict[tuple[int, int], int] = {}  # (window_idx, cluster_idx) -> node idx
    for wi, pw in enumerate(per_win):
        if pw is None:
            continue
        for c in pw["clusters"]:
            node_at[(wi, c["cluster_idx"])] = len(nodes)
            nodes.append({
                "window_idx": wi,
                "window_start": windows[wi]["start"],
                "window_end": windows[wi]["end"],
                "cluster_idx": c["cluster_idx"],
                "label": c["label"], "size": c["size"],
                "sov_share": round(c["size"] / pw["total"], 4),
                "cohesion": c["cohesion"],
                "top_tags": c["top_tags"][:8],
                "rep_trend_ids": c["rep_trend_ids"],
                "centroid": pw["centroids"][c["cluster_idx"]].tobytes(),
                "status": "",
            })

    edges: list[dict] = []
    computed_idx = [i for i, pw in enumerate(per_win) if pw is not None]
    for a, b in zip(computed_idx, computed_idx[1:]):
        if b != a + 1:
            continue  # gap between them — no matching across data holes
        S = per_win[a]["centroids"] @ per_win[b]["centroids"].T
        pairs = [(i, j, float(S[i, j]))
                 for i in range(S.shape[0]) for j in range(S.shape[1])
                 if S[i, j] >= match_sim]
        out_deg = Counter(i for i, _, _ in pairs)
        in_deg = Counter(j for _, j, _ in pairs)
        for i, j, sim in pairs:
            edges.append({
                "from_node": node_at[(a, i)], "to_node": node_at[(b, j)],
                "sim": round(sim, 4), "drift": round(1.0 - sim, 4),
                "relation": _relation(out_deg[i], in_deg[j]),
            })

    # Emergence / decline: comparing against the *adjacent* window is useless
    # when windows overlap (span > step) — 9 of 12 shared months means almost
    # every cluster has a neighbour match, so nothing ever looks new. Judge
    # instead against the nearest NON-overlapping window (>= span months apart),
    # i.e. "did this theme exist as a distinct cluster a full span ago / will it
    # a full span from now". overlap_steps windows on each side share data.
    overlap_steps = max(1, span_months // max(step_months, 1))
    comp_set = set(computed_idx)

    def _ref_before(wi: int) -> int | None:
        for r in range(wi - overlap_steps, computed_idx[0] - 1, -1):
            if r in comp_set:
                return r
        return None

    def _ref_after(wi: int) -> int | None:
        for r in range(wi + overlap_steps, computed_idx[-1] + 1):
            if r in comp_set:
                return r
        return None

    def _matches(wi: int, ci: int, ref: int) -> bool:
        cen = per_win[wi]["centroids"][ci]
        return bool((per_win[ref]["centroids"] @ cen).max() >= match_sim)

    for n in nodes:
        wi, ci = n["window_idx"], n["cluster_idx"]
        before, after = _ref_before(wi), _ref_after(wi)
        if before is not None and not _matches(wi, ci, before):
            n["status"] = "emerged"      # absent a full span ago
        elif after is not None and not _matches(wi, ci, after):
            n["status"] = "declined"     # gone a full span from now
    return {"windows": windows, "nodes": nodes, "edges": edges}
