#!/usr/bin/env python3
"""Accounts / entitlement schema for the alpha (Epic W2.1/W2.2, issue #17).

Self-contained additive migration — NOT wired into db.init_db, so the running
pipeline is untouched (same pattern as pipeline/foresight_snapshot.py). Creates:

  app_users       — one row per registered email, with a subscription tier
  magic_tokens    — single-use, short-lived magic-link login tokens (hashed)

Sessions are stateless (signed HMAC cookie), so no session table. The tier is
always read fresh from app_users, so upgrades/downgrades take effect at once.

    python scripts/migrate_accounts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline.db import get_connection


def migrate() -> None:
    pk = ("id SERIAL PRIMARY KEY" if db_mod.USE_POSTGRES
          else "id INTEGER PRIMARY KEY AUTOINCREMENT")
    created = ("created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if db_mod.USE_POSTGRES
               else "created_at TEXT DEFAULT (datetime('now'))")
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_users ("
            f" {pk},"
            " email TEXT UNIQUE NOT NULL,"
            " tier TEXT NOT NULL DEFAULT 'free',"       # free|starter|pro|superpro
            " stripe_customer_id TEXT,"
            " stripe_subscription_id TEXT,"
            # timestamp of the newest subscription-lifecycle event already applied to
            # tier — the webhook only writes tier when an event is at least this new,
            # so an out-of-order redelivery cannot resurrect a cancelled paid tier.
            " sub_event_at TIMESTAMP,"
            " newsletter_opt_in BOOLEAN DEFAULT FALSE,"
            " last_login_at TIMESTAMP,"
            f" {created})"
        )
        # Additive back-fill for DBs created before sub_event_at existed. Postgres
        # supports IF NOT EXISTS; SQLite does not, so tolerate a duplicate-column error.
        try:
            conn.execute("ALTER TABLE app_users ADD COLUMN "
                         + ("IF NOT EXISTS " if db_mod.USE_POSTGRES else "")
                         + "sub_event_at TIMESTAMP")
        except Exception:
            pass  # column already present
        conn.execute(
            "CREATE TABLE IF NOT EXISTS magic_tokens ("
            f" {pk},"
            " token_hash TEXT UNIQUE NOT NULL,"         # sha256 of the raw token
            " email TEXT NOT NULL,"
            " expires_at TIMESTAMP NOT NULL,"
            " used BOOLEAN DEFAULT FALSE,"
            " newsletter_opt_in BOOLEAN DEFAULT FALSE,"
            f" {created})"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_magic_tokens_hash "
                     "ON magic_tokens(token_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_app_users_email "
                     "ON app_users(email)")
    print("accounts schema ready (app_users, magic_tokens)")


if __name__ == "__main__":
    migrate()
