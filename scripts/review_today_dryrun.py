"""Dry-run of the mega-trend reviewer limited to trends published today.

Reuses pipeline.mega_trend_reviewer.review_batch with dry_run=True so no DB
writes happen. Groups today's published trends by primary_vertical and runs
one batched review per vertical.
"""
from __future__ import annotations

import sys
import time
from datetime import date

from pipeline.config import get_mega_trend_prompt_block
from pipeline.db import get_connection
from pipeline.mega_trend_reviewer import (
    BATCH_SIZE,
    REVIEW_SYSTEM,
    review_batch,
)


def load_todays_trends() -> list[dict]:
    today = date.today().isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title_en, summary_en, mega_trend, tags, primary_vertical
            FROM trends
            WHERE status = 'published'
              AND DATE(COALESCE(published_at, created_at)) = ?
            ORDER BY primary_vertical, id
            """,
            (today,),
        ).fetchall()
    return [dict(r) for r in rows]


def main():
    trends = load_todays_trends()
    if not trends:
        print("No trends published today.")
        return

    print(f"Found {len(trends)} trends published today ({date.today().isoformat()})")
    by_vertical: dict[str, list[dict]] = {}
    for t in trends:
        by_vertical.setdefault(t["primary_vertical"], []).append(t)

    for v, rows in sorted(by_vertical.items()):
        print(f"  {v}: {len(rows)}")

    system_prompt = REVIEW_SYSTEM.format(mega_trend_block=get_mega_trend_prompt_block())

    t0 = time.time()
    grand_reviewed = 0
    grand_would_update = 0

    for vertical, rows in sorted(by_vertical.items()):
        print(f"\n=== {vertical} ({len(rows)} trends) ===")
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            stats = review_batch(batch, system_prompt, dry_run=True)
            grand_reviewed += stats["reviewed"]
            grand_would_update += stats["updated"]

    print(
        f"\nDRY RUN COMPLETE in {time.time()-t0:.1f}s: "
        f"{grand_reviewed} reviewed, {grand_would_update} would be updated."
    )


if __name__ == "__main__":
    main()
