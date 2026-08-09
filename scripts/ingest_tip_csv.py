#!/usr/bin/env python3
"""Ingest der PATSTAT-TIP-Exporte (#14, Issue #7).

Liest die 4 CSVs, die der Owner auf tip.epo.org mit scripts/tip_queries.sql
erzeugt und per Taildrop geschickt hat, in Referenz-Tabellen:

  leading_applicants.csv → tip_leading_applicants  (Top-50 PSN-Anmelder je Achse)
  sector_shares.csv      → tip_sector_shares       (Sektor × Achse × Anmeldejahr)
  legal_event_curve.csv  → tip_legal_event_curve   (INPADOC-Kategorie × Achse × Jahr)
  publn_volume.csv       → tip_publn_volume        (Amt × Jahr — Dichte-Kalibrierung)

Das sind die PATSTAT-Deltas, die unser BDDS-Eigenbestand nicht hat
(harmonisierte PSN-Namen + Sektoren, Rechtsstands-Kurven in der Breite) —
der Ersatz für den 2.700-€-Bulk-Kauf. Voll-Replace pro Tabelle in einer
Transaktion; PATSTAT-Platzhalterjahr 9999 (= Datum unbekannt) wird gefiltert.

    python scripts/ingest_tip_csv.py [--dir /mnt/data-hdd/taildrop]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402

TABLES = {
    "leading_applicants.csv": (
        "tip_leading_applicants",
        """CREATE TABLE tip_leading_applicants (
             cpc_subclass TEXT NOT NULL,
             rank INTEGER NOT NULL,
             psn_name TEXT NOT NULL,
             psn_sector TEXT,
             ctry TEXT,
             families INTEGER NOT NULL,
             PRIMARY KEY (cpc_subclass, rank))""",
        lambda r: (r["cpc_subclass"], int(r["rank"]), r["psn_name"],
                   r["psn_sector"] or None, r["person_ctry_code"] or None,
                   int(r["families"])),
        6,
    ),
    "sector_shares.csv": (
        "tip_sector_shares",
        """CREATE TABLE tip_sector_shares (
             cpc_subclass TEXT NOT NULL,
             filing_year INTEGER NOT NULL,
             psn_sector TEXT NOT NULL,
             families INTEGER NOT NULL,
             PRIMARY KEY (cpc_subclass, filing_year, psn_sector))""",
        lambda r: (r["cpc_subclass"], int(r["filing_year"]),
                   r["psn_sector"] or "UNKNOWN", int(r["families"])),
        4,
    ),
    "legal_event_curve.csv": (
        "tip_legal_event_curve",
        """CREATE TABLE tip_legal_event_curve (
             cpc_subclass TEXT NOT NULL,
             event_year INTEGER NOT NULL,
             event_category TEXT NOT NULL,
             events INTEGER NOT NULL,
             PRIMARY KEY (cpc_subclass, event_year, event_category))""",
        lambda r: (r["cpc_subclass"], int(r["event_year"]),
                   r["event_category"], int(r["events"])),
        4,
    ),
    "publn_volume.csv": (
        "tip_publn_volume",
        """CREATE TABLE tip_publn_volume (
             publn_auth TEXT NOT NULL,
             publn_year INTEGER NOT NULL,
             publications BIGINT NOT NULL,
             PRIMARY KEY (publn_auth, publn_year))""",
        lambda r: (r["publn_auth"], int(r["publn_year"]),
                   int(r["publications"])),
        3,
    ),
}

YEAR_COLS = {"filing_year", "event_year", "publn_year"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/mnt/data-hdd/taildrop")
    args = ap.parse_args()
    src = Path(args.dir)

    import psycopg2
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor()
    for fname, (table, ddl, rowfn, ncols) in TABLES.items():
        path = src / fname
        if not path.exists():
            print(f"FEHLT: {path} — übersprungen")
            continue
        rows, dropped = [], 0
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if any(r.get(c) == "9999" for c in YEAR_COLS):
                    dropped += 1
                    continue
                rows.append(rowfn(r))
        if table == "tip_sector_shares":
            # PATSTAT liefert leeren UND literalen 'UNKNOWN'-Sektor — beides
            # heißt "nicht harmonisiert klassifiziert" → zusammenfassen.
            agg: dict[tuple, int] = {}
            for cs, yr, sec, fam in rows:
                agg[(cs, yr, sec)] = agg.get((cs, yr, sec), 0) + fam
            rows = [(cs, yr, sec, fam) for (cs, yr, sec), fam in sorted(agg.items())]
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(ddl)
        ph = ",".join(["%s"] * ncols)
        cur.executemany(f"INSERT INTO {table} VALUES ({ph})", rows)
        print(f"{table}: {len(rows):,} Zeilen"
              + (f" ({dropped} × Jahr-9999 gefiltert)" if dropped else ""))
    conn.commit()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
