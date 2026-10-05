#!/usr/bin/env python3
"""Archiv-Extrakt (#80, Stufe 2): Autoren, Institutionen, Zitationskurven.

Liest das lokale Parquet-Archiv (/mnt/data-hdd/openalex_snapshot, 2.261
Dateien) EINMAL und befüllt drei Tabellen — kein S3-Zugriff nötig:

  research_authors_flat(work_id PK, authors, institutions)
      Konkatenierte, deduplizierte Namen je Werk (Autoren-Cap 30 — Physik-
      Kollaborationen haben Tausende) → Basis für author:/institution:-
      Suche (Trigram-Indizes baut der Abschluss-Schritt).
  research_work_inst(work_id, topic, institution, country)
      Lead-Institution (erste Institution des Erstautors) je Werk → speist
      das Aggregat research_topic_institutions (Leading-Institutions-Panel)
      und künftige Research-Country-Analysen.
  research_citation_recent(work_id PK, cites_recent, cites_total)
      Zitationen 2025+2026 vs. gesamt (aus counts_by_year) → echte
      Rising-Papers-Metrik statt des cited/age-Proxys. Nur Werke mit
      mindestens einer Zitation.

Resumable per State-Tabelle (openalex_extract_state). Abschluss-Schritt
baut Indizes + das Topic-Institutionen-Aggregat und läuft automatisch,
wenn alle Parts verarbeitet sind.

    python scripts/extract_openalex_archive.py --workers 4
"""
from __future__ import annotations

import argparse
import glob
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402
from pipeline.openalex_sync import recent_floor  # noqa: E402

# „Jüngste Zitationen" rollierend: laufendes + voriges Jahr (bis 05.10.2026 fest >= 2025).
RECENT_FLOOR = recent_floor()

ARCHIVE = "/mnt/data-hdd/openalex_snapshot"
AUTHOR_CAP = 30

DDL = """
CREATE TABLE IF NOT EXISTS research_authors_flat (
    work_id      TEXT PRIMARY KEY,
    authors      TEXT,
    institutions TEXT);
CREATE TABLE IF NOT EXISTS research_work_inst (
    work_id     TEXT PRIMARY KEY,
    topic       TEXT,
    institution TEXT,
    country     TEXT);
CREATE TABLE IF NOT EXISTS research_citation_recent (
    work_id      TEXT PRIMARY KEY,
    cites_recent INTEGER NOT NULL,
    cites_total  INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS openalex_extract_state (
    part    TEXT PRIMARY KEY,
    done_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"""


def process_part(part: str) -> tuple[str, int, str]:
    import psycopg2
    import psycopg2.extras
    import pyarrow.parquet as pq

    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        f = pq.ParquetFile(part)
        af_buf: list[tuple] = []
        wi_buf: list[tuple] = []
        cr_buf: list[tuple] = []

        def flush():
            if af_buf:
                psycopg2.extras.execute_values(
                    cur, "INSERT INTO research_authors_flat VALUES %s "
                         "ON CONFLICT (work_id) DO NOTHING", af_buf, page_size=2000)
                af_buf.clear()
            if wi_buf:
                psycopg2.extras.execute_values(
                    cur, "INSERT INTO research_work_inst VALUES %s "
                         "ON CONFLICT (work_id) DO NOTHING", wi_buf, page_size=2000)
                wi_buf.clear()
            if cr_buf:
                psycopg2.extras.execute_values(
                    cur, "INSERT INTO research_citation_recent VALUES %s "
                         "ON CONFLICT (work_id) DO NOTHING", cr_buf, page_size=2000)
                cr_buf.clear()

        n = 0
        for i in range(f.metadata.num_row_groups):
            rg = f.read_row_group(i, columns=["id", "authorships", "counts_by_year",
                                              "primary_topic"])
            for r in rg.to_pylist():
                wid = (r["id"] or "").rsplit("/", 1)[-1]
                if not wid:
                    continue
                n += 1
                topic = r["primary_topic"]
                topic = topic.get("display_name") if isinstance(topic, dict) else None

                auths = r["authorships"] or []
                names: list[str] = []
                insts: list[str] = []
                for a in auths[:AUTHOR_CAP]:
                    nm = ((a.get("author") or {}).get("display_name") or "").strip()
                    if nm:
                        names.append(nm)
                    for inst in a.get("institutions") or []:
                        dn = (inst.get("display_name") or "").strip()
                        if dn and dn not in insts:
                            insts.append(dn)
                if names or insts:
                    af_buf.append((wid, "; ".join(names) or None,
                                   "; ".join(insts[:AUTHOR_CAP]) or None))
                if auths:
                    a0 = auths[0]
                    i0 = (a0.get("institutions") or [{}])[0]
                    lead = (i0.get("display_name") or "").strip() or None
                    ctry = i0.get("country_code") or None
                    if lead:
                        wi_buf.append((wid, topic, lead, ctry))

                cby = r["counts_by_year"] or []
                total = sum(x.get("cited_by_count") or 0 for x in cby)
                if total > 0:
                    recent = sum(x.get("cited_by_count") or 0 for x in cby
                                 if (x.get("year") or 0) >= RECENT_FLOOR)
                    cr_buf.append((wid, recent, total))
                if len(af_buf) >= 2000:
                    flush()
        flush()
        cur.execute("INSERT INTO openalex_extract_state (part) VALUES (%s) "
                    "ON CONFLICT DO NOTHING", (part,))
        return (part, n, "")
    except Exception as e:  # noqa: BLE001
        return (part, 0, f"{type(e).__name__}: {e}")
    finally:
        conn.close()


