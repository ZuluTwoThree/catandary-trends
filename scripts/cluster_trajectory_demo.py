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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from pipeline.db import get_connection

SPARK = "▁▂▃▄▅▆▇█"


def sparkline(counts: list[int]) -> str:
    if not counts or max(counts) == 0:
        return " " * len(counts)
    hi = max(counts)
    return "".join(SPARK[min(len(SPARK) - 1, int(c / hi * (len(SPARK) - 1)))] for c in counts)


def load(vertical: str, status: str, limit: int, patents_only: bool = False,
         source_like: str | None = None) -> list[dict]:
    # status: "all" = every status; else a single status or comma list.
    # vertical: "ALL"/empty = no vertical filter (e.g. the funding pool spans all
    # verticals after classification). source_like: comma-separated substrings
    # matched (OR) against t.source_name — e.g. "NSF,NIH,OpenAIRE,UKRI" isolates
    # the funding signal pool regardless of vertical.
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
    if patents_only:
        where.append("r.pub_number IS NOT NULL")  # only patent signals
    if source_like:
        pats = [p.strip() for p in source_like.split(",") if p.strip()]
        if pats:
            where.append("(" + " OR ".join(["t.source_name LIKE ?"] * len(pats)) + ")")
            params += [f"%{p}%" for p in pats]
    sql = ("SELECT t.id, t.title_en, t.mega_trend, t.tags, t.source_name, t.status, "
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
        # Keep the raw float32 bytes; decode to a numpy matrix in bulk (main()).
        # Decoding each to a Python list here materialises ~46 GB at 400k signals
        # (the Stage-5 OOM pattern) — frombuffer on the raw bytes avoids it.
        if not isinstance(emb, (bytes, bytearray)) or len(emb) < 4:
            continue
        r["_emb"] = bytes(emb)
        r["embedding"] = None  # drop the duplicate blob to keep memory flat
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
    ap.add_argument("--vertical", default="FOOD", help="primary_vertical, or ALL for no vertical filter")
    ap.add_argument("--status", default="signal")
    ap.add_argument("--k", type=int, help="cluster count (default: silhouette-chosen)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--patents-only", action="store_true", help="only patent signals (pub_number set)")
    ap.add_argument("--source-like", default=None,
                    help="comma-separated substrings matched (OR) against source_name, "
                         "e.g. 'NSF,NIH,OpenAIRE,UKRI' for the funding signal pool")
    ap.add_argument("--sov", action="store_true",
                    help="Share-of-Voice: each cluster's share of the vertical's monthly "
                         "volume + Δ-share early→late (removes the source-growth bias)")
    args = ap.parse_args()

    rows = load(args.vertical, args.status, args.limit, args.patents_only, args.source_like)
    label = "patent signals" if args.patents_only else "signals"
    scope = args.source_like if args.source_like else args.vertical
    print(f"{scope} {label} (status={args.status}) with embedding: {len(rows)}")
    if len(rows) < 20:
        print("Too few signals for a meaningful demo.")
        return 0

    # Build the matrix straight from the raw bytes (no Python-list intermediary).
    _dim = len(rows[0]["_emb"]) // 4
    X = np.empty((len(rows), _dim), dtype=np.float32)
    for _i, _r in enumerate(rows):
        X[_i] = np.frombuffer(_r["_emb"], dtype=np.float32)
        _r["_emb"] = None  # free the raw bytes as we go (~6.5 GB at full-pool scale)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)  # spherical k-means
    k = args.k or pick_k(X)
    # n_init=8 is fine at demo scale; at full-pool scale (400k×4096) it's the cost
    # driver, so drop to 3 restarts above 50k points (KMeans is stable here).
    n_init = 8 if X.shape[0] <= 50000 else 3
    print(f"clustering {X.shape[0]} × {X.shape[1]} into k={k} (cosine/spherical KMeans, n_init={n_init}) ...\n")
    km = KMeans(n_clusters=k, n_init=n_init, random_state=42).fit(X)
    labels = km.labels_

    # global month axis + per-month total (the SoV denominator)
    months = sorted({m for r in rows if (m := month_key(r["published_date"]))})
    midx = {m: i for i, m in enumerate(months)}
    total_by_month = [0] * len(months)
    for r in rows:
        mk = month_key(r["published_date"])
        if mk in midx:
            total_by_month[midx[mk]] += 1

    sov = args.sov
    if sov:
        # restrict to months with enough volume (sparse early months → noisy share),
        # then split that window into early/late thirds for the Δ-share.
        meaningful = [i for i in range(len(months)) if total_by_month[i] >= 5]
        third = max(1, len(meaningful) // 3)
        early_idx, late_idx = set(meaningful[:third]), set(meaningful[-third:])

        def share(traj, idxs):
            cs = sum(traj[i] for i in idxs); ts = sum(total_by_month[i] for i in idxs)
            return cs / ts if ts else 0.0

    def cluster_traj(members):
        t = [0] * len(months)
        for m in members:
            mk = month_key(m["published_date"])
            if mk in midx:
                t[midx[mk]] += 1
        return t

    order = [c for c, _ in Counter(labels).most_common()]
    print(f"Months covered: {months[0]}..{months[-1]} ({len(months)})")
    if sov and meaningful:
        print(f"SoV-Fenster: früh {months[min(early_idx)]}..{months[max(early_idx)]}  vs  "
              f"spät {months[min(late_idx)]}..{months[max(late_idx)]}  "
              f"(Anteil am monatlichen {scope}-Volumen)")
    print()

    sov_rows = []
    for c in order:
        members = [rows[i] for i in range(len(rows)) if labels[i] == c]
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
        traj = cluster_traj(members)
        top_mega = megas.most_common(1)[0][0] if megas else "—"
        toptags = ", ".join(t for t, _ in tags.most_common(6))
        if sov:
            se, sl = share(traj, early_idx), share(traj, late_idx)
            spark = sparkline([traj[i] / total_by_month[i] if total_by_month[i] else 0
                               for i in range(len(months))])
            sov_rows.append((sl - se, se, sl, c, len(members), top_mega, toptags, spark,
                             (reps[0]["title_en"] or "")[:80] if reps else ""))
        else:
            print(f"━━ Cluster {c}  ·  {len(members)} signals  ·  {len(sources)} distinct sources")
            print(f"   mega-trend: {top_mega}   |   top tags: {toptags}")
            print(f"   trajectory {months[0]}…{months[-1]}: {sparkline(traj)}  (peak {max(traj)}/mo)")
            for r in reps:
                print(f"     • {(r['title_en'] or '')[:84]}")
            print()

    if sov:
        print("Share-of-Voice je Cluster — sortiert nach Δ-Anteil (steigende zuerst):\n")
        for ds, se, sl, c, n, top_mega, toptags, spark, rep0 in sorted(sov_rows, key=lambda x: -x[0]):
            arrow = "↑ steigt" if ds > 0.005 else ("↓ fällt" if ds < -0.005 else "→ stabil")
            print(f"━━ Cluster {c}  ·  {n} signals  ·  {top_mega}")
            print(f"   Anteil: {se*100:4.1f}% → {sl*100:4.1f}%   (Δ {ds*100:+.1f}pp  {arrow})")
            print(f"   share-Verlauf {months[0]}…{months[-1]}: {spark}")
            print(f"   tags: {toptags}")
            print(f"     • {rep0}\n")

    # mega-trend roll-up
    mega_month: dict[str, list[int]] = {}
    for r in rows:
        mt, mk = r["mega_trend"], month_key(r["published_date"])
        if mt and mk in midx:
            mega_month.setdefault(mt, [0] * len(months))[midx[mk]] += 1
    if sov:
        print("Top Mega-Trends — Share-of-Voice (Δ früh→spät):")
        mt_rows = [(share(s, late_idx) - share(s, early_idx), share(s, early_idx),
                    share(s, late_idx), mt, sum(s)) for mt, s in mega_month.items()]
        for ds, se, sl, mt, tot in sorted(mt_rows, key=lambda x: -x[0])[:10]:
            arrow = "↑" if ds > 0.005 else ("↓" if ds < -0.005 else "→")
            print(f"   {mt[:32]:<33} {se*100:4.1f}%→{sl*100:4.1f}% (Δ{ds*100:+5.1f}pp {arrow})  Σ{tot}")
    else:
        print("Top mega-trends — monthly trajectory (volume = momentum):")
        for mt, series in sorted(mega_month.items(), key=lambda kv: -sum(kv[1]))[:8]:
            print(f"   {mt[:34]:<35} {sparkline(series)}  Σ{sum(series)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
