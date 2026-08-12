#!/usr/bin/env python3
"""Materialize the Patent Explorer CPC browse index.

The Patent Explorer's technology facet cannot browse via `patent_cpc` directly:
the table has 128M rows, and "newest 25 patents in subclass X" degenerates into
either a huge EXISTS-probed index scan or a full sort (measured: >240s for
B64G). This script materializes `patent_explorer_cpc` — one row per
(curated subclass, patent) with the publication date — so the browse query is
a single (subclass, published DESC) index scan.

Seit #78 Stufe 2 werden ALLE Subclasses materialisiert (~650, ~70M Zeilen),
nicht mehr nur die 26 kuratierten Achsen — freie CPC-Eingaben im Suchfeld
brauchen denselben schnellen Pfad. `--curated-only` stellt den alten,
schlankeren Stand wieder her (26 Achsen, ~9M Zeilen).

Full rebuild mit Staging-Tabelle + atomarem Swap, idempotent. Wöchentlich
von weekly_patent_analytics.sh aufgerufen (nach assign_cpc, damit frisch
klassifizierte Patente in derselben Woche browsebar werden).

    python scripts/build_patent_explorer_index.py
    python scripts/build_patent_explorer_index.py --curated-only
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402
from scripts.build_cpc_insights import CURATED  # noqa: E402

EXTRA_SUBCLASSES = [
    ("B64G", "Spacecraft & Space Technology", "TECH"),
    ("H10K", "Organic & Hybrid Electronics", "TECH"),
    ("H01L", "Semiconductor Devices", "TECH"),
]


def explorer_subclasses() -> list[str]:
    return [sc for sc, _, _ in CURATED] + [sc for sc, _, _ in EXTRA_SUBCLASSES]


def main() -> int:
    import argparse
    import psycopg2
    ap = argparse.ArgumentParser()
    ap.add_argument("--curated-only", action="store_true",
                    help="nur die 26 kuratierten Achsen (alter Stand vor #78 Stufe 2)")
    args = ap.parse_args()
    subs = explorer_subclasses()
    t0 = time.time()
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS patent_explorer_cpc (
            subclass   TEXT NOT NULL,
            pub_number TEXT NOT NULL,
            published  DATE
        )""")
    cur.execute("DROP TABLE IF EXISTS patent_explorer_cpc_new")
    cur.execute("CREATE TABLE patent_explorer_cpc_new (LIKE patent_explorer_cpc)")
    # DISTINCT: patent_cpc ist auf (pub_number, cpc) eindeutig — pro Subclass
    # kann ein Patent mehrere Gruppen tragen (G06N10/20 + G06N10/40 etc.).
    #
    # Seit #78 Stufe 2 ALLE Subclasses (~650, ~70M Zeilen) statt nur der 26
    # kuratierten: sonst laufen freie CPC-Eingaben im Suchfeld entweder in
    # einen >240s-Scan oder in einen irreführenden Nulltreffer.
    if args.curated_only:
        cur.execute("""
            INSERT INTO patent_explorer_cpc_new
            SELECT DISTINCT pc.subclass, pc.pub_number,
                   LEAST(r.published_date, NOW())::date
            FROM patent_cpc pc
            JOIN raw_entries r ON r.pub_number = pc.pub_number
            WHERE pc.subclass = ANY(%s)""", (subs,))
    else:
        # subclass IS NOT NULL: 5,9 Mio. Zeilen (4,6 %) tragen keine Subclass —
        # überwiegend japanische F-Term-/FI-Codes ('3E068/AA40'), die keine CPC
        # sind, plus ein Rest CPC-Codes mit verirrter führender Ziffer
        # ('4F21S43/237'). Per Subclass browsebar ist beides nicht; die
        # Recovery des zweiten Teils ist ein eigener Datenqualitäts-Fix.
        cur.execute("""
            INSERT INTO patent_explorer_cpc_new
            SELECT DISTINCT pc.subclass, pc.pub_number,
                   LEAST(r.published_date, NOW())::date
            FROM patent_cpc pc
            JOIN raw_entries r ON r.pub_number = pc.pub_number
            WHERE pc.subclass IS NOT NULL""")
    n = cur.rowcount
    cur.execute("""CREATE INDEX ON patent_explorer_cpc_new
                   (subclass, published DESC)""")
    cur.execute("DROP TABLE patent_explorer_cpc")
    cur.execute("ALTER TABLE patent_explorer_cpc_new RENAME TO patent_explorer_cpc")
    conn.commit()
    cur.execute("ANALYZE patent_explorer_cpc")
    conn.commit()
    conn.close()
    scope = f"{len(subs)} kuratierte" if args.curated_only else "alle"
    print(f"patent_explorer_cpc: {n:,} Zeilen ({scope} Subclasses) "
          f"in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
