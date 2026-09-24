#!/usr/bin/env python3
"""Story grouping post-pass (#109): find published articles that report the
same event and record the groups in `trend_stories`.

Rule (pipeline/stories.py): same extracted brand · sort_date within 48 h ·
cosine >= 0.80 on embedding_1024, groups closed transitively. The oldest
article leads. Nothing is filtered, unpublished or rewritten — Stage 1 only
measures and shows ("also reported by" on the article page).

    python scripts/group_stories.py                  # dry-run over the last 3 days
    python scripts/group_stories.py --days 30        # measure a month
    python scripts/group_stories.py --days 3 --apply # write trend_stories (cron)

The window is re-derived on every run, so `--apply` is idempotent; the story
id is the lead's trend id. Meant to run daily before the static export
(deploy/crontab.txt), CPU only, seconds.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import stories as st
from pipeline.config import DATA_DIR
from pipeline.db import get_connection


def main() -> int:
    ap = argparse.ArgumentParser(description="Story grouping post-pass (#109)")
    ap.add_argument("--days", type=float, default=3.0,
                    help="window of published sort_dates to (re)group, ending now (default 3)")
    ap.add_argument("--since", help="explicit window start (ISO), overrides --days")
    ap.add_argument("--until", help="explicit window end (ISO)")
    ap.add_argument("--hours", type=float, default=st.STORY_WINDOW_HOURS)
    ap.add_argument("--min-sim", type=float, default=st.STORY_MIN_SIMILARITY)
    ap.add_argument("--apply", action="store_true", help="write trend_stories (default: dry-run)")
    ap.add_argument("--show", type=int, default=5, help="print the N largest groups with titles")
    args = ap.parse_args()

    now = datetime.now()
    since = datetime.fromisoformat(args.since) if args.since else now - timedelta(days=args.days)
    until = datetime.fromisoformat(args.until) if args.until else None
    t0 = time.time()
    with get_connection() as conn:
        arts = st.load_window(conn, since, until)
        groups = st.group_stories(arts, window_hours=args.hours, min_similarity=args.min_sim)
        summary = st.summarize(groups, len(arts))
        summary.update({"since": since.isoformat(timespec="minutes"),
                        "until": until.isoformat(timespec="minutes") if until else None,
                        "hours": args.hours, "min_sim": args.min_sim, "apply": args.apply})
        by_id = {a.id: a for a in arts}
        print(json.dumps({k: v for k, v in summary.items() if k != "largest"}, ensure_ascii=False))
        for g in sorted(groups, key=lambda s: -len(s.member_ids))[:args.show]:
            print(f"\n[{g.brand_key}] {len(g.member_ids)} articles, lead #{g.lead_id}")
            for m in g.member_ids:
                a = by_id[m]
                sim = "lead " if m == g.lead_id else f"{g.sims.get(m, 0):.2f} "
                print(f"   {sim}#{m} {a.date:%m-%d %H:%M} {a.source_name or '?'}: {(a.title or '')[:90]}")
        if args.apply:
            n = st.write_stories(conn, groups, [a.id for a in arts],
                                 datetime.now(timezone.utc).replace(tzinfo=None))
            summary["rows_written"] = n
            print(f"\nwrote {n} trend_stories rows for {len(groups)} groups")
    summary["seconds"] = round(time.time() - t0, 1)
    try:
        (DATA_DIR / "story_groups_last.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    try:
        from pipeline.ops_events import record  # Laufprotokoll fuer /trends/ops (#104)
    except ImportError:  # pragma: no cover
        from contextlib import nullcontext as record  # type: ignore
    with record("group_stories"):
        sys.exit(main())
