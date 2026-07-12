#!/usr/bin/env python3
"""Refit the TIR calibration ln(K)=a+b·X for the full-graph z-score normalization,
against the 24 Magee et al. (2016) benchmark domains with empirically observed
annual improvement rates (S1_File). X = mean normalized centrality of a domain's
eligible patents from the staging SPNP (patent_spnp_staging via spnp_full.csv).

    python scripts/calibrate_tir.py --spnp /mnt/data-hdd/patent_staging/spnp_full.csv
"""
from __future__ import annotations
import argparse, glob, sys
from pathlib import Path
import numpy as np
import pyarrow as pa, pyarrow.compute as pc, pyarrow.csv as pacsv, pyarrow.parquet as pq

# (domain, observed annual improvement rate [%/yr], CPC prefix(es)). Rates: Magee
# et al. 2016 S1. CPC mapping = best single-domain approximation (the paper uses
# COM UPC×IPC sets; we map to the closest CPC subclass/group).
BENCH = [
    ("Aircraft transport",        12.2, ["B64C"]),
    ("Camera sensitivity",        15.6, ["H04N25", "H01L27/146"]),
    ("Capacitor energy storage",  14.6, ["H01G"]),
    ("Combustion engines",         5.7, ["F02B", "F02D"]),
    ("Electric motors",            3.1, ["H02K"]),
    ("Electrical energy transm.", 14.9, ["H02J"]),
    ("Electrical info transm.",   14.3, ["H04L", "H04B3"]),
    ("Electrochem. battery",       7.0, ["H01M10"]),
    ("Electronic computation",    33.0, ["G06F"]),
    ("Fuel cell",                 14.4, ["H01M8"]),
    ("Genome sequencing",         29.3, ["C12Q1/6869", "C12Q1/6874", "C12Q1/6809"]),
    ("Incandescent illumination",  4.5, ["H01K", "F21K"]),
    ("LED illumination",          36.2, ["H01L33", "H10H20"]),
    ("MRI",                       47.5, ["A61B5/055", "G01R33"]),
    ("Magnetic info storage",     31.9, ["G11B5"]),
    ("Milling machines",           3.4, ["B23C"]),
    ("Optical info storage",      27.1, ["G11B7"]),
    ("Optical info transm.",      65.1, ["H04B10"]),
    ("Photolithography",          24.0, ["G03F"]),
    ("Solar PV",                   9.5, ["H02S"]),
    ("Superconductivity",          9.5, ["H10N60", "H01L39"]),
    ("Wind turbine",               9.2, ["F03D"]),
    ("Wireless info transm.",      50.4, ["H04B7", "H04W"]),
]
# Flywheel (n=154) dropped — too few patents for a stable X.

YEAR_LO, YEAR_HI = 1985, 2019   # eligible window for the domain-mean X


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spnp", default="/mnt/data-hdd/patent_staging/spnp_full.csv")
    ap.add_argument("--staging", default="/mnt/data-hdd/patent_staging")
    args = ap.parse_args()

    print("loading SPNP …", flush=True)
    sp = pacsv.read_csv(args.spnp,
        read_options=pacsv.ReadOptions(column_names=["pub", "year", "pctl"]),
        convert_options=pacsv.ConvertOptions(column_types={
            "pub": pa.large_string(), "year": pa.int16(), "pctl": pa.float32()}))
    sp_pub = sp.column("pub").combine_chunks()
    sp_year = sp.column("year").to_numpy(zero_copy_only=False)
    sp_pctl = sp.column("pctl").to_numpy(zero_copy_only=False)
    print(f"  {len(sp_pub):,} eligible", flush=True)

    prefs = [p for _, _, ps in BENCH for p in ps]
    sums = {p: 0.0 for p in prefs}; cnts = {p: 0 for p in prefs}
    for i, sh in enumerate(sorted(glob.glob(f"{args.staging}/nodes-*.parquet"))):
        t = pq.read_table(sh, columns=["pub_number", "cpc"])
        pub = t.column("pub_number").combine_chunks().cast(pa.large_string())
        idx = pc.index_in(pub, value_set=sp_pub).to_numpy(zero_copy_only=False).astype("float64")
        elig = ~np.isnan(idx)
        flat = t.column("cpc").combine_chunks(); codes = pc.list_flatten(flat)
        parent = pc.list_parent_indices(flat).to_numpy(zero_copy_only=False)
        for p in prefs:
            m = pc.starts_with(codes, p).to_numpy(zero_copy_only=False)
            rows = np.unique(parent[m]); rows = rows[elig[rows]]
            if not len(rows):
                continue
            sidx = idx[rows].astype(np.int64)
            yy = sp_year[sidx]; pp = sp_pctl[sidx]
            w = (yy >= YEAR_LO) & (yy <= YEAR_HI)
            sums[p] += float(pp[w].sum()); cnts[p] += int(w.sum())
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/162", flush=True)

    print(f"\n{'domain':26s}{'obs%':>7s}{'X':>7s}{'n':>9s}", flush=True)
    X, Y, names = [], [], []
    for name, rate, ps in BENCH:
        s = sum(sums[p] for p in ps); c = sum(cnts[p] for p in ps)
        if c < 100:
            print(f"{name:26s}{rate:>7.1f}{'—':>7s}{c:>9,}  (skip, thin)"); continue
        x = s / c
        X.append(x); Y.append(np.log(rate / 100.0)); names.append(name)
        print(f"{name:26s}{rate:>7.1f}{x:>7.3f}{c:>9,}", flush=True)

    X = np.array(X); Y = np.array(Y)
    A = np.column_stack([np.ones(len(X)), X])
    (b0, b1), *_ = np.linalg.lstsq(A, Y, rcond=None)
    resid = Y - A @ np.array([b0, b1])
    ss_res = float((resid ** 2).sum()); ss_tot = float(((Y - Y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot
    sigma2 = ss_res / (len(X) - 2)
    # Spearman
    rx = np.argsort(np.argsort(X)); ry = np.argsort(np.argsort(Y))
    spear = float(np.corrcoef(rx, ry)[0, 1])
    print(f"\n=== REFIT (n={len(X)}) ===")
    print(f"  COEF_A (b0) = {b0:.4f}")
    print(f"  COEF_B (b1) = {b1:.4f}")
    print(f"  SIGMA2      = {sigma2:.4f}")
    print(f"  R² = {r2:.3f}   Spearman = {spear:.3f}")
    print(f"\n  (current in code: A=-6.460 B=10.192 SIGMA2=0.374)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
