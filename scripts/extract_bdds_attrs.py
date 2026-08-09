#!/usr/bin/env python3
"""Extract family-id + applicant names from the archived BDDS DOCDB zips (#7).

The 205-GB back-file on /mnt/data-hdd/bdds_backfile contains BOTH attributes we
were about to buy from PATSTAT (2026-08-09 finding): every exch:exchange-document
carries a `family-id` attribute (DOCDB simple family) and applicant names in up
to three data-formats. Our original ingest never stored either — this re-parse
extracts JUST those two things into:

    patent_family(pub_number PK, family_id)         + index on family_id
    patent_assignee_raw(pub_number, seq, name, fmt) PK (pub_number, seq)

Filtered to OUR pub_numbers: the back-file is the whole world DOCDB (~350M
documents across 162 zips — the smoke run yielded 2.2M rows from ONE zip), so
unfiltered tables would balloon past 40 GB for data we mostly never touch.
The 18.7M-entry pub_number set loads once and is shared with the fork-based
workers via copy-on-write. Resumable via bdds_attr_state (one row per inner zip).
Applicant format preference per (doc, seq): docdba (ASCII) > original > docdb.

    python scripts/extract_bdds_attrs.py --limit-outer 1 --workers 1   # smoke
    python scripts/extract_bdds_attrs.py --workers 3                   # full run
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402

BACKFILE_DIR = Path("/mnt/data-hdd/bdds_backfile")
PUB_SET: set[str] = set()  # unsere pub_numbers; von Workern per fork/COW geteilt
EXCH = "{http://www.epo.org/exchange}"
FMT_PREF = {"docdba": 0, "original": 1, "docdb": 2}
BATCH = 5000

# DOCDB-XMLs referenzieren docdb-entities.dtd (&alpha; usw.) — ElementTree löst
# keine externen Entities auf. Der Alt-Ingest ÜBERSPRANG solche Dateien komplett
# (except ParseError: continue). Wir ersetzen unbekannte Entities durch ihren
# Namen (Titel/Abstracts interessieren hier nicht, Attribute nie betroffen).
ENTITY_RE = re.compile(rb"&(?!amp;|lt;|gt;|quot;|apos;|#)([a-zA-Z][a-zA-Z0-9._-]*);")


def ensure_tables() -> None:
    import psycopg2
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS patent_family (
        pub_number TEXT PRIMARY KEY, family_id BIGINT NOT NULL)""")
    cur.execute("""CREATE INDEX IF NOT EXISTS idx_patent_family_fid
        ON patent_family(family_id)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS patent_assignee_raw (
        pub_number TEXT, seq SMALLINT, name TEXT, fmt TEXT,
        PRIMARY KEY (pub_number, seq))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bdds_attr_state (
        inner_name TEXT PRIMARY KEY, outer_name TEXT, docs INT,
        ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()


def parse_inner(xml_bytes: bytes):
    """One inner DOCDB xml → (fam_rows, asg_rows)."""
    fam, asg = [], []
    xml_bytes = ENTITY_RE.sub(rb"\1", xml_bytes)
    for _, doc in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
        if doc.tag != f"{EXCH}exchange-document":
            continue
        c, n, k = doc.get("country", ""), doc.get("doc-number", ""), doc.get("kind", "")
        fid = doc.get("family-id")
        if c and n and k:
            pub = f"{c}-{n}-{k}"
            if PUB_SET and pub not in PUB_SET:
                doc.clear()
                continue
            if fid and fid.isdigit():
                fam.append((pub, int(fid)))
            # applicants: best format per sequence
            best: dict[int, tuple[int, str]] = {}
            for ap in doc.iter(f"{EXCH}applicant"):
                fmt = ap.get("data-format", "docdb")
                try:
                    seq = int(ap.get("sequence", "0"))
                except ValueError:
                    continue
                nm = ap.find(f"{EXCH}applicant-name/name")
                if nm is None:
                    nm = ap.find("applicant-name/name")
                name = (nm.text or "").strip() if nm is not None else ""
                if not name:
                    continue
                rank = FMT_PREF.get(fmt, 9)
                if seq not in best or rank < best[seq][0]:
                    best[seq] = (rank, f"{name}\x00{fmt}")
            for seq, (_, packed) in best.items():
                name, fmt = packed.split("\x00")
                asg.append((pub, seq, name[:500], fmt))
        doc.clear()
    return fam, asg


def process_outer(outer_path: str) -> dict:
    """Worker: one outer zip, own DB connection, resume via state table."""
    import psycopg2
    from psycopg2.extras import execute_values
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor()
    st = {"inner": 0, "skipped": 0, "docs": 0, "fam": 0, "asg": 0}
    outer_name = Path(outer_path).name
    with zipfile.ZipFile(outer_path) as oz:
        inners = [i for i in oz.namelist() if i.startswith("Root/DOC/") and i.endswith(".zip")]
        for inner in inners:
            inner_name = Path(inner).name
            cur.execute("SELECT 1 FROM bdds_attr_state WHERE inner_name = %s", (inner_name,))
            if cur.fetchone():
                st["skipped"] += 1
                continue
            try:
                with oz.open(inner) as ih:
                    with zipfile.ZipFile(io.BytesIO(ih.read())) as iz:
                        xml_name = next((x for x in iz.namelist() if x.endswith(".xml")), None)
                        if not xml_name:
                            continue
                        fam, asg = parse_inner(iz.read(xml_name))
            except (zipfile.BadZipFile, ET.ParseError) as exc:
                print(f"  PARSE-SKIP {inner_name}: {type(exc).__name__}: {exc}")
                st.setdefault("parse_errors", 0)
                st["parse_errors"] += 1
                continue
            for i in range(0, len(fam), BATCH):
                execute_values(cur, "INSERT INTO patent_family (pub_number, family_id) "
                               "VALUES %s ON CONFLICT DO NOTHING", fam[i:i + BATCH])
            for i in range(0, len(asg), BATCH):
                execute_values(cur, "INSERT INTO patent_assignee_raw (pub_number, seq, name, fmt) "
                               "VALUES %s ON CONFLICT DO NOTHING", asg[i:i + BATCH])
            cur.execute("INSERT INTO bdds_attr_state (inner_name, outer_name, docs) "
                        "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                        (inner_name, outer_name, len(fam)))
            conn.commit()
            st["inner"] += 1
            st["docs"] += len(fam)
            st["fam"] += len(fam)
            st["asg"] += len(asg)
    conn.close()
    return {"outer": outer_name, **st}


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract family-id + applicants from BDDS back-file")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--limit-outer", type=int, default=0, help="smoke test: only N outer zips")
    args = ap.parse_args()

    ensure_tables()
    global PUB_SET
    t_load = time.time()
    import psycopg2
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor("pubs")
    cur.itersize = 500_000
    cur.execute("SELECT pub_number FROM raw_entries WHERE pub_number IS NOT NULL")
    PUB_SET = {r[0] for r in cur}
    conn.close()
    print(f"pub_number-Set: {len(PUB_SET):,} geladen in {time.time()-t_load:.0f}s")
    outers = sorted(str(p) for p in BACKFILE_DIR.glob("*.zip"))
    if args.limit_outer:
        outers = outers[:args.limit_outer]
    print(f"{len(outers)} outer zips · {args.workers} workers")
    t0 = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_outer, o): o for o in outers}
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            print(f"[{done}/{len(outers)}] {r['outer']}: inner {r['inner']} "
                  f"(+{r['skipped']} skip) · fam {r['fam']:,} · asg {r['asg']:,} "
                  f"· {time.time()-t0:.0f}s")
    print(f"FERTIG in {(time.time()-t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
