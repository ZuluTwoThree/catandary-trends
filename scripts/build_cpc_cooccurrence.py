#!/usr/bin/env python3
"""Build the CPC co-occurrence layer (issue #28) — the EMPIRICAL technology axis.

Patents carry ~5.3 CPC codes on average; two subclasses appearing on the SAME
patent is expert-assigned evidence that those technology fields belong together
(H01M+B60L = EV batteries, H01M+A61B = medical implants …). Aggregated over the
18.7M-patent back-file, per year, this gives:

  • sharper technology axes than any single CPC (the combination IS the tech)
  • an empirical relatedness graph complementing the semantic backbone (#28)
  • convergence detection: pairs whose co-occurrence RISES = emerging
    cross-domain fronts (early indicator)

One row per (cpc_a, cpc_b, year): subclass-level (4-char), a < b, year from the
patent's publication date. Pure SQL over patent_cpc (131M rows) — GPU-free.

    python scripts/build_cpc_cooccurrence.py            # build/refresh
    python scripts/build_cpc_cooccurrence.py --top H01M # show top partners
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection

BUILD_SQL = """
DROP TABLE IF EXISTS cpc_cooccurrence;
CREATE TABLE cpc_cooccurrence AS
WITH pc AS (
    SELECT DISTINCT pub_number, substr(cpc, 1, 4) AS sub
    FROM patent_cpc
),
yrs AS (
    SELECT pub_number, substr(published_date::text, 1, 4)::int AS year
    FROM raw_entries
    WHERE pub_number IS NOT NULL AND published_date IS NOT NULL
)
SELECT a.sub AS cpc_a, b.sub AS cpc_b, y.year, COUNT(*)::int AS n
FROM pc a
JOIN pc b  ON b.pub_number = a.pub_number AND a.sub < b.sub
JOIN yrs y ON y.pub_number = a.pub_number
WHERE y.year BETWEEN 1980 AND 2026
GROUP BY a.sub, b.sub, y.year;
CREATE INDEX idx_cpccoocc_a ON cpc_cooccurrence (cpc_a, year);
CREATE INDEX idx_cpccoocc_b ON cpc_cooccurrence (cpc_b, year);
"""


def build() -> None:
    t0 = time.time()
    with get_connection() as conn:
        cur = conn._conn.cursor()
        cur.execute("SET LOCAL work_mem = '1GB'")
        for stmt in BUILD_SQL.split(";"):
            if stmt.strip():
                cur.execute(stmt)
        conn._conn.commit()
        cur.execute("SELECT COUNT(*), SUM(n) FROM cpc_cooccurrence")
        rows, pairs = cur.fetchone()
    print(f"cpc_cooccurrence built in {time.time()-t0:.0f}s: "
          f"{rows:,} (a,b,year) rows | {pairs:,} co-occurrence pairs")


def show_top(sub: str, limit: int = 12) -> None:
    with get_connection() as c:
        rows = c.execute(
            "SELECT CASE WHEN cpc_a = ? THEN cpc_b ELSE cpc_a END AS partner, "
            "       SUM(n) AS total, "
            "       SUM(n) FILTER (WHERE year >= 2020) AS recent, "
            "       SUM(n) FILTER (WHERE year < 2015) AS early "
            "FROM cpc_cooccurrence WHERE cpc_a = ? OR cpc_b = ? "
            "GROUP BY partner ORDER BY total DESC LIMIT ?",
            (sub, sub, sub, limit)).fetchall()
        print(f"\nTop-Partner von {sub} (empirische Technologie-Achsen):")
        for r in rows:
            p = r["partner"] if isinstance(r, dict) else r[0]
            tot = r["total"] if isinstance(r, dict) else r[1]
            rec = (r["recent"] if isinstance(r, dict) else r[2]) or 0
            ear = (r["early"] if isinstance(r, dict) else r[3]) or 0
            trend = "↑" if rec > 2 * max(ear, 1) else ("↓" if ear > 2 * max(rec, 1) else "→")
            t = c.execute("SELECT title FROM cpc_definitions WHERE symbol = ?", (p,)).fetchone()
            title = ((t["title"] if isinstance(t, dict) else t[0]) if t else "")[:52]
            print(f"  {sub}+{p}  n={tot:>8,}  {trend}  {title}")


def main() -> int:
    ap = argparse.ArgumentParser(description="CPC co-occurrence layer (#28)")
    ap.add_argument("--top", help="show top co-occurring partners for a subclass (e.g. H01M)")
    ap.add_argument("--skip-build", action="store_true", help="query only, no rebuild")
    args = ap.parse_args()
    if not USE_POSTGRES:
        print("co-occurrence layer targets Postgres"); return 1
    if not args.skip_build:
        build()
    if args.top:
        show_top(args.top.upper())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
