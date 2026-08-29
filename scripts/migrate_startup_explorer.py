#!/usr/bin/env python3
"""Schema für den Startup Explorer (#87, Phase 1) — idempotent.

Legt die Korpus-Tabellen (startup_companies/aliases/events/links) und die
Resolution-Backbones (gleif_entities, ch_companies) an. Additiv; gehört wie
alle Zusatzmigrationen NICHT in init_db (siehe prod-db-migration-gap-Memory)
und wird manuell bzw. von den Ingestern selbst aufgerufen.

    python scripts/migrate_startup_explorer.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("migrate_startup_explorer")

DDL = [
    # Kanonische Firma. IDs sind Stufe-A-Anker (§4); jede kann NULL sein,
    # aber wo vorhanden identifiziert sie die Firma hart.
    """CREATE TABLE IF NOT EXISTS startup_companies (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        name_norm TEXT NOT NULL,
        country TEXT, region TEXT, city TEXT,
        website TEXT,
        founded_date DATE,
        founded_bucket TEXT,
        sector TEXT,
        verticals JSONB DEFAULT '[]',
        cik TEXT, duns TEXT, pic TEXT, lei TEXT, ch_number TEXT,
        wikidata_qid TEXT,
        employees INTEGER,
        first_event_at DATE, last_event_at DATE,
        event_count INTEGER DEFAULT 0,
        total_funding_usd NUMERIC,
        embedding_1024 VECTOR(1024),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sc_name_norm ON startup_companies (name_norm)",
    "CREATE INDEX IF NOT EXISTS idx_sc_country ON startup_companies (country)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sc_cik ON startup_companies (cik) WHERE cik IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sc_pic ON startup_companies (pic) WHERE pic IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_sc_duns ON startup_companies (duns) WHERE duns IS NOT NULL",
    # Nachträglich (Wikidata-Enrichment): Gründer-Personen — einzige freie Quelle
    "ALTER TABLE startup_companies ADD COLUMN IF NOT EXISTS founders JSONB DEFAULT '[]'",
    # Nachträglich (manueller Merge-Audit nach dem Rebuild, Plan §7): markiert
    # Fondsvehikel/Presse-Namensartefakte, die trotz der Ausschluss-Filter in
    # ingest_secform_d.py/extract_press_rounds.py durchgerutscht sind. War auf
    # der Live-DB bereits vorhanden, aber nie in dieser Migration nachgezogen
    # (Doku-Drift, #94) — Werte 'fund_vehicle'/'press_name_artifact' werden seit
    # #94 zusätzlich automatisiert von scripts/update_startup_companies.py für
    # NEU angelegte Firmen gesetzt (pipeline.company_norm.classify_new_company_exclusion).
    "ALTER TABLE startup_companies ADD COLUMN IF NOT EXISTS excluded TEXT",

    # Namensvarianten je Firma (Quelle + Original-Schreibweise).
    """CREATE TABLE IF NOT EXISTS startup_aliases (
        company_id INTEGER NOT NULL REFERENCES startup_companies(id) ON DELETE CASCADE,
        alias TEXT NOT NULL,
        source TEXT NOT NULL,
        PRIMARY KEY (company_id, alias, source)
    )""",

    # Datierte Events; source_url = Quellennennung (Pflicht, Repo-Prinzip).
    """CREATE TABLE IF NOT EXISTS startup_events (
        id SERIAL PRIMARY KEY,
        company_id INTEGER NOT NULL REFERENCES startup_companies(id) ON DELETE CASCADE,
        event_type TEXT NOT NULL CHECK (event_type IN (
            'regd_offering','sbir_award','grant','press_round','trademark',
            'launch','clinical','fda_clearance','gov_contract')),
        event_date DATE NOT NULL,
        amount NUMERIC,
        currency TEXT,
        round_label TEXT,
        investors JSONB DEFAULT '[]',
        meta JSONB DEFAULT '{}',
        source TEXT NOT NULL,
        source_url TEXT NOT NULL,
        raw_entry_id INTEGER,
        UNIQUE (company_id, event_type, event_date, source_url)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_se_company ON startup_events (company_id, event_date)",
    "CREATE INDEX IF NOT EXISTS idx_se_type ON startup_events (event_type)",

    # Brücken (Phase 3 füllt sie; Schema jetzt, damit §4 komplett steht).
    """CREATE TABLE IF NOT EXISTS startup_patent_links (
        company_id INTEGER NOT NULL REFERENCES startup_companies(id) ON DELETE CASCADE,
        pub_number TEXT NOT NULL,
        match_method TEXT NOT NULL,
        match_score REAL,
        PRIMARY KEY (company_id, pub_number)
    )""",
    """CREATE TABLE IF NOT EXISTS startup_research_links (
        company_id INTEGER NOT NULL REFERENCES startup_companies(id) ON DELETE CASCADE,
        openalex_id TEXT NOT NULL,
        kind TEXT,
        match_method TEXT NOT NULL,
        match_score REAL,
        PRIMARY KEY (company_id, openalex_id)
    )""",

    # GLEIF-Backbone (CC0): LEI <-> nationale Register-IDs.
    """CREATE TABLE IF NOT EXISTS gleif_entities (
        lei TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        name_norm TEXT NOT NULL,
        country TEXT, city TEXT,
        hq_country TEXT, hq_city TEXT,
        ra_id TEXT, ra_entity_id TEXT,
        category TEXT, status TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_gleif_name_norm ON gleif_entities (name_norm)",
    "CREATE INDEX IF NOT EXISTS idx_gleif_ra_entity ON gleif_entities (ra_entity_id) WHERE ra_entity_id IS NOT NULL",

    # Companies-House-Subset (OGL): UK-Stammdaten mit Gründungsdatum + SIC.
    """CREATE TABLE IF NOT EXISTS ch_companies (
        number TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        name_norm TEXT NOT NULL,
        city TEXT, postcode TEXT,
        status TEXT, category TEXT,
        inc_date DATE,
        sic JSONB DEFAULT '[]'
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ch_name_norm ON ch_companies (name_norm)",
]


def main() -> int:
    with get_connection() as conn:
        for stmt in DDL:
            conn.execute(stmt)
    logger.info("Startup-Explorer-Schema angelegt/aktuell (%d Statements).", len(DDL))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
