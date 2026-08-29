#!/usr/bin/env python3
"""Startup-Firmenstamm + Event-Historie aufbauen (#87 Phase 1, Plan §4/§5.8).

Liest die vier Phase-0-Quellen und baut daraus die kanonischen Tabellen
`startup_companies` / `startup_aliases` / `startup_events` neu auf
(idempotenter Rebuild: TRUNCATE + Insert — solange Phase 3 keine Links
persistiert hat, ist das der einfachste konsistente Weg).

Die eigentliche Entity-Resolution (Loader, Group, merge, Corroboration,
Regexe) lebt seit #94 in `pipeline/startup_resolution.py` — importiert,
nicht kopiert, damit der additive Update-Pfad
(`scripts/update_startup_companies.py`) exakt dieselbe Auflösungslogik
nutzt. Dieses Skript und sein Verhalten sind dadurch UNVERÄNDERT: die
Loader werden hier wie vorher ohne Filter aufgerufen (voller Bestand).

Resolution konservativ nach Plan §4:
  Stufe A (hart):   Form D per CIK · SBIR per DUNS (aus data/sbir_award_data.csv)
                    · CORDIS per PIC. Innerhalb der Quelle fehlerfrei.
  Stufe B (Name+Gate): quellübergreifender Merge nur bei gleichem name_norm
                    UND kompatibler Geografie (US-State bzw. Land). Presse-
                    Runden tragen keine Geografie — sie mergen nur, wenn der
                    Namensschlüssel im Korpus EINDEUTIG ist und lang genug
                    (>=5 Zeichen; "Realize"-Befund 2026-08-21).
  Kein Fuzzy hier — Stufe C bleibt späteren Kandidaten-Vorschlägen vorbehalten.

    python scripts/build_startup_companies.py --dry-run
    python scripts/build_startup_companies.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.company_norm import norm_company_name
from pipeline.startup_resolution import (  # noqa: F401 (re-exported for tests/importers)
    Group, MIN_PRESS_KEY_LEN, SBIR_CSV, US_STATE_NAMES,
    _CORDIS_TITLE, _FORMD_GEO, _FORMD_TITLE, _PREFIX_GEO, _SBIR_TITLE,
    _corroborates_regd, _event, _geo_compatible, _us_state,
    load_cordis, load_formd, load_press, load_sbir, merge, parse_money,
)
from scripts.ingest_secform_d import INDUSTRY_VERTICAL
from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("build_startup_companies")


# ---------------------------------------------------------------- Schreiben

def write(groups: list[Group], dry_run: bool) -> None:
    groups = [g for g in groups if g.events]
    n_events = sum(len(g.events) for g in groups)
    multi = sum(1 for g in groups if len(g.events) >= 2)
    cross = sum(1 for g in groups if len(g.sources) >= 2)
    logger.info("Ergebnis: %d Firmen · %d Events · %d mit >=2 Events · %d quellübergreifend",
                len(groups), n_events, multi, cross)
    if dry_run:
        logger.info("DRY-RUN — nichts geschrieben.")
        return
    t0 = time.time()
    with get_connection() as conn:
        conn.execute("TRUNCATE startup_events, startup_aliases, "
                     "startup_patent_links, startup_research_links, "
                     "startup_companies RESTART IDENTITY CASCADE")
        comp_buf, alias_buf, event_buf = [], [], []
        next_id = 1
        for g in groups:
            name = g.display_name()
            dates = sorted(e["event_date"] for e in g.events)
            usd = [float(e["amount"]) for e in g.events
                   if e["amount"] and e["currency"] == "USD"
                   and not _corroborates_regd(e, g.events)]
            vert = INDUSTRY_VERTICAL.get((g.sector or "").upper())
            comp_buf.append((
                next_id, name[:500], norm_company_name(name)[:500],
                g.country, g.region, (g.city or None),
                g.website, g.sector, g.cik, g.duns, g.pic,
                g.employees, dates[0], dates[-1], len(g.events),
                sum(usd) if usd else None,
                json.dumps([vert] if vert else []),
            ))
            for alias in {n.strip() for n in g.names if n.strip() and n.strip() != name}:
                alias_buf.append((next_id, alias[:500], "phase0"))
            for e in g.events:
                event_buf.append((
                    next_id, e["event_type"], e["event_date"], e["amount"],
                    e["currency"], e["round_label"], json.dumps(e["investors"]),
                    json.dumps(e["meta"]), e["source"][:200], e["source_url"],
                    e["raw_entry_id"]))
            next_id += 1
        for i in range(0, len(comp_buf), 5000):
            conn.executemany(
                "INSERT INTO startup_companies (id, name, name_norm, country, region, "
                "city, website, sector, cik, duns, pic, employees, first_event_at, "
                "last_event_at, event_count, total_funding_usd, verticals) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                comp_buf[i:i + 5000])
        for i in range(0, len(alias_buf), 5000):
            conn.executemany(
                "INSERT OR IGNORE INTO startup_aliases (company_id, alias, source) "
                "VALUES (?, ?, ?)", alias_buf[i:i + 5000])
        for i in range(0, len(event_buf), 5000):
            conn.executemany(
                "INSERT OR IGNORE INTO startup_events (company_id, event_type, "
                "event_date, amount, currency, round_label, investors, meta, "
                "source, source_url, raw_entry_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", event_buf[i:i + 5000])
        conn.execute("SELECT setval('startup_companies_id_seq', ?)", (next_id,))
    logger.info("Geschrieben in %.0fs: %d Firmen, %d Aliasse, %d Events",
                time.time() - t0, len(comp_buf), len(alias_buf), len(event_buf))


def main() -> int:
    ap = argparse.ArgumentParser(description="Startup-Firmenstamm aufbauen (#87 Phase 1)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    all_groups = (list(load_formd().values()) + list(load_sbir().values())
                  + list(load_cordis().values()) + list(load_press().values()))
    merged = merge(all_groups)
    write(merged, args.dry_run)
    logger.info("Gesamt %.0fs", time.time() - t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
