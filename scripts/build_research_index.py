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
  kind      = article | preprint | review | chapter | artifact | unknown (#73):
              from the stored OpenAlex type (openalex_meta.work_type via
              raw_entries.openalex_id), overridden to `artifact` for
              repository hosts (Zenodo/figshare/GitHub …), `preprint` for the
              preprint servers, else `unknown` — pipeline/research_kinds.py.
              Pulse and Explorer filter `kind <> 'artifact'` by default.
  tsv       = to_tsvector(title + abstract), GIN-indexed

Full rebuild, idempotent, pure SQL (~1–2 min at 550k rows). Refreshed by the
Saturday ingester cron after new research signals are processed. Indexes are
created under staging names and renamed after the swap — the earlier
`LIKE … INCLUDING ALL` copied every existing index on each rebuild and left six
identical sets behind (docs/research_pulse.md, Nebenbefund).

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
from pipeline.research_kinds import kind_sql  # noqa: E402

# staging index name → final name (the swap renames them)
INDEXES = {
    "research_signals_new_tsv": ("research_signals_tsv_idx", "USING gin (tsv)"),
    "research_signals_new_published": ("research_signals_published_idx", "(published DESC)"),
    "research_signals_new_mega": ("research_signals_mega_trend_idx", "(mega_trend)"),
    "research_signals_new_kind": ("research_signals_kind_idx", "(kind)"),
}

KIND_EXPR = kind_sql("m.work_type", "t.source_url", "t.source_name")


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
            tsv        tsvector,
            kind       TEXT
        )""")
    # additive: pre-#73 tables lack the column (the LIKE below copies it)
    cur.execute("ALTER TABLE research_signals ADD COLUMN IF NOT EXISTS kind TEXT")
    # Voll-Rebuild in eine Staging-Tabelle, dann atomarer Tausch — die Seite
    # sieht nie einen halb gefüllten Index.
    cur.execute("DROP TABLE IF EXISTS research_signals_new")
    cur.execute("CREATE TABLE research_signals_new (LIKE research_signals INCLUDING DEFAULTS)")
    cur.execute(f"""
        INSERT INTO research_signals_new
            (trend_id, title, abstract, url, source, concept, published, mega_trend,
             vertical, tsv, kind)
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
                        100000)),
               {KIND_EXPR}
        FROM trends t
        JOIN raw_entries r ON t.raw_entry_id = r.id
        JOIN sources s ON r.source_id = s.id
        LEFT JOIN openalex_meta m ON m.work_id = r.openalex_id
        WHERE s.source_type = 'research' AND t.title_en IS NOT NULL""")
    n = cur.rowcount
    cur.execute("ALTER TABLE research_signals_new ADD CONSTRAINT research_signals_new_pk "
                "PRIMARY KEY (trend_id)")
    for staging, (_final, spec) in INDEXES.items():
        cur.execute(f"CREATE INDEX {staging} ON research_signals_new {spec}")
    cur.execute("DROP TABLE research_signals")
    cur.execute("ALTER TABLE research_signals_new RENAME TO research_signals")
    cur.execute("ALTER TABLE research_signals RENAME CONSTRAINT research_signals_new_pk "
                "TO research_signals_pkey")
    for staging, (final, _spec) in INDEXES.items():
        cur.execute(f"ALTER INDEX {staging} RENAME TO {final}")
    conn.commit()
    cur.execute("ANALYZE research_signals")
    cur.execute("SELECT kind, count(*) FROM research_signals GROUP BY kind ORDER BY 2 DESC")
    kinds = ", ".join(f"{k} {c:,}" for k, c in cur.fetchall())
    conn.commit()
    conn.close()
    print(f"research_signals: {n:,} Zeilen in {time.time()-t0:.0f}s | kind: {kinds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
