#!/usr/bin/env python3
"""Calibrate the mega layer's clustering parameters against the current corpus.

Read-only. The mega layer's defaults (PCA dims, HDBSCAN selection method and
min_cluster_size) were set when the corpus was ~0.5M signals and much less
heterogeneous. At 1.1M they returned 2-4 super-blobs at 54-71 % noise with a
stability ARI of 0.19-0.55 — i.e. the parameters, not the data, decided the
outcome. This sweeps them on ONE drawn sample (loaded once, PCA fitted once —
PCA components are nested, so a k-dim run is exactly the leading k columns) and
reports what each setting actually yields:

  n_clusters · noise fraction · median cluster size · stability ARI (80 % resample)

Usage:
  python scripts/tune_mega_clustering.py                     # default sweep
  python scripts/tune_mega_clustering.py --sample 80000 --dim1024
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sklearn.decomposition import PCA

from pipeline import discovery
from pipeline.foresight import build_matrix

DIMS = [15, 30, 50]
METHODS = ["eom", "leaf"]
MIN_SIZES = [60, 150, 400]


def main() -> int:
    ap = argparse.ArgumentParser(description="Sweep mega-layer clustering parameters")
    ap.add_argument("--sample", type=int, default=50_000)
    ap.add_argument("--status", default="signal,published")
    ap.add_argument("--strata", choices=["tier", "proportional"], default="tier")
    ap.add_argument("--source-cap", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dim1024", action="store_true")
    ap.add_argument("--dims", type=int, nargs="+", default=DIMS)
    ap.add_argument("--methods", nargs="+", default=METHODS)
    ap.add_argument("--min-sizes", type=int, nargs="+", default=MIN_SIZES)
    ap.add_argument("--out", default="data/discovery/tuning.json")
    args = ap.parse_args()

    t0 = time.time()
    meta = discovery.load_scope_meta("global", args.status, args.dim1024)
    ids, rep = discovery.plan_sample(meta, args.sample, args.strata,
                                     args.source_cap, args.seed)
    rows = discovery.load_scope("global", args.status, ids=ids, dim1024=args.dim1024)
    X = build_matrix(rows)
    print(f"{len(rows)} signals · {X.shape[1]}-D · loaded in {time.time()-t0:.0f}s")

    # One PCA per dim rather than slicing a wide one: randomized SVD approximates
    # a different subspace depending on how many components it is asked for, and
    # production calls reduce_dims(X, d) — the sweep has to fit what ships.
    t1 = time.time()
    var = {}
    for d in args.dims:
        p = PCA(n_components=d, svd_solver="randomized", random_state=42).fit(X)
        var[d] = float(p.explained_variance_ratio_.sum())
    print(f"PCA fits in {time.time()-t1:.0f}s · explained variance: "
          + " · ".join(f"{d}D={var[d]:.1%}" for d in args.dims))

    results = []
    print(f"\n{'dims':>5} {'method':<6} {'min_size':>8} {'clusters':>9} {'noise':>7} "
          f"{'median_n':>9} {'max_n':>8} {'ARI':>6} {'s':>5}")
    for d in args.dims:
        Xr = discovery.reduce_dims(X, d)
        for method in args.methods:
            for mcs in args.min_sizes:
                t = time.time()
                labels = discovery.cluster_density(Xr, mcs, method=method)
                k = len({int(x) for x in labels if x >= 0})
                noise = float((labels < 0).mean())
                sizes = [int((labels == c).sum()) for c in range(k)] or [0]
                ari = discovery.stability_ari(Xr, labels, min_cluster_size=mcs,
                                              method=method)
                dur = time.time() - t
                results.append({"dims": d, "method": method, "min_cluster_size": mcs,
                                "n_clusters": k, "noise_frac": round(noise, 3),
                                "median_size": int(np.median(sizes)),
                                "max_size": int(max(sizes)), "ari": round(ari, 3),
                                "seconds": round(dur, 1)})
                print(f"{d:>5} {method:<6} {mcs:>8} {k:>9} {noise:>6.0%} "
                      f"{int(np.median(sizes)):>9} {max(sizes):>8} {ari:>6.2f} {dur:>5.0f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"sample": rep, "dim": X.shape[1],
                               "explained_variance": {str(d): round(var[d], 4)
                                                      for d in args.dims},
                               "results": results}, indent=2), encoding="utf-8")
    print(f"\n→ {out}  ({time.time()-t0:.0f}s total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
