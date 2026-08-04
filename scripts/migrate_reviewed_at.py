#!/usr/bin/env python3
"""Additive migration: trends.reviewed_at (issue #71).

A human review decision was only half-visible: publishing sets published_at,
but rejecting left no trace at all. That made "what did I get through this
morning?" unanswerable for rejections, and it leaves no audit trail for why an
article never went live.

reviewed_at is set by BOTH decisions in the review UI, so progress and
accountability are measurable regardless of the outcome.

    python -m scripts.migrate_reviewed_at            # apply
    python -m scripts.migrate_reviewed_at --check    # report only

NB: additive migrations are NOT run by init_db() — this must be executed
manually against the live database (the gap that broke the Stripe webhook on
2026-07-19).
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
logger = logging.getLogger("migrate_reviewed_at")


def column_exists() -> bool:
    with get_connection() as conn:
        if db_mod.USE_POSTGRES:
            row = conn.execute(
                "SELECT 1 FROM information_schema.columns "
                " WHERE table_name = 'trends' AND column_name = 'reviewed_at'"
            ).fetchone()
            return row is not None
        rows = conn.execute("PRAGMA table_info(trends)").fetchall()
        names = [(r[1] if not hasattr(r, "keys") else r["name"]) for r in rows]
        return "reviewed_at" in names


def migrate() -> None:
    if column_exists():
        logger.info("trends.reviewed_at already present — nothing to do")
        return
    with get_connection() as conn:
        conn.execute(
            "ALTER TABLE trends ADD COLUMN "
            + ("IF NOT EXISTS " if db_mod.USE_POSTGRES else "")
            + "reviewed_at TIMESTAMP"
        )
    logger.info("added trends.reviewed_at")

    # Back-fill what can be known: manual publishes already carry their time in
    # published_at (auto_published=false is the review UI's signature).
    # Rejections are NOT back-filled — their decision time was never recorded,
    # and inventing one would be worse than leaving it NULL.
    with get_connection() as conn:
        conn.execute(
            "UPDATE trends SET reviewed_at = published_at "
            " WHERE status = 'published' AND auto_published = false "
            "   AND published_at IS NOT NULL AND reviewed_at IS NULL"
        )
    logger.info("back-filled reviewed_at for manually published articles")


def report() -> None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FILTER (WHERE reviewed_at IS NOT NULL) AS reviewed, "
            "       COUNT(*) FILTER (WHERE reviewed_at >= CURRENT_DATE) AS today, "
            "       COUNT(*) FILTER (WHERE status='draft' AND confidence >= 0.85) AS pending "
            "  FROM trends"
        ).fetchone()
    r = dict(row) if hasattr(row, "keys") else {
        "reviewed": row[0], "today": row[1], "pending": row[2]}
    logger.info("reviewed total=%s, today=%s, still pending=%s",
                r["reviewed"], r["today"], r["pending"])


def main() -> int:
    ap = argparse.ArgumentParser(description="Add trends.reviewed_at")
    ap.add_argument("--check", action="store_true", help="report only, do not alter")
    args = ap.parse_args()
    if args.check:
        logger.info("column present: %s", column_exists())
        if column_exists():
            report()
        return 0
    migrate()
    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
