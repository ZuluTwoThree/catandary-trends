#!/usr/bin/env python3
"""Migration für den Newsletter-Deep-Dive (#96 Phase 1): Spalte
`newsletter_editions.deep_dive` (JSONB auf Postgres, TEXT auf SQLite).

Additiv + idempotent (Muster: migrate_dead_links.py / migrate_research_pulse.py
— NICHT in init_db verdrahtet; auf der Live-DB EINMAL von Hand ausführen).
`scripts/newsletter_deep_dive.py` ruft dieselbe ensure_deep_dive_column() vor
jedem Lauf, dieses Skript existiert für die explizite, sichtbare Migration und
den Zeilen-Check.

Inhalt der Spalte (ein JSON-Objekt je Edition, NULL = kein Deep-Dive):
  theme, theme_name, body_md, citations[] (url, title, kind, outlet, date),
  dossier_slug, dossier_version, corpus_asof, audit{…}, gates{…},
  gate_passed, dry_run, generated_at, models{research, condense}, words,
  seconds, condensate_check{…}. Öffentlich gerendert wird NUR
  gate_passed && !dry_run (Phase 2) — im Dry-Run bleibt es ein Owner-Hinweis.

    .venv/bin/python scripts/migrate_newsletter_deep_dive.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402
from pipeline.db import get_connection  # noqa: E402
from pipeline.newsletter_generator import ensure_deep_dive_column  # noqa: E402


def main() -> int:
    added = ensure_deep_dive_column()
    backend = "PostgreSQL" if db_mod.USE_POSTGRES else "SQLite"
    print(f"newsletter_editions.deep_dive: {'added' if added else 'already present'} ({backend})")
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT year, week, deep_dive FROM newsletter_editions "
            "WHERE deep_dive IS NOT NULL ORDER BY year DESC, week DESC LIMIT 6"
        ).fetchall()
    for r in rows:
        d = dict(r)
        dd = d["deep_dive"]
        if isinstance(dd, str):
            try:
                dd = json.loads(dd)
            except ValueError:
                dd = {}
        print(f"  {d['year']}-W{d['week']:02d}: theme={dd.get('theme')} "
              f"gate_passed={dd.get('gate_passed')} dry_run={dd.get('dry_run')} "
              f"words={dd.get('words')}")
    if not rows:
        print("  (no edition carries a deep dive yet)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
