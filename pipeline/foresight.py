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

import numpy as np
from sklearn.cluster import KMeans, MiniBatchKMeans
from sklearn.metrics import silhouette_score

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

MINIBATCH_ABOVE = 100_000  # switch to MiniBatchKMeans above this many points


# ---------------------------------------------------------------- data loading

def load_signals(status: str = "signal,published", vertical: str | None = None,
                 source_like: str | None = None, limit: int = 0,
                 since: str | None = None, until: str | None = None) -> list[dict]:
    """Load embedded trends joined to their raw entry's published_date.

    status: comma list or 'all'. vertical: primary_vertical or None/'ALL' for no
    filter. source_like: comma-separated substrings OR-matched against
    source_name (e.g. 'NSF,NIH,OpenAIRE,UKRI' = the funding pool).
    since/until: ISO date bounds on published_date (for time-window runs).
    Embeddings are kept as raw bytes in row['_emb'] for build_matrix().
    """
    where: list[str] = []
    params: list = []
    if status and status.lower() != "all":
        sts = [s.strip() for s in status.split(",")]
        where.append(f"t.status IN ({','.join('?' * len(sts))})")
        params += sts
    if vertical and vertical.upper() != "ALL":
        where.append("t.primary_vertical = ?")
        params.append(vertical)
    where.append("t.embedding IS NOT NULL")
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
    sql = ("SELECT t.id, t.title_en, t.mega_trend, t.tags, t.source_name, "
           "       t.primary_vertical, t.status, t.source_url, "
           "       r.published_date, t.embedding "
           "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
           f"WHERE {' AND '.join(where)}")
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
    out = []
    for r in rows:
        emb = r["embedding"]
        if not isinstance(emb, (bytes, bytearray)) or len(emb) < 4:
            continue
        r["_emb"] = bytes(emb)
        r["embedding"] = None  # drop duplicate blob reference, keep memory flat
        try:
            r["tags"] = json.loads(r["tags"]) if r["tags"] else []
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


def derive_label(tags: list[str], fallback: str = "Unlabelled cluster") -> str:
    """Human-readable label from the top thematic tags (geo/generic filtered)."""
    themal = [t for t in tags if t and t.lower() not in GENERIC_TAGS]
    picked = themal[:2] if themal else tags[:1]
    if not picked:
        return fallback
    return " · ".join(p.replace("_", " ").title() for p in picked)


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

    # SoV windows: only months with enough volume, early/late thirds
    meaningful = [i for i in range(len(months)) if totals[i] >= 5]
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
        if len(months) < 6:
            momentum, delta_pp = "unknown", 0.0

        top_tags = [t for t, _ in tags.most_common(12)]
        clusters.append({
            "cluster_idx": cid,
            "label": derive_label(top_tags, fallback=f"Cluster {cid}"),
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
    return {"months": months, "totals": totals, "clusters": clusters}
