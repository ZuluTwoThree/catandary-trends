#!/usr/bin/env python3
"""Retire drafts that have aged out of the public window (Owner 2026-09-25).

A draft older than the archive window can never be published into the feed
the public sees (the window filters on sort_date), Stage 8 no longer touches
it (reclassified_at) and the judge stamps it once (judged_at) — it only
inflates the draft count, which should mean "open work". This pass sets such
drafts to `rejected` with review_reason 'expired:window' — nothing is deleted,
`reviewed_at` stays NULL (this is not a human decision), and a row a person
already decided on (reviewed_at set) is never touched.

    python scripts/expire_old_drafts.py              # dry-run: counts
    python scripts/expire_old_drafts.py --apply      # write, batched

Batched commits (default 1000 rows) — never one big UPDATE on `trends`
(HNSW bloat, 2026-09-17).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import DATA_DIR
from pipeline.db import get_connection

REASON = "expired:window"


def main() -> int:
    ap = argparse.ArgumentParser(description="Retire drafts older than the public window")
    ap.add_argument("--days", type=int, default=30, help="window in days (PUBLIC_WINDOW_DAYS, default 30)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", type=int, default=1000)
    args = ap.parse_args()

    t0 = time.time()
    where = ("status = 'draft' AND reviewed_at IS NULL AND sort_date IS NOT NULL "
             "AND sort_date < CURRENT_TIMESTAMP - make_interval(days => ?)")
    with get_connection() as conn:
        rows = conn.execute(f"SELECT id FROM trends WHERE {where} ORDER BY id", (args.days,)).fetchall()
        ids = [r["id"] if isinstance(r, dict) else r[0] for r in rows]
        oldest = conn.execute(f"SELECT MIN(sort_date)::text AS m FROM trends WHERE {where}", (args.days,)).fetchall()
        oldest = (oldest[0]["m"] if isinstance(oldest[0], dict) else oldest[0][0]) if oldest else None
        summary = {"generated": datetime.now(timezone.utc).isoformat(), "days": args.days,
                   "candidates": len(ids), "oldest_sort_date": oldest, "apply": args.apply}
        print(json.dumps(summary))
        if args.apply and ids:
            written = 0
            for start in range(0, len(ids), args.batch):
                chunk = ids[start:start + args.batch]
                conn.execute(
                    "UPDATE trends SET status = 'rejected', review_reason = ? "
                    "WHERE id = ANY(?) AND status = 'draft' AND reviewed_at IS NULL",
                    (REASON, chunk))
                conn.commit()
                written += len(chunk)
                print(f"  {written}/{len(ids)}", flush=True)
            summary["rows_written"] = written
    summary["seconds"] = round(time.time() - t0, 1)
    try:
        (DATA_DIR / "expire_old_drafts_last.json").write_text(json.dumps(summary, indent=1))
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
