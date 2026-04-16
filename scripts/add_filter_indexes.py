"""Add supporting indexes for Phase 2 trends filter/sort queries.

Creates indexes used by `frontend/src/lib/db.ts::getTrendsFiltered()` so the
composite filter query stays sub-100ms on the current ~8.7k published trends:

    idx_trends_signal_type   — signal-type chip filter
    idx_trends_mega_trend    — mega-trend chip filter
    idx_trends_trend_score   — min_score slider + score_desc sort
    idx_trends_source_name   — exclude-sources multi-select

The `status`, `primary_vertical`, and `raw_entry_id` columns are already
covered by existing indexes (see schema migrations); we don't duplicate them.

Idempotent via IF NOT EXISTS — safe to re-run.

Usage:
    python scripts/add_filter_indexes.py
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.config import DATABASE_PATH


INDEXES = [
    ("idx_trends_signal_type", "CREATE INDEX IF NOT EXISTS idx_trends_signal_type ON trends(trend_signal_type)"),
    ("idx_trends_mega_trend",  "CREATE INDEX IF NOT EXISTS idx_trends_mega_trend ON trends(mega_trend)"),
    ("idx_trends_trend_score", "CREATE INDEX IF NOT EXISTS idx_trends_trend_score ON trends(trend_score)"),
    ("idx_trends_source_name", "CREATE INDEX IF NOT EXISTS idx_trends_source_name ON trends(source_name)"),
]


def main():
    db = sqlite3.connect(DATABASE_PATH)
    db.execute("PRAGMA journal_mode=WAL")

    for name, ddl in INDEXES:
        db.execute(ddl)
        print(f"[ok] {name}")

    # ANALYZE so the planner picks up the new indexes
    db.execute("ANALYZE trends")

    db.commit()

    # Sanity: list trend indexes currently present
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='trends' ORDER BY name"
    ).fetchall()
    print(f"\nIndexes on trends: {[r[0] for r in rows]}")

    db.close()
    print("Done.")


if __name__ == "__main__":
    main()
