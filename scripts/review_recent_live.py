"""Live mega-trend reviewer for trends published yesterday and today.

Runs pipeline.mega_trend_reviewer.review_batch with dry_run=False so updates
are written to the DB. Groups by primary_vertical and batches per BATCH_SIZE.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

from pipeline.config import get_mega_trend_prompt_block
from pipeline.db import get_connection
from pipeline.mega_trend_reviewer import BATCH_SIZE, REVIEW_SYSTEM, review_batch


def load_recent_trends() -> list[dict]:
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title_en, summary_en, mega_trend, tags, primary_vertical
            FROM trends
            WHERE status = 'published'
              AND DATE(COALESCE(published_at, created_at)) IN (?, ?)
            ORDER BY primary_vertical, id
            """,
            (today, yesterday),
        ).fetchall()
    return [dict(r) for r in rows]


def main():
    trends = load_recent_trends()
    if not trends:
        print("No trends to review.")
        return

    print(f"Reviewing {len(trends)} trends published yesterday + today")
    by_vertical: dict[str, list[dict]] = {}
    for t in trends:
        by_vertical.setdefault(t["primary_vertical"], []).append(t)
    for v, rows in sorted(by_vertical.items()):
        print(f"  {v}: {len(rows)}")

    system_prompt = REVIEW_SYSTEM.format(mega_trend_block=get_mega_trend_prompt_block())

    t0 = time.time()
    grand_reviewed = 0
    grand_updated = 0

    for vertical, rows in sorted(by_vertical.items()):
        print(f"\n=== {vertical} ({len(rows)}) ===")
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            stats = review_batch(batch, system_prompt, dry_run=False)
            grand_reviewed += stats["reviewed"]
            grand_updated += stats["updated"]

    print(
        f"\nLIVE REVIEW COMPLETE in {time.time()-t0:.1f}s: "
        f"{grand_reviewed} reviewed, {grand_updated} updated."
    )


if __name__ == "__main__":
    main()
