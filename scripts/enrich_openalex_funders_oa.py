#!/usr/bin/env python3
"""Funder- und Open-Access-Nachladelauf (#83): zwei Spalten von S3.

Wie enrich_openalex_journals.py (dort fehlte primary_location im Erst-
Ingest) — hier holt der schmale Spalten-Read `funders` und `open_access`:

  research_work_funder(work_id, funder)  — mehrere je Werk (PK-Paar);
      Follow-the-money-Block + funder:-Operator
  research_work_oa(work_id PK, oa_url)   — nur frei lesbare Werke;
      Open-Access-Badge mit PDF-Direktlink

Keeper-Filter per JOIN gegen research_corpus. Finalize baut das Aggregat
research_topic_funders. Resumable (openalex_funder_state).

    python scripts/enrich_openalex_funders_oa.py --workers 4
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402

S3_PREFIX = "openalex/data/parquet/works/"

DDL = """
CREATE TABLE IF NOT EXISTS research_work_funder (
    work_id TEXT NOT NULL,
    funder  TEXT NOT NULL,
    PRIMARY KEY (work_id, funder));
CREATE TABLE IF NOT EXISTS research_work_oa (
    work_id TEXT PRIMARY KEY,
    oa_url  TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS openalex_funder_state (
    part    TEXT PRIMARY KEY,
    done_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""


def process_part(part: str) -> tuple[str, int, str]:
    import psycopg2
    import psycopg2.extras
    import pyarrow.parquet as pq
    import s3fs

    fs = s3fs.S3FileSystem(anon=True)
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        f = pq.ParquetFile(fs.open(part))
        fu_buf: list[tuple] = []
        oa_buf: list[tuple] = []
        inserted = 0

        def flush():
            nonlocal inserted
            if fu_buf:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO research_work_funder (work_id, funder)
                       SELECT v.wid, v.f FROM (VALUES %s) v(wid, f)
                       JOIN research_corpus rc ON rc.id = v.wid
                       ON CONFLICT DO NOTHING""",
                    fu_buf, page_size=2000)
                inserted += max(cur.rowcount, 0)
                fu_buf.clear()
            if oa_buf:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO research_work_oa (work_id, oa_url)
                       SELECT v.wid, v.u FROM (VALUES %s) v(wid, u)
                       JOIN research_corpus rc ON rc.id = v.wid
                       ON CONFLICT DO NOTHING""",
                    oa_buf, page_size=2000)
                oa_buf.clear()

        for i in range(f.metadata.num_row_groups):
            rg = f.read_row_group(i, columns=["id", "funders", "open_access"])
            for r in rg.to_pylist():
                wid = (r["id"] or "").rsplit("/", 1)[-1]
                if not wid:
                    continue
                for fu in (r["funders"] or [])[:10]:
                    name = ((fu or {}).get("display_name") or "").strip()
                    if name:
                        fu_buf.append((wid, name[:300]))
                oa = r["open_access"] or {}
                url = (oa.get("oa_url") or "").strip() if isinstance(oa, dict) else ""
                if url and oa.get("is_oa"):
                    oa_buf.append((wid, url[:600]))
                if len(fu_buf) >= 3000 or len(oa_buf) >= 3000:
                    flush()
        flush()
        cur.execute("INSERT INTO openalex_funder_state (part) VALUES (%s) "
                    "ON CONFLICT DO NOTHING", (part,))
        return (part, inserted, "")
    except Exception as e:  # noqa: BLE001
        return (part, 0, f"{type(e).__name__}: {e}")
    finally:
        conn.close()


def finalize(cur) -> None:
    for label, sql in [
        ("Aggregat topic_funders",
         """DROP TABLE IF EXISTS research_topic_funders;
            CREATE TABLE research_topic_funders AS
              SELECT rc.topic, f.funder, COUNT(*)::int AS n
              FROM research_work_funder f
              JOIN research_corpus rc ON rc.id = f.work_id
              WHERE rc.topic IS NOT NULL
              GROUP BY 1, 2;
            CREATE INDEX ON research_topic_funders (topic, n DESC)"""),
        ("Index funder-Name",
         "CREATE INDEX IF NOT EXISTS idx_rwf_funder ON research_work_funder (funder)"),
        ("ANALYZE", "ANALYZE research_work_funder; ANALYZE research_work_oa"),
    ]:
        t0 = time.time()
        for stmt in sql.split(";"):
            if stmt.strip():
                cur.execute(stmt)
        print(f"  finalize {label}: {time.time()-t0:.0f}s", flush=True)


def main() -> int:
    import psycopg2
    import s3fs
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-files", type=int, default=0)
    args = ap.parse_args()

    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    for stmt in DDL.split(";\n"):
        cur.execute(stmt)
    cur.execute("SELECT part FROM openalex_funder_state")
    done = {r[0] for r in cur.fetchall()}

    fs = s3fs.S3FileSystem(anon=True)
    parts = []
    for d in sorted(fs.ls(S3_PREFIX, detail=False)):
        if "updated_date" not in d:
            continue
        parts.extend(p for p in sorted(fs.ls(d, detail=False))
                     if p.endswith(".parquet"))
    todo = [p for p in parts if p not in done]
    if args.max_files:
        todo = todo[:args.max_files]
    print(f"{len(parts)} Parts, {len(done)} erledigt, {len(todo)} zu tun", flush=True)

    t0 = time.time()
    total = files = 0
    from multiprocessing import Pool
    with Pool(args.workers) as pool:
        for part, n, err in pool.imap_unordered(process_part, todo):
            files += 1
            if err:
                print(f"FEHLER {part}: {err}", flush=True)
                continue
            total += n
            if files % 100 == 0:
                print(f"[{files}/{len(todo)}] {total:,} Funder-Zeilen, "
                      f"{time.time()-t0:.0f}s", flush=True)

    cur.execute("SELECT COUNT(*) FROM openalex_funder_state")
    if cur.fetchone()[0] >= len(parts) and not args.max_files:
        finalize(cur)
    cur.execute("SELECT (SELECT COUNT(*) FROM research_work_funder), "
                "(SELECT COUNT(*) FROM research_work_oa)")
    fu, oa = cur.fetchone()
    print(f"FERTIG: funder {fu:,} | oa {oa:,} in {(time.time()-t0)/3600:.1f}h",
          flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
