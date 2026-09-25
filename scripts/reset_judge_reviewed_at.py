#!/usr/bin/env python3
"""One-off (2026-09-25): take the human mark off the judge's releases.

Until 2026-09-25 draft_judge.publish_draft stamped `reviewed_at` on machine
releases (auto_published = true). That column means "a person decided"
(owner rule 2026-09-22), so those rows were skipped by
recheck_published_grounding.py, the review agent and any hand correction
guarded by `reviewed_at IS NULL`. This pass clears it on exactly those rows:
auto_published AND status = 'published' AND reviewed_at set. Desk releases
set auto_published = false, hand rejections have status 'rejected' — neither
is touched. Batched commits, never one big UPDATE (HNSW bloat, 2026-09-17).

    python scripts/reset_judge_reviewed_at.py          # dry-run
    python scripts/reset_judge_reviewed_at.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.db import get_connection

WHERE = "auto_published = TRUE AND status = 'published' AND reviewed_at IS NOT NULL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", type=int, default=1000)
    args = ap.parse_args()
    with get_connection() as conn:
        rows = conn.execute(f"SELECT id FROM trends WHERE {WHERE} ORDER BY id").fetchall()
        ids = [r["id"] if isinstance(r, dict) else r[0] for r in rows]
        print(f"judge releases carrying the human mark: {len(ids)}")
        if not args.apply:
            return 0
        done = 0
        for i in range(0, len(ids), args.batch):
            chunk = ids[i:i + args.batch]
            conn.execute(f"UPDATE trends SET reviewed_at = NULL WHERE id = ANY(?) AND {WHERE}", (chunk,))
            conn.commit()
            done += len(chunk)
            print(f"  {done}/{len(ids)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
