#!/usr/bin/env python3
"""WS1: Kalibrierung + Prädiktor-Experiment gegen den ORIGINALEN MIT-Datensatz.

Beantwortet die WS1e-Kernfrage rein im MIT-Datensatz (also methodisch unbelastet
von unserem Substrat): Ist der bessere TIR-Prädiktor die EIGENE Zentralität der
Domänen-Patente (SPNP_count_t3) oder die Zentralität der ZITIERTEN Patente
(meanSPNPcited) — der Prädiktor, den das TechNext-Patent als kanonisch nennt?

  1) K_true je Domäne = Steigung von ln(performance) über die Jahre
     (performance_time_series.csv, 29 Domänen).
  2) X je Domäne = Mittel des Prädiktors über die Domänen-Patente
     (Domains_patent_info.csv).
  3) Fit ln(K)=a+b·X je Prädiktor; R², Spearman, LOO-CV-R². Vergleich A vs B.

    python scripts/mit_calibrate.py
"""
from __future__ import annotations
import csv, math, sys
from collections import defaultdict

PERF = "/mnt/data-hdd/performance_time_series.csv"
INFO = "/mnt/data-hdd/Domains_patent_info.csv"
PREDICTORS = {
    "A_own_SPNP_t3":    "SPNP_count_t3_randomized_zscore_RPbyYear",
    "B_cited_meanSPNP": "meanSPNPcited_1year_before_randomized_zscore_RPbyYear",
    "A2_own_t3_rankpc": "SPNP_count_t3_RankPerc_by_year",
    "B2_cited_rankpc":  "meanSPNPcited_1year_before_RankPerc_by_year",
}
csv.field_size_limit(1 << 24)


def k_true() -> dict[str, float]:
    """ln(perf) ~ year slope je Domäne = jährliche Verbesserungsrate K."""
    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in csv.DictReader(open(PERF)):
        try:
            y = float(r["Year"]); v = float(r["Data"])
        except (ValueError, TypeError):
            continue
        if v > 0:
            series[r["Domain"]].append((y, math.log(v)))
    K = {}
    for dom, pts in series.items():
        if len(pts) < 3:
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        mx = sum(xs) / len(xs); my = sum(ys) / len(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den <= 0:
            continue
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
        K[dom] = slope  # fraction/yr
    return K


def domain_X() -> dict[str, dict[str, float]]:
    """Mittel jedes Prädiktors je Domäne über die Domänen-Patente."""
    acc = {p: defaultdict(lambda: [0.0, 0]) for p in PREDICTORS}
    with open(INFO) as f:
        rd = csv.DictReader(f)
        for r in rd:
            dom = r["Domain"]
            for p, col in PREDICTORS.items():
                v = r.get(col, "")
                if v not in ("", "NA", "NaN", None):
                    try:
                        fv = float(v)
                    except ValueError:
                        continue
                    acc[p][dom][0] += fv; acc[p][dom][1] += 1
    out: dict[str, dict[str, float]] = {p: {} for p in PREDICTORS}
    for p in PREDICTORS:
        for dom, (s, n) in acc[p].items():
            if n > 0:
                out[p][dom] = s / n
    return out


def fit(xs: list[float], ys: list[float]):
    n = len(xs)
    mx = sum(xs) / n; my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs) or 1e-12
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    a = my - b * mx
    pred = [a + b * x for x in xs]
    ssr = sum((y - p) ** 2 for y, p in zip(ys, pred))
    sst = sum((y - my) ** 2 for y in ys) or 1e-12
    return a, b, 1 - ssr / sst


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for rnk, i in enumerate(order):
            r[i] = rnk
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs); mrx = sum(rx) / n; mry = sum(ry) / n
    num = sum((a - mrx) * (b - mry) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mrx) ** 2 for a in rx) * sum((b - mry) ** 2 for b in ry)) or 1e-12
    return num / den


def loo_r2(xs, ys):
    """Leave-one-out CV R² (echte Out-of-Sample-Güte bei n=29)."""
    n = len(xs); errs = []
    for i in range(n):
        xtr = xs[:i] + xs[i+1:]; ytr = ys[:i] + ys[i+1:]
        a, b, _ = fit(xtr, ytr)
        errs.append((ys[i] - (a + b * xs[i])) ** 2)
    my = sum(ys) / n
    sst = sum((y - my) ** 2 for y in ys) or 1e-12
    return 1 - sum(errs) / sst


def main() -> int:
    K = k_true()
    X = domain_X()
    print(f"K_true: {len(K)} Domänen aus Performance-Zeitreihen\n")
    print(f"{'Prädiktor':20s} {'n':>3} {'a':>8} {'b':>8} {'R²':>6} {'Spearman':>9} {'LOO-R²':>7}")
    print("-" * 66)
    results = {}
    for p, col in PREDICTORS.items():
        doms = [d for d in K if d in X[p]]
        xs = [X[p][d] for d in doms]
        ys = [math.log(K[d]) for d in doms if K[d] > 0]
        doms = [d for d in doms if K[d] > 0]
        xs = [X[p][d] for d in doms]
        if len(xs) < 5:
            print(f"{p:20s} zu wenige Domänen ({len(xs)})"); continue
        a, b, r2 = fit(xs, ys)
        sp = spearman(xs, ys); loo = loo_r2(xs, ys)
        results[p] = (r2, sp, loo)
        print(f"{p:20s} {len(xs):>3} {a:8.3f} {b:8.3f} {r2:6.3f} {sp:9.3f} {loo:7.3f}")
    print("\nDeutung: A* = EIGENE Zentralität (unser aktueller Prädiktor); "
          "B* = ZITIERTE Zentralität (Patent-kanonisch).")
    if "A_own_SPNP_t3" in results and "B_cited_meanSPNP" in results:
        ra, rb = results["A_own_SPNP_t3"][0], results["B_cited_meanSPNP"][0]
        la, lb = results["A_own_SPNP_t3"][2], results["B_cited_meanSPNP"][2]
        win = "B (zitiert)" if lb > la else "A (eigen)"
        print(f"→ Besserer OOS-Prädiktor (LOO-R²): {win}  (A={la:.3f} vs B={lb:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
