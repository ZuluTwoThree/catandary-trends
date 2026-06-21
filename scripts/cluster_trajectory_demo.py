#!/usr/bin/env python3
"""Cluster + trajectory demo on signal embeddings (Foresight preview).

Shows what the signal-mode data (classification + embedding + date) yields BEFORE
any article exists: semantic clusters of the embeddings (= candidate trends), each
with representative titles, dominant mega-trend/tags, cross-source corroboration,
and a monthly trajectory (signal volume over time → momentum). Read-only.

    python scripts/cluster_trajectory_demo.py --vertical FOOD
    python scripts/cluster_trajectory_demo.py --vertical FOOD --status signal --k 10
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from pipeline.db import get_connection
from pipeline.llm_processor import bytes_to_embedding

SPARK = "▁▂▃▄▅▆▇█"


def sparkline(counts: list[int]) -> str:
    if not counts or max(counts) == 0:
        return " " * len(counts)
    hi = max(counts)
    return "".join(SPARK[min(len(SPARK) - 1, int(c / hi * (len(SPARK) - 1)))] for c in counts)


def load(vertical: str, status: str, limit: int) -> list[dict]:
    sql = ("SELECT t.id, t.title_en, t.mega_trend, t.tags, t.source_name, "
           "       r.published_date, t.embedding "
           "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
           "WHERE t.status = ? AND t.primary_vertical = ? AND t.embedding IS NOT NULL")
    params = [status, vertical]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
    out = []
    for r in rows:
        emb = r["embedding"]
        try:
            vec = bytes_to_embedding(emb) if isinstance(emb, (bytes, bytearray)) else None
        except Exception:
            vec = None
        if not vec:
            continue
        r["_vec"] = vec
        out.append(r)
    return out


def month_key(d) -> str | None:
    if not d:
        return None
    s = str(d)[:7]
    return s if len(s) == 7 and s[4] == "-" else None


def pick_k(X: np.ndarray, lo: int = 6, hi: int = 14) -> int:
    n = X.shape[0]
    if n < 60:
        return max(2, min(6, n // 8))
    sample = X if n <= 3000 else X[np.random.default_rng(42).choice(n, 3000, replace=False)]
    best_k, best_s = lo, -1.0
    for k in range(lo, min(hi, n // 10) + 1):
        labels = KMeans(n_clusters=k, n_init=4, random_state=42).fit_predict(sample)
        s = silhouette_score(sample, labels, sample_size=min(1500, len(sample)), random_state=42)
        if s > best_s:
            best_k, best_s = k, s
    return best_k


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vertical", default="FOOD")
    ap.add_argument("--status", default="signal")
    ap.add_argument("--k", type=int, help="cluster count (default: silhouette-chosen)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = load(args.vertical, args.status, args.limit)
    print(f"{args.vertical} signals (status={args.status}) with embedding: {len(rows)}")
    if len(rows) < 20:
        print("Too few signals for a meaningful demo.")
        return 0

    X = np.asarray([r["_vec"] for r in rows], dtype=np.float32)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)  # spherical k-means
    k = args.k or pick_k(X)
    print(f"clustering into k={k} (cosine/spherical KMeans) ...\n")
    km = KMeans(n_clusters=k, n_init=8, random_state=42).fit(X)
    labels = km.labels_

    # global month axis
    months = sorted({m for r in rows if (m := month_key(r["published_date"]))})
    midx = {m: i for i, m in enumerate(months)}

    # cluster summaries, ordered by size
    order = [c for c, _ in Counter(labels).most_common()]
    print(f"Months covered: {months[0]}..{months[-1]} ({len(months)})\n")
    for c in order:
        members = [rows[i] for i in range(len(rows)) if labels[i] == c]
        # representative: closest to centroid
        cen = km.cluster_centers_[c]
        idxs = [i for i in range(len(rows)) if labels[i] == c]
        d = X[idxs] @ (cen / max(np.linalg.norm(cen), 1e-9))
        reps = [rows[idxs[j]] for j in np.argsort(-d)[:3]]
        megas = Counter(m["mega_trend"] for m in members if m["mega_trend"])
        tags = Counter()
        for m in members:
            try:
                tags.update(json.loads(m["tags"]) if m["tags"] else [])
            except Exception:
                pass
        sources = {m["source_name"] for m in members if m["source_name"]}
        traj = [0] * len(months)
        for m in members:
            mk = month_key(m["published_date"])
            if mk in midx:
                traj[midx[mk]] += 1

        top_mega = megas.most_common(1)[0][0] if megas else "—"
        print(f"━━ Cluster {c}  ·  {len(members)} signals  ·  {len(sources)} distinct sources")
        print(f"   mega-trend: {top_mega}   |   top tags: {', '.join(t for t,_ in tags.most_common(6))}")
        print(f"   trajectory {months[0]}…{months[-1]}: {sparkline(traj)}  (peak {max(traj)}/mo)")
        for r in reps:
            print(f"     • {(r['title_en'] or '')[:84]}")
        print()

    # overall mega-trend trajectories (verification: sustained vs spike)
    print("Top mega-trends — monthly trajectory (volume = momentum):")
    mega_month: dict[str, list[int]] = {}
    for r in rows:
        mt, mk = r["mega_trend"], month_key(r["published_date"])
        if mt and mk in midx:
            mega_month.setdefault(mt, [0] * len(months))[midx[mk]] += 1
    for mt, series in sorted(mega_month.items(), key=lambda kv: -sum(kv[1]))[:8]:
        print(f"   {mt[:34]:<35} {sparkline(series)}  Σ{sum(series)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
