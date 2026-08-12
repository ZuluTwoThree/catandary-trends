#!/usr/bin/env python3
"""Materialisierte Volltextsuche für den Patent Explorer (#78 Stufe 3).

Bis Stufe 2 lief die Suche über einen Ausdrucks-Index auf
`to_tsvector(title || excerpt)`. Das hat zwei Kosten, die sich nicht
wegkonfigurieren lassen:

  * **Phrasen- und Ausschluss-Anfragen** ("solid state" -lithium) brauchen
    einen Recheck, der den tsvector pro Kandidatenzeile NEU berechnet —
    gemessen 3,9–8,6 s, unabhängig davon, ob der Planer GIN oder den
    Datums-Index wählt.
  * **Ranking** kann Titel nicht höher gewichten als Abstract, weil im
    Ausdruck keine Gewichte stecken.

Diese Tabelle speichert den tsvector einmal — mit `setweight` (Titel A,
Abstract B). Der Recheck liest dann eine Spalte statt Text zu zerlegen, und
`ts_rank` bewertet Titeltreffer höher.

Aufbau bewusst als eigene Tabelle statt als Spalte in `raw_entries`: die ist
41 GB groß, ein UPDATE über 19,6M Zeilen würde sie durch tote Tupel
aufblähen und ein VACUUM FULL nötig machen. Die Suchtabelle trägt zusätzlich
`published`, damit die häufigste Abfrage (Filter + Sortierung nach Datum)
ganz ohne Join auskommt.

Inkrementell per Wasserstand (höchste bereits verarbeitete raw_entries.id) —
der wöchentliche Lauf verarbeitet nur die neuen Patente (~50–150k), statt
22 GB neu zu schreiben. Das ist zulässig, weil der Ingest bestehende Zeilen
nie anfasst (`INSERT … ON CONFLICT (url) DO NOTHING`, db.insert_raw_entries_batch)
— Titel und Abstract stehen nach dem ersten Einfügen fest, spätere
Amend-Lieferungen tragen nur CPC-Codes und Zitationen nach. Ändert sich das,
gehört hier ein `--rebuild` in den Cron.

    python scripts/build_patent_search_index.py            # inkrementell
    python scripts/build_patent_search_index.py --rebuild  # von vorn
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

BATCH = 250_000

DDL = """
CREATE TABLE IF NOT EXISTS patent_search (
    id         BIGINT PRIMARY KEY,
    pub_number TEXT NOT NULL,
    published  DATE,
    tsv        tsvector NOT NULL
)"""

# Titel wiegt A, Abstract B — ts_rank gewichtet A standardmäßig ~4x höher.
SELECT_ROWS = """
    SELECT r.id, r.pub_number, LEAST(r.published_date, NOW())::date,
           setweight(to_tsvector('english', left(coalesce(r.title, ''), 20000)), 'A') ||
           setweight(to_tsvector('english', left(coalesce(r.excerpt, ''), 80000)), 'B')
    FROM raw_entries r
    WHERE r.pub_number IS NOT NULL AND r.id > %s AND r.id <= %s"""


def main() -> int:
    import psycopg2
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true",
                    help="Tabelle verwerfen und komplett neu aufbauen")
    ap.add_argument("--batch", type=int, default=BATCH)
    args = ap.parse_args()

    t0 = time.time()
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    if args.rebuild:
        cur.execute("DROP TABLE IF EXISTS patent_search")
    cur.execute(DDL)

    cur.execute("SELECT coalesce(max(id), 0) FROM patent_search")
    watermark = cur.fetchone()[0]
    cur.execute("SELECT coalesce(max(id), 0) FROM raw_entries WHERE pub_number IS NOT NULL")
    top = cur.fetchone()[0]
    print(f"Wasserstand {watermark:,} → {top:,}", flush=True)

    done = 0
    lo = watermark
    while lo < top:
        hi = min(lo + args.batch, top)
        cur.execute(f"INSERT INTO patent_search (id, pub_number, published, tsv) "
                    f"{SELECT_ROWS} ON CONFLICT (id) DO NOTHING", (lo, hi))
        done += cur.rowcount
        lo = hi
        pct = 100.0 * (lo - watermark) / max(1, top - watermark)
        print(f"  id ≤ {lo:,} ({pct:.1f}%) — {done:,} Zeilen, "
              f"{time.time()-t0:.0f}s", flush=True)

    # Indizes erst nach dem Voll-Aufbau anlegen (schneller als inkrementelles
    # Pflegen während Millionen Inserts); beim inkrementellen Lauf existieren
    # sie bereits und IF NOT EXISTS greift.
    print("Indizes ...", flush=True)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_patent_search_tsv "
                "ON patent_search USING gin (tsv)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_patent_search_published "
                "ON patent_search (published DESC)")
    cur.execute("ANALYZE patent_search")
    cur.execute("SELECT COUNT(*), pg_size_pretty(pg_total_relation_size('patent_search')) "
                "FROM patent_search")
    n, size = cur.fetchone()
    conn.close()
    print(f"patent_search: {n:,} Zeilen ({done:,} neu), {size}, "
          f"{time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
