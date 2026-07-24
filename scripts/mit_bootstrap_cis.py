#!/usr/bin/env python3
"""Bootstrap-Konfidenzintervalle für die Paper-Pflichtanalysen (Future-Work #9).

(1) Reproduziert die Kalibrier-Punktschätzer (own/cited: a, b, R², Spearman,
    LOO-R²) lokal aus den Dateien — Sanity-Check gegen mit_calibrate_substrate.
(2) Domänen-Bootstrap (B=10.000) über die n=29 Kalibrierdomänen: CIs für a, b,
    R², Spearman (cited) + gepaarter Bootstrap cited-vs-own (ΔR², ΔSpearman).
(3) Direkte LOO-Statistik: corr(K̂_LOO, K_true) auf ln-Skala + LOO-R².
(4) Cluster-Bootstrap über die Benchmark-Domänen (651 bei n≥500, 1299 bei
    n≥100): CIs für Spearman und Pearson(ln K) gegen die publizierten Prognosen.

Inputs: /mnt/data-hdd/Domains_patent_info.csv (Goldliste),
/mnt/data-hdd/performance_time_series.csv (K_true),
data/mit_benchmark/ours_us_grants.csv (unsere Perzentile, auto via mit_crosswalk),
data/mit_benchmark/com_abgleich_domains.csv (Benchmark-Paare).
Output: data/mit_benchmark/bootstrap_cis.json
"""
import csv, json, math, os
from collections import defaultdict

import numpy as np

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "mit_benchmark")
GOLD = "/mnt/data-hdd/Domains_patent_info.csv"
PERF = "/mnt/data-hdd/performance_time_series.csv"
OURS = os.path.join(BASE, "ours_us_grants.csv")
DOMS = os.path.join(BASE, "com_abgleich_domains.csv")
MIT_CSV = "/mnt/data-hdd/shared_tir_research/Technology_improvement_rates_for_all_technologies_Singh_Triulzi_Magee_May6.csv"
OUT = os.path.join(BASE, "bootstrap_cis.json")
B = 10_000
rng = np.random.default_rng(20260724)

def log(m): print(m, flush=True)

def pearson(a, b):
    return float(np.corrcoef(np.asarray(a, float), np.asarray(b, float))[0, 1])

def rank(v):
    v = np.asarray(v, float)
    o = np.argsort(v, kind="mergesort"); r = np.empty(len(v)); r[o] = np.arange(len(v))
    return r

def spearman(a, b):
    return pearson(rank(a), rank(b))

def ols(x, y):
    x = np.asarray(x, float); y = np.asarray(y, float)
    b_, a_ = np.polyfit(x, y, 1)
    pred = a_ + b_ * x
    ss_res = float(np.sum((y - pred) ** 2)); ss_tot = float(np.sum((y - y.mean()) ** 2))
    return float(a_), float(b_), 1 - ss_res / ss_tot, ss_res / max(len(x) - 2, 1)

def ci(vals, lo=2.5, hi=97.5):
    return [round(float(np.percentile(vals, lo)), 4), round(float(np.percentile(vals, hi)), 4)]

# --- K_true (wie mit_calibrate: ln(perf) ~ Jahr OLS-Steigung je Domäne) -------
series = defaultdict(list)
for r in csv.DictReader(open(PERF)):
    try:
        y = float(r["Year"]); v = float(r["Data"])
    except (TypeError, ValueError):
        continue
    if v > 0:
        series[r["Domain"]].append((y, math.log(v)))
K_true = {}
for d, pts in series.items():
    if len(pts) >= 5:
        xs, ys = zip(*sorted(pts))
        K_true[d] = float(np.polyfit(xs, ys, 1)[0])
log(f"K_true: {len(K_true)} Domänen")

# --- Domänen-X aus Goldliste × unseren Perzentilen ---------------------------
csv.field_size_limit(1 << 24)
ours = {}
for r in csv.reader(open(OURS)):
    if r[0] == "pnum": continue
    ours[int(r[0])] = (float(r[2]) if r[2] else None, float(r[3]) if r[3] else None)
agg = defaultdict(lambda: [0.0, 0, 0.0, 0])   # own_sum, own_n, cited_sum, cited_n
for r in csv.DictReader(open(GOLD)):
    pn = r["patent_number"].strip()
    if not pn.isdigit(): continue
    v = ours.get(int(pn))
    if not v: continue
    o, c = v
    a_ = agg[r["Domain"]]
    if o is not None: a_[0] += o; a_[1] += 1
    if c is not None: a_[2] += c; a_[3] += 1
