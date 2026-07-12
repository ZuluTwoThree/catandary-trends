#!/usr/bin/env python3
"""Refit ln(K)=a+b·X for the #35 full-archive substrate (patent_spnp_full +
patent_cpc_full), against the Magee 2016 benchmark domains (reused from
calibrate_tir.BENCH). X = mean year-only SPNP percentile of a domain's patents in
the eligible window. Reports coefficients, R², Spearman — compare to the current
full-graph fit (-6.460/10.192, Spearman 0.83) and check the A61B/MRI outlier.

    python scripts/recalibrate_full.py                 # patent_spnp_full
    python scripts/recalibrate_full.py --spnp patent_spnp --cpc patent_cpc --raw
"""
from __future__ import annotations
import argparse, math, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection
from scripts.calibrate_tir import BENCH, YEAR_LO, YEAR_HI


def domain_x(cur, patterns, spnp, cpc, raw):
    like = " OR ".join("pc.cpc LIKE %s" for _ in patterns)
    args = tuple(p + "%" for p in patterns)
    if raw:  # full DB graph: patent_cpc→raw_entries→patent_spnp (raw_id)
        sql = (f"SELECT AVG(sp.spnp_pctl), COUNT(*) FROM ("
               f"  SELECT DISTINCT re.id FROM raw_entries re "
               f"    JOIN {cpc} pc ON pc.pub_number=re.pub_number WHERE ({like})"
               f") p JOIN {spnp} sp ON sp.raw_id=p.id "
               f"WHERE sp.year BETWEEN {YEAR_LO} AND {YEAR_HI}")
    else:    # staging graph: pub_number join
        sql = (f"SELECT AVG(sp.spnp_pctl), COUNT(*) FROM ("
               f"  SELECT DISTINCT pc.pub_number FROM {cpc} pc WHERE ({like})"
               f") p JOIN {spnp} sp ON sp.pub_number=p.pub_number "
               f"WHERE sp.year BETWEEN {YEAR_LO} AND {YEAR_HI}")
    cur.execute(sql, args)
    x, n = cur.fetchone()
    return (float(x) if x is not None else None), int(n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spnp", default="patent_spnp_full")
    ap.add_argument("--cpc", default="patent_cpc_full")
    ap.add_argument("--raw", action="store_true", help="raw_id join (full DB graph)")
    args = ap.parse_args()

    xs, ys, names, ns = [], [], [], []
    with get_connection() as c:
        cur = c._conn.cursor()
        for name, rate, pats in BENCH:
            x, n = domain_x(cur, pats, args.spnp, args.cpc, args.raw)
            if x is None or n < 100:
                print(f"  SKIP {name:28s} n={n}")
                continue
            xs.append(x); ys.append(math.log(rate)); names.append(name); ns.append(n)

    xs = np.array(xs); ys = np.array(ys)
    A = np.column_stack([np.ones(len(xs)), xs])
    beta, *_ = np.linalg.lstsq(A, ys, rcond=None)
    a, b = beta
    pred = A @ beta
    ss_res = float(np.sum((ys - pred) ** 2)); ss_tot = float(np.sum((ys - ys.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot
    sigma2 = ss_res / (len(xs) - 2)
    # Spearman (rank corr) of X vs observed rate
    rx = np.argsort(np.argsort(xs)); ry = np.argsort(np.argsort(np.exp(ys)))
    sp = float(np.corrcoef(rx, ry)[0, 1])

    print(f"\n  domains used: {len(xs)}")
    print(f"  COEF_A={a:.4f} COEF_B={b:.4f} SIGMA2={sigma2:.4f}")
    print(f"  R²={r2:.3f}  Spearman(X,rate)={sp:.3f}\n")
    print(f"  {'domain':28s} {'obs%':>6s} {'predK%':>7s} {'X':>5s} {'n':>8s}")
    for nm, x, y, n in sorted(zip(names, xs, ys, ns), key=lambda t: -t[1]):
        k = 100 * math.exp(a + b * x) * math.exp(sigma2 / 2) if False else math.exp(a + b * x)
        print(f"  {nm:28s} {math.exp(y):6.1f} {k:7.1f} {x:5.2f} {n:8,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
