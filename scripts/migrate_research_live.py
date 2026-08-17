#!/usr/bin/env python3
"""Migration für die Live-API-Features des Research Explorers (#83).

Additiv + idempotent (Muster: migrate_accounts.py — NICHT in init_db,
auf Prod-DBs manuell nachziehen, siehe docs/issue_status.md Migrationslücke).

- research_live_cache: Server-Cache für OpenAlex-Live-Antworten (Singleton,
  cites:-Listen, Spotlights, Latest-Listen). Cache-Hits kosten kein
  Tages-Budget des Nutzers.
- research_live_usage: 25-Live-Abfragen/Tag-Zähler je Account (Owner-Regel
  2026-08-16: Live-API = Super-Pro-Feature; Dev/Admins unbegrenzt).
- research_funders / research_institutions: kleine Distinct-Aggregate für
  das lokale Typeahead (aus den Topic-Aggregaten, keine API nötig).

    python scripts/migrate_research_live.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402


def main() -> int:
    import psycopg2

    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS research_live_cache (
        kind TEXT NOT NULL,
        key TEXT NOT NULL,
        payload JSONB NOT NULL,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (kind, key))""")

    cur.execute("""CREATE TABLE IF NOT EXISTS research_live_usage (
        user_id INTEGER NOT NULL,
        day DATE NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, day))""")

    # Distinct-Aggregate fürs Typeahead — klein (Zehntausende Zeilen),
    # ILIKE-Scan reicht; Neuaufbau gehört in den Monats-Sync Schritt 5.
    cur.execute("DROP TABLE IF EXISTS research_funders_new")
    cur.execute("""CREATE TABLE research_funders_new AS
        SELECT funder, SUM(n)::int AS n FROM research_topic_funders
        GROUP BY funder""")
    cur.execute("ALTER TABLE research_funders_new ADD PRIMARY KEY (funder)")
    cur.execute("DROP TABLE IF EXISTS research_funders")
    cur.execute("ALTER TABLE research_funders_new RENAME TO research_funders")

    cur.execute("DROP TABLE IF EXISTS research_institutions_new")
    cur.execute("""CREATE TABLE research_institutions_new AS
        SELECT institution, MAX(country) AS country, SUM(n)::int AS n
        FROM research_topic_institutions GROUP BY institution""")
    cur.execute(
        "ALTER TABLE research_institutions_new ADD PRIMARY KEY (institution)")
    cur.execute("DROP TABLE IF EXISTS research_institutions")
    cur.execute(
        "ALTER TABLE research_institutions_new RENAME TO research_institutions")

    for t in ("research_live_cache", "research_live_usage",
              "research_funders", "research_institutions"):
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"{t}: {cur.fetchone()[0]:,} rows")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