doms = sorted(d for d in agg if d in K_true and K_true[d] > 0 and agg[d][1] > 0 and agg[d][3] > 0)
own_x = np.array([agg[d][0] / agg[d][1] for d in doms])
cit_x = np.array([agg[d][2] / agg[d][3] for d in doms])
lnk = np.array([math.log(K_true[d]) for d in doms])
log(f"Kalibrierbasis: n={len(doms)} Domänen")

# --- (1) Punktschätzer + LOO --------------------------------------------------
def loo_stats(x, y):
    preds = []
    for i in range(len(x)):
        m = np.ones(len(x), bool); m[i] = False
        a_, b_, _, _ = ols(x[m], y[m])
        preds.append(a_ + b_ * x[i])
    preds = np.array(preds)
    ss_res = float(np.sum((y - preds) ** 2)); ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1 - ss_res / ss_tot, pearson(preds, y), spearman(preds, y)

point = {}
for label, x in (("own", own_x), ("cited", cit_x)):
    a_, b_, r2, sig2 = ols(x, lnk)
    loo_r2, loo_pear, loo_spear = loo_stats(x, lnk)
    point[label] = {"a": round(a_, 4), "b": round(b_, 4), "sigma2": round(sig2, 4),
                    "r2": round(r2, 4), "spearman": round(spearman(x, lnk), 4),
                    "loo_r2": round(loo_r2, 4),
                    "loo_corr_pred_true_ln": round(loo_pear, 4),
                    "loo_spearman_pred_true": round(loo_spear, 4)}
log(json.dumps(point, indent=2))

# --- (2) Domänen-Bootstrap (gepaart) -----------------------------------------
n = len(doms)
bs = {k: [] for k in ("a_c", "b_c", "r2_c", "sp_c", "r2_o", "d_r2", "d_sp")}
for _ in range(B):
    idx = rng.integers(0, n, n)
    if len(np.unique(idx)) < 4: continue
    x_c, x_o, y = cit_x[idx], own_x[idx], lnk[idx]
    if np.ptp(x_c) < 1e-9 or np.ptp(x_o) < 1e-9 or np.ptp(y) < 1e-9: continue
    a_c, b_c, r2_c, _ = ols(x_c, y)
    _, _, r2_o, _ = ols(x_o, y)
    sp_c, sp_o = spearman(x_c, y), spearman(x_o, y)
    bs["a_c"].append(a_c); bs["b_c"].append(b_c); bs["r2_c"].append(r2_c)
    bs["sp_c"].append(sp_c); bs["r2_o"].append(r2_o)
    bs["d_r2"].append(r2_c - r2_o); bs["d_sp"].append(sp_c - sp_o)
boot = {"B_effective": len(bs["a_c"]),
        "cited": {"a_ci": ci(bs["a_c"]), "b_ci": ci(bs["b_c"]),
                  "r2_ci": ci(bs["r2_c"]), "spearman_ci": ci(bs["sp_c"])},
        "own": {"r2_ci": ci(bs["r2_o"])},
        "paired_cited_minus_own": {
            "delta_r2_ci": ci(bs["d_r2"]),
            "p_delta_r2_gt0": round(float(np.mean(np.array(bs["d_r2"]) > 0)), 4),
            "delta_spearman_ci": ci(bs["d_sp"]),
            "p_delta_sp_gt0": round(float(np.mean(np.array(bs["d_sp"]) > 0)), 4)}}
log(json.dumps(boot, indent=2))

# --- (4) Cluster-Bootstrap Benchmark -----------------------------------------
mit_k = {}
for r in csv.DictReader(open(MIT_CSV)):
    mit_k[r["Domain Code (UPC-IPC)"].strip()] = float(r["Predicted K (% per annum)"])
rows = [(math.log(mit_k[r["code"]]), math.log(float(r["ours_K"])), int(r["n_matched"]))
        for r in csv.DictReader(open(DOMS))]
bench = {}
for floor, name in ((500, "floor_500"), (100, "floor_100")):
    sub = [(m, o) for m, o, nm in rows if nm >= floor]
    a = np.array([s[0] for s in sub]); b_ = np.array([s[1] for s in sub])
    sps, prs = [], []
    for _ in range(B):
        idx = rng.integers(0, len(sub), len(sub))
        sps.append(spearman(a[idx], b_[idx])); prs.append(pearson(a[idx], b_[idx]))
    bench[name] = {"n_domains": len(sub),
                   "spearman": round(spearman(a, b_), 4), "spearman_ci": ci(sps),
                   "pearson_ln": round(pearson(a, b_), 4), "pearson_ln_ci": ci(prs)}
log(json.dumps(bench, indent=2))

json.dump({"calibration_point": point, "calibration_bootstrap": boot,
           "benchmark_bootstrap": bench, "n_calibration_domains": n, "B": B},
          open(OUT, "w"), indent=2)
log(f"→ {OUT}")
