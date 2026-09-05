#!/usr/bin/env python3
"""Reset raw_entries written off as filter_reason='embedding_error' (#98 d).

Until 2026-09-05 signal_batch recorded EVERY embedding failure as
`filtered_out=TRUE, filter_reason='embedding_error'` — including the 2,416
entries whose only fault was that the embedding server had been killed under
them. A filtered entry is never picked up again, so a server outage silently
deleted signals. signal_batch now leaves backend failures unprocessed; this
script repairs a database where it did happen anyway (or an older run).

It flips matching rows back to `processed=FALSE, filtered_out=FALSE,
filter_reason=NULL`; the next signal_batch / weekly_ingesters run embeds them
again. Nothing else is touched (no trends row exists for these entries).

    python scripts/reset_embedding_errors.py                 # dry-run: counts per source
    python scripts/reset_embedding_errors.py --apply         # do it
    python scripts/reset_embedding_errors.py --since 2026-09-01 --apply   # fetched_at >= date
    python scripts/reset_embedding_errors.py --min-id 21600000 --apply    # id > N
    python scripts/reset_embedding_errors.py --source-type research --apply

Exit 0 (also when nothing matched); prints what it would/did change.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.db import get_connection  # noqa: E402

REASON = "embedding_error"


def _scope(args) -> tuple[str, list]:
    where = ["re.filtered_out = TRUE", "re.filter_reason = ?"]
    params: list = [REASON]
    if args.since:
        where.append("re.fetched_at >= ?")
        params.append(args.since)
    if args.min_id:
        where.append("re.id > ?")
        params.append(args.min_id)
    if args.source_type:
        where.append("s.source_type = ?")
        params.append(args.source_type)
    return " AND ".join(where), params


def count_by_source(args) -> list[tuple[str, int]]:
    where, params = _scope(args)
    with get_connection() as c:
        rows = c.execute(
            "SELECT s.name AS name, COUNT(*) AS n FROM raw_entries re "
            "JOIN sources s ON re.source_id = s.id "
            f"WHERE {where} GROUP BY s.name ORDER BY n DESC, s.name", params).fetchall()
    return [((r["name"] if hasattr(r, "keys") else r[0]),
             int(r["n"] if hasattr(r, "keys") else r[1])) for r in rows]


def reset(args) -> int:
    """Flip the rows back; returns the number of rows changed."""
    where, params = _scope(args)
    with get_connection() as c:
        cur = c.execute(
            "UPDATE raw_entries SET processed = FALSE, filtered_out = FALSE, "
            "filter_reason = NULL WHERE id IN ("
            "  SELECT re.id FROM raw_entries re JOIN sources s ON re.source_id = s.id "
            f" WHERE {where})", params)
        n = cur.rowcount if cur.rowcount is not None else -1
        c.commit()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n", 1)[1])
    ap.add_argument("--apply", action="store_true",
                    help="really reset the rows (default: dry-run, counts only)")
    ap.add_argument("--dry-run", action="store_true",
                    help="explicit dry-run (the default) — counts per source, changes nothing")
    ap.add_argument("--since", default="",
                    help="only rows fetched_at >= YYYY-MM-DD (default: all)")
    ap.add_argument("--min-id", type=int, default=0, help="only rows with id > MIN_ID")
    ap.add_argument("--source-type", default="",
                    help="only sources of this source_type (research, api, …)")
    args = ap.parse_args(argv)
    if args.apply and args.dry_run:
        ap.error("--apply and --dry-run are mutually exclusive")

    per_source = count_by_source(args)
    total = sum(n for _, n in per_source)
    print(f"raw_entries with filter_reason='{REASON}' in scope: {total}")
    for name, n in per_source[:30]:
        print(f"  {n:>8}  {name}")
    if len(per_source) > 30:
        print(f"  … and {len(per_source) - 30} more sources")
    if total == 0:
        return 0
    if not args.apply:
        print("\nDRY-RUN — nothing changed. Re-run with --apply to reset these rows "
              "(processed=FALSE, filtered_out=FALSE, filter_reason=NULL).")
        return 0
    n = reset(args)
    print(f"\nReset {n} rows — the next signal_batch / weekly_ingesters run embeds them again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
