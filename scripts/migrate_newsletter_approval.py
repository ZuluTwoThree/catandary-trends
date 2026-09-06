#!/usr/bin/env python3
"""Migration für die Newsletter-Freigabe (Owner-Auftrag 2026-09-06): Spalten
`newsletter_editions.approved_at / approved_by / approval_note`.

Additiv + idempotent (Muster: migrate_newsletter_deep_dive.py — NICHT in
init_db verdrahtet; auf der Live-DB EINMAL von Hand ausführen). Der Sender
ruft dieselbe ensure_approval_columns() vor jedem Lauf, dieses Skript
existiert für die explizite, sichtbare Migration und den Zeilen-Check.

Bedeutung:
  approved_at    Zeitpunkt der Freigabe durch einen Menschen. NULL = Entwurf;
                 ohne Wert verweigert pipeline/newsletter_sender.py den Versand.
  approved_by    Wer freigegeben hat (die Freigabe-Ansicht schreibt
                 NEWSLETTER_APPROVER, Default "owner").
  approval_note  Optionale Notiz aus der Freigabe-Ansicht.
`sent_at`/`recipients_count` bleiben unverändert — Freigabe und Versand sind
zwei getrennte Tatsachen.

    .venv/bin/python scripts/migrate_newsletter_approval.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402
from pipeline.db import get_connection  # noqa: E402
from pipeline.newsletter_generator import ensure_approval_columns  # noqa: E402


def main() -> int:
    added = ensure_approval_columns()
    backend = "PostgreSQL" if db_mod.USE_POSTGRES else "SQLite"
    print(f"newsletter_editions approval columns ({backend}): "
          f"{'added ' + ', '.join(added) if added else 'already present'}")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT year, week, approved_at, approved_by, sent_at "
            "FROM newsletter_editions ORDER BY year DESC, week DESC LIMIT 6"
        ).fetchall()
    for r in rows:
        d = dict(r)
        state = ("sent" if d["sent_at"] else
                 "released" if d["approved_at"] else "draft")
        print(f"  {d['year']}-W{d['week']:02d}: {state}"
              f"{' by ' + str(d['approved_by']) if d['approved_by'] else ''}"
              f"{' at ' + str(d['approved_at']) if d['approved_at'] else ''}")
    if not rows:
        print("  (no editions yet)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
