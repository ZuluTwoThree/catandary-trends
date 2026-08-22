#!/usr/bin/env python3
"""Firma→Patent- und Firma→Research-Brücke (#87 Phase 3, Plan §5.10/§5.11).

Patent-Brücke, zweistufig nach §4:
  1. Exakter normalisierter Namens-Match (KEIN Substring — der
     "Realize"-Befund) über eine einmalig aufgebaute Hilfstabelle
     patent_assignee_norm (4,3M distinkte Anmelder-Namen, Python-normiert
     mit derselben Funktion wie der Firmenstamm). score 0.5, method
     'name_norm' — im Frontend NICHT als belegte Substanz gezählt.
  2. Tech-Bestätigung: hat mindestens ein gematchtes Patent eine
     CPC-Subklasse, die zum Vertical der Firma passt, steigen ALLE
     Patente des Paars auf score 0.9 / 'name+tech' — erst das zählt.

Schutzgates: nur eindeutige Firmen-Namensschlüssel >= 6 Zeichen; Norm-
Schlüssel mit > 15 Anmelder-Schreibvarianten gelten als generisch und
werden übersprungen (z. B. "advanced technology").

Research-Brücke: exakter Norm-Match gegen research_institutions MIT
Länder-Gate; kind='institution_name' (die Institutions-Tabellen sind
namens-gekeyt).

    python scripts/build_startup_links.py
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.company_norm import norm_company_name
from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("build_startup_links")

MIN_KEY_LEN = 6
MAX_NAME_VARIANTS = 15

# Grobe CPC-Subklassen→Vertical-Kompatibilität — nur fürs Bestätigungs-Gate,
# keine Klassifikation. Präfix-Match auf die 4-stellige Subklasse.
CPC_VERTICAL = {
    "HEALTH": ("A61", "C12", "C07", "G16H", "B01L"),
    "TECH": ("G06", "H01", "H03", "H04", "G05", "G02", "G01", "B25J",
             "G16Y", "H10", "G11", "B64G", "G21"),
    "ECO": ("H02", "H01M", "C25B", "F03D", "B09B", "B60L", "C02F", "F24S"),
    "FOOD": ("A23", "A01", "A21", "A22"),
    "BIZ": ("G06Q",),
    "FASHION": ("A41", "A42", "A43", "A44", "A45D", "D01", "D02", "D03",
                "D04", "D06"),
    "DESIGN": ("B44", "F21", "A47"),
    "LIFESTYLE": ("A63",),
}


def ensure_assignee_norm() -> None:
    with get_connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS patent_assignee_norm ("
                     "name TEXT PRIMARY KEY, name_norm TEXT)")
        n = conn.execute("select count(*) c from patent_assignee_norm").fetchone()["c"]
    if n > 0:
        logger.info("patent_assignee_norm vorhanden (%d Namen).", n)
        return
    t0 = time.time()
    logger.info("Baue patent_assignee_norm (einmalig, 4,3M Namen)…")
    with get_connection() as conn:
        rows = conn.execute("select distinct name from patent_assignee_raw "
                            "where name is not null").fetchall()
    logger.info("  %d distinkte Namen geladen (%.0fs)", len(rows), time.time() - t0)
    buf = []
    with get_connection() as conn:
        for x in rows:
            nn = norm_company_name(x["name"])
            if len(nn) >= MIN_KEY_LEN:
                buf.append((x["name"], nn))
            if len(buf) >= 10000:
                conn.executemany("INSERT OR IGNORE INTO patent_assignee_norm "
                                 "(name, name_norm) VALUES (?, ?)", buf)
                buf = []
        if buf:
            conn.executemany("INSERT OR IGNORE INTO patent_assignee_norm "
                             "(name, name_norm) VALUES (?, ?)", buf)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pan_norm "
                     "ON patent_assignee_norm (name_norm)")
    logger.info("  fertig in %.0fs", time.time() - t0)


def build_patent_links() -> None:
    t0 = time.time()
    with get_connection() as conn:
        conn.execute("TRUNCATE startup_patent_links")
        # Stufe 1: exakter Norm-Match, generische Schlüssel raus
        conn.execute(f"""
            insert into startup_patent_links (company_id, pub_number, match_method, match_score)
            select distinct c.id, par.pub_number, 'name_norm', 0.5
            from (
                select id, name_norm from startup_companies
                where excluded is null and length(name_norm) >= {MIN_KEY_LEN}
                  and name_norm in (select name_norm from startup_companies
                                    group by name_norm having count(*) = 1)
            ) c
            join (
                select name, name_norm from patent_assignee_norm
                where name_norm in (select name_norm from patent_assignee_norm
                                    group by name_norm
                                    having count(*) <= {MAX_NAME_VARIANTS})
            ) pan on pan.name_norm = c.name_norm
            join patent_assignee_raw par on par.name = pan.name
            on conflict do nothing
        """)
        n1 = conn.execute("select count(*) c, count(distinct company_id) f "
                          "from startup_patent_links").fetchone()
        logger.info("Stufe 1: %s Kanten für %s Firmen (%.0fs)",
                    n1["c"], n1["f"], time.time() - t0)
        # Stufe 2: Tech-Bestätigung über CPC↔Vertical
        pairs = [(v, p) for v, prefixes in CPC_VERTICAL.items() for p in prefixes]
        values = ", ".join(f"('{v}', '{p}')" for v, p in pairs)
        conn.execute(f"""
            with compat as (
                select distinct l.company_id
                from startup_patent_links l
                join startup_companies c on c.id = l.company_id
                join patent_explorer_cpc pc on pc.pub_number = l.pub_number
                join (values {values}) as m(vertical, prefix)
                  on strpos(pc.subclass, m.prefix) = 1
                where c.verticals @> jsonb_build_array(m.vertical)
            )
            update startup_patent_links l
            set match_method = 'name+tech', match_score = 0.9
            from compat where compat.company_id = l.company_id
        """)
        n2 = conn.execute("select count(distinct company_id) f from startup_patent_links "
                          "where match_score >= 0.9").fetchone()
        logger.info("Stufe 2: %s Firmen tech-bestätigt (%.0fs)", n2["f"], time.time() - t0)


def build_research_links() -> None:
    """Python-Matching: research_institutions ist klein genug, und nur so ist
    die Normalisierung identisch mit dem Firmenstamm (norm_company_name)."""
    t0 = time.time()
    with get_connection() as conn:
        inst = conn.execute("select institution, country, n "
                            "from research_institutions").fetchall()
        comps = conn.execute(f"""
            select id, name_norm, country from startup_companies
            where excluded is null and country is not null
              and length(name_norm) >= {MIN_KEY_LEN}
              and name_norm in (select name_norm from startup_companies
                                group by name_norm having count(*) = 1)
        """).fetchall()
    from collections import defaultdict
    by_key = defaultdict(list)
    for x in inst:
        nn = norm_company_name(x["institution"])
        if len(nn) >= MIN_KEY_LEN:
            by_key[(nn, (x["country"] or "").upper())].append(x)
    links = []
    for c in comps:
        hits = by_key.get((c["name_norm"], (c["country"] or "").upper()), [])
        if len(hits) == 1:
            links.append((c["id"], hits[0]["institution"][:500],
                          "institution_name", "name+country", 0.9))
    with get_connection() as conn:
        conn.execute("TRUNCATE startup_research_links")
        for i in range(0, len(links), 2000):
            conn.executemany(
                "INSERT OR IGNORE INTO startup_research_links (company_id, "
                "openalex_id, kind, match_method, match_score) VALUES (?,?,?,?,?)",
                links[i:i + 2000])
    logger.info("Research-Brücke: %d Kanten (%.0fs)", len(links), time.time() - t0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Startup-Brücken (#87 Phase 3)")
    ap.parse_args()
    ensure_assignee_norm()
    build_patent_links()
    build_research_links()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
