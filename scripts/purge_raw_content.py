#!/usr/bin/env python3
"""Retention for fetched full text: NULL `raw_entries.raw_content` once the copy
is no longer needed (compliance review 2026-09-02, §44b Abs. 2 S. 2 UrhG).

The full-text fetcher (pipeline/article_fetcher.py) stores up to 12,000
characters of a publisher's article for text and data mining. §44b UrhG covers
that copy only while it is required for the mining — and the pipeline needs it
for a short, bounded window:

  - content generation + grounding gate: the same night (run_full_cycle)
  - auto-publish grounding re-check: the same night
  - draft judge (stage 10): fresh drafts only, stamped judged_at, never re-judged
  - corpus_research / dossiers: read raw_content of published trends as
    evidence when present, fall back to the feed excerpt otherwise

After the judge window nothing re-reads the text, so 90 days is a generous
ceiling. Everything else stays: title, feed excerpt (≤ 2,000 chars, what the
publisher put into the feed), extraction_json, embeddings, the generated trend.

Selection (both flags must hold):
    processed = TRUE                     -- the pipeline is done with the entry
    fetched_at < now - N days            -- older than the retention window
    raw_content IS NOT NULL
    [source in sources.yaml fulltext:true]   -- --fulltext-sources-only

Writes go in id-range batches over the primary key (there is no index on
fetched_at or raw_content and none is needed: a range of 50,000 ids is one
index-range scan), one transaction per batch, progress on stderr — the table
holds ~25M rows / 41 GB, a single UPDATE would hold a lock for an hour and
bloat WAL. Dry run is the default and touches nothing.

    python scripts/purge_raw_content.py                          # dry run: count + bytes
    python scripts/purge_raw_content.py --days 90 --by-source    # + top sources
    python scripts/purge_raw_content.py --days 90 --apply        # write
    python scripts/purge_raw_content.py --apply --max-rows 200000   # cautious first run

Cron suggestion (deploy/crontab.txt, commented out until the owner enables it):
    30 3 * * 0  purge_raw_content.py --days 90 --apply
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s",
                    stream=sys.stderr)
logger = logging.getLogger("purge_raw_content")

DEFAULT_DAYS = 90
DEFAULT_BATCH_IDS = 50_000

# On Postgres long texts live TOASTed (compressed, out of line); pg_column_size
# reports the stored bytes WITHOUT detoasting, so the dry run is one cheap
# pass over the heap. SQLite has no TOAST — length() is the honest number there.
_BYTES_EXPR = "pg_column_size(raw_content)" if USE_POSTGRES else "length(raw_content)"


def cutoff_iso(days: int, now: datetime | None = None) -> str:
    """Naive UTC timestamp string — compares on both backends (raw_entries.fetched_at
    is `timestamp without time zone` on PG, an ISO text on SQLite)."""
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def fulltext_source_ids(conn) -> list[int]:
    """DB ids of the sources flagged fulltext:true in sources.yaml (by name, the
    key article_fetcher uses)."""
    from pipeline.article_fetcher import fulltext_source_names
    names = sorted(fulltext_source_names())
    if not names:
        return []
    ph = ",".join("?" * len(names))
    rows = conn.execute(f"SELECT id FROM sources WHERE name IN ({ph})", names).fetchall()
    return sorted(r["id"] if isinstance(r, dict) else r[0] for r in rows)


def _where(cutoff: str, source_ids: list[int] | None) -> tuple[str, list]:
    sql = "processed = TRUE AND raw_content IS NOT NULL AND fetched_at < ?"
    params: list = [cutoff]
    if source_ids is not None:
        if not source_ids:
            return "1 = 0", []
        sql += f" AND source_id IN ({','.join('?' * len(source_ids))})"
        params.extend(source_ids)
    return sql, params


def count_candidates(conn, cutoff: str, source_ids: list[int] | None) -> dict:
    where, params = _where(cutoff, source_ids)
    row = conn.execute(
        f"SELECT COUNT(*) AS n, COALESCE(SUM({_BYTES_EXPR}), 0) AS bytes, "
        f"MIN(id) AS min_id, MAX(id) AS max_id, "
        f"MIN(fetched_at) AS oldest, MAX(fetched_at) AS newest "
        f"FROM raw_entries WHERE {where}", params).fetchone()
    r = dict(row) if isinstance(row, dict) else {
        "n": row[0], "bytes": row[1], "min_id": row[2], "max_id": row[3],
        "oldest": row[4], "newest": row[5]}
    r["n"] = int(r["n"] or 0)
    r["bytes"] = int(r["bytes"] or 0)
    return r


def by_source(conn, cutoff: str, source_ids: list[int] | None, top: int = 15) -> list[dict]:
    where, params = _where(cutoff, source_ids)
    rows = conn.execute(
        f"SELECT s.name AS name, COUNT(*) AS n, COALESCE(SUM({_BYTES_EXPR}), 0) AS bytes "
        f"FROM raw_entries re JOIN sources s ON s.id = re.source_id "
        f"WHERE {where} GROUP BY s.name ORDER BY bytes DESC LIMIT ?",
        [*params, top]).fetchall()
    return [dict(r) if isinstance(r, dict) else {"name": r[0], "n": r[1], "bytes": r[2]}
            for r in rows]


def purge(cutoff: str, source_ids: list[int] | None, min_id: int, max_id: int,
          batch_ids: int = DEFAULT_BATCH_IDS, max_rows: int | None = None) -> int:
    """NULL raw_content in id-range batches; returns rows updated."""
    where, params = _where(cutoff, source_ids)
    total = 0
    t0 = time.time()
    batches = 0
    for lo in range(min_id, max_id + 1, batch_ids):
        hi = lo + batch_ids
        with get_connection() as conn:
            cur = conn.execute(
                f"UPDATE raw_entries SET raw_content = NULL "
                f"WHERE id >= ? AND id < ? AND {where}", [lo, hi, *params])
            n = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
        total += n
        batches += 1
        if n or batches % 20 == 0:
            logger.info("ids %d–%d: %d nulled (total %d, %.0fs)", lo, hi - 1, n, total, time.time() - t0)
        if max_rows is not None and total >= max_rows:
            logger.info("--max-rows %d reached, stopping", max_rows)
            break
    return total


def fmt_bytes(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if x < 1024 or unit == "TB":
            return f"{x:.1f} {unit}" if unit != "B" else f"{int(x)} B"
        x /= 1024
    return f"{n} B"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help=f"retention window in days after fetch (default {DEFAULT_DAYS})")
    ap.add_argument("--fulltext-sources-only", action="store_true",
                    help="only entries of sources flagged fulltext:true in sources.yaml")
    ap.add_argument("--by-source", action="store_true",
                    help="dry run: also list the top sources by stored bytes (second pass)")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH_IDS,
                    help=f"id-range width per UPDATE transaction (default {DEFAULT_BATCH_IDS})")
    ap.add_argument("--max-rows", type=int, default=None,
                    help="stop after this many rows were nulled (cautious first run)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="count + bytes only (default)")
    mode.add_argument("--apply", action="store_true", help="actually NULL raw_content")
    args = ap.parse_args(argv)

    cutoff = cutoff_iso(args.days)
    backend = "postgres" if USE_POSTGRES else "sqlite"
    with get_connection() as conn:
        source_ids = fulltext_source_ids(conn) if args.fulltext_sources_only else None
        stats = count_candidates(conn, cutoff, source_ids)
        top = by_source(conn, cutoff, source_ids) if args.by_source else []

    scope = (f"{len(source_ids)} fulltext:true sources" if source_ids is not None
             else "all sources")
    print(f"backend={backend} cutoff=fetched_at<{cutoff} ({args.days} days) scope={scope}")
    print(f"candidates: {stats['n']:,} rows, {fmt_bytes(stats['bytes'])} stored "
          f"({'on-disk, compressed' if USE_POSTGRES else 'characters'})")
    if stats["n"]:
        print(f"id range {stats['min_id']}–{stats['max_id']}, "
              f"fetched {stats['oldest']} … {stats['newest']}")
    for r in top:
        print(f"  {fmt_bytes(int(r['bytes'])):>10}  {int(r['n']):>8,}  {r['name']}")

    if not args.apply:
        print("dry run — nothing written (use --apply to purge)")
        return 0
    if not stats["n"]:
        print("nothing to purge")
        return 0
    nulled = purge(cutoff, source_ids, int(stats["min_id"]), int(stats["max_id"]),
                   batch_ids=args.batch, max_rows=args.max_rows)
    print(f"purged raw_content on {nulled:,} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
