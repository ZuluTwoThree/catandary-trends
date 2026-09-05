#!/usr/bin/env python3
"""Corpus statistics for /trends/methodology as a JSON snapshot (static export).

Why: the page's live aggregates (COUNT over trends, a trends×raw_entries×sources
join, MIN/MAX(published_date) over 21M raw_entries) ran into the frontend's 20 s
statement_timeout while six export workers hammered the DB — the first
production export on 2026-09-05 died on exactly that page. The build now
computes the numbers ONCE here (no statement timeout, ~1 min) and hands the file
to `next build` via METHODOLOGY_STATS_FILE; `getMethodologyStats()` in
frontend/src/lib/db.ts reads it when the variable is set. The local owner
instance keeps the live (cached) queries.

    python scripts/methodology_stats.py frontend/.export/methodology_stats.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.db import get_connection  # noqa: E402

# LIKE patterns as parameters: the pipeline connection rewrites `?` to `%s`,
# so a literal `%` inside the SQL would break psycopg2's formatting (#81 lesson).
TIER_PARAMS = ("%NSF%", "%NIH%", "%OpenAIRE%", "%UKRI%", "%RePORTER%",
               "%Gateway to Research%", "%arXiv%", "%rxiv%", "%Preprint%")
TIER_SQL = """
SELECT CASE
         WHEN re.pub_number IS NOT NULL THEN 'patent'
         WHEN s.source_type = 'research' THEN 'science'
         WHEN s.source_type = 'api' AND (s.name LIKE ? OR s.name LIKE ? OR s.name LIKE ?
              OR s.name LIKE ? OR s.name LIKE ? OR s.name LIKE ?) THEN 'funding'
         WHEN s.source_type = 'api' AND (s.name LIKE ? OR s.name LIKE ? OR s.name LIKE ?) THEN 'science'
         ELSE 'market'
       END AS tier, COUNT(*) AS c
FROM trends t JOIN raw_entries re ON t.raw_entry_id = re.id JOIN sources s ON re.source_id = s.id
GROUP BY tier"""


def _one(conn, sql: str):
    """Scalar via alias `c` — the pipeline connection yields dict rows."""
    row = conn.execute(sql).fetchone()
    if row is None:
        return None
    return row["c"] if isinstance(row, dict) or hasattr(row, "keys") else row[0]


def compute() -> dict:
    with get_connection() as conn:
        try:
            conn.execute("SET statement_timeout = 0")
        except Exception:  # SQLite has no statement_timeout
            pass
        analyzed = int(_one(conn, "SELECT COUNT(*) AS c FROM trends") or 0)
        published = int(_one(conn, "SELECT COUNT(*) AS c FROM trends WHERE status = 'published'") or 0)
        sources = int(_one(conn, "SELECT COUNT(*) AS c FROM sources WHERE active = TRUE") or 0)
        mega = int(_one(conn, "SELECT COUNT(DISTINCT mega_trend) AS c FROM trends "
                              "WHERE mega_trend IS NOT NULL AND mega_trend <> ''") or 0)
        tiers = {r["tier"]: int(r["c"]) for r in conn.execute(TIER_SQL, TIER_PARAMS).fetchall()}
        span = conn.execute(
            "SELECT MIN(published_date) AS f, MAX(published_date) AS l FROM raw_entries "
            "WHERE published_date IS NOT NULL AND published_date <= CURRENT_TIMESTAMP").fetchone()

    def ym(v):
        if v is None:
            return None
        s = str(v)
        return s[:7] if len(s) >= 7 else None

    return {
        "analyzed": analyzed,
        "published": published,
        "sources": sources,
        "megaTrends": mega,
        "tierCounts": tiers,
        "dateSpan": {"first": ym(span["f"]) if span else None, "last": ym(span["l"]) if span else None},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    out = Path(argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    stats = compute()
    out.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"methodology stats → {out}: analyzed={stats['analyzed']:,} published={stats['published']:,} "
          f"sources={stats['sources']} span={stats['dateSpan']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
