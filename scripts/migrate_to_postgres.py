#!/usr/bin/env python3
"""Migrate the SQLite DB → PostgreSQL + pgvector. Preparation tool for the patent
depth ingest (the back-file needs Postgres; mass vector search outgrows SQLite).

SAFE BY DESIGN: reads SQLite read-only (WAL → does not block the live pipeline),
writes only to the target Postgres. It does NOT switch the app over — that's a
manual cutover (set DATABASE_URL, port the frontend). Run the real migration only
when the SQLite writers (signal_batch) are idle, so Postgres gets a complete copy.

Modes (run the first two with NO Postgres needed):
  --self-check   exercise every value transformer on a sample → proves conversion
  --dry-run      count rows per table from SQLite (volumes), no writes
  (real)         DATABASE_URL=postgresql://… python scripts/migrate_to_postgres.py [--limit N]

The schema is created from pipeline.db.PG_SCHEMA (single source of truth).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline import db as dbmod
from pipeline.config import DATABASE_PATH

# Tables in FK-dependency order. patent_* and newsletter have no inbound FKs.
TABLES = ["sources", "raw_entries", "trends", "source_discoveries",
          "trend_clusters", "trend_metrics", "patent_links", "patent_cpc",
          "newsletter_subscribers"]
SERIAL_TABLES = {"sources", "raw_entries", "trends", "source_discoveries",
                 "trend_clusters", "trend_metrics", "newsletter_subscribers"}
# child FK → parent, so a --limit probe stays referentially consistent (only copy
# child rows whose parent was copied). Full runs (no limit) copy everything in order.
FK_PARENT = {
    "raw_entries": [("source_id", "sources")],
    "trends": [("raw_entry_id", "raw_entries")],
    "trend_metrics": [("trend_id", "trends")],
}

BOOL_COLS = {
    "sources": {"active", "auto_discovered"},
    "raw_entries": {"processed", "filtered_out"},
    "trends": {"auto_published"},
    "source_discoveries": {"has_rss_feed", "added_to_sources"},
    "newsletter_subscribers": {"confirmed"},
}
JSONB_COLS = {
    "sources": {"sub_categories"},
    "trends": {"verticals", "pestel", "tags", "brands", "companies", "regions"},
    "trend_clusters": {"verticals", "pestel", "trend_ids"},
    "newsletter_subscribers": {"verticals"},
}
VECTOR_COLS = {"trends": {"embedding"}}            # SQLite BLOB(16384) → vector(4096)
BYTEA_COLS = {"raw_entries": {"embedding_blob"}}   # SQLite BLOB → bytea (raw bytes)
DATE_COLS = {
    "sources": {"last_fetched", "created_at"},
    "raw_entries": {"published_date", "fetched_at"},
    "trends": {"published_at", "created_at", "sort_date"},
    "source_discoveries": {"discovered_at"},
    "trend_clusters": {"created_at", "updated_at"},
    "trend_metrics": {"updated_at"},
    "newsletter_subscribers": {"subscribed_at", "unsubscribed_at"},
}

_FULL_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?)?")


def coerce_dt(v):
    """SQLite text date → a Postgres-castable timestamp string, or None.
    Handles full ISO, 'YYYY-MM', 'YYYY', empties, and junk (→ None)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if _FULL_ISO.match(s):
        return s
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s + "-01"
    if re.fullmatch(r"\d{4}", s):
        return s + "-01-01"
    return None  # unparseable → NULL rather than a failed insert


def blob_to_vector(b):
    """BLOB of float32 → pgvector literal string '[f1,f2,…]' (or None)."""
    if b is None:
        return None
    if isinstance(b, memoryview):
        b = b.tobytes()
    n = len(b) // 4
    if n == 0:
        return None
    floats = struct.unpack(f"<{n}f", b[: n * 4])
    return "[" + ",".join(repr(float(x)) for x in floats) + "]"


def make_value(table, col, v, Json):
    if v is None:
        return None
    if col in BOOL_COLS.get(table, ()):
        return bool(v)
    if col in JSONB_COLS.get(table, ()):
        try:
            return Json(json.loads(v))
        except Exception:
            return Json([])
    if col in VECTOR_COLS.get(table, ()):
        return blob_to_vector(v)
    if col in BYTEA_COLS.get(table, ()):
        return v.tobytes() if isinstance(v, memoryview) else bytes(v)
    if col in DATE_COLS.get(table, ()):
        return coerce_dt(v)
    return v


