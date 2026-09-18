#!/usr/bin/env python3
"""Stufe 1 des Dossier-Agent-Plans (2026-09-19): Auftrags-Intake und
Owner-Checkpoint — Spalten und Status auf dossier_orders.

Self-contained additive Migration — NICHT in db.init_db verdrahtet (gleiches
Muster wie scripts/migrate_dossier_orders.py / migrate_dossier_run_outcomes.py):
ein Merge fasst die laufende Pipeline nicht an.

⚠️  Wie alle additiven Migrationen in diesem Repo läuft dieses Skript NIE
automatisch. Nach dem Merge EINMAL von Hand gegen die Live-DB:

    .venv/bin/python scripts/migrate_dossier_brief.py

Was es tut (idempotent, sicher erneut auszuführen):

  dossier_orders.brief_json    JSONB  — strukturierter Auftrag (pipeline/dossier_brief.Brief)
  dossier_orders.plan_json     JSONB  — Rechercheplan (+ Landkarte im Landschafts-Modus)
  dossier_orders.profile_json  JSONB  — Feldprofil (corpus_research.TopicProfile)
  dossier_orders.confirmed_at  TIMESTAMP — Owner-Bestätigung am Checkpoint
  dossier_orders.owner_note    TEXT   — „Korrektur in einem Satz"
  CHECK (status IN …)          um 'awaiting_confirmation' erweitert (drop + re-add;
                               Postgres — SQLite kann Tabellen-Constraints nicht
                               ändern, dort gilt die neue Liste für neu angelegte
                               Tabellen)

Der Worker-Statusfluss ist in pipeline/dossier_orders.py beschrieben.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.dossier_orders import (VALID_STATUS, ensure_schema, migrate_brief_columns,
                                     migrate_status_check)


def migrate() -> None:
    ensure_schema()   # legt dossier_orders + dossiers an, falls sie fehlen (frische DB)
    with get_connection() as conn:
        added = migrate_brief_columns(conn)
        changed = migrate_status_check(conn)
    backend = "PostgreSQL" if db_mod.USE_POSTGRES else "SQLite"
    print(f"OK ({backend}): Spalten neu: {', '.join(added) or 'keine'}; "
          f"Status-CHECK {'auf ' + ', '.join(VALID_STATUS) + ' gesetzt' if changed else 'unverändert'}.")


if __name__ == "__main__":
    migrate()
