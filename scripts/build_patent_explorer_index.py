#!/usr/bin/env python3
"""Materialize the Patent Explorer CPC browse index.

The Patent Explorer's technology facet cannot browse via `patent_cpc` directly:
the table has 128M rows, and "newest 25 patents in subclass X" degenerates into
either a huge EXISTS-probed index scan or a full sort (measured: >240s for
B64G). This script materializes `patent_explorer_cpc` — one row per
(curated subclass, patent) with the publication date — so the browse query is
a single (subclass, published DESC) index scan.

Curated set = build_cpc_insights.CURATED (23 technology axes) plus the
2026-08 taxonomy additions B64G / H10K / H01L that are not yet part of the
insights pages. Full rebuild with staging table + atomic swap, idempotent.
Refreshed weekly by weekly_patent_analytics.sh (after assign_cpc, so freshly
classified patents enter the same week).

    python scripts/build_patent_explorer_index.py
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
    import psycopg2
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
    cur.execute("""
        INSERT INTO patent_explorer_cpc_new
        SELECT DISTINCT pc.subclass, pc.pub_number,
               LEAST(r.published_date, NOW())::date
        FROM patent_cpc pc
        JOIN raw_entries r ON r.pub_number = pc.pub_number
        WHERE pc.subclass = ANY(%s)""", (subs,))
    n = cur.rowcount
    cur.execute("""CREATE INDEX ON patent_explorer_cpc_new
                   (subclass, published DESC)""")
    cur.execute("DROP TABLE patent_explorer_cpc")
    cur.execute("ALTER TABLE patent_explorer_cpc_new RENAME TO patent_explorer_cpc")
    conn.commit()
    cur.execute("ANALYZE patent_explorer_cpc")
    conn.commit()
    conn.close()
    print(f"patent_explorer_cpc: {n:,} Zeilen ({len(subs)} Subclasses) "
          f"in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
