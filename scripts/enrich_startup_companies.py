#!/usr/bin/env python3
"""Firmenstamm anreichern: GLEIF-LEI + Companies-House-Stammdaten (#87 §5.5-5.7).

Konservativ nach §4-Philosophie — nur EINDEUTIGE Treffer mit Länder-Gate:
- GLEIF: name_norm + Land (Legal- oder HQ-Adresse) muss passen, und es darf
  genau EINE aktive GLEIF-Entität auf den Schlüssel matchen. Setzt lei; bei
  GB-Treffern mit Companies-House-Registernummer auch ch_number (Stufe A!).
- Companies House: nur für Firmen mit country='GB'; eindeutiger name_norm-
  Treffer setzt ch_number, founded_date (exakt!), city.
Presse-only-Firmen ohne Land werden bewusst NICHT gegen CH/GLEIF gematcht —
ein US-Startup mit UK-Namensvetter wäre sonst falsch verortet.

    python scripts/enrich_startup_companies.py
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("enrich_startup_companies")

# GLEIF RegistrationAuthority-Codes, deren ra_entity_id die Companies-House-
# Nummer ist (RA000585 = Companies House England/Wales etc.)
CH_RA_IDS = ("RA000585", "RA000586", "RA000587", "RA000588")


def enrich_gleif() -> dict:
    st = {"lei": 0, "ch_from_gleif": 0}
    t0 = time.time()
    with get_connection() as conn:
        rows = conn.execute("""
            with cand as (
                select c.id as company_id, g.lei, g.ra_id, g.ra_entity_id,
                       count(*) over (partition by c.id) as n
                from startup_companies c
                join gleif_entities g on g.name_norm = c.name_norm
                where c.lei is null and c.country is not null
                  and c.name_norm != '' and length(c.name_norm) >= 4
                  and (g.country = c.country or g.hq_country = c.country)
                  and coalesce(g.status, 'ACTIVE') = 'ACTIVE'
            )
            select * from cand where n = 1
        """).fetchall()
        for x in rows:
            ch = (x["ra_entity_id"]
                  if x["ra_id"] in CH_RA_IDS and x["ra_entity_id"] else None)
            conn.execute(
                "update startup_companies set lei = ?, "
                "ch_number = coalesce(ch_number, ?) where id = ?",
                (x["lei"], ch, x["company_id"]))
            st["lei"] += 1
            if ch:
                st["ch_from_gleif"] += 1
    logger.info("GLEIF: %d LEIs gesetzt (%d davon mit CH-Nummer) in %.0fs",
                st["lei"], st["ch_from_gleif"], time.time() - t0)
    return st


def enrich_ch() -> dict:
    st = {"matched": 0}
    t0 = time.time()
    with get_connection() as conn:
        rows = conn.execute("""
            with cand as (
                select c.id as company_id, h.number, h.inc_date, h.city,
                       count(*) over (partition by c.id) as n
                from startup_companies c
                join ch_companies h on h.name_norm = c.name_norm
                where c.country = 'GB' and c.ch_number is null
                  and c.name_norm != '' and length(c.name_norm) >= 4
            )
            select * from cand where n = 1
        """).fetchall()
        for x in rows:
            conn.execute(
                "update startup_companies set ch_number = ?, "
                "founded_date = coalesce(founded_date, ?), "
                "city = coalesce(city, ?) where id = ?",
                (x["number"], x["inc_date"], x["city"], x["company_id"]))
            st["matched"] += 1
        # Zweiter Weg: ch_number kam aus GLEIF -> Gründungsdatum direkt joinen
        n = conn.execute("""
            update startup_companies c set founded_date = h.inc_date
            from ch_companies h
            where c.ch_number = h.number and c.founded_date is null
        """).rowcount
    logger.info("Companies House: %d Namens-Matches (GB), %s Gründungsdaten "
                "via CH-Nummer, in %.0fs", st["matched"], n, time.time() - t0)
    return st


def main() -> int:
    enrich_gleif()
    enrich_ch()
    with get_connection() as conn:
        r = conn.execute("""
            select count(*) total,
                   count(lei) lei, count(ch_number) ch,
                   count(founded_date) founded
            from startup_companies
        """).fetchone()
        logger.info("Stand: %s", dict(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
