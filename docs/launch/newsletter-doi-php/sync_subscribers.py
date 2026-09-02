#!/usr/bin/env python3
"""Variante A – Brücke Hetzner-MySQL -> lokales Postgres.

MySQL auf Hetzner ist das System of Record der Einwilligung — UND der
Abmeldung (unsubscribe.php schreibt status='unsubscribed' + unsubscribed_at).
Postgres bekommt nur eine Versand-Replik: export.php liefert jede Zeile mit
status IN ('confirmed','unsubscribed') samt unsubscribed_at, hier wird sie in
newsletter_subscribers gespiegelt. pipeline/newsletter_sender.py mailt nur an
`confirmed = TRUE AND unsubscribed_at IS NULL` — eine Abmeldung auf dem
Webspace ist also nach dem nächsten Sync-Lauf lokal wirksam.

Lokaler Cron:  */30 * * * * .venv/bin/python -m scripts.sync_subscribers
(Datei vorher nach scripts/sync_subscribers.py kopieren, s. NEWSLETTER_GOLIVE.md.)
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import httpx

from pipeline.db import get_connection

EXPORT_URL = os.getenv("NL_EXPORT_URL", "https://catandary.de/newsletter/export.php")
EXPORT_TOKEN = os.getenv("NL_EXPORT_TOKEN", "")   # = export_token (Block 6) in nl_config.php
STATE = pathlib.Path(os.getenv("NL_SYNC_STATE", "data/nl_sync_state.json"))

# MySQL gewinnt — mit EINER Ausnahme: eine LOKALE Abmeldung (Next-Route der
# localhost-Instanz), die NACH der letzten MySQL-Bestätigung liegt, bleibt
# stehen. Lieber einen Re-Abonnenten einmal zu wenig anschreiben als einen
# Abgemeldeten erneut. Eine spätere Neu-Anmeldung auf dem Webspace (jüngeres
# confirmed_at = EXCLUDED.subscribed_at) hebt sie wieder auf.
UPSERT_SQL = """
INSERT INTO newsletter_subscribers
    (email, verticals, confirmed, subscribed_at, unsubscribed_at)
VALUES (%s, %s::jsonb, %s, %s, %s)
ON CONFLICT (email) DO UPDATE SET
    verticals       = EXCLUDED.verticals,
    confirmed       = EXCLUDED.confirmed,
    subscribed_at   = LEAST(newsletter_subscribers.subscribed_at,
                            EXCLUDED.subscribed_at),
    unsubscribed_at = CASE
        WHEN newsletter_subscribers.unsubscribed_at IS NOT NULL
         AND newsletter_subscribers.unsubscribed_at > EXCLUDED.subscribed_at
        THEN newsletter_subscribers.unsubscribed_at
        ELSE EXCLUDED.unsubscribed_at
    END
"""


def row_to_params(row: dict) -> tuple:
    """export.php-Zeile -> Parameter für UPSERT_SQL.

    `confirmed` ist NUR bei status == 'confirmed' wahr; eine abgemeldete Zeile
    kommt mit confirmed = False UND gesetztem unsubscribed_at an — beides
    schließt sie beim Versand aus.
    """
    status = row["status"]
    return (
        row["email"].strip().lower(),
        row.get("verticals") or "[]",
        status == "confirmed",
        row.get("confirmed_at") or row["signup_at"],
        row.get("unsubscribed_at") if status == "unsubscribed" else None,
    )


def load_since() -> str:
    if STATE.exists():
        return json.loads(STATE.read_text()).get("since", "1970-01-01 00:00:00")
    return "1970-01-01 00:00:00"


def main() -> int:
    if not EXPORT_TOKEN:
        print("NL_EXPORT_TOKEN not set (= export_token in nl_config.php)", file=sys.stderr)
        return 2
    since = load_since()
    r = httpx.get(
        EXPORT_URL,
        params={"since": since},
        headers={"Authorization": f"Bearer {EXPORT_TOKEN}"},
        timeout=30,
        follow_redirects=False,          # kein Redirect auf http:// zulassen
    )
    r.raise_for_status()
    payload = r.json()
    rows = payload["subscribers"]

    max_seen = since
    n_unsub = 0
    with get_connection() as conn:
        for row in rows:
            conn.execute(UPSERT_SQL, row_to_params(row))
            n_unsub += row["status"] == "unsubscribed"
            max_seen = max(max_seen, row["updated_at"])

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"since": max_seen}))
    print(f"synced {len(rows)} rows ({n_unsub} unsubscribed), watermark={max_seen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
