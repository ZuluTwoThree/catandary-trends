#!/usr/bin/env python3
"""Year-by-year TIR trajectory K(t) for a fine-grained technology (issue #36).

A technology = a set of fine CPC codes (LIKE patterns), e.g.
"protein via electrodialysis" = A23J3/* ∪ B01D61/44 ∪ A23C9/144. For each year
we take the patents granted in a rolling window that carry ANY of the codes,
average their SPNP centrality percentile X(t), and map it to an improvement rate
K(t) via the refit MIT regression (spnp_centrality). The SHAPE of K(t) — rising
vs falling — is the S-curve signal: is the technology accelerating or maturing.

Honesty is built in:
  • per-year MIN_N gate — a window with too few patents is not reported.
  • truncation — the last TRUNC_YEARS carry incomplete forward citations, so
    their K is flagged `complete=False` (grey it out) and excluded from the
    direction fit.
  • calibration — the refit was trained up to ~20%/yr; a K above CALIB_MAX is
    outside the calibrated range (software/AI saturation), so the absolute value
    is withheld and only the DIRECTION is reported. `calibrated` says which.

    python scripts/tir_trajectory.py --like "H01M10/052%"
    python scripts/tir_trajectory.py --like "A23J3/%" "B01D61/44%" "A23C9/144%" --name "Protein via electrodialysis"
    python scripts/tir_trajectory.py --like "Y02E10/7%" --json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from scripts.spnp_centrality import COEF_A, COEF_B, SIGMA2

# --- tunables (the honesty gates) --------------------------------------------
WINDOW = 5              # rolling-window years for each K(t) point
MIN_N = 300            # min patents in a window to report that year
# Empirically, a domain's mean SPNP percentile peaks ~2018-2019 and then droops
# for EVERY domain — patents granted after ~2019 haven't accumulated enough of
# the forward-citation descendant tree for their centrality RANK to stabilize
# (it regresses toward the cohort mean 0.5). So the reliably-measurable window
# ends ~7 years before present; more recent years are flagged incomplete and
# excluded from the direction fit. This is the honest citation-maturity horizon.
TRUNC_YEARS = 7        # last N years have immature citation centrality → grey
RECENT_YEARS = 7       # direction is fit over the most recent complete window
YEAR_LO, YEAR_HI = 1990, 2026
CALIB_MAX = 50.0       # K above this %/yr is outside the calibrated range
DOMAIN_MIN_TOTAL = 500  # total distinct patents below this → "insufficient data"
# direction thresholds on the relative K trend over the reported window
ACCEL_PP = 0.15        # +15% relative rise → accelerating
MATURE_PP = -0.15      # -15% → maturing; below -0.45 → decelerating
DECEL_PP = -0.45


def _x_by_year(patterns: list[str]) -> dict[int, tuple[float, int]]:
    """year -> (mean spnp_pctl, n_patents) for patents carrying ANY pattern."""
    like = " OR ".join("pc.cpc LIKE %s" for _ in patterns)
    sql = (
        "SELECT sp.year, AVG(sp.spnp_pctl) x, COUNT(*) n FROM ("
        "  SELECT DISTINCT re.id FROM raw_entries re JOIN patent_cpc pc "
        "    ON pc.pub_number = re.pub_number WHERE (" + like + ")"
        ") p JOIN patent_spnp sp ON sp.raw_id = p.id "
        f"WHERE sp.year BETWEEN {YEAR_LO - WINDOW} AND {YEAR_HI} "
        "GROUP BY sp.year ORDER BY sp.year")
    with get_connection() as c:
        cur = c._conn.cursor()
        cur.execute(sql, tuple(patterns))
        return {r[0]: (float(r[1]) if r[1] is not None else None, int(r[2]))
                for r in cur.fetchall()}


def _k_from_x(x: float) -> float:
    return 100.0 * math.exp(COEF_A + COEF_B * x) * math.exp(SIGMA2 / 2)


def build_points(by_year: dict, now_year: int = YEAR_HI) -> list[dict]:
    """Rolling-window K(t) points with the MIN_N gate + truncation flag (pure)."""
    last_complete = now_year - TRUNC_YEARS
    points = []
    for t in range(YEAR_LO, now_year + 1):
        xs, ns = [], []
        for y in range(t - WINDOW + 1, t + 1):
            v = by_year.get(y)
            if v and v[0] is not None:
                xs.append(v[0]); ns.append(v[1])
        n = sum(ns)
        if len(xs) < WINDOW or n < MIN_N:
            continue
        x = sum(xs) / len(xs)
        points.append({"year": t, "K": round(_k_from_x(x), 1), "n": n,
                       "complete": t <= last_complete})
    return points


def classify(points: list[dict], n_total: int) -> dict:
    """Pure direction/calibration classifier over K(t) points (unit-tested).

    Direction is fit over the RECENT complete window (S-curve phase = current
    trend, not the 20-year net — a field can decline from an early high yet be
    accelerating again now, e.g. CRISPR post-2012). Absolute K is withheld when
    the median is outside the calibrated range (software/AI saturation)."""
    reported = [p for p in points if p["complete"]]
    if n_total < DOMAIN_MIN_TOTAL or len(reported) < 4:
        return {"direction": "insufficient_data", "direction_de": "zu wenig Daten",
                "rel_change": None, "K_latest": None, "K_median": None,
                "calibrated": None,
                "reason": f"total patents {n_total:,} < {DOMAIN_MIN_TOTAL} or "
                          f"< 4 complete windows"}
    recent = reported[-RECENT_YEARS:] if len(reported) >= RECENT_YEARS else reported
    yrs = [p["year"] for p in recent]
    ks_r = [p["K"] for p in recent]
    my = sum(yrs) / len(yrs)
    mk = sum(ks_r) / len(ks_r)
    denom = sum((y - my) ** 2 for y in yrs) or 1.0
    slope = sum((y - my) * (k - mk) for y, k in zip(yrs, ks_r)) / denom
    span = (yrs[-1] - yrs[0]) or 1
    rel = (slope * span) / mk if mk else 0.0
    if rel >= ACCEL_PP:
        direction, de = "accelerating", "beschleunigt"
    elif rel <= DECEL_PP:
        direction, de = "decelerating", "verlangsamt sich"
    elif rel <= MATURE_PP:
        direction, de = "maturing", "reift"
    else:
        direction, de = "steady", "stetig"
    ks = [p["K"] for p in reported]
    med_k = sorted(ks)[len(ks) // 2]
    calibrated = med_k <= CALIB_MAX
    return {"direction": direction, "direction_de": de, "rel_change": round(rel, 3),
            "K_latest": reported[-1]["K"] if calibrated else None,
            "K_median": round(med_k, 1), "calibrated": calibrated,
            "reason": None if calibrated else
                      f"median K {med_k:.0f}%/yr > {CALIB_MAX:.0f}% — outside "
                      "calibrated range; direction only"}


def trajectory(patterns: list[str], now_year: int = YEAR_HI) -> dict:
    by_year = _x_by_year(patterns)
    total = sum(n for _, n in by_year.values())
    points = build_points(by_year, now_year)
    res = classify(points, total)
    res.update({"patterns": patterns, "n_total": total, "points": points})
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="Fine-grained TIR trajectory K(t) (#36)")
    ap.add_argument("--like", nargs="+", required=True, help="CPC LIKE patterns")
    ap.add_argument("--name", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = trajectory(args.like)
    res["name"] = args.name
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    name = args.name or " ∪ ".join(args.like)
    print(f"\n{name}  (patterns: {', '.join(args.like)})")
    print(f"  patents: {res['n_total']:,}")
    if res["direction"] == "insufficient_data":
        print(f"  → zu wenig Daten ({res['reason']})")
        return 0
    for p in res["points"][::3]:
        flag = "" if p["complete"] else "  (unvollständig)"
        print(f"    {p['year']}: K={p['K']:>5}%/yr  n={p['n']:>6,}{flag}")
    kv = f"{res['K_latest']}%/yr" if res["calibrated"] else "n/a (außer Kalibrierung)"
    print(f"  → Richtung: {res['direction_de']}  (rel. Δ {res['rel_change']:+.0%}); "
          f"aktueller TIR: {kv}")
    if res["reason"]:
        print(f"    Hinweis: {res['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
