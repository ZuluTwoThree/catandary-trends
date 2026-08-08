"""Measured mega-trend momentum — the Python mirror of
frontend/src/lib/momentum.ts (keep thresholds in sync).

Replaces the hand-typed ``momentum:`` field in mega_trends.yaml as a data
source: on 2026-08-08, 19 of 26 yaml claims contradicted the measurement, and
both the /trends/mega badges and the newsletter editorial prompt were built on
them. Measurement: the key's share of published signals in the last
``window_days`` vs the ``window_days`` before — shares, not raw counts, so a
growing corpus never masquerades as a growing trend (the same normalization the
methodology page promises for cluster momentum).
"""
from __future__ import annotations

from pipeline.db import get_connection

MIN_N = 10        # fewer signals across both windows → None (no claim)
THRESHOLD = 0.15  # relative share change for rising/declining


def classify(recent: int, prior: int, total_recent: int, total_prior: int) -> str | None:
    """'rising' | 'stable' | 'declining' | 'emerging' | None (too thin)."""
    if recent + prior < MIN_N:
        return None
    if total_recent <= 0 or total_prior <= 0:
        return None
    share_recent = recent / total_recent
    share_prior = prior / total_prior
    if share_prior == 0:
        return "emerging"
    change = (share_recent - share_prior) / share_prior
    if change > THRESHOLD:
        return "rising"
    if change < -THRESHOLD:
        return "declining"
    return "stable"


def measure(status: str = "published", window_days: int = 90) -> dict[str, dict]:
    """{mega_key: {momentum, recent, prior, share_recent, share_prior}} for
    every labeled key. One aggregate query, read-only."""
    sql = (
        "SELECT mega_trend, "
        "  count(*) FILTER (WHERE sort_date >= NOW() - (?||' days')::interval) AS recent, "
        "  count(*) FILTER (WHERE sort_date >= NOW() - (?||' days')::interval "
        "                     AND sort_date <  NOW() - (?||' days')::interval) AS prior "
        "FROM trends WHERE mega_trend IS NOT NULL AND status = ? GROUP BY 1")
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(
            sql, (window_days, 2 * window_days, window_days, status)).fetchall()]
    total_recent = sum(r["recent"] for r in rows)
    total_prior = sum(r["prior"] for r in rows)
    out = {}
    for r in rows:
        out[r["mega_trend"]] = {
            "momentum": classify(r["recent"], r["prior"], total_recent, total_prior),
            "recent": r["recent"], "prior": r["prior"],
            "share_recent": r["recent"] / total_recent if total_recent else 0.0,
            "share_prior": r["prior"] / total_prior if total_prior else 0.0,
        }
    return out
