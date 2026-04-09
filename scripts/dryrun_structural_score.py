"""Dry-run: derive a 'structural vs. hype' indicator per mega-trend from signal
timing only. No hardcoded horizons.

Method
------
For each mega-trend we build a monthly signal-count time series from
raw_entries.published_date (only published trends). From that series we derive:

  span_months    = months between first and last signal
  active_months  = number of distinct months with >=1 signal
  coverage       = active_months / max(span_months, 1)        # 0..1
  entropy_norm   = H(monthly_shares) / log(active_months)      # 0..1
  post_peak_hl   = half-life of the post-peak decay (months), computed by
                   fitting a linear regression on log(monthly_count + 0.5)
                   for months from the peak month onwards. If the trend is
                   still rising or flat after the peak, half-life is infinite
                   and the trend is structurally sustained.

Structural score (0..1, higher = more structural, lower = more hype-like):

  structural = 0.5 * coverage + 0.5 * entropy_norm

Interpretation hint
-------------------
- high structural (>=0.7)  → broad, persistent signal over time → treat as
  true mega-trend
- mid (0.4 .. 0.7)         → in transition, possibly accelerating
- low (<0.4)               → concentrated in time → likely hype or one-off
  news burst; still a business opportunity, but not a structural shift
"""
from __future__ import annotations

import math
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

import numpy as np

DB = Path("data/catandary.db")


def load_signals():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT t.mega_trend, r.published_date
        FROM trends t
        JOIN raw_entries r ON t.raw_entry_id = r.id
        WHERE t.status = 'published'
          AND t.mega_trend IS NOT NULL
          AND r.published_date IS NOT NULL
    """).fetchall()
    conn.close()
    return rows


def month_key(dt_str: str) -> str | None:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None
    return f"{dt.year:04d}-{dt.month:02d}"


def analyze(mt: str, months: list[str]) -> dict:
    counts = Counter(months)
    if not counts:
        return {}
    # Sort months chronologically
    all_months = sorted(counts.keys())
    # Fill gaps between first and last month
    first = datetime.strptime(all_months[0], "%Y-%m")
    last = datetime.strptime(all_months[-1], "%Y-%m")
    full_series: list[tuple[str, int]] = []
    cur = first
    while cur <= last:
        key = f"{cur.year:04d}-{cur.month:02d}"
        full_series.append((key, counts.get(key, 0)))
        # next month
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    span_months = len(full_series)
    active_months = sum(1 for _, c in full_series if c > 0)
    total = sum(c for _, c in full_series)
    coverage = active_months / max(span_months, 1)

    # Entropy on active-month shares
    if active_months > 1:
        shares = np.array([c for _, c in full_series if c > 0], dtype=float)
        shares /= shares.sum()
        entropy = -(shares * np.log(shares)).sum()
        entropy_norm = entropy / math.log(active_months)
    else:
        entropy_norm = 0.0

    # Post-peak half-life
    counts_arr = np.array([c for _, c in full_series], dtype=float)
    peak_idx = int(counts_arr.argmax())
    post = counts_arr[peak_idx:]
    half_life: float | None = None
    if len(post) >= 3 and post.max() > 0:
        x = np.arange(len(post), dtype=float)
        y = np.log(post + 0.5)
        # Linear regression slope
        slope, _ = np.polyfit(x, y, 1)
        if slope < -1e-6:
            half_life = float(math.log(2) / (-slope))
        else:
            half_life = math.inf  # still rising or flat
    months_since_peak = len(post) - 1

    structural = 0.5 * coverage + 0.5 * entropy_norm

    return {
        "mega_trend": mt,
        "total": total,
        "span_months": span_months,
        "active_months": active_months,
        "coverage": round(coverage, 3),
        "entropy_norm": round(entropy_norm, 3),
        "half_life_months": (
            "inf" if half_life == math.inf else
            (round(half_life, 1) if half_life is not None else "n/a")
        ),
        "months_since_peak": months_since_peak,
        "structural_score": round(structural, 3),
    }


def main():
    rows = load_signals()
    grouped: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        mk = month_key(r["published_date"])
        if mk:
            grouped[r["mega_trend"]].append(mk)

    results = [analyze(mt, months) for mt, months in grouped.items()]
    results = [r for r in results if r]
    results.sort(key=lambda r: r["structural_score"], reverse=True)

    print(f"{'mega_trend':<55} {'n':>5} {'span':>5} {'act':>4} "
          f"{'cov':>6} {'H':>6} {'hl_m':>7} {'d_peak':>6} {'score':>6}  label")
    print("-" * 120)
    for r in results:
        score = r["structural_score"]
        if score >= 0.70:
            label = "STRUCTURAL"
        elif score >= 0.40:
            label = "transitional"
        else:
            label = "hype / burst"
        print(
            f"{r['mega_trend']:<55} "
            f"{r['total']:>5} "
            f"{r['span_months']:>5} "
            f"{r['active_months']:>4} "
            f"{r['coverage']:>6.2f} "
            f"{r['entropy_norm']:>6.2f} "
            f"{str(r['half_life_months']):>7} "
            f"{r['months_since_peak']:>6} "
            f"{score:>6.2f}  {label}"
        )

    print()
    print("Legend:")
    print("  n      = total signals       span  = months first→last")
    print("  act    = months with >=1 signal   cov = active/span")
    print("  H      = normalized entropy of monthly shares (1=uniform, 0=spike)")
    print("  hl_m   = half-life (months) of post-peak exponential decay; inf = still rising/flat")
    print("  d_peak  = months since peak")
    print("  score  = 0.5*cov + 0.5*H    STRUCTURAL>=0.70   transitional>=0.40   else hype")


if __name__ == "__main__":
    main()
