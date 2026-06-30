#!/usr/bin/env python3
"""Idempotent sweep: reject + filter any sponsored/advertorial entries.

Uses the shipped is_advertorial() guard (pipeline.llm_processor) as the single
source of truth, so it stays consistent with the live pipeline filter. Safe to
re-run any time — e.g. after a pipeline run that was started before the guard
shipped (old-code processes can re-create advertorial signals mid-run).

Effect: trends tied to an advertorial raw_entry -> status='rejected' (removed
from the public grid AND the signal/foresight pool); the raw_entry ->
processed=1, filtered_out=1, filter_reason='sponsored/advertorial'.

    python scripts/sweep_advertorials.py            # apply
    python scripts/sweep_advertorials.py --dry-run  # report only
"""
from __future__ import annotations
import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import DATABASE_PATH
from pipeline.llm_processor import is_advertorial

# Broad SQL prefilter (cheap), then the exact guard decides — keeps us aligned
# with the live filter and avoids scanning every row.
PREFIXES = ["Sponsored%", "Advertorial%", "Paid Post%", "Partner Content%", "Anzeige%"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    c = sqlite3.connect(DATABASE_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=30000")
    like = " OR ".join(["title LIKE ?"] * len(PREFIXES))
    cand = c.execute(f"SELECT id, title FROM raw_entries WHERE {like}", PREFIXES).fetchall()
    ids = [r["id"] for r in cand if is_advertorial(r["title"] or "")]
    print(f"candidates {len(cand)} | confirmed advertorial {len(ids)}")
    if not ids:
        return 0
    qm = ",".join("?" * len(ids))
    live = c.execute(f"""SELECT COUNT(*) FROM trends WHERE raw_entry_id IN ({qm})
                         AND status IN ('published','signal','draft','review')""", ids).fetchone()[0]
    unfiltered = c.execute(f"SELECT COUNT(*) FROM raw_entries WHERE id IN ({qm}) AND filtered_out=0", ids).fetchone()[0]
    print(f"  trends still live: {live} | raw_entries not yet filtered: {unfiltered}")
    if args.dry_run:
        print("DRY-RUN — nothing changed.")
        return 0

    def retry(sql, p, t=8):
        for i in range(t):
            try:
                return c.execute(sql, p)
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and i < t - 1:
                    time.sleep(1.0 * (i + 1)); continue
                raise

    retry(f"UPDATE trends SET status='rejected' WHERE raw_entry_id IN ({qm}) AND status!='rejected'", ids)
    tr = c.total_changes
    retry(f"""UPDATE raw_entries SET processed=1, filtered_out=1,
              filter_reason='sponsored/advertorial' WHERE id IN ({qm}) AND filtered_out=0""", ids)
    c.commit()
    after = c.execute(f"""SELECT COUNT(*) FROM trends WHERE raw_entry_id IN ({qm})
                          AND status IN ('published','signal','draft','review')""", ids).fetchone()[0]
    print(f"rejected trends: {tr} | advertorials still live after sweep (should be 0): {after}")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
