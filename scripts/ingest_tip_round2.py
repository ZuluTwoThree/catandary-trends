#!/usr/bin/env python3
"""Ingest der PATSTAT-TIP-Exporte Runde 2 (#75).

Acht CSVs aus scripts/tip_round2_cell.py → acht tip_*-Referenztabellen.
Voll-Replace in einer Transaktion, wie ingest_tip_csv.py (Runde 1).

Bekannte Lücke: npl_share.median_lag_days kam leer zurück (npl_publn_date
liegt auf TIP in einem Format, das SAFE_CAST nicht parst — Diagnose-Query
für die nächste TIP-Session in #75). Die Spalte wird als NULL geladen.

    python scripts/ingest_tip_round2.py [--dir /mnt/data-hdd/taildrop]
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


def _i(v):
    return int(float(v)) if v not in ("", None) else None


def _f(v):
    return float(v) if v not in ("", None) else None


TABLES = {
    "npl_share.csv": (
        "tip_npl_share",
        """CREATE TABLE tip_npl_share (
             cpc_subclass TEXT NOT NULL, publn_year INTEGER NOT NULL,
             citations BIGINT NOT NULL, npl_citations BIGINT NOT NULL,
             median_lag_days INTEGER,
             PRIMARY KEY (cpc_subclass, publn_year))""",
        lambda r: (r["cpc_subclass"], _i(r["publn_year"]), _i(r["citations"]),
                   _i(r["npl_citations"]), _i(r["median_lag_days"])), 5),
    "survival.csv": (
        "tip_survival",
        """CREATE TABLE tip_survival (
             cpc_subclass TEXT NOT NULL, filing_year INTEGER NOT NULL,
             cohort_size INTEGER NOT NULL, age_years INTEGER NOT NULL,
             cessations INTEGER NOT NULL,
             PRIMARY KEY (cpc_subclass, filing_year, age_years))""",
        # age_years -1 = Kohorte ohne einziges Cease-Event (reine Nenner-Zeile
        # aus dem LEFT JOIN der Query; cohort_size zählt trotzdem)
        lambda r: (r["cpc_subclass"], _i(r["filing_year"]), _i(r["cohort_size"]),
                   _i(r["age_years"]) if r["age_years"] else -1,
                   _i(r["cessations"]) or 0), 5),
    "country_race.csv": (
        "tip_country_race",
        """CREATE TABLE tip_country_race (
             cpc_subclass TEXT NOT NULL, filing_year INTEGER NOT NULL,
             ctry TEXT NOT NULL, families INTEGER NOT NULL,
             PRIMARY KEY (cpc_subclass, filing_year, ctry))""",
        lambda r: (r["cpc_subclass"], _i(r["filing_year"]),
                   r["ctry"].strip(), _i(r["families"])), 4),
    "internationalization.csv": (
        "tip_internationalization",
        """CREATE TABLE tip_internationalization (
             cpc_subclass TEXT NOT NULL, filing_year INTEGER NOT NULL,
             families INTEGER NOT NULL, multi_office_families INTEGER NOT NULL,
             pct_families INTEGER NOT NULL, median_offices INTEGER,
             PRIMARY KEY (cpc_subclass, filing_year))""",
        lambda r: (r["cpc_subclass"], _i(r["filing_year"]), _i(r["families"]),
                   _i(r["multi_office_families"]), _i(r["pct_families"]),
                   _i(r["median_offices"])), 6),
    "collaborations.csv": (
        "tip_collaborations",
        """CREATE TABLE tip_collaborations (
             cpc_subclass TEXT NOT NULL, rank INTEGER NOT NULL,
             university TEXT NOT NULL, company TEXT NOT NULL,
             families INTEGER NOT NULL,
             PRIMARY KEY (cpc_subclass, rank))""",
        lambda r: (r["cpc_subclass"], _i(r["rank"]), r["university"],
                   r["company"], _i(r["families"])), 5),
    "cpc_groups.csv": (
        "tip_cpc_groups",
        """CREATE TABLE tip_cpc_groups (
             cpc_subclass TEXT NOT NULL, cpc_group TEXT NOT NULL,
             filing_year INTEGER NOT NULL, families INTEGER NOT NULL,
             PRIMARY KEY (cpc_subclass, cpc_group, filing_year))""",
        lambda r: (r["cpc_subclass"], r["cpc_group"], _i(r["filing_year"]),
                   _i(r["families"])), 4),
    "nace2_bridge.csv": (
        "tip_nace2_bridge",
        """CREATE TABLE tip_nace2_bridge (
             cpc_subclass TEXT NOT NULL, nace2_code TEXT NOT NULL,
             nace2_descr TEXT, applications BIGINT NOT NULL,
             weighted_applications DOUBLE PRECISION NOT NULL,
             PRIMARY KEY (cpc_subclass, nace2_code))""",
        lambda r: (r["cpc_subclass"], r["nace2_code"], r["nace2_descr"] or None,
                   _i(r["applications"]), _f(r["weighted_applications"])), 5),
    "ep_oppositions.csv": (
        "tip_ep_oppositions",
        """CREATE TABLE tip_ep_oppositions (
             cpc_subclass TEXT NOT NULL, event_year INTEGER NOT NULL,
             event_code TEXT NOT NULL, event_descr TEXT,
             applications INTEGER NOT NULL,
             PRIMARY KEY (cpc_subclass, event_year, event_code))""",
        lambda r: (r["cpc_subclass"], _i(r["event_year"]), r["event_code"],
                   r["event_descr"] or None, _i(r["applications"])), 5),
}


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
        with path.open(newline="", encoding="utf-8") as fh:
            rows = [rowfn(r) for r in csv.DictReader(fh)]
        if table == "tip_nace2_bridge":
            # tls902 führt je Code mehrere Beschreibungsvarianten → der Join
            # dupliziert (cpc, code). Summen zusammenfassen, erste Descr behalten.
            agg: dict[tuple, list] = {}
            for cs, code, descr, apps, w in rows:
                e = agg.setdefault((cs, code), [descr, 0, 0.0])
                e[0] = e[0] or descr
                e[1] += apps
                e[2] += w
            rows = [(cs, code, d, a, w) for (cs, code), (d, a, w) in sorted(agg.items())]
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(ddl)
        ph = ",".join(["%s"] * ncols)
        cur.executemany(f"INSERT INTO {table} VALUES ({ph})", rows)
        print(f"{table}: {len(rows):,} Zeilen")
    conn.commit()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
