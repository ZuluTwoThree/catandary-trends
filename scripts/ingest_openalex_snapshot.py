#!/usr/bin/env python3
"""OpenAlex-Snapshot-Ingest: Research-Korpus auf Patent-Parität (#80).

Liest die Works-Parquet-Partitionen (s3://openalex/data/parquet/works/, frei,
anonym) mit Spaltenauswahl, filtert auf

    Typ Artikel/Preprint/Review · kein Paratext · Englisch · Jahr >= 2010 ·
    Abstract vorhanden · Zitations-Floor: Werke aelter als 3 Jahre brauchen
    cited_by_count >= 1 (junge Werke bleiben citation-free drin — Fresh-Gedanke)

und schreibt zwei Ziele:

  * /mnt/data-hdd/openalex_snapshot/<partition>/<part>.parquet — gefiltertes
    Archiv mit ALLEN gelesenen Spalten (inkl. authorships/topics/counts_by_year)
    fuer spaetere Ausbauten (Autoren-Suche, Rising Papers) ohne Re-Download.
  * research_corpus (Postgres) — die durchsuchbare Schicht des Research
    Explorers: Kernfelder + fertig gewichteter tsvector (Titel=A, Abstract=B,
    Muster patent_search #78). BEWUSST NICHT raw_entries: das wuerde den
    idx_re_patent_fts-GIN aufblaehen und die Signal-Pipeline-Crons streifen.
    source_type-Semantik: diese Schicht ist reine Suche, KEIN Signal-Korpus.

Resumable per State-Tabelle (openalex_snap_state, eine Zeile je Part-Datei).
Platz-Waechter: bricht sauber ab, wenn HDD < 150 GB oder NVMe < 100 GB frei.
Checkpoint: loggt laufend Hochrechnung (Keep-Rate, erwartete Endgroesse).

    python scripts/ingest_openalex_snapshot.py --max-files 1     # Probelauf
    python scripts/ingest_openalex_snapshot.py --workers 5      # Volllauf
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402

ARCHIVE = Path("/mnt/data-hdd/openalex_snapshot")
S3_PREFIX = "openalex/data/parquet/works/"
COLS = ["id", "doi", "title", "publication_date", "publication_year", "language",
        "type", "is_paratext", "is_retracted", "abstract_inverted_index",
        "cited_by_count", "counts_by_year", "fwci", "authorships",
        "primary_topic", "topics"]
KEEP_TYPES = ["article", "preprint", "review"]
MIN_YEAR = 2010
CITE_FLOOR_BEFORE = 2023   # Jahr <= 2023 (aelter als 3 J.) -> cited_by_count >= 1
HDD_MIN_FREE = 150e9
NVME_MIN_FREE = 100e9

DDL = """
CREATE TABLE IF NOT EXISTS research_corpus (
    id             TEXT PRIMARY KEY,        -- OpenAlex W-Id (Kurzform)
    doi            TEXT,
    title          TEXT NOT NULL,
    abstract       TEXT NOT NULL,
    published      DATE,
    year           INTEGER,
    type           TEXT,
    topic          TEXT,
    cited_by_count INTEGER,
    fwci           REAL,
    is_retracted   BOOLEAN,
    tsv            tsvector NOT NULL
);
CREATE TABLE IF NOT EXISTS openalex_snap_state (
    part       TEXT PRIMARY KEY,
    rows_total INTEGER,
    kept       INTEGER,
    done_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)"""

INSERT_TMPL = ("(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,"
               "setweight(to_tsvector('english', left(%s, 2000)), 'A') || "
               "setweight(to_tsvector('english', left(%s, 16000)), 'B'))")


def reconstruct(inv) -> str:
    """Abstract aus dem invertierten Index zusammensetzen."""
    if inv is None:
        return ""
    if isinstance(inv, str):
        try:
            inv = json.loads(inv)
        except ValueError:
            return ""
    if isinstance(inv, dict):
        inv = inv.get("InvertedIndex", inv)
    if not isinstance(inv, dict):
        return ""
    pos: dict[int, str] = {}
    for word, places in inv.items():
        for p in places or []:
            pos[p] = word
    return " ".join(pos[k] for k in sorted(pos))


def disk_ok() -> bool:
    return (shutil.disk_usage(ARCHIVE).free > HDD_MIN_FREE
            and shutil.disk_usage("/").free > NVME_MIN_FREE)


def process_part(part: str) -> tuple[str, int, int, str]:
    """Eine Part-Datei: lesen, filtern, archivieren, einfuegen. Idempotent."""
    import psycopg2
    import psycopg2.extras
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    import s3fs

    fs = s3fs.S3FileSystem(anon=True)
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        f = pq.ParquetFile(fs.open("openalex/" + part if not part.startswith("openalex/") else part))
        kept_tables = []
        rows_total = 0
        buf: list[tuple] = []

        def flush():
            if buf:
                psycopg2.extras.execute_values(
                    cur, "INSERT INTO research_corpus (id, doi, title, abstract, "
                         "published, year, type, topic, cited_by_count, fwci, "
                         "is_retracted, tsv) VALUES %s ON CONFLICT (id) DO NOTHING",
                    buf, template=INSERT_TMPL, page_size=2000)
                buf.clear()

        for i in range(f.metadata.num_row_groups):
            rg = f.read_row_group(i, columns=COLS)
            rows_total += rg.num_rows
            m = pc.is_in(rg["type"], value_set=pa.array(KEEP_TYPES))
            m = pc.and_(m, pc.equal(rg["is_paratext"], False))
            m = pc.and_(m, pc.equal(rg["language"], "en"))
            m = pc.and_(m, pc.greater_equal(rg["publication_year"], MIN_YEAR))
            m = pc.and_(m, pc.is_valid(rg["abstract_inverted_index"]))
            floor = pc.or_(pc.greater(rg["publication_year"], CITE_FLOOR_BEFORE),
                           pc.greater_equal(rg["cited_by_count"], 1))
            m = pc.and_(m, floor)
            kept = rg.filter(m)
            if kept.num_rows == 0:
                continue
            kept_tables.append(kept)
            slim = kept.select(["id", "doi", "title", "publication_date",
                                "publication_year", "type", "primary_topic",
                                "cited_by_count", "fwci", "is_retracted",
                                "abstract_inverted_index"]).to_pylist()
            for r in slim:
                abstract = reconstruct(r["abstract_inverted_index"])[:16000]
                if len(abstract) < 50:
                    continue
                wid = (r["id"] or "").rsplit("/", 1)[-1]
                title = (r["title"] or "").strip()[:2000]
                if not wid or not title:
                    continue
                topic = r["primary_topic"]
                topic = topic.get("display_name") if isinstance(topic, dict) else None
                buf.append((wid, r["doi"], title, abstract, r["publication_date"],
                            r["publication_year"], r["type"], topic,
                            r["cited_by_count"], r["fwci"], r["is_retracted"],
                            title, abstract))
                if len(buf) >= 2000:
                    flush()
        flush()

        kept_n = sum(t.num_rows for t in kept_tables)
        if kept_tables:
            out = ARCHIVE / Path(part).parent.name
            out.mkdir(parents=True, exist_ok=True)
            pq.write_table(pa.concat_tables(kept_tables),
                           out / Path(part).name, compression="zstd")
        cur.execute("INSERT INTO openalex_snap_state (part, rows_total, kept) "
                    "VALUES (%s, %s, %s) ON CONFLICT (part) DO NOTHING",
                    (part, rows_total, kept_n))
        return (part, rows_total, kept_n, "")
    except Exception as e:  # noqa: BLE001 — Fehler je Datei melden, Lauf geht weiter
        return (part, 0, 0, f"{type(e).__name__}: {e}")
    finally:
        conn.close()


def main() -> int:
    import psycopg2
    import s3fs
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--max-files", type=int, default=0)
    args = ap.parse_args()

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    for stmt in DDL.split(";\n"):
        cur.execute(stmt)
    cur.execute("SELECT part FROM openalex_snap_state")
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
    print(f"{len(parts)} Part-Dateien gesamt, {len(done)} erledigt, "
          f"{len(todo)} zu tun", flush=True)

    t0 = time.time()
    tot_rows = tot_kept = files = 0
    from multiprocessing import Pool
    with Pool(args.workers) as pool:
        for part, rows, kept, err in pool.imap_unordered(process_part, todo):
            files += 1
            if err:
                print(f"FEHLER {part}: {err}", flush=True)
                continue
            tot_rows += rows
            tot_kept += kept
            if files % 10 == 0 or files == len(todo):
                rate = tot_kept / max(tot_rows, 1)
                frac = files / max(len(todo), 1)
                est_total = tot_kept / max(frac, 1e-9)
                cur2 = psycopg2.connect(db_mod.DATABASE_URL).cursor()
                cur2.execute("SELECT pg_size_pretty(pg_total_relation_size('research_corpus'))")
                size = cur2.fetchone()[0]
                cur2.connection.close()
                print(f"[{files}/{len(todo)} | {frac*100:.1f}%] keep {rate*100:.1f}% "
                      f"| {tot_kept:,} übernommen | DB {size} | Hochrechnung "
                      f"~{est_total/1e6:.0f}M | {time.time()-t0:.0f}s", flush=True)
            if not disk_ok():
                print("ABBRUCH: Platz-Wächter (HDD<150GB oder NVMe<100GB frei) "
                      "— Lauf ist resumable.", flush=True)
                pool.terminate()
                return 2
    print(f"FERTIG: {files} Dateien, {tot_kept:,} übernommen in "
          f"{(time.time()-t0)/3600:.1f}h", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
