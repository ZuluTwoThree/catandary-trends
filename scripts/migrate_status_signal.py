#!/usr/bin/env python3
"""Migrate the live trends.status CHECK constraint to allow 'signal'.

SQLite cannot ALTER a CHECK constraint; rebuilding a 1.5 GB / 41k-row table with
its indexes is risky. Instead this edits the stored CREATE TABLE sql in place via
PRAGMA writable_schema (minimal-touch, no data movement), then verifies integrity
and that a 'signal' row now inserts. Idempotent and safe to re-run.

Usage:
    python scripts/migrate_status_signal.py            # migrate data/catandary.db
    python scripts/migrate_status_signal.py --db path  # other DB
"""
from __future__ import annotations
import argparse
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import DATABASE_PATH

OLD = "'published', 'rejected')"
NEW = "'published', 'rejected', 'signal')"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DATABASE_PATH)
    args = ap.parse_args()
    db = args.db

    conn = sqlite3.connect(db)
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='trends' AND type='table'").fetchone()[0]

    if "'signal'" in sql:
        print("Already migrated — trends.status CHECK includes 'signal'. No-op.")
        conn.close()
        return 0
    if OLD not in sql:
        print(f"ERROR: expected CHECK fragment {OLD!r} not found in trends schema; aborting.")
        conn.close()
        return 1

    new_sql = sql.replace(OLD, NEW)
    print("Applying writable_schema CHECK edit ...")
    conn.execute("PRAGMA writable_schema=ON")
    conn.execute("UPDATE sqlite_master SET sql=? WHERE name='trends' AND type='table'", (new_sql,))
    conn.execute("PRAGMA writable_schema=OFF")
    conn.commit()
    conn.close()

    # Reopen to reload the schema, verify integrity + a real 'signal' insert.
    conn = sqlite3.connect(db)
    integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"integrity_check: {integ}")
    if integ != "ok":
        print("ERROR: integrity check failed — restore from backup.")
        conn.close()
        return 1
    try:
        conn.execute("BEGIN")
        conn.execute(
            "INSERT INTO trends (title_en, slug, source_url, status) VALUES (?,?,?,?)",
            ("__migration_probe__", "__migration_probe__", "test://probe", "signal"))
        conn.execute("ROLLBACK")
        print("Verified: a status='signal' row now inserts (rolled back).")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"ERROR: 'signal' insert still rejected: {e}")
        conn.close()
        return 1
    conn.close()
    print("Migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
