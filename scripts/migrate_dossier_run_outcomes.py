#!/usr/bin/env python3
"""dossier_run_outcomes — Nutzen U je Dossier-Lauf (Stufe 0 des Plans
docs/plan_dossier_agent_2026-09-18.md; Rechenregeln in pipeline/dossier_utility.py).

Self-contained additive Migration — wie scripts/migrate_dossier_orders.py
NICHT in db.init_db verdrahtet (Dossier-Tabellen sind Owner-Werkzeug, ein
Merge fasst die laufende Pipeline nicht an).

⚠️  Additive Migrationsskripte laufen NIE automatisch auf der Live-DB. Nach
dem Merge einmal manuell ausführen (auf dem Host mit DATABASE_URL):

    .venv/bin/python scripts/migrate_dossier_run_outcomes.py

Bis dahin zeigt der Desk in der dritten Ampel „—" (to_regclass-Prüfung,
kein Crash), der Worker protokolliert nur eine Warnung und der Lauf endet
normal in 'review'. Danach:

    .venv/bin/python scripts/dossier_eval.py --backfill   # alle alten Läufe nachrechnen

Angelegt wird:

  dossier_run_outcomes — eine Zeile je dossiers.id (UNIQUE): utility,
                         weights (JSONB), components (JSONB), delivery_ready,
                         reader_answers, signed_off, owner_edit_diff (Stufe 5),
                         notes. Upsert beim Backfill, nie zwei Zeilen je Lauf.

Idempotent (CREATE TABLE IF NOT EXISTS) — sicher erneut auszuführen.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline.dossier_utility import ensure_schema


def migrate() -> None:
    ensure_schema()
    backend = "PostgreSQL" if db_mod.USE_POSTGRES else "SQLite"
    print(f"OK: dossier_run_outcomes vorhanden ({backend}).")


if __name__ == "__main__":
    migrate()