def finalize(cur) -> None:
    """Indizes + Aggregate — läuft einmal, wenn alle Parts durch sind."""
    steps = [
        ("Aggregat topic_institutions",
         """DROP TABLE IF EXISTS research_topic_institutions;
            CREATE TABLE research_topic_institutions AS
              SELECT topic, institution, country, COUNT(*)::int AS n
              FROM research_work_inst WHERE topic IS NOT NULL
              GROUP BY 1, 2, 3;
            CREATE INDEX ON research_topic_institutions (topic, n DESC)"""),
        ("Trigram authors",
         "CREATE INDEX IF NOT EXISTS idx_raf_authors_trgm ON research_authors_flat "
         "USING gin (authors gin_trgm_ops)"),
        ("Trigram institutions",
         "CREATE INDEX IF NOT EXISTS idx_raf_inst_trgm ON research_authors_flat "
         "USING gin (institutions gin_trgm_ops)"),
        ("Index citation_recent",
         "CREATE INDEX IF NOT EXISTS idx_rcr_recent ON research_citation_recent "
         "(cites_recent DESC)"),
        ("ANALYZE", "ANALYZE research_authors_flat; ANALYZE research_work_inst; "
                    "ANALYZE research_citation_recent"),
    ]
    for label, sql in steps:
        t0 = time.time()
        for stmt in sql.split(";"):
            if stmt.strip():
                cur.execute(stmt)
        print(f"  finalize {label}: {time.time()-t0:.0f}s", flush=True)


def main() -> int:
    import psycopg2
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-files", type=int, default=0)
    args = ap.parse_args()

    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    for stmt in DDL.split(";\n"):
        cur.execute(stmt)
    cur.execute("SELECT part FROM openalex_extract_state")
    done = {r[0] for r in cur.fetchall()}
    parts = sorted(glob.glob(f"{ARCHIVE}/*/part_*.parquet"))
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
                print(f"[{files}/{len(todo)}] {total:,} Werke, "
                      f"{time.time()-t0:.0f}s", flush=True)

    cur.execute("SELECT COUNT(*) FROM openalex_extract_state")
    if cur.fetchone()[0] >= len(parts) and not args.max_files:
        finalize(cur)
    cur.execute("""SELECT
        (SELECT COUNT(*) FROM research_authors_flat),
        (SELECT COUNT(*) FROM research_work_inst),
        (SELECT COUNT(*) FROM research_citation_recent)""")
    a, w, c = cur.fetchone()
    conn.close()
    print(f"FERTIG: authors_flat {a:,} | work_inst {w:,} | citation_recent {c:,} "
          f"in {(time.time()-t0)/3600:.1f}h", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
