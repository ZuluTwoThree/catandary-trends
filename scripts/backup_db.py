#!/usr/bin/env python3
"""Daily online-consistent SQLite backup for catandary-trends.

Uses sqlite3.Connection.backup() (online — safe during pipeline writes).
Compresses with gzip, copies .env alongside, prunes snapshots older than
--keep-days in each destination.

Cron example (one destination):
    5 0 * * * /home/dirk/projects/catandary-trends/.venv/bin/python \
        /home/dirk/projects/catandary-trends/scripts/backup_db.py \
        --dest /mnt/data-hdd/backups/catandary \
        >> /home/dirk/logs/catandary-backup.log 2>&1
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "catandary.db"
DEFAULT_ENV = Path(__file__).resolve().parent.parent / ".env"
DEFAULT_KEEP_DAYS = 14


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def snapshot_db(src: Path, target_gz: Path) -> int:
    """Online SQLite backup → gzip. Returns final compressed size in bytes.

    Strategy:
      1. sqlite3.Connection.backup() into a temp .db file (consistent snapshot)
      2. gzip that temp into <target>.tmp
      3. atomic rename to final <target>
      4. unlink temp .db
    """
    target_gz.parent.mkdir(parents=True, exist_ok=True)

    src_conn = sqlite3.connect(str(src))
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".db", dir=str(target_gz.parent)
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            dst_conn = sqlite3.connect(str(tmp_path))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()

            staging = target_gz.with_suffix(target_gz.suffix + ".tmp")
            with open(tmp_path, "rb") as f_in, gzip.open(
                str(staging), "wb", compresslevel=6
            ) as f_out:
                shutil.copyfileobj(f_in, f_out, length=1024 * 1024)
            os.replace(str(staging), str(target_gz))
        finally:
            tmp_path.unlink(missing_ok=True)
    finally:
        src_conn.close()

    return target_gz.stat().st_size


def prune_old(folder: Path, prefix: str, keep_days: int) -> int:
    """Delete files matching <prefix>-* older than keep_days. Returns count removed."""
    if not folder.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0
    for p in folder.glob(f"{prefix}-*"):
        if not p.is_file():
            continue
        if datetime.fromtimestamp(p.stat().st_mtime) < cutoff:
            p.unlink()
            removed += 1
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=DEFAULT_DB,
                    help="Source SQLite DB path")
    ap.add_argument("--env", type=Path, default=DEFAULT_ENV,
                    help=".env file to copy alongside the DB snapshot")
    ap.add_argument("--dest", action="append", required=True,
                    help="Destination directory (repeat for multiple targets)")
    ap.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS,
                    help="Prune snapshots older than this many days")
    args = ap.parse_args()

    if not args.db.exists():
        log(f"ERROR: source DB missing: {args.db}")
        return 1

    date_tag = datetime.now().strftime("%Y-%m-%d")
    db_size_mb = args.db.stat().st_size / 1e6
    log(f"backup start — DB={args.db} ({db_size_mb:.1f} MB), "
        f"{len(args.dest)} destination(s), keep_days={args.keep_days}")

    failures = 0
    for dest in args.dest:
        dest_path = Path(dest)
        try:
            t0 = time.time()
            snap_path = dest_path / f"catandary-{date_tag}.db.gz"
            size = snapshot_db(args.db, snap_path)

            if args.env.exists():
                shutil.copy2(args.env, dest_path / f"env-{date_tag}")

            removed_db = prune_old(dest_path, "catandary", args.keep_days)
            removed_env = prune_old(dest_path, "env", args.keep_days)

            ratio = size / args.db.stat().st_size
            log(f"  {dest}: {size/1e6:.1f} MB ({ratio*100:.0f}% of source), "
                f"pruned {removed_db}+{removed_env} old, {time.time()-t0:.1f}s")
        except Exception as e:
            log(f"  {dest}: FAILED ({e!r})")
            failures += 1

    if failures:
        log(f"ERROR: {failures} destination(s) failed")
        return 1

    log("backup OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
