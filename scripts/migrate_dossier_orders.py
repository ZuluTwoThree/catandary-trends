#!/usr/bin/env python3
"""dossier_orders- + dossiers-Schema für die Agentic-Dossiers (Owner-only).

Self-contained additive Migration — NICHT in db.init_db verdrahtet (gleiches
Muster wie scripts/migrate_dead_links.py): ein Merge fasst die laufende
Pipeline nicht an.

⚠️  WICHTIG — bekannte Falle in diesem Repo: additive Migrationsskripte laufen
NIE automatisch auf der Live-DB. Nach dem Merge muss dieses Skript EINMAL
MANUELL gegen die Produktions-DB ausgeführt werden (auf dem Host, auf dem
DATABASE_URL in der Umgebung/.env steht):

    .venv/bin/python scripts/migrate_dossier_orders.py

Bis dahin existieren die Tabellen dort nicht — die Frontend-Seite
/trends/dossiers prüft to_regclass() vorab und zeigt dann einen klaren
Hinweis statt zu crashen; der Worker legt sich sein Schema zur Not selbst an
(ensure_schema ist idempotent), aber die dossiers-Tabelle des Rechercheurs
braucht diesen Lauf ebenfalls, bevor das Frontend Berichte anzeigen kann.

Angelegt werden:

  dossier_orders — die Auftragszettel (siehe pipeline/dossier_orders.py;
                   Statusfluss queued→running→review→done, nie automatisch
                   über 'review' hinaus).
  dossiers       — versionierte Berichte des agentischen Rechercheurs
                   (scripts/corpus_research.py save_dossier legt sie sonst
                   beim ersten CLI-Lauf an; hier explizit, damit das
                   Frontend vor dem ersten Lauf nicht ins Leere liest).

Idempotent (CREATE TABLE IF NOT EXISTS) — sicher erneut auszuführen.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.dossier_orders import ensure_schema


def migrate() -> None:
    ensure_schema()  # dossier_orders + dossiers, backend-gerecht
    with get_connection() as conn:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dossier_orders_status "
                     "ON dossier_orders (status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dossiers_slug "
                     "ON dossiers (slug, version)")
    backend = "PostgreSQL" if db_mod.USE_POSTGRES else "SQLite"
    print(f"OK: dossier_orders + dossiers vorhanden ({backend}).")


if __name__ == "__main__":
    migrate()
