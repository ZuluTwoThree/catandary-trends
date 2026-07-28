#!/usr/bin/env python3
"""Variante A – Brücke Hetzner-MySQL -> lokales Postgres.

MySQL auf Hetzner ist das System of Record der Einwilligung.
Postgres bekommt nur eine Versand-Replik (inkl. Abmeldungen!).

Lokaler Cron:  */30 * * * * .venv/bin/python -m scripts.sync_subscribers
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import httpx

from pipeline.db import get_connection

EXPORT_URL = os.environ["NL_EXPORT_URL"]          # https://catandary.de/newsletter/export.php
EXPORT_TOKEN = os.environ["NL_EXPORT_TOKEN"]
STATE = pathlib.Path(os.getenv("NL_SYNC_STATE", "data/nl_sync_state.json"))


def load_since() -> str:
    if STATE.exists():
        return json.loads(STATE.read_text()).get("since", "1970-01-01 00:00:00")
    return "1970-01-01 00:00:00"


def main() -> int:
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
    with get_connection() as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO newsletter_subscribers
                    (email, verticals, confirmed, subscribed_at, unsubscribed_at)
                VALUES (%s, %s::jsonb, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET
                    verticals       = EXCLUDED.verticals,
                    confirmed       = EXCLUDED.confirmed,
                    subscribed_at   = LEAST(newsletter_subscribers.subscribed_at,
                                            EXCLUDED.subscribed_at),
                    unsubscribed_at = EXCLUDED.unsubscribed_at
                """,
                (
                    row["email"].lower(),
                    row.get("verticals") or "[]",
                    row["status"] == "confirmed",
                    row.get("confirmed_at") or row["signup_at"],
                    row.get("unsubscribed_at"),
                ),
            )
            max_seen = max(max_seen, row["updated_at"])

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"since": max_seen}))
    print(f"synced {len(rows)} rows, watermark={max_seen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
