#!/usr/bin/env python3
"""Journal-Nachladelauf (#80, Stufe 2): primary_location von S3 nachziehen.

Das Archiv (extract-Spalten des Erst-Ingests) enthält primary_location NICHT —
Journal-Namen brauchen einen zweiten, schmalen S3-Durchgang: nur die Spalten
id + primary_location (Spalten-Chunk-Read, kein Voll-Download). Befüllt:

  research_work_journal(work_id PK, journal)
      Nur für Werke, die in research_corpus existieren — der Filter passiert
      per JOIN gegen den PK beim Insert (die 45M-Id-Menge passt in keinen
      Worker-RAM).

Der Abschluss-Schritt baut das Aggregat research_topic_journals(topic,
journal, n) für die Top-Journals-Facette. Resumable (openalex_journal_state).

    python scripts/enrich_openalex_journals.py --workers 5
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
CREATE TABLE IF NOT EXISTS research_work_journal (
    work_id TEXT PRIMARY KEY,
    journal TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS openalex_journal_state (
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
        buf: list[tuple] = []
        inserted = 0

        def flush():
            nonlocal inserted
            if not buf:
                return
            # JOIN gegen research_corpus filtert auf unsere Keeper — die
            # Partitionen enthalten die volle Weltmenge (~10x mehr).
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO research_work_journal (work_id, journal)
                   SELECT v.wid, v.j FROM (VALUES %s) v(wid, j)
                   JOIN research_corpus rc ON rc.id = v.wid
                   ON CONFLICT (work_id) DO NOTHING""",
                buf, page_size=2000)
            inserted += max(cur.rowcount, 0)
            buf.clear()

        for i in range(f.metadata.num_row_groups):
            rg = f.read_row_group(i, columns=["id", "primary_location"])
            for r in rg.to_pylist():
                loc = r["primary_location"]
                src = (loc or {}).get("source") if isinstance(loc, dict) else None
                name = ((src or {}).get("display_name") or "").strip()
                if not name:
                    continue
                wid = (r["id"] or "").rsplit("/", 1)[-1]
                if wid:
                    buf.append((wid, name[:300]))
                if len(buf) >= 3000:
                    flush()
        flush()
        cur.execute("INSERT INTO openalex_journal_state (part) VALUES (%s) "
                    "ON CONFLICT DO NOTHING", (part,))
        return (part, inserted, "")
    except Exception as e:  # noqa: BLE001
        return (part, 0, f"{type(e).__name__}: {e}")
    finally:
        conn.close()


def finalize(cur) -> None:
    for label, sql in [
        ("Aggregat topic_journals",
         """DROP TABLE IF EXISTS research_topic_journals;
            CREATE TABLE research_topic_journals AS
              SELECT rc.topic, j.journal, COUNT(*)::int AS n
              FROM research_work_journal j
              JOIN research_corpus rc ON rc.id = j.work_id
              WHERE rc.topic IS NOT NULL
              GROUP BY 1, 2;
            CREATE INDEX ON research_topic_journals (topic, n DESC)"""),
        ("Journal-Namensliste",
         """DROP TABLE IF EXISTS research_journals;
            CREATE TABLE research_journals AS
              SELECT journal, COUNT(*)::int AS n FROM research_work_journal
              GROUP BY 1;
            ALTER TABLE research_journals ADD PRIMARY KEY (journal)"""),
        ("ANALYZE", "ANALYZE research_work_journal"),
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
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--max-files", type=int, default=0)
    args = ap.parse_args()

    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    for stmt in DDL.split(";\n"):
        cur.execute(stmt)
    cur.execute("SELECT part FROM openalex_journal_state")
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
            if files % 50 == 0:
                print(f"[{files}/{len(todo)}] {total:,} Journal-Zeilen, "
                      f"{time.time()-t0:.0f}s", flush=True)

    cur.execute("SELECT COUNT(*) FROM openalex_journal_state")
    if cur.fetchone()[0] >= len(parts) and not args.max_files:
        finalize(cur)
    cur.execute("SELECT COUNT(*) FROM research_work_journal")
    print(f"FERTIG: {cur.fetchone()[0]:,} Werke mit Journal in "
          f"{(time.time()-t0)/3600:.1f}h", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
