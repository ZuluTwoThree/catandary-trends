-- Post-migration finalize for the SQLite→Postgres cutover (2026-07-03).
-- Run once against the target DB after scripts/migrate_to_postgres.py.
-- (The straggler tables below are NOT in the migration's TABLES list; their
-- data is copied by the migration follow-up, this file (re)creates the schema
-- + all indexes the frontend hot paths and pgvector ANN need.)

-- Foresight snapshot artifacts + lead-time tier map + newsletter editions ------
CREATE TABLE IF NOT EXISTS source_lead_time_tier (
  source_name TEXT PRIMARY KEY,
  lead_time_tier TEXT CHECK (lead_time_tier IN ('future','market','now')));
CREATE TABLE IF NOT EXISTS foresight_runs (
  id SERIAL PRIMARY KEY, scope TEXT NOT NULL, tier TEXT, status_filter TEXT,
  k INTEGER, signals INTEGER, first_month TEXT, last_month TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS foresight_clusters (
  id SERIAL PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES foresight_runs(id),
  cluster_idx INTEGER, label TEXT, size INTEGER, cohesion REAL, mega_trend TEXT,
  mega_purity REAL, verticals TEXT, top_tags TEXT, n_sources INTEGER, momentum TEXT,
  sov_delta_pp REAL, tier TEXT, rep_trend_ids TEXT, rep_titles TEXT, monthly_series TEXT);
CREATE TABLE IF NOT EXISTS newsletter_editions (
  id SERIAL PRIMARY KEY, year INTEGER, week INTEGER, editorial TEXT,
  vertical_summaries TEXT, mega_trend_radar TEXT, trend_refs TEXT,
  total_signals INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(year, week));

-- Full-text search: GIN over the same fields the SQLite FTS5 table indexed.
-- The tsvector expression must MATCH lib/db.ts FTS_VECTOR + api/search verbatim.
CREATE INDEX IF NOT EXISTS idx_trends_fts ON trends USING gin(
  to_tsvector('english', coalesce(title_en,'') || ' ' || coalesce(summary_en,'')
              || ' ' || coalesce(tags::text,'')));

-- Hot-path btree indexes for the card grid / filters.
CREATE INDEX IF NOT EXISTS idx_trends_status_sort ON trends (status, sort_date DESC);
CREATE INDEX IF NOT EXISTS idx_trends_vertical    ON trends (primary_vertical, status);
CREATE INDEX IF NOT EXISTS idx_trends_mega        ON trends (mega_trend) WHERE mega_trend IS NOT NULL;

-- Vector ANN: see scripts/build_ann_index.py — populates embedding_1024
-- (Matryoshka prefix; pgvector caps HNSW at 2000 dims so the 4096 col can't be
-- indexed) and builds the partial HNSW index over published rows:
--   CREATE INDEX idx_trends_emb1024_pub_hnsw ON trends
--     USING hnsw (embedding_1024 vector_cosine_ops) WHERE status = 'published';

-- FK child-column index: Postgres does NOT auto-index a referencing column, so
-- deleting/updating a raw_entry triggered a full trends scan per row (a 6764-row
-- DELETE hung for minutes). Required for any raw_entries maintenance at scale.
CREATE INDEX IF NOT EXISTS idx_trends_raw_entry ON trends(raw_entry_id);
