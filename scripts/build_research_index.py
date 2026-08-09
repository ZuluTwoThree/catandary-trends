#!/usr/bin/env python3
"""Materialize the Research Explorer index (#72).

Builds `research_signals` — one row per research-tier signal with searchable
full text — so /trends/foresight/research can serve FTS over 500k+ abstracts
from an indexed table instead of on-the-fly tsvectors (the main feed's
FTS_VECTOR approach works for 67k published rows, not here).

  abstract  = raw_entries.excerpt without the "[Science · …]"/"[Preprint · …]"
              routing prefix (display text = the actual abstract)
  concept   = the prefix content (e.g. "Quantum information", "arXiv:quant-ph")
              — doubles as a facet badge
  tsv       = to_tsvector(title + abstract), GIN-indexed

Full rebuild, idempotent, pure SQL (~1–2 min at 450k rows). Refreshed by the
Saturday ingester cron after new research signals are processed.

    python scripts/build_research_index.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import db as db_mod  # noqa: E402


def main() -> int:
    import psycopg2
    t0 = time.time()
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS research_signals (
            trend_id   BIGINT PRIMARY KEY,
            title      TEXT NOT NULL,
            abstract   TEXT,
            url        TEXT NOT NULL,
            source     TEXT,
            concept    TEXT,
            published  DATE,
            mega_trend TEXT,
            vertical   TEXT,
            tsv        tsvector
        )""")
    # Voll-Rebuild in eine Staging-Tabelle, dann atomarer Tausch — die Seite
    # sieht nie einen halb gefüllten Index.
    cur.execute("DROP TABLE IF EXISTS research_signals_new")
    cur.execute("CREATE TABLE research_signals_new (LIKE research_signals INCLUDING ALL)")
    cur.execute("""
        INSERT INTO research_signals_new
        SELECT t.id,
               t.title_en,
               NULLIF(regexp_replace(coalesce(r.excerpt, ''), '^\\[[^\\]]+\\]\\s*', ''), ''),
               t.source_url,
               t.source_name,
               (regexp_match(coalesce(r.excerpt, ''),
                             '^\\[(?:Science|Preprint)\\s*·\\s*([^\\]]+)\\]'))[1],
               LEAST(r.published_date, NOW())::date,
               t.mega_trend,
               t.primary_vertical,
               to_tsvector('english',
                   left(coalesce(t.title_en, '') || ' ' ||
                        regexp_replace(coalesce(r.excerpt, ''), '^\\[[^\\]]+\\]\\s*', ''),
                        100000))
        FROM trends t
        JOIN raw_entries r ON t.raw_entry_id = r.id
        JOIN sources s ON r.source_id = s.id
        WHERE s.source_type = 'research' AND t.title_en IS NOT NULL""")
    n = cur.rowcount
    cur.execute("CREATE INDEX ON research_signals_new USING gin (tsv)")
    cur.execute("CREATE INDEX ON research_signals_new (published DESC)")
    cur.execute("CREATE INDEX ON research_signals_new (mega_trend)")
    cur.execute("DROP TABLE research_signals")
    cur.execute("ALTER TABLE research_signals_new RENAME TO research_signals")
    conn.commit()
    conn.close()
    print(f"research_signals: {n:,} Zeilen in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
