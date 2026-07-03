"""Trend & mega-trend discovery core (docs/mega_discovery_architecture.md).

Two layers over the same machinery:
  • scope clustering  — within a vertical or a cross-vertical pair (customer-facing
    Macro/Micro + intersection trends)
  • mega discovery    — global themes, characterized on two axes (reach + maturity)

Method (v1, sklearn-only, deterministic): reduce 4096-D → ~50-D with PCA (raw-embedding
distances are useless at 4096-D — distance concentration), then HDBSCAN (variable
density, labels background as noise instead of forcing every point into a cluster,
no k to choose). Each cluster is characterized by metrics *on the cluster*, never by
the overlapping scope structure (which would make cross-cutting detection circular).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

import numpy as np
from sklearn.cluster import HDBSCAN, KMeans, MiniBatchKMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.foresight import derive_label, month_key

VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]

# --- lead-time tiers (Axis B), same map as scripts/lead_time_discoverer -------
TIER_ORDER = {"science": 0, "patent": 1, "funding": 2, "market": 3}
EARLY_TIERS = ("science", "patent", "funding")
PREPRINT_MARKERS = ("arxiv", "biorxiv", "medrxiv", "preprint")
FUNDING_MARKERS = ("nsf", "nih", "reporter", "openaire", "ukri", "gateway to research")


def tier_of(source_type: str | None, source_name: str | None, pub_number) -> str:
    if pub_number:
        return "patent"
    st, sn = (source_type or "").lower(), (source_name or "").lower()
    if st == "research":
        return "science"
    if st == "api":
        if any(m in sn for m in PREPRINT_MARKERS):
            return "science"
        if any(m in sn for m in FUNDING_MARKERS):
            return "funding"
        return "market"
    return "market"


# ------------------------------------------------------------------ scope load
def load_scope(scope: str, status: str = "signal,published", limit: int = 0) -> list[dict]:
    """scope: 'global' | 'vertical:FOOD' | 'pair:FOOD&HEALTH'. Cross-vertical pair =
    rows whose `verticals` JSON contains BOTH codes."""
    # CURRENT_TIMESTAMP is portable (SQLite + Postgres); datetime('now') is not.
    where = ["t.embedding IS NOT NULL",
             "(r.published_date IS NULL OR r.published_date <= CURRENT_TIMESTAMP)"]
    params: list = []
    if status and status.lower() != "all":
        sts = [s.strip() for s in status.split(",")]
        where.append(f"t.status IN ({','.join('?' * len(sts))})")
        params += sts
    if scope.startswith("vertical:"):
        where.append("t.primary_vertical = ?")
        params.append(scope.split(":", 1)[1])
    elif scope.startswith("pair:"):
        a, b = scope.split(":", 1)[1].split("&")
        # JSON array membership via LIKE on the quoted code (verticals are UPPER
        # codes). Works on both backends (jsonb::text under PG via the cast below).
        vt = "t.verticals::text" if db_mod.USE_POSTGRES else "t.verticals"
        where.append(f"{vt} LIKE ? AND {vt} LIKE ?")
        params += [f'%"{a}"%', f'%"{b}"%']
    emb_col = "t.embedding::text" if db_mod.USE_POSTGRES else "t.embedding"
    sql = ("SELECT t.id, t.title_en, t.tags, t.source_name, t.primary_vertical, "
           "       t.verticals, t.mega_trend, r.published_date, r.pub_number, "
           f"       s.source_type, {emb_col} AS embedding "
           "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
           "JOIN sources s ON r.source_id = s.id "
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
        r["embedding"] = None
        r["_tier"] = tier_of(r["source_type"], r["source_name"], r["pub_number"])
        if isinstance(r["published_date"], datetime):
            r["published_date"] = r["published_date"].isoformat()
        try:
            tags = r["tags"]
            r["tags"] = tags if isinstance(tags, list) else (json.loads(tags) if tags else [])
        except Exception:
            r["tags"] = []
        try:
            verts = r["verticals"]
            r["_verts"] = verts if isinstance(verts, list) else (json.loads(verts) if verts else [])
        except Exception:
            r["_verts"] = []
        out.append(r)
    return out


# ------------------------------------------------------------- reduce + cluster
def reduce_dims(X: np.ndarray, n_components: int = 50) -> np.ndarray:
    """PCA 4096-D → n-D. Randomized SVD scales to 500k×4096. Deterministic."""
    n = min(n_components, X.shape[1], max(2, X.shape[0] - 1))
    return PCA(n_components=n, svd_solver="randomized",
               random_state=42).fit_transform(X).astype(np.float32)


def cluster_density(Xr: np.ndarray, min_cluster_size: int | None = None,
                    min_samples: int | None = None, method: str = "eom") -> np.ndarray:
    """HDBSCAN on the reduced space (MEGA layer). -1 = noise (background, not a
    trend) — honest about how much of the corpus is a real dense theme vs diffuse.
    method='eom' (default) = few large density modes (mega-appropriate); 'leaf' =
    more, finer themes but higher noise."""
    mcs = min_cluster_size or max(100, Xr.shape[0] // 300)
    hdb = HDBSCAN(min_cluster_size=mcs, min_samples=(min_samples or 5),
                  cluster_selection_method=method, metric="euclidean",
                  copy=True, n_jobs=-1)
    return hdb.fit_predict(Xr)


def pick_partition_k(size: int) -> int:
    """A stable, customer-friendly number of sub-themes for a scope partition —
    not a silhouette guess (which is still weak even on reduced dims). Scales gently
    with volume, clamped to an interpretable 5–10."""
    return int(min(10, max(5, round(size / 3000))))


def cluster_partition(Xr: np.ndarray, k: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """KMeans on the reduced space (SCOPE layer): a full partition into interpretable
    sub-themes (customers want every signal placed, not a big 'noise' bucket).
    Defensible because it runs on PCA-reduced dims, not raw 4096-D. Returns
    (labels, centroids)."""
    k = k or pick_partition_k(Xr.shape[0])
    if Xr.shape[0] > 100_000:
        km = MiniBatchKMeans(n_clusters=k, batch_size=4096, n_init=3, random_state=42).fit(Xr)
    else:
        km = KMeans(n_clusters=k, n_init=6, random_state=42).fit(Xr)
    return km.labels_, km.cluster_centers_


# --------------------------------------------------------------- metrics (axes)
def vertical_entropy(members: list[dict]) -> float:
    """Axis A (reach): normalized Shannon entropy over members' verticals. 0 =
    single-industry, 1 = spread evenly across all 8. Counts every vertical a signal
    carries (a cross-vertical signal contributes to each)."""
    cnt: Counter = Counter()
    for m in members:
        for v in (m.get("_verts") or []):
            cnt[v] += 1
    tot = sum(cnt.values())
    if tot == 0 or len(cnt) < 2:
        return 0.0
    p = np.array([c / tot for c in cnt.values()])
    h = -(p * np.log(p)).sum()
    return float(h / np.log(len(VERTICALS)))


def _onset(members: list[dict], frac: float = 0.10, min_signals: int = 8) -> tuple[str | None, int]:
    months = sorted(m for x in members if (m := month_key(x["published_date"])))
    total = len(months)
    if total < min_signals:
        return None, total
    target = max(3, int(frac * total))
    cum, counts = 0, Counter(months)
    for mo in sorted(counts):
        cum += counts[mo]
        if cum >= target:
            return mo, total
    return months[-1], total


def _months_between(a: str, b: str) -> int:
    return (int(b[:4]) - int(a[:4])) * 12 + (int(b[5:7]) - int(a[5:7]))


def maturity(members: list[dict]) -> dict:
    """Axis B: tier onsets + span. maturity_span = #tiers present (of 4). lead_months =
    earliest early-tier onset → market onset (positive = the theme leads the market)."""
    onsets, totals = {}, {}
    for tier in TIER_ORDER:
        grp = [m for m in members if m["_tier"] == tier]
        o, t = _onset(grp)
        onsets[tier], totals[tier] = o, t
    present = [t for t in TIER_ORDER if onsets[t]]
    market = onsets["market"]
    early = sorted((onsets[t], t) for t in EARLY_TIERS if onsets[t])
    lead_months, lead_tier = None, None
    if early and market:
        first, lead_tier = early[0]
        lead_months = _months_between(first, market)
    return {"onsets": onsets, "tier_totals": totals, "maturity_span": len(present),
            "lead_tier": lead_tier, "lead_months": lead_months}


def durability(members: list[dict], months: list[str], totals: list[int]) -> float:
    """Fraction of the covered window where the cluster holds a non-trivial monthly
    share (persistence, not a one-off spike). 1 = present throughout, ~0 = a blip."""
    midx = {m: i for i, m in enumerate(months)}
    series = [0] * len(months)
    for m in members:
        mk = month_key(m["published_date"])
        if mk in midx:
            series[midx[mk]] += 1
    # count activity only within sufficiently-dense months (a lone signal in a
    # sparse month trivially hits any share threshold → would inflate durability >1)
    dense = [i for i in range(len(months)) if totals[i] >= 5]
    active = sum(1 for i in dense if series[i] / totals[i] >= 0.02)
    return float(active / len(dense)) if dense else 0.0


# --------------------------------------------------------------- characterize
def characterize(rows: list[dict], Xr: np.ndarray, labels: np.ndarray) -> dict:
    """Per-cluster metrics + mega_score. Ignores HDBSCAN noise (label -1)."""
    months = sorted({m for r in rows if (m := month_key(r["published_date"]))})
    midx = {m: i for i, m in enumerate(months)}
    totals = [0] * len(months)
    for r in rows:
        mk = month_key(r["published_date"])
        if mk in midx:
            totals[midx[mk]] += 1

    idx_by: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        if lab >= 0:
            idx_by.setdefault(int(lab), []).append(i)

    # tag document-frequency across clusters (for distinctive labels)
    tag_df: Counter = Counter()
    per_tags = {}
    for cid, idxs in idx_by.items():
        tc = Counter(t for i in idxs for t in (rows[i].get("tags") or []))
        per_tags[cid] = tc
        for norm in {(t or "").lower().replace("_", " ").replace("-", " ").strip()
                     for t in [x for x, _ in tc.most_common(20)]}:
            if norm:
                tag_df[norm] += 1
    n_c = len(idx_by)

    from pipeline.foresight import distinctive_label
    clusters = []
    for cid, idxs in sorted(idx_by.items(), key=lambda kv: -len(kv[1])):
        members = [rows[i] for i in idxs]
        cen = Xr[idxs].mean(axis=0)
        d = ((Xr[idxs] - cen) ** 2).sum(axis=1)
        reps = [members[j] for j in np.argsort(d)[:5]]
        tc = per_tags[cid]
        top_tags = [t for t, _ in tc.most_common(12)]
        vent = vertical_entropy(members)
        mat = maturity(members)
        dur = durability(members, months, totals)
        # mega_score in [0,1]: broad (reach) × deep (maturity chain) × durable
        mega = round(0.40 * vent + 0.35 * (mat["maturity_span"] / 4.0) + 0.25 * dur, 3)
        clusters.append({
            "cluster": cid, "size": len(members),
            "label": distinctive_label(tc, len(members), tag_df, n_c,
                                       fallback=derive_label(top_tags, f"Cluster {cid}")),
            "n_sources": len({m["source_name"] for m in members if m["source_name"]}),
            "verticals": [v for v, _ in Counter(
                m["primary_vertical"] for m in members if m["primary_vertical"]).most_common(3)],
            "vertical_entropy": round(vent, 3),
            "maturity_span": mat["maturity_span"],
            "tier_onsets": mat["onsets"], "tier_totals": mat["tier_totals"],
            "lead_tier": mat["lead_tier"], "lead_months": mat["lead_months"],
            "durability": round(dur, 3),
            "mega_score": mega,
            "top_tags": top_tags,
            "rep_titles": [(r["title_en"] or "")[:110] for r in reps],
            "rep_ids": [r["id"] for r in reps],
        })
    noise = int((labels < 0).sum())
    return {"n_clusters": n_c, "noise": noise, "noise_frac": round(noise / len(rows), 3),
            "months": months, "clusters": clusters}


# ------------------------------------------------------------------- stability
def stability_ari(Xr: np.ndarray, labels: np.ndarray, frac: float = 0.8,
                  min_cluster_size: int | None = None) -> float:
    """Re-cluster a random `frac` subsample; ARI of the two labelings on the shared
    points. High (→1) = clusters are stable/real; low (→0) = noise. HDBSCAN is
    deterministic on fixed data, so we perturb via subsampling."""
    n = Xr.shape[0]
    rng = np.random.default_rng(7)
    sub = rng.choice(n, int(frac * n), replace=False)
    mcs = min_cluster_size or max(30, Xr.shape[0] // 400)
    lab2 = HDBSCAN(min_cluster_size=mcs, metric="euclidean", n_jobs=-1).fit_predict(Xr[sub])
    return float(adjusted_rand_score(labels[sub], lab2))