def sqlite_conn() -> sqlite3.Connection:
    # immutable read-only URI → never blocks or is blocked by the live writer (WAL)
    uri = f"file:{DATABASE_PATH}?mode=ro"
    c = sqlite3.connect(uri, uri=True, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def columns(sq: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in sq.execute(f"PRAGMA table_info({table})").fetchall()]


def count(sq, table) -> int:
    return sq.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def self_check() -> int:
    """Validate transformers on a live sample without any Postgres."""
    class _FakeJson:
        def __init__(self, o): self.o = o
        def __repr__(self): return f"Json({self.o!r})"
    sq = sqlite_conn()
    print("self-check — transformer output on sample rows (no Postgres):\n")
    for table in ("trends", "raw_entries", "sources"):
        cols = columns(sq, table)
        row = sq.execute(f"SELECT * FROM {table} LIMIT 1").fetchone()
        if not row:
            print(f"  {table}: empty"); continue
        print(f"━━ {table}")
        for col in cols:
            out = make_value(table, col, row[col], _FakeJson)
            kind = ("vector" if col in VECTOR_COLS.get(table, ()) else
                    "jsonb" if col in JSONB_COLS.get(table, ()) else
                    "bool" if col in BOOL_COLS.get(table, ()) else
                    "bytea" if col in BYTEA_COLS.get(table, ()) else
                    "date" if col in DATE_COLS.get(table, ()) else "")
            shown = out if not isinstance(out, str) else (out[:60] + ("…" if len(out) > 60 else ""))
            if kind:
                print(f"   {col:18} [{kind:6}] {shown}")
        # spot-check the vector roundtrip dimension
        if table == "trends" and row["embedding"] is not None:
            vec = blob_to_vector(row["embedding"])
            dim = vec.count(",") + 1
            print(f"   → embedding vector dim = {dim} (expect 4096)")
    sq.close()
    return 0


def dry_run() -> int:
    sq = sqlite_conn()
    print(f"dry-run — SQLite source: {DATABASE_PATH}\n")
    total = 0
    for t in TABLES:
        try:
            n = count(sq, t); total += n
            print(f"  {t:24} {n:>10}")
        except sqlite3.OperationalError as e:
            print(f"  {t:24} (missing: {e})")
    print(f"  {'TOTAL':24} {total:>10}")
    sq.close()
    return 0


def migrate(pg_url: str, limit: int, batch: int, fresh: bool) -> int:
    import psycopg2
    from psycopg2.extras import execute_values, Json

    sq = sqlite_conn()
    pg = psycopg2.connect(pg_url)
    pg.autocommit = False
    cur = pg.cursor()
    if fresh:
        print("--fresh: dropping target tables …")
        cur.execute("DROP TABLE IF EXISTS " + ", ".join(TABLES) + " CASCADE")
        pg.commit()
    print("creating schema from pipeline.db.PG_SCHEMA …")
    cur.execute(dbmod.PG_SCHEMA)
    pg.commit()

    copied_ids: dict[str, set] = {}  # parent table → copied id set (only under --limit)
    for table in TABLES:
        try:
            cols = columns(sq, table)
        except sqlite3.OperationalError:
            print(f"  {table}: not in SQLite, skip"); continue
        if not cols:
            continue
        # FK-consistent --limit: restrict child rows to copied parents
        where = ""
        if limit and table in FK_PARENT:
            clauses = []
            for fk_col, parent in FK_PARENT[table]:
                ids = copied_ids.get(parent)
                if ids is None:
                    continue
                clauses.append(f"{fk_col} IN ({','.join(map(str, ids))})" if ids else "0=1")
            if clauses:
                where = " WHERE " + " AND ".join(clauses)
        # per-row placeholder template: vector columns need an explicit ::vector cast
        ph = ", ".join("%s::vector" if c in VECTOR_COLS.get(table, ()) else "%s" for c in cols)
        collist = ", ".join(cols)
        sel = f"SELECT {collist} FROM {table}{where}" + (f" LIMIT {limit}" if limit else "")
        track = limit and "id" in cols  # remember ids so children stay consistent
        if track:
            copied_ids[table] = set()
        n = count(sq, table)
        if limit:
            n = min(n, limit)
        done = 0
        buf = []
        for r in sq.execute(sel):
            if track:
                copied_ids[table].add(r["id"])
            buf.append(tuple(make_value(table, c, r[c], Json) for c in cols))
            if len(buf) >= batch:
                execute_values(cur, f"INSERT INTO {table} ({collist}) VALUES %s",
                               buf, template=f"({ph})")
                done += len(buf); buf.clear()
                print(f"  {table}: {done}/{n}", end="\r")
        if buf:
            execute_values(cur, f"INSERT INTO {table} ({collist}) VALUES %s",
                           buf, template=f"({ph})")
            done += len(buf)
        pg.commit()
        # reset the SERIAL sequence so future inserts don't collide with copied ids
        if table in SERIAL_TABLES and "id" in cols:
            cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'), "
                        f"COALESCE((SELECT MAX(id) FROM {table}),1))")
            pg.commit()
        print(f"  {table}: {done}/{n} done           ")

    cur.close(); pg.close(); sq.close()
    print("\nmigration complete. Verify counts, then cut over (set DATABASE_URL).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="SQLite → PostgreSQL+pgvector migration")
    ap.add_argument("--self-check", action="store_true", help="validate transformers, no PG")
    ap.add_argument("--dry-run", action="store_true", help="count rows per table, no PG")
    ap.add_argument("--pg", help="target Postgres URL (else $DATABASE_URL)")
    ap.add_argument("--limit", type=int, default=0, help="rows/table cap (small test migration)")
    ap.add_argument("--fresh", action="store_true", help="DROP all target tables first (clean re-run)")
    ap.add_argument("--batch", type=int, default=2000)
    args = ap.parse_args()

    if args.self_check:
        return self_check()
    if args.dry_run:
        return dry_run()
    pg_url = args.pg or os.getenv("DATABASE_URL")
    if not pg_url:
        print("ERROR: no Postgres URL. Pass --pg or set DATABASE_URL, or use "
              "--self-check / --dry-run (no PG needed).")
        return 2
    return migrate(pg_url, args.limit, args.batch, args.fresh)


if __name__ == "__main__":
    raise SystemExit(main())
