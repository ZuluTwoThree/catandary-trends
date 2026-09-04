#!/usr/bin/env python3
"""Migration für Research Pulse (#73 Teil 1): Tabelle `research_pulse`.

Additiv + idempotent (Muster: migrate_dead_links.py / migrate_research_live.py
— NICHT in init_db, auf Prod-DBs manuell nachziehen). `scripts/research_pulse.py`
ruft dasselbe ensure_schema() vor jedem Lauf, dieses Skript existiert für die
explizite, sichtbare Migration und den Zeilen-Check.

research_pulse: eine Zeile je Rechenlauf (versioniert — ein Theme/Woche kann
mehrfach gerechnet werden, „Neu rechnen" im Frontend; die Seite liest je
(theme, year, week) den jüngsten computed_at).

    python scripts/migrate_research_pulse.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline.db import get_connection  # noqa: E402
from pipeline.research_pulse import ensure_schema  # noqa: E402


def main() -> int:
    with get_connection() as conn:
        ensure_schema(conn)
        n = conn.execute("SELECT count(*) AS n FROM research_pulse").fetchone()["n"]
        latest = conn.execute(
            "SELECT year, week, count(DISTINCT theme) AS themes, max(computed_at) AS at "
            "FROM research_pulse GROUP BY year, week ORDER BY year DESC, week DESC LIMIT 3"
        ).fetchall()
    print(f"research_pulse: {n:,} rows")
    for r in latest:
        print(f"  {r['year']}-W{r['week']:02d}: {r['themes']} themes, latest {r['at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
