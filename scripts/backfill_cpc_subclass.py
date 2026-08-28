#!/usr/bin/env python3
"""Backfill patent_cpc.subclass for the #79 leading-digit parse-error rows.

Root cause (see #79 + pipeline/db.py::cpc_subclass / scripts/ingest_patents.py
::parse_docdb_document): BDDS DOCDB bundles JP's national "FI" classification
scheme under the same <patent-classification> tag as real CPC. FI notation
prepends a stray single digit (historically the IPC edition) to an otherwise
CPC-shaped symbol, e.g. "4F21S43/237" instead of "F21S43/237". The old ingest
read every classification-symbol regardless of scheme, so ~1.49M of these
landed in patent_cpc with subclass NULL (cpc_subclass() didn't strip the
digit). The ingest itself is now fixed (only scheme="CPCI" is extracted), so
this script repairs the pre-existing rows.

Japanese F-term rows (scheme="FTERM", e.g. "3E068/AA40") never match the
CPC-shaped pattern this script targets and are correctly left untouched —
whether to keep/mark/drop those ~4.4M rows is a separate, still-open Owner
decision (#79) and out of scope here.

Idempotent: re-running finds 0 affected rows once applied. Safe to interrupt
and resume (each batch commits independently).

Usage:
    python scripts/backfill_cpc_subclass.py                # dry-run (default)
    python scripts/backfill_cpc_subclass.py --dry-run
    python scripts/backfill_cpc_subclass.py --apply         # perform the UPDATE
    python scripts/backfill_cpc_subclass.py --apply --batch-size 20000
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, cpc_subclass, get_connection

# Same pattern as the Issue-#79 proposal: a stray leading digit in front of an
# otherwise valid CPC section/class/subclass/main-group symbol.
_PATTERN = r"^\d[A-HY]\d{2}[A-Z]"
_SUBSTR_PATTERN = r"^\d([A-HY]\d{2}[A-Z])"
DEFAULT_BATCH = 50_000


def _scalar(row):
    return row["n"] if isinstance(row, dict) else row[0]


def count_affected(conn) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM patent_cpc WHERE subclass IS NULL AND cpc ~ ?",
        (_PATTERN,)).fetchone()
    return _scalar(row)


def count_null_total(conn) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM patent_cpc WHERE subclass IS NULL").fetchone()
    return _scalar(row)


def sample_rows(conn, limit: int = 10):
    return conn.execute(
        "SELECT pub_number, cpc FROM patent_cpc "
        "WHERE subclass IS NULL AND cpc ~ ? LIMIT ?",
        (_PATTERN, limit)).fetchall()


def dry_run() -> int:
    with get_connection() as conn:
        total_null = count_null_total(conn)
        affected = count_affected(conn)
        rows = sample_rows(conn, 10)

    print(f"patent_cpc rows with subclass IS NULL (total): {total_null:,}")
    print(f"  matching the leading-digit CPC pattern (fixable here): {affected:,}")
    print(f"  remaining (JP F-term / other — NOT touched by --apply): "
          f"{total_null - affected:,}")
    print(f"\nSample (up to 10) of what --apply would set:")
    print(f"  {'pub_number':<20} {'cpc':<20} -> subclass")
    for r in rows:
        pub = r["pub_number"] if isinstance(r, dict) else r[0]
        cpc = r["cpc"] if isinstance(r, dict) else r[1]
        print(f"  {pub:<20} {cpc:<20} -> {cpc_subclass(cpc)}")
    if affected:
        print(f"\n[DRY RUN] No changes applied. Run with --apply to backfill "
              f"{affected:,} rows.")
    else:
        print("\n[DRY RUN] Nothing to do — already backfilled.")
    return 0


def apply(batch_size: int) -> int:
    total = 0
    t0 = time.time()
    while True:
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE patent_cpc SET subclass = substring(cpc from ?) "
                "WHERE ctid IN (SELECT ctid FROM patent_cpc "
                "WHERE subclass IS NULL AND cpc ~ ? LIMIT ?)",
                (_SUBSTR_PATTERN, _PATTERN, batch_size))
            n = cur.rowcount
        total += n
        if n:
            rate = total / max(time.time() - t0, 1e-9)
            print(f"  +{n:,} rows  ({total:,} total, {rate:,.0f} rows/s)", flush=True)
        if n < batch_size:
            break

    with get_connection() as conn:
        remaining = count_affected(conn)
        still_null = count_null_total(conn)

    print(f"\ndone: backfilled {total:,} rows in {time.time() - t0:,.0f}s")
    print(f"remaining leading-digit-pattern rows (should be 0): {remaining:,}")
    print(f"remaining subclass IS NULL total (JP F-term / other, untouched): "
          f"{still_null:,}")
    if remaining:
        print("WARNING: pattern still matches rows after backfill — investigate.")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill patent_cpc.subclass (#79)")
    ap.add_argument("--apply", action="store_true",
                     help="perform the UPDATE (default is dry-run)")
    ap.add_argument("--dry-run", action="store_true",
                     help="count affected rows + show samples (default behavior)")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH,
                     help=f"rows per UPDATE batch (default {DEFAULT_BATCH:,})")
    args = ap.parse_args()

    if not USE_POSTGRES:
        print("patent_cpc backfill targets PostgreSQL (DATABASE_URL not set)")
        return 1

    if args.apply and args.dry_run:
        print("--apply and --dry-run are mutually exclusive")
        return 1

    if args.apply:
        return apply(args.batch_size)
    return dry_run()


if __name__ == "__main__":
    raise SystemExit(main())
