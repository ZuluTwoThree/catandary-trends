#!/usr/bin/env python3
"""Migration + Backfill für `research_signals.kind` (#73, 2026-09-05).

Additiv + idempotent (Muster: migrate_research_pulse.py — NICHT in init_db,
auf Prod-DBs manuell nachziehen). Legt die Spalte `kind TEXT` und ihren Index
an und füllt den Bestand per UPDATE (kein DELETE) nach denselben Regeln, die
build_research_index.py beim nächsten Voll-Rebuild anwendet
(pipeline/research_kinds.kind_sql): gespeicherter OpenAlex-Typ aus
`openalex_meta` (Join über raw_entries.openalex_id) → Host-Heuristik
(Repository-Hosts = artifact) → Preprint-Server = preprint → sonst unknown.

Nur Zeilen mit `kind IS NULL` werden angefasst; ein zweiter Lauf ist ein No-op.
Die Zeilen selbst bleiben erhalten — Pulse und Explorer filtern
`kind <> 'artifact'` per Default, die Explorer-Facette blendet sie wieder ein.

    python scripts/migrate_research_signals_kind.py            # migrieren + backfillen
    python scripts/migrate_research_signals_kind.py --dry-run  # nur zählen
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402
from pipeline.research_kinds import kind_sql  # noqa: E402

KIND_EXPR = kind_sql("m.work_type", "t.source_url", "t.source_name")


def _distribution(cur) -> list[tuple[str, int]]:
    cur.execute("SELECT coalesce(kind, '<null>'), count(*) FROM research_signals "
                "GROUP BY 1 ORDER BY 2 DESC")
    return cur.fetchall()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="nur zählen, nichts schreiben")
    args = ap.parse_args()

    import psycopg2
    if not db_mod.USE_POSTGRES:
        print("research_signals existiert nur auf PostgreSQL — nichts zu tun")
        return 0
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor()
    t0 = time.time()

    if args.dry_run:
        cur.execute(f"""
            SELECT {KIND_EXPR} AS kind, count(*)
            FROM research_signals rs
            JOIN trends t ON t.id = rs.trend_id
            JOIN raw_entries r ON r.id = t.raw_entry_id
            LEFT JOIN openalex_meta m ON m.work_id = r.openalex_id
            GROUP BY 1 ORDER BY 2 DESC""")
        print("[dry] kind-Verteilung nach den Regeln (nichts geschrieben):")
        for k, n in cur.fetchall():
            print(f"  {k:10s} {n:>9,}")
        conn.close()
        return 0

    cur.execute("ALTER TABLE research_signals ADD COLUMN IF NOT EXISTS kind TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS research_signals_kind_idx ON research_signals (kind)")
    conn.commit()
    before = _distribution(cur)
    print("vorher: " + ", ".join(f"{k} {n:,}" for k, n in before))

    cur.execute(f"""
        UPDATE research_signals rs
        SET kind = {KIND_EXPR}
        FROM trends t
        JOIN raw_entries r ON r.id = t.raw_entry_id
        LEFT JOIN openalex_meta m ON m.work_id = r.openalex_id
        WHERE t.id = rs.trend_id AND rs.kind IS NULL""")
    updated = cur.rowcount
    # Zeilen ohne trends/raw_entries-Gegenstück (sollte es nicht geben) → unknown
    cur.execute("UPDATE research_signals SET kind = 'unknown' WHERE kind IS NULL")
    orphans = cur.rowcount
    conn.commit()
    cur.execute("ANALYZE research_signals")
    conn.commit()
    after = _distribution(cur)
    conn.close()
    print(f"backfill: {updated:,} Zeilen klassifiziert, {orphans} ohne Gegenstück → unknown, "
          f"{time.time()-t0:.0f}s")
    print("nachher: " + ", ".join(f"{k} {n:,}" for k, n in after))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
