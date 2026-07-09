#!/usr/bin/env python3
"""Field-normalized forward velocity for OpenAlex works (#9).

Citation *rates* differ ~10× between fields, so raw cited_by_count is useless
as a cross-field "hot research" signal. This computes, per work:

  velocity_3y    mean citations/year over the last 3 FULL years — the forward
                 velocity OpenAlex delivers natively via counts_by_year. Chosen
                 over a lifetime percentile because counts_by_year is windowed
                 (~15y) and carries no publication year, so recency-velocity is
                 the one indicator we can compute correctly for 100% of works.
  velocity_pctl  percent-rank of velocity_3y within the work's PRIMARY subfield
                 (the #9 field normalization). Retracted works are excluded
                 from the cohort and get no percentile (negative signal).

Both stored as columns on openalex_meta; ~180k works, pure SQL, seconds.

    python scripts/openalex_velocity.py            # compute/refresh
    python scripts/openalex_velocity.py --report   # top research fronts
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection


def migrate() -> None:
    with get_connection() as conn:
        for col, typ in (("velocity_3y", "REAL"), ("velocity_pctl", "REAL")):
            try:
                conn.execute(f"ALTER TABLE openalex_meta ADD COLUMN {col} {typ}")
            except Exception:
                pass  # column exists


def compute() -> None:
    y = datetime.now(timezone.utc).year
    y0, y1 = y - 3, y - 1  # last 3 FULL years
    t0 = time.time()
    with get_connection() as conn:
        # forward velocity from the native counts_by_year payload
        conn.execute(
            "UPDATE openalex_meta m SET velocity_3y = sub.v FROM ("
            "  SELECT work_id, COALESCE(SUM((e->>'cited_by_count')::int) "
            f"    FILTER (WHERE (e->>'year')::int BETWEEN {y0} AND {y1}), 0) / 3.0 AS v "
            "  FROM openalex_meta, LATERAL jsonb_array_elements("
            "    CASE WHEN counts_by_year IS NULL OR counts_by_year IN ('', '[]') "
            "         THEN '[{}]'::jsonb ELSE counts_by_year::jsonb END) e "
            "  GROUP BY work_id) sub "
            "WHERE sub.work_id = m.work_id")
        # field-normalized percentile within the primary subfield; retracted
        # works are excluded from the cohort AND get no percentile
        conn.execute("UPDATE openalex_meta SET velocity_pctl = NULL")
        conn.execute(
            "UPDATE openalex_meta m SET velocity_pctl = p.pr FROM ("
            "  SELECT m2.work_id, percent_rank() OVER ("
            "    PARTITION BY t.subfield ORDER BY m2.velocity_3y) AS pr "
            "  FROM openalex_meta m2 "
            "  JOIN openalex_topics t ON t.work_id = m2.work_id AND t.is_primary = 1 "
            "  WHERE m2.is_retracted = 0 AND m2.velocity_3y IS NOT NULL "
            "    AND t.subfield IS NOT NULL) p "
            "WHERE p.work_id = m.work_id")
    with get_connection() as conn:
        r = conn.execute(
            "SELECT COUNT(*) AS total, COUNT(velocity_3y) AS with_v, "
            "COUNT(velocity_pctl) AS with_p FROM openalex_meta").fetchone()
    d = dict(r)
    print(f"velocity computed in {time.time() - t0:.0f}s: "
          f"{d['with_v']:,}/{d['total']:,} with velocity, {d['with_p']:,} with percentile "
          f"(window {y0}-{y1})")


def report(top: int = 12) -> None:
    """Research fronts: subfields with the most works in their global top decile."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT t.subfield, COUNT(*) AS works, "
            "       COUNT(*) FILTER (WHERE m.velocity_pctl >= 0.9) AS hot, "
            "       MAX(m.velocity_3y) AS max_v "
            "FROM openalex_meta m JOIN openalex_topics t "
            "  ON t.work_id = m.work_id AND t.is_primary = 1 "
            "WHERE m.velocity_pctl IS NOT NULL "
            "GROUP BY t.subfield HAVING COUNT(*) >= 100 "
            f"ORDER BY COUNT(*) FILTER (WHERE m.velocity_pctl >= 0.9)::float / COUNT(*) DESC "
            f"LIMIT {int(top)}").fetchall()
    print(f"{'subfield':48s} {'works':>7s} {'top-decile':>10s} {'max v/yr':>9s}")
    for r in rows:
        d = dict(r)
        print(f"{(d['subfield'] or '?')[:47]:48s} {d['works']:>7,} "
              f"{d['hot']:>10,} {d['max_v']:>9,.0f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Field-normalized OpenAlex velocity (#9)")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if not USE_POSTGRES:
        print("targets Postgres")
        return 1
    migrate()
    if args.report:
        report()
        return 0
    compute()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
