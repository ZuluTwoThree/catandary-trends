#!/usr/bin/env python3
"""Additive migration: startup_press_rounds.investors_enriched_at (#94 Teil 2).

The LLM investor-enrichment pass (`extract_press_rounds.py --mode investors`)
needs an idempotency marker so it never re-runs the 8B over a row it already
processed — the same "stamped once, checked, never redone" pattern as
trends.judged_at (pipeline.draft_judge, see judged_at-Memory): an errored row
(res is None) is deliberately left UNSTAMPED so it retries on the next pass,
but a row the model successfully looked at — even with an empty investors
result — is done for good.

    python -m scripts.migrate_press_investor_enrichment            # apply
    python -m scripts.migrate_press_investor_enrichment --check    # report only

NB: additive migrations are NOT run automatically (not in ensure_table(), not
in init_db()) — this must be executed manually against the live database, the
same gap that broke the Stripe webhook on 2026-07-19 (prod-db-migration-gap
memory). Per the #94-Teil-2 task instructions this script is prepared but NOT
executed against the production database in this session — only read-only
SELECTs were used to size the candidate pool.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("migrate_press_investor_enrichment")

TABLE = "startup_press_rounds"
COLUMN = "investors_enriched_at"


def column_exists() -> bool:
    with get_connection() as conn:
        if db_mod.USE_POSTGRES:
            row = conn.execute(
                "SELECT 1 FROM information_schema.columns "
                " WHERE table_name = ? AND column_name = ?",
                (TABLE, COLUMN),
            ).fetchone()
            return row is not None
        rows = conn.execute(f"PRAGMA table_info({TABLE})").fetchall()
        names = [(r["name"] if hasattr(r, "keys") else r[1]) for r in rows]
        return COLUMN in names


def migrate() -> None:
    if column_exists():
        logger.info("%s.%s already present — nothing to do", TABLE, COLUMN)
        return
    with get_connection() as conn:
        conn.execute(
            f"ALTER TABLE {TABLE} ADD COLUMN "
            + ("IF NOT EXISTS " if db_mod.USE_POSTGRES else "")
            + f"{COLUMN} TIMESTAMP"
        )
    logger.info("added %s.%s", TABLE, COLUMN)


def report() -> None:
    if not column_exists():
        logger.info("%s.%s not present yet", TABLE, COLUMN)
        return
    with get_connection() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS total,"
            f"       COUNT(*) FILTER (WHERE {COLUMN} IS NOT NULL) AS enriched,"
            f"       COUNT(*) FILTER (WHERE {COLUMN} IS NULL AND investors = '[]'"
            f"                        AND company IS NOT NULL"
            f"                        AND coalesce(round_label, '') != 'vc_fund') AS eligible"
            f"  FROM {TABLE}"
        ).fetchone()
    r = dict(row) if hasattr(row, "keys") else {
        "total": row[0], "enriched": row[1], "eligible": row[2]}
    logger.info("rows=%s already enriched=%s still eligible=%s",
                r["total"], r["enriched"], r["eligible"])


def main() -> int:
    ap = argparse.ArgumentParser(description=f"Add {TABLE}.{COLUMN}")
    ap.add_argument("--check", action="store_true", help="report only, do not alter")
    args = ap.parse_args()
    if args.check:
        logger.info("column present: %s", column_exists())
        report()
        return 0
    migrate()
    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
