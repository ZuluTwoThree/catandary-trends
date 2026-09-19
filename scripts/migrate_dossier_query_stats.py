#!/usr/bin/env python3
"""dossier_query_stats — Erfahrungsbasis je (Lückenart, Anfrage-Schablone) für
den Dossier-Rechercheur (Stufe 3 des Plans docs/plan_dossier_agent_2026-09-18.md;
Rechenregeln in pipeline/dossier_query_stats.py).

Self-contained additive Migration — wie scripts/migrate_dossier_source_priors.py
NICHT in db.init_db verdrahtet (Dossier-Tabellen sind Owner-Werkzeug).

⚠️  Additive Migrationsskripte laufen NIE automatisch auf der Live-DB. Nach
dem Merge einmal manuell ausführen (auf dem Host mit DATABASE_URL):

    .venv/bin/python scripts/migrate_dossier_query_stats.py             # Tabelle anlegen
    .venv/bin/python scripts/migrate_dossier_query_stats.py --backfill  # + aus allen Läufen rechnen

Ohne Tabelle liest der Planer den Prior 0,5 und der Lauf schreibt nichts
(Hinweis im Log, Lauf endet normal). Angelegt wird:

  dossier_query_stats — PK (gap_kind, template): n_used, n_hits, n_admitted,
                        n_read, n_cited, updated_at. Der Worker addiert am Ende
                        jedes Laufs; --backfill rechnet die Tabelle aus
                        `dossiers.result` NEU (löscht vorher).

Idempotent (CREATE TABLE IF NOT EXISTS) — sicher erneut auszuführen.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline import dossier_query_stats


def migrate(backfill: bool = False) -> None:
    dossier_query_stats.ensure_schema()
    backend = "PostgreSQL" if db_mod.USE_POSTGRES else "SQLite"
    print(f"OK: dossier_query_stats vorhanden ({backend}).")
    if backfill:
        from scripts import corpus_research as cr
        out = dossier_query_stats.backfill(
            entity_fn=lambda srcs, topic: cr.harvest_entities(srcs, topic)[0])
        print(f"Backfill: {out['runs']} Lauf/Läufe, {out['queries']} Anfragen → "
              f"{out['templates']} Schablonen "
              f"({', '.join(f'{k}={v}' for k, v in sorted(out['kinds'].items()))})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backfill", action="store_true",
                    help="Tabelle aus allen gespeicherten Läufen neu rechnen (löscht vorher)")
    a = ap.parse_args()
    migrate(backfill=a.backfill)
