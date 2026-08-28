#!/usr/bin/env python3
"""dead_links schema for source-link-rot monitoring (#48).

Self-contained additive migration — NOT wired into db.init_db (same pattern as
scripts/migrate_accounts.py). A single small table instead of an ALTER on the
45 GB trends table:

  dead_links   — one row per source_url currently flagged dead by
                 scripts/check_source_links.py --mark. check_count only
                 crosses into "confirmed dead" (what the frontend shows a
                 badge for) at >=2 — a single blip must not flag a healthy
                 link (see the --mark 2-strike logic in check_source_links.py).

⚠️  WICHTIG — bekannte Falle in diesem Repo: additive Migrationsskripte wie
dieses laufen NIE automatisch auf der Live-DB (sie sind bewusst nicht in
db.init_db() verdrahtet, damit ein Merge die laufende Pipeline nicht anfasst).
migrate_accounts.py ist dieselbe Falle real getreten: sub_event_at fehlte auf
der Live-DB und crashte den Stripe-Webhook, bis es von Hand nachgezogen wurde.

Nach diesem Merge muss jemand dieses Skript EINMAL MANUELL gegen die
Produktions-DB ausführen, z.B. auf dem Host, auf dem DATABASE_URL bereits in
der Umgebung/.env steht:

    .venv/bin/python scripts/migrate_dead_links.py

Bis dahin existiert dead_links auf der Live-DB nicht — `check_source_links.py
--mark` würde dann bei jedem INSERT/SELECT gegen dead_links fehlschlagen, und
das Frontend fällt defensiv auf "kein Badge" zurück (siehe
frontend/src/lib/db.ts — die Lookup-Funktion prüft to_regclass() vorab und
schluckt jeden DB-Fehler, damit eine fehlende Tabelle die Artikelseite nicht
zum Absturz bringt).

Idempotent (CREATE TABLE IF NOT EXISTS) — sicher erneut auszuführen.

    python scripts/migrate_dead_links.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline.db import get_connection


def migrate() -> None:
    ts_default = ("TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if db_mod.USE_POSTGRES
                  else "TEXT DEFAULT (datetime('now'))")
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS dead_links ("
            " url TEXT PRIMARY KEY,"
            " status TEXT NOT NULL,"                # '404' | '410' | 'conn_error'
            f" first_seen {ts_default},"
            f" last_checked {ts_default},"
            " check_count INTEGER NOT NULL DEFAULT 1"
            ")"
        )
    print("dead_links schema ready")


if __name__ == "__main__":
    migrate()
