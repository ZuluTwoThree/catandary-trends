"""Database layer for Catandary Trends.

Supports SQLite (development) and PostgreSQL (production).
Set DATABASE_URL env var for PostgreSQL, otherwise falls back to SQLite.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import DATABASE_PATH, DATABASE_URL

logger = logging.getLogger(__name__)

# Detect database backend
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        logger.warning("psycopg2 not installed, falling back to SQLite")
        USE_POSTGRES = False

# --- Schema ---

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    source_type TEXT CHECK (source_type IN ('trade_media', 'press_wire', 'brand', 'api', 'radar', 'research', 'science', 'sitemap')),
    vertical TEXT CHECK (vertical IN ('FOOD','TECH','HEALTH','ECO','DESIGN','FASHION','BIZ','LIFESTYLE','CROSS')),
    sub_categories TEXT DEFAULT '[]',
    active INTEGER DEFAULT 1,
    -- Feeds this source the LLM content cycle? FALSE for pseudo-sources whose
    -- entries are signal data, not article material (funding awards, grants).
    -- The entry-level analogue of pub_number for patents: get_unprocessed_entries
    -- filters on it, so a mass funding ingest can never flood the RSS pool
    -- (2026-08-20: 235k SBIR/CORDIS rows tripped the cycle's 50k sanity abort).
    llm_pipeline INTEGER DEFAULT 1,
    auto_discovered INTEGER DEFAULT 0,
    discovery_count INTEGER DEFAULT 0,
    last_fetched TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS raw_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER REFERENCES sources(id),
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    excerpt TEXT,
    raw_content TEXT,
    published_date TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    processed INTEGER DEFAULT 0,
    filtered_out INTEGER DEFAULT 0,
    filter_reason TEXT,
    -- Stage cache for crash-resilience: persisted after each LLM call,
    -- allows pipeline restart without redoing completed stages.
    relevance_json TEXT,
    extraction_json TEXT,
    classification_json TEXT,
    embedding_blob BLOB,
    content_en_json TEXT,
    -- Patent node key (e.g. US-1234567-B2); links the citation/family graph
    -- (patent_links) back to this row. NULL for non-patent entries.
    pub_number TEXT,
    -- Patent kind code (A1/A2 = application/first publication, B1/B2 = grant, U =
    -- utility model …). A* is the earliest lead-time signal; used for app/grant
    -- split and earliest-publication dedup. NULL for non-patent entries.
    kind_code TEXT
);

CREATE TABLE IF NOT EXISTS trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_entry_id INTEGER REFERENCES raw_entries(id),
    title_en TEXT NOT NULL,
    title_de TEXT,
    slug TEXT UNIQUE NOT NULL,
    summary_en TEXT,
    summary_de TEXT,
    body_en TEXT,
    body_de TEXT,
    verticals TEXT DEFAULT '[]',
    primary_vertical TEXT,
    pestel TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]',
    trend_signal_type TEXT,
    mega_trend TEXT,
    macro_trend TEXT,
    trend_level TEXT CHECK (trend_level IN ('mega', 'macro', 'micro')),
    brands TEXT DEFAULT '[]',
    companies TEXT DEFAULT '[]',
    regions TEXT DEFAULT '[]',
    trend_score REAL,
    confidence REAL,
    source_url TEXT NOT NULL,
    source_name TEXT,
    embedding BLOB,
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'rejected', 'signal')),
    auto_published INTEGER DEFAULT 0,
    published_at TEXT,
    -- Set by BOTH review decisions (publish and reject), so review progress is
    -- measurable either way — a rejection used to leave no trace at all (#71).
    -- Also separates a human rejection from an automated sweep, which
    -- get_recent_embeddings() relies on.
    reviewed_at TEXT,
    -- When the nightly draft judge (stage 10) last verdicted this draft — held
    -- or released. NULL = never judged. The candidate query filters on it so a
    -- held cohort is judged ONCE, not re-judged every night while it blocks
    -- fresh drafts from the 600-slot window (2026-08-25 finding).
    judged_at TEXT,
    -- Why a row sits in status 'review' (#11, 2026-09-05): set by the corpus
    -- re-check (scripts/recheck_published_grounding.py, e.g.
    -- 'recheck_2026-09-05:garbled:script_leak:续约') and by the draft judge when
    -- it diverts a garbage candidate. NULL for owner-set reviews. Deliberately
    -- NOT reviewed_at — that stamp means "a human decided" (review UI, #71).
    review_reason TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    sort_date TEXT
);

CREATE TABLE IF NOT EXISTS source_discoveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    radar_source TEXT DEFAULT 'trendhunter',
    radar_vertical TEXT,
    original_title TEXT,
    extracted_brand TEXT,
    discovered_url TEXT,
    discovered_domain TEXT,
    has_rss_feed INTEGER,
    feed_url TEXT,
    added_to_sources INTEGER DEFAULT 0,
    discovered_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trend_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    verticals TEXT DEFAULT '[]',
    pestel TEXT DEFAULT '[]',
    mega_trend TEXT,
    trend_ids TEXT DEFAULT '[]',
    cluster_score REAL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trend_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trend_id INTEGER REFERENCES trends(id),
    page_views INTEGER DEFAULT 0,
    unique_visitors INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    newsletter_clicks INTEGER DEFAULT 0,
    avg_time_on_page REAL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_raw_entries_url ON raw_entries(url);
CREATE INDEX IF NOT EXISTS idx_raw_entries_processed ON raw_entries(processed);
CREATE INDEX IF NOT EXISTS idx_trends_slug ON trends(slug);
CREATE INDEX IF NOT EXISTS idx_trends_status ON trends(status);
CREATE INDEX IF NOT EXISTS idx_trends_vertical ON trends(primary_vertical);
CREATE INDEX IF NOT EXISTS idx_trends_created ON trends(created_at);
-- NB: sort_date column + its indexes/trigger are created in _migrate_trends_sort_date()
-- (after the ALTER), so they also apply cleanly to pre-existing DBs.

CREATE TABLE IF NOT EXISTS newsletter_subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    verticals TEXT DEFAULT '[]',
    confirmed INTEGER DEFAULT 0,
    subscribed_at TEXT DEFAULT (datetime('now')),
    unsubscribed_at TEXT
);
"""

PG_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    source_type TEXT CHECK (source_type IN ('trade_media', 'press_wire', 'brand', 'api', 'radar', 'research', 'science', 'sitemap')),
    vertical TEXT CHECK (vertical IN ('FOOD','TECH','HEALTH','ECO','DESIGN','FASHION','BIZ','LIFESTYLE','CROSS')),
    sub_categories JSONB DEFAULT '[]',
    active BOOLEAN DEFAULT true,
    -- See the SQLite schema above: FALSE = signal-only source, never article material.
    llm_pipeline BOOLEAN DEFAULT true,
    auto_discovered BOOLEAN DEFAULT false,
    discovery_count INTEGER DEFAULT 0,
    last_fetched TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS raw_entries (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id),
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    excerpt TEXT,
    raw_content TEXT,
    published_date TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT false,
    filtered_out BOOLEAN DEFAULT false,
    filter_reason TEXT,
    relevance_json TEXT,
    extraction_json TEXT,
    classification_json TEXT,
    embedding_blob BYTEA,
    content_en_json TEXT,
    -- Patent node key + kind code (parity with the SQLite _migrate_patent_graph).
    pub_number TEXT,
    kind_code TEXT
);

CREATE TABLE IF NOT EXISTS trends (
    id SERIAL PRIMARY KEY,
    raw_entry_id INTEGER REFERENCES raw_entries(id),
    title_en TEXT NOT NULL,
    title_de TEXT,
    slug TEXT UNIQUE NOT NULL,
    summary_en TEXT,
    summary_de TEXT,
    body_en TEXT,
    body_de TEXT,
    verticals JSONB DEFAULT '[]',
    primary_vertical TEXT,
    pestel JSONB DEFAULT '[]',
    tags JSONB DEFAULT '[]',
    trend_signal_type TEXT,
    mega_trend TEXT,
    macro_trend TEXT,
    trend_level TEXT CHECK (trend_level IN ('mega', 'macro', 'micro')),
    brands JSONB DEFAULT '[]',
    companies JSONB DEFAULT '[]',
    regions JSONB DEFAULT '[]',
    trend_score REAL,
    confidence REAL,
    source_url TEXT NOT NULL,
    source_name TEXT,
    -- qwen3-embedding outputs 4096-dim vectors (16384 bytes float32). The old
    -- VECTOR(1024) declaration would reject every insert on Postgres. Note: pgvector
    -- hnsw/ivfflat indexes cap at 2000 dims, so a 4096-dim column stores fine but
    -- can't be ANN-indexed — truncate (Matryoshka) to <=2000 for an indexed column
    -- when the prod ANN search lands. SQLite path stores raw bytes (BLOB), unaffected.
    embedding VECTOR(4096),
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'rejected', 'signal')),
    auto_published BOOLEAN DEFAULT false,
    published_at TIMESTAMP,
    -- See the SQLite schema above: written by both review decisions (#71).
    reviewed_at TIMESTAMP,
    judged_at TIMESTAMP,           -- stage-10 draft judge verdict stamp (see SQLite schema)
    review_reason TEXT,            -- why status='review' (see SQLite schema; #11 re-check)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sort_date TIMESTAMP            -- parity with SQLite _migrate_trends_sort_date
);

CREATE TABLE IF NOT EXISTS source_discoveries (
    id SERIAL PRIMARY KEY,
    radar_source TEXT DEFAULT 'trendhunter',
    radar_vertical TEXT,
    original_title TEXT,
    extracted_brand TEXT,
    discovered_url TEXT,
    discovered_domain TEXT,
    has_rss_feed BOOLEAN,
    feed_url TEXT,
    added_to_sources BOOLEAN DEFAULT false,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trend_clusters (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    verticals JSONB DEFAULT '[]',
    pestel JSONB DEFAULT '[]',
    mega_trend TEXT,
    trend_ids JSONB DEFAULT '[]',
    cluster_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trend_metrics (
    id SERIAL PRIMARY KEY,
    trend_id INTEGER REFERENCES trends(id),
    page_views INTEGER DEFAULT 0,
    unique_visitors INTEGER DEFAULT 0,
    shares INTEGER DEFAULT 0,
    newsletter_clicks INTEGER DEFAULT 0,
    avg_time_on_page REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Patent citation/family graph (parity with SQLite _migrate_patent_graph).
CREATE TABLE IF NOT EXISTS patent_links (
    src_pub TEXT NOT NULL,
    dst_pub TEXT NOT NULL,
    link_type TEXT NOT NULL,
    category TEXT,
    UNIQUE(src_pub, dst_pub, link_type)
);

-- Structured CPC (parity with SQLite _migrate_patent_cpc).
CREATE TABLE IF NOT EXISTS patent_cpc (
    pub_number TEXT NOT NULL,
    cpc TEXT NOT NULL,
    subclass TEXT,
    inventive INTEGER DEFAULT 1,
    UNIQUE(pub_number, cpc)
);

CREATE INDEX IF NOT EXISTS idx_raw_entries_url ON raw_entries(url);
CREATE INDEX IF NOT EXISTS idx_raw_entries_processed ON raw_entries(processed);
CREATE INDEX IF NOT EXISTS idx_raw_pubnum ON raw_entries(pub_number);
CREATE INDEX IF NOT EXISTS idx_trends_slug ON trends(slug);
CREATE INDEX IF NOT EXISTS idx_trends_status ON trends(status);
CREATE INDEX IF NOT EXISTS idx_trends_vertical ON trends(primary_vertical);
CREATE INDEX IF NOT EXISTS idx_trends_created ON trends(created_at);
CREATE INDEX IF NOT EXISTS idx_trends_status_sort ON trends(status, sort_date);
CREATE INDEX IF NOT EXISTS idx_trends_vert_sort ON trends(primary_vertical, status, sort_date);
CREATE INDEX IF NOT EXISTS idx_trends_source ON trends(status, source_name);
CREATE INDEX IF NOT EXISTS idx_plinks_src ON patent_links(src_pub, link_type);
CREATE INDEX IF NOT EXISTS idx_plinks_dst ON patent_links(dst_pub, link_type);
CREATE INDEX IF NOT EXISTS idx_pcpc_pub ON patent_cpc(pub_number);
CREATE INDEX IF NOT EXISTS idx_pcpc_sub ON patent_cpc(subclass);

CREATE TABLE IF NOT EXISTS newsletter_subscribers (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    verticals JSONB DEFAULT '[]',
    confirmed BOOLEAN DEFAULT false,
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    unsubscribed_at TIMESTAMP
);
"""


# --- Connection Management ---

def get_db_path() -> str:
    path = Path(DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


@contextmanager
def get_connection():
    """Get a database connection. Returns SQLite or PostgreSQL based on config."""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        try:
            yield _PgConnectionWrapper(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(get_db_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class _PgConnectionWrapper:
    """Wraps psycopg2 connection to provide a sqlite3-like interface."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        # Convert ? placeholders to %s for psycopg2
        sql = sql.replace("?", "%s")
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        return _PgCursorWrapper(cur)

    def executemany(self, sql, rows):
        """Batch insert. Translates SQLite 'INSERT OR IGNORE INTO t (cols) VALUES
        (?, …)' → 'INSERT INTO t (cols) VALUES %s ON CONFLICT DO NOTHING' and runs
        it through psycopg2.execute_values (fast path for the patent graph ingest).
        Falls back to a plain executemany for non-INSERT-OR-IGNORE statements."""
        import re as _re
        rows = list(rows)
        if not rows:
            return _PgCursorWrapper(self._conn.cursor())
        m = _re.match(r"(?is)\s*INSERT\s+OR\s+IGNORE\s+INTO\s+(.+?)\s+VALUES\s*\(.+\)\s*$", sql)
        cur = self._conn.cursor()
        if m:
            psycopg2.extras.execute_values(
                cur, f"INSERT INTO {m.group(1)} VALUES %s ON CONFLICT DO NOTHING", rows)
        else:
            cur.executemany(sql.replace("?", "%s"), rows)
        return _PgCursorWrapper(cur)

    def executescript(self, sql):
        cur = self._conn.cursor()
        cur.execute(sql)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


class _PgCursorWrapper:
    """Wraps psycopg2 cursor to provide fetchone/fetchall with dict-like access."""

    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def lastrowid(self):
        # For INSERT ... RETURNING id
        row = self._cursor.fetchone()
        if row and "id" in row:
            return row["id"]
        return None

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


# --- Helpers ---

def _json_loads(val):
    """Parse JSON string, handling both SQLite (string) and PG (already parsed)."""
    if val is None:
        return []
    if isinstance(val, (list, dict)):
        return val
    return json.loads(val)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Init ---

_STAGE_CACHE_COLUMNS = [
    ("relevance_json", "TEXT", "TEXT"),
    ("extraction_json", "TEXT", "TEXT"),
    ("classification_json", "TEXT", "TEXT"),
    ("embedding_blob", "BLOB", "BYTEA"),
    ("content_en_json", "TEXT", "TEXT"),
]


def _migrate_stage_cache_columns():
    """Add stage-cache columns to existing raw_entries tables. Idempotent."""
    with get_connection() as conn:
        for col, sqlite_type, pg_type in _STAGE_CACHE_COLUMNS:
            if USE_POSTGRES:
                # Native idempotence — a caught failure would still abort the
                # PG transaction and poison every later statement on this conn.
                conn.execute(f"ALTER TABLE raw_entries ADD COLUMN IF NOT EXISTS {col} {pg_type}")
                continue
            try:
                conn.execute(f"ALTER TABLE raw_entries ADD COLUMN {col} {sqlite_type}")
            except Exception as e:
                msg = str(e).lower()
                if "duplicate column" in msg or "already exists" in msg:
                    continue
                raise


def _migrate_sources_llm_pipeline():
    """Add sources.llm_pipeline to pre-existing databases. Idempotent.

    TRUE (default) = entries feed the LLM content cycle. FALSE = signal-only
    pseudo-source (funding, grants): embedded + distill-classified by
    signal_batch, but never turned into articles. Wired into init_db — the
    standalone-script-only migration was the gap that broke the Stripe webhook
    (2026-07-19) and nearly broke dedup (2026-08-12)."""
    with get_connection() as conn:
        if USE_POSTGRES:
            conn.execute("ALTER TABLE sources ADD COLUMN IF NOT EXISTS "
                         "llm_pipeline BOOLEAN DEFAULT true")
            return
        rows = conn.execute("PRAGMA table_info(sources)").fetchall()
        names = [(r[1] if not hasattr(r, "keys") else r["name"]) for r in rows]
        if "llm_pipeline" not in names:
            conn.execute("ALTER TABLE sources ADD COLUMN llm_pipeline INTEGER DEFAULT 1")


def _migrate_open_licence():
    """Add raw_entries.open_licence / oa_url. Idempotent, wired into init_db.

    Weg B+C (#97, 2026-09-09): a source can carry a machine-readable TDM
    reservation while individual articles are licensed CC BY. `open_licence`
    records the licence found for THIS entry, `oa_url` the open location the
    text came from — the reserved host itself is never fetched. Entries with
    an `open_licence` are admitted to the content cycle even though their
    source runs signal-only (see get_unprocessed_entries).
    """
    with get_connection() as conn:
        if USE_POSTGRES:
            conn.execute("ALTER TABLE raw_entries ADD COLUMN IF NOT EXISTS open_licence TEXT")
            conn.execute("ALTER TABLE raw_entries ADD COLUMN IF NOT EXISTS oa_url TEXT")
            return
        rows = conn.execute("PRAGMA table_info(raw_entries)").fetchall()
        names = [(r[1] if not hasattr(r, "keys") else r["name"]) for r in rows]
        if "open_licence" not in names:
            conn.execute("ALTER TABLE raw_entries ADD COLUMN open_licence TEXT")
        if "oa_url" not in names:
            conn.execute("ALTER TABLE raw_entries ADD COLUMN oa_url TEXT")


def _migrate_licence_checked():
    """Add raw_entries.licence_checked_at. Idempotent, wired into init_db.

    Stamped by scripts/resolve_open_licence.py on EVERY attempt, positive or
    negative (#97, 2026-09-09). Without it the nightly run re-resolves the same
    ~85 % non-open entries for as long as they sit unprocessed — the reserved
    sources run signal-only, so their rows stay in the pool until the Saturday
    sweep retires them. At ~254 entries/day that is up to six repeat lookups per
    entry against a paid API, and with a 300-row limit the older ones would never
    get their turn at all.
    """
    with get_connection() as conn:
        if USE_POSTGRES:
            conn.execute("ALTER TABLE raw_entries ADD COLUMN IF NOT EXISTS licence_checked_at TIMESTAMP")
            return
        rows = conn.execute("PRAGMA table_info(raw_entries)").fetchall()
        names = [(r[1] if not hasattr(r, "keys") else r["name"]) for r in rows]
        if "licence_checked_at" not in names:
            conn.execute("ALTER TABLE raw_entries ADD COLUMN licence_checked_at TEXT")


def _migrate_reviewed_at():
    """Add trends.reviewed_at to pre-existing databases. Idempotent.

    The column shipped as a standalone script (scripts/migrate_reviewed_at.py)
    and was applied to production by hand, but was never wired into init_db —
    so a fresh clone or a second environment lacked it. get_recent_embeddings()
    now filters on it, which would turn that gap into a hard failure of the
    dedup step rather than a missing feature (#71).
    """
    with get_connection() as conn:
        if USE_POSTGRES:
            conn.execute("ALTER TABLE trends ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP")
            return
        rows = conn.execute("PRAGMA table_info(trends)").fetchall()
        names = [(r[1] if not hasattr(r, "keys") else r["name"]) for r in rows]
        if "reviewed_at" not in names:
            conn.execute("ALTER TABLE trends ADD COLUMN reviewed_at TEXT")


def _migrate_judged_at():
    """Add trends.judged_at to pre-existing databases. Idempotent.

    Stage-10 verdict stamp (held OR released). Without it the judge re-judged
    the same held cohort every night (30h window, oldest ids first) and the
    fresh drafts never reached the 600-slot window — on 2026-08-25 all 600
    candidates were the previous day's already-held drafts. Wired into init_db
    from day one (lesson of the reviewed_at/llm_pipeline migration gaps)."""
    with get_connection() as conn:
        if USE_POSTGRES:
            conn.execute("ALTER TABLE trends ADD COLUMN IF NOT EXISTS judged_at TIMESTAMP")
            return
        rows = conn.execute("PRAGMA table_info(trends)").fetchall()
        names = [(r[1] if not hasattr(r, "keys") else r["name"]) for r in rows]
        if "judged_at" not in names:
            conn.execute("ALTER TABLE trends ADD COLUMN judged_at TEXT")


def _migrate_review_reason():
    """Add trends.review_reason to pre-existing databases. Idempotent (#11).

    Marker for rows the corpus re-check or the draft judge moved to status
    'review' (garbled body, ungrounded person name). The review UI filters on
    it ("Bestandsprüfung 05.09."), so a database without the column would break
    that queue — wired into init_db from day one, like judged_at."""
    with get_connection() as conn:
        if USE_POSTGRES:
            conn.execute("ALTER TABLE trends ADD COLUMN IF NOT EXISTS review_reason TEXT")
            return
        rows = conn.execute("PRAGMA table_info(trends)").fetchall()
        names = [(r[1] if not hasattr(r, "keys") else r["name"]) for r in rows]
        if "review_reason" not in names:
            conn.execute("ALTER TABLE trends ADD COLUMN review_reason TEXT")


def _migrate_trends_sort_date():
    """Add the indexed sort_date column (capped published date) + its indexes and
    auto-maintaining trigger to existing trends tables, and backfill rows. Idempotent.
    sort_date lets the frontend ORDER BY an index instead of a temp-b-tree over the
    trends⋈raw_entries join (the /trends slowness)."""
    if USE_POSTGRES:
        # Postgres path: a BEFORE INSERT trigger keeps sort_date populated. Without
        # it (the SQLite-only trigger didn't carry over the 2026-07-03 migration)
        # new trends got sort_date=NULL and floated to the top of ORDER BY
        # sort_date DESC (NULLs sort first). Parity with the SQLite trigger below.
        with get_connection() as conn:
            cur = conn._conn.cursor()
            cur.execute(
                "CREATE OR REPLACE FUNCTION trends_set_sort_date() RETURNS trigger AS $$\n"
                "BEGIN\n"
                "  IF NEW.sort_date IS NULL THEN\n"
                "    NEW.sort_date := LEAST(\n"
                "      COALESCE((SELECT published_date FROM raw_entries WHERE id = NEW.raw_entry_id),\n"
                "               COALESCE(NEW.created_at, now())),\n"
                "      COALESCE(NEW.created_at, now()));\n"
                "  END IF;\n"
                "  RETURN NEW;\n"
                "END;\n"
                "$$ LANGUAGE plpgsql;")
            cur.execute("DROP TRIGGER IF EXISTS trends_set_sort_date ON trends")
            cur.execute("CREATE TRIGGER trends_set_sort_date BEFORE INSERT ON trends "
                        "FOR EACH ROW EXECUTE FUNCTION trends_set_sort_date()")
            conn._conn.commit()
        return
    with get_connection() as conn:
        first_time = False
        try:
            conn.execute("ALTER TABLE trends ADD COLUMN sort_date TEXT")
            first_time = True
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                raise
        # Index the common /trends access paths so they use indexes instead of a
        # temp-b-tree / table scan over 40k+ rows:
        #  - status_sort / vert_sort: main grid + vertical pages (ORDER BY sort_date)
        #  - source: getTopSourcesByCount GROUP BY source_name
        #  - mega_cover: COVERING index for getMegaTrends (group + first_seen/30d, no row lookup)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trends_status_sort ON trends(status, sort_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trends_vert_sort ON trends(primary_vertical, status, sort_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trends_source ON trends(status, source_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trends_mega_cover ON trends(status, mega_trend, primary_vertical, sort_date)")
        conn.execute(
            "CREATE TRIGGER IF NOT EXISTS trends_set_sort_date AFTER INSERT ON trends "
            "BEGIN "
            "UPDATE trends SET sort_date = MIN("
            "COALESCE((SELECT published_date FROM raw_entries WHERE id = NEW.raw_entry_id), NEW.created_at), "
            "NEW.created_at) WHERE id = NEW.id; "
            "END"
        )
        if first_time:
            # Backfill existing rows and update planner stats once (not every run).
            conn.execute(
                "UPDATE trends SET sort_date = COALESCE("
                "(SELECT MIN(COALESCE(re.published_date, trends.created_at), trends.created_at) "
                "FROM raw_entries re WHERE re.id = trends.raw_entry_id), trends.created_at) "
                "WHERE sort_date IS NULL"
            )
            conn.execute("ANALYZE")


def _migrate_patent_graph():
    """Add the patent citation/family graph: raw_entries.pub_number (node key) +
    a patent_links edge table (cites / parent / child). Idempotent. SQLite only.

    Forward citations are *not* stored on the cited patent — they are derived by
    inverting the backward edges (SELECT src WHERE dst=X), so even old foundational
    patents that were never ingested surface as heavily-cited dst nodes."""
    if USE_POSTGRES:
        return
    with get_connection() as conn:
        for col in ("pub_number TEXT", "kind_code TEXT"):
            try:
                conn.execute(f"ALTER TABLE raw_entries ADD COLUMN {col}")
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    raise
        conn.execute(
            "CREATE TABLE IF NOT EXISTS patent_links ("
            " src_pub TEXT NOT NULL,"        # the citing patent / the patent this family-link belongs to
            " dst_pub TEXT NOT NULL,"        # the cited patent / the parent|child patent
            " link_type TEXT NOT NULL,"      # 'cites' | 'parent' | 'child'
            " category TEXT,"                # citations: EXA(examiner)|APP(applicant)|X|Y|A …
            " UNIQUE(src_pub, dst_pub, link_type))"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_plinks_src ON patent_links(src_pub, link_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_plinks_dst ON patent_links(dst_pub, link_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_pubnum ON raw_entries(pub_number)")
        # Backfill pub_number for already-ingested Google-Patents rows (url -> number).
        conn.execute(
            "UPDATE raw_entries SET pub_number = "
            "replace(replace(url, 'https://patents.google.com/patent/', ''), '/en', '') "
            "WHERE pub_number IS NULL AND url LIKE 'https://patents.google.com/patent/%'"
        )
        # Backfill kind_code by parsing the trailing segment of pub_number (US-123-B2 -> B2).
        import re as _re
        todo = conn.execute(
            "SELECT id, pub_number FROM raw_entries WHERE pub_number IS NOT NULL AND kind_code IS NULL"
        ).fetchall()
        upd = []
        for row in todo:
            rid = row["id"] if isinstance(row, dict) else row[0]
            pub = row["pub_number"] if isinstance(row, dict) else row[1]
            last = (pub or "").rsplit("-", 1)[-1]
            if _re.fullmatch(r"[A-Z]{1,2}\d?", last):
                upd.append((last, rid))
        if upd:
            conn.executemany("UPDATE raw_entries SET kind_code = ? WHERE id = ?", upd)


def insert_patent_links(rows: list[tuple]) -> int:
    """Batch-insert citation/family edges (src_pub, dst_pub, link_type, category).
    INSERT OR IGNORE on the UNIQUE key so re-ingests don't duplicate edges."""
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO patent_links (src_pub, dst_pub, link_type, category) "
            "VALUES (?, ?, ?, ?)", rows)
        return len(rows)


import re as _re_cpc
# Optional leading digit: BDDS ingests before the #79 fix mixed JP's national
# "FI" classification scheme in with real CPC. FI symbols embed a stray leading
# digit (historically the IPC edition) before an otherwise CPC-shaped symbol,
# e.g. "4F21S43/237" — strip it so the real subclass ("F21S") is recovered.
# JP F-term codes ("3E068/AA40") never match — after the digit there's no
# valid [A-HY]\d{2}[A-Z] pattern — so they correctly still resolve to None.
_CPC_SUBCLASS = _re_cpc.compile(r"^\d?([A-HY]\d{2}[A-Z])")


def cpc_subclass(code: str) -> str | None:
    """CPC code → subclass key for domain grouping, e.g. 'A61K9/00' → 'A61K'."""
    m = _CPC_SUBCLASS.match((code or "").replace(" ", ""))
    return m.group(1) if m else None


def _migrate_patent_cpc():
    """Structured CPC storage: one row per (patent, CPC symbol) so domain scoping /
    grouping is an indexed GROUP BY instead of parsing CPC out of the excerpt text.
    `subclass` is denormalized (A61K9/00 → A61K) for the tir_graph domain rollup.
    Idempotent, SQLite only — created on the next init_db (i.e. next ingest run)."""
    if USE_POSTGRES:
        return
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS patent_cpc ("
            " pub_number TEXT NOT NULL,"      # the patent (= raw_entries.pub_number)
            " cpc TEXT NOT NULL,"             # full CPC symbol, e.g. A61K9/00
            " subclass TEXT,"                 # denormalized subclass, e.g. A61K
            " inventive INTEGER DEFAULT 1,"   # 1=inventive (I), 0=additional (A)
            " UNIQUE(pub_number, cpc))"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pcpc_pub ON patent_cpc(pub_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pcpc_sub ON patent_cpc(subclass)")


def insert_patent_cpc(rows: list[tuple]) -> int:
    """Batch-insert (pub_number, cpc, subclass, inventive). INSERT OR IGNORE on
    UNIQUE(pub_number, cpc) so re-ingests stay idempotent."""
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO patent_cpc (pub_number, cpc, subclass, inventive) "
            "VALUES (?, ?, ?, ?)", rows)
        return len(rows)


def insert_patent_family(rows: list[tuple]) -> int:
    """Batch-insert (pub_number, family_id) — DOCDB-simple-family aus dem
    exchange-document-Attribut (#7, 2026-08-09). Idempotent via PK pub_number;
    Tabelle wird von scripts/extract_bdds_attrs.py angelegt (Back-File) und hier
    vom Weekly-Ingest weitergefuehrt."""
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO patent_family (pub_number, family_id) "
            "VALUES (?, ?)", rows)
        return len(rows)


def insert_patent_assignees(rows: list[tuple]) -> int:
    """Batch-insert (pub_number, seq, name, fmt) — Anmelder-Rohnamen, bester
    Format-Rang je Sequenz (docdba > original > docdb), analog extract_bdds_attrs."""
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO patent_assignee_raw (pub_number, seq, name, fmt) "
            "VALUES (?, ?, ?, ?)", rows)
        return len(rows)


# --- OpenAlex graph layer (issue #9) — science analog of the patent graph -----

def _migrate_openalex_graph():
    """Science-signal graph layer (issue #9), mirroring the patent graph:
    raw_entries.openalex_id = node key (analog pub_number);
    openalex_citations = referenced_works edges (analog patent_links);
    openalex_topics = Topic/Subfield/Field/Domain rows (analog patent_cpc);
    openalex_meta = native forward-velocity (cited_by_count, counts_by_year)
    + type (preprint = earliest tier) + is_retracted (negative signal).
    Idempotent."""
    with get_connection() as conn:
        if USE_POSTGRES:
            conn.execute("ALTER TABLE raw_entries ADD COLUMN IF NOT EXISTS openalex_id TEXT")
        else:
            try:
                conn.execute("ALTER TABLE raw_entries ADD COLUMN openalex_id TEXT")
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    raise
        conn.execute(
            "CREATE TABLE IF NOT EXISTS openalex_citations ("
            " src_id TEXT NOT NULL,"      # citing work (our ingested work)
            " dst_id TEXT NOT NULL,"      # referenced work (OpenAlex id, self-contained)
            " UNIQUE(src_id, dst_id))")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oacit_src ON openalex_citations(src_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oacit_dst ON openalex_citations(dst_id)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS openalex_topics ("
            " work_id TEXT NOT NULL,"
            " topic_id TEXT NOT NULL,"    # T####
            " topic TEXT," " subfield TEXT," " field TEXT," " domain TEXT,"
            " score REAL,"
            " is_primary INTEGER DEFAULT 0,"
            " UNIQUE(work_id, topic_id))")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oatop_work ON openalex_topics(work_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_oatop_sub ON openalex_topics(subfield)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS openalex_meta ("
            " work_id TEXT PRIMARY KEY,"
            " cited_by_count INTEGER,"
            " counts_by_year TEXT,"       # JSON [{year, cited_by_count}, …]
            " work_type TEXT,"            # article | preprint | review | …
            " is_retracted INTEGER DEFAULT 0)")


def insert_openalex_citations(rows: list[tuple]) -> int:
    """Batch (src_id, dst_id) edges; idempotent on UNIQUE(src,dst)."""
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO openalex_citations (src_id, dst_id) VALUES (?, ?)", rows)
        return len(rows)


def insert_openalex_topics(rows: list[tuple]) -> int:
    """Batch (work_id, topic_id, topic, subfield, field, domain, score, is_primary)."""
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO openalex_topics "
            "(work_id, topic_id, topic, subfield, field, domain, score, is_primary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        return len(rows)


def insert_openalex_meta(rows: list[tuple]) -> int:
    """Batch (work_id, cited_by_count, counts_by_year_json, work_type, is_retracted).
    Upsert — a re-ingest refreshes the forward-velocity counters."""
    if not rows:
        return 0
    # dedup within-batch by work_id (keep last) — ON CONFLICT DO UPDATE can't hit
    # the same target row twice in one statement (a work can recur across pages)
    rows = list({r[0]: r for r in rows}.values())
    with get_connection() as conn:
        if USE_POSTGRES:
            import psycopg2.extras
            cur = conn._conn.cursor()
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO openalex_meta (work_id, cited_by_count, counts_by_year, "
                "work_type, is_retracted) VALUES %s "
                "ON CONFLICT (work_id) DO UPDATE SET cited_by_count = EXCLUDED.cited_by_count, "
                "counts_by_year = EXCLUDED.counts_by_year, is_retracted = EXCLUDED.is_retracted",
                rows, page_size=max(len(rows), 1000))
            return len(rows)
        conn.executemany(
            "INSERT OR REPLACE INTO openalex_meta (work_id, cited_by_count, counts_by_year, "
            "work_type, is_retracted) VALUES (?, ?, ?, ?, ?)", rows)
        return len(rows)


def insert_raw_entries_market_batch(rows: list[tuple]) -> int:
    """Bulk market-tier raw-entry insert (WordPress archives, GDELT, …). Row shape:
    (source_id, url, title, excerpt, published_date). Dedup on url. Returns inserted."""
    if not rows:
        return 0
    rows = list({r[1]: r for r in rows}.values())  # dedup by url within batch
    with get_connection() as conn:
        if USE_POSTGRES:
            import psycopg2.extras
            cur = conn._conn.cursor()
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO raw_entries (source_id, url, title, excerpt, published_date) "
                "VALUES %s ON CONFLICT (url) DO NOTHING",
                rows, page_size=max(len(rows), 1000))
            return max(cur.rowcount, 0)
        conn.executemany(
            "INSERT OR IGNORE INTO raw_entries (source_id, url, title, excerpt, published_date) "
            "VALUES (?, ?, ?, ?, ?)", rows)
        return len(rows)


def insert_raw_entries_batch_oa(rows: list[tuple]) -> int:
    """Bulk raw-entry insert incl. openalex_id (node key). Row shape:
    (source_id, url, title, excerpt, published_date, openalex_id)."""
    if not rows:
        return 0
    rows = list({r[1]: r for r in rows}.values())  # dedup by url within batch
    with get_connection() as conn:
        if USE_POSTGRES:
            import psycopg2.extras
            cur = conn._conn.cursor()
            # On a url-conflict (the work was already ingested as a text-layer
            # journal/concept entry), backfill the openalex_id node key so the
            # existing row joins the graph — don't just skip it.
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO raw_entries (source_id, url, title, excerpt, published_date, "
                "openalex_id) VALUES %s ON CONFLICT (url) DO UPDATE SET "
                "openalex_id = COALESCE(raw_entries.openalex_id, EXCLUDED.openalex_id)",
                rows, page_size=max(len(rows), 1000))
            return max(cur.rowcount, 0)
        for r in rows:
            conn.execute(
                "INSERT INTO raw_entries (source_id, url, title, excerpt, published_date, openalex_id) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(url) DO UPDATE SET "
                "openalex_id = COALESCE(raw_entries.openalex_id, excluded.openalex_id)", r)
        return len(rows)


def backfill_patent_cpc_from_excerpt(batch: int = 5000) -> int:
    """One-off: populate patent_cpc for already-ingested patents by parsing the
    'CPC: ...' field out of their excerpt (lossy — only the ≤6 codes the excerpt
    kept). Future ingests write the full set structured at parse time. Run AFTER
    the live pipeline run finishes (writes to a new table; no locking of trends)."""
    if USE_POSTGRES:
        return 0
    _migrate_patent_cpc()
    field = _re_cpc.compile(r"CPC:\s*([^.]+)", _re_cpc.IGNORECASE)
    code_re = _re_cpc.compile(r"[A-HY]\d{2}[A-Z]\d{1,4}/?\d*")
    total = 0
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT pub_number, excerpt FROM raw_entries "
            "WHERE pub_number IS NOT NULL AND excerpt LIKE '%CPC:%'"
        ).fetchall()
    buf: list[tuple] = []
    for r in rows:
        pub = r["pub_number"] if isinstance(r, dict) else r[0]
        ex = r["excerpt"] if isinstance(r, dict) else r[1]
        m = field.search(ex or "")
        if not m:
            continue
        for code in {c.replace(" ", "") for c in code_re.findall(m.group(1))}:
            buf.append((pub, code, cpc_subclass(code), 1))
        if len(buf) >= batch:
            total += insert_patent_cpc(buf); buf.clear()
    total += insert_patent_cpc(buf)
    logger.info("patent_cpc backfill: %d (pub,cpc) rows from excerpts", total)
    return total


def _migrate_embedding_1024():
    """Add the 1024-dim Matryoshka-prefix ANN column + partial HNSW index the search
    API / technology views depend on (#52). Idempotent; Postgres only (SQLite keeps
    raw embedding bytes). scripts/build_ann_index.py backfills existing rows from the
    4096-dim vectors; this guarantees a FRESH schema already has the column so the
    first insert_trend() (which writes embedding_1024) doesn't fail."""
    if not USE_POSTGRES:
        return
    with get_connection() as conn:
        cur = conn._conn.cursor()
        cur.execute("ALTER TABLE trends ADD COLUMN IF NOT EXISTS embedding_1024 VECTOR(1024)")
        # partial HNSW over published rows — matches api/search ANN assumptions and
        # pg_finalize.sql. Instant on an empty table; IF NOT EXISTS on a built one.
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trends_emb1024_pub_hnsw ON trends "
                    "USING hnsw (embedding_1024 vector_cosine_ops) WHERE status = 'published'")
        conn._conn.commit()


def _migrate_source_lead_time_tier():
    """Create + populate the source_name→lead_time_tier lookup the search API LEFT
    JOINs (#53). Without it a fresh/rebuilt Postgres 500s on /api/search. Idempotent:
    CREATE IF NOT EXISTS + upsert from sources.yaml. Postgres only (SQLite builds it
    via scripts/setup_fts5.py)."""
    if not USE_POSTGRES:
        return
    import yaml
    from psycopg2.extras import execute_values
    tier_map: dict[str, str] = {}
    sources_yaml = Path(__file__).parent.parent / "sources.yaml"
    if sources_yaml.exists():
        def _walk(node):
            if isinstance(node, list):
                for i in node:
                    _walk(i)
            elif isinstance(node, dict):
                if "name" in node and "lead_time_tier" in node:
                    tier_map[node["name"]] = node["lead_time_tier"]
                for v in node.values():
                    _walk(v)
        _walk(yaml.safe_load(sources_yaml.read_text(encoding="utf-8")))
    with get_connection() as conn:
        cur = conn._conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS source_lead_time_tier ("
                    "source_name TEXT PRIMARY KEY, "
                    "lead_time_tier TEXT CHECK (lead_time_tier IN ('future','market','now')))")
        if tier_map:
            execute_values(cur,
                "INSERT INTO source_lead_time_tier (source_name, lead_time_tier) VALUES %s "
                "ON CONFLICT (source_name) DO UPDATE SET lead_time_tier = EXCLUDED.lead_time_tier",
                list(tier_map.items()))
        conn._conn.commit()


def init_db():
    """Initialize database schema."""
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        try:
            cur = conn.cursor()
            cur.execute(PG_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        logger.info("PostgreSQL database initialized")
    else:
        with get_connection() as conn:
            conn.executescript(SQLITE_SCHEMA)
        logger.info("SQLite database initialized at %s", get_db_path())
    _migrate_stage_cache_columns()
    _migrate_trends_sort_date()
    _migrate_reviewed_at()
    _migrate_open_licence()
    _migrate_licence_checked()
    _migrate_judged_at()
    _migrate_review_reason()
    _migrate_sources_llm_pipeline()
    _migrate_patent_graph()
    _migrate_patent_cpc()
    _migrate_openalex_graph()
    _migrate_embedding_1024()
    _migrate_source_lead_time_tier()


# --- Source Operations ---

def upsert_source(name: str, feed_url: str, source_type: str, vertical: str,
                  llm_pipeline: bool = True) -> int:
    """Insert or update a source. Returns source id.

    `llm_pipeline=False` marks a signal-only pseudo-source (funding, grants):
    its entries get embedded and distill-classified, but the content cycle
    never writes articles from them. Existing sources keep their stored flag —
    like every other column, upsert does not overwrite."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM sources WHERE feed_url = ?", (feed_url,)
        ).fetchone()
        if row:
            return row["id"] if isinstance(row, dict) else row[0]

        if USE_POSTGRES:
            cursor = conn.execute(
                "INSERT INTO sources (name, feed_url, source_type, vertical, llm_pipeline) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (name, feed_url, source_type, vertical, llm_pipeline),
            )
            return cursor.lastrowid
        else:
            cursor = conn.execute(
                "INSERT INTO sources (name, feed_url, source_type, vertical, llm_pipeline) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, feed_url, source_type, vertical, int(llm_pipeline)),
            )
            return cursor.lastrowid


# --- Raw Entry Operations ---

def known_entry_urls(urls: list[str]) -> set[str]:
    """Which of these URLs already sit in raw_entries. Read-only.

    For the poller's dry run (#97, 2026-09-09): count what a real poll WOULD
    insert without writing a row or touching sources.last_fetched."""
    if not urls:
        return set()
    out: set[str] = set()
    with get_connection() as conn:
        for i in range(0, len(urls), 500):
            chunk = urls[i:i + 500]
            marks = ", ".join(["?"] * len(chunk))
            rows = conn.execute(
                f"SELECT url FROM raw_entries WHERE url IN ({marks})", chunk).fetchall()
            out.update(r["url"] if hasattr(r, "keys") else r[0] for r in rows)
    return out


def insert_raw_entry(source_id: int, url: str, title: str, excerpt: str,
                     published_date: str | None = None, pub_number: str | None = None,
                     kind_code: str | None = None, openalex_id: str | None = None) -> int | None:
    """Insert a raw entry. Returns id or None if duplicate URL.

    `pub_number` (patent publication number) is the node key for the citation/
    family graph; `kind_code` (A1/B2/…) flags application vs grant. Both NULL for
    non-patent entries. `openalex_id` (W…) is the science-graph node key — the
    join to `openalex_meta` (work type, #73); on a duplicate URL it is backfilled
    onto the existing row (COALESCE, never overwritten) so an earlier text-layer
    ingest of the same work still gets its type."""
    cols = "source_id, url, title, excerpt, published_date, pub_number, kind_code"
    vals: tuple = (source_id, url, title, excerpt, published_date, pub_number, kind_code)
    if openalex_id:
        cols += ", openalex_id"
        vals += (openalex_id,)
    marks = ", ".join(["%s" if USE_POSTGRES else "?"] * len(vals))
    with get_connection() as conn:
        try:
            if USE_POSTGRES:
                cursor = conn.execute(
                    f"INSERT INTO raw_entries ({cols}) VALUES ({marks}) "
                    "ON CONFLICT (url) DO NOTHING RETURNING id", vals)
                result = cursor.fetchone()
                if result:
                    return result["id"]
            else:
                cursor = conn.execute(f"INSERT INTO raw_entries ({cols}) VALUES ({marks})", vals)
                return cursor.lastrowid
        except (sqlite3.IntegrityError, Exception) as e:
            if not ("IntegrityError" in type(e).__name__ or "unique" in str(e).lower()
                    or "duplicate" in str(e).lower()):
                raise
    # duplicate URL: backfill the node key onto the existing row
    if openalex_id:
        with get_connection() as conn:
            conn.execute("UPDATE raw_entries SET openalex_id = COALESCE(openalex_id, ?) WHERE url = ?",
                         (openalex_id, url))
    return None


def insert_raw_entries_batch(rows: list[tuple]) -> int:
    """Bulk raw-entry insert for mass ingest (the DOCDB back-file is ~16M rows —
    the per-row insert_raw_entry opens a connection per patent, ~100/s ≈ 44h;
    batched this is ~1-2h). Row shape mirrors insert_raw_entry:
    (source_id, url, title, excerpt, published_date, pub_number, kind_code).
    Duplicates (url) are skipped. Returns inserted count."""
    if not rows:
        return 0
    with get_connection() as conn:
        if USE_POSTGRES:
            import psycopg2.extras
            cur = conn._conn.cursor()
            # page_size >= len(rows) → one statement → cur.rowcount is the exact
            # number actually inserted (ON CONFLICT skips don't count).
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO raw_entries (source_id, url, title, excerpt, published_date, "
                "pub_number, kind_code) VALUES %s ON CONFLICT (url) DO NOTHING",
                rows, page_size=max(len(rows), 1000))
            return max(cur.rowcount, 0)
        conn.executemany(
            "INSERT OR IGNORE INTO raw_entries (source_id, url, title, excerpt, "
            "published_date, pub_number, kind_code) VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        return len(rows)  # approximation under SQLite (dups not separable cheaply)


def get_unprocessed_entries(limit: int = 50, min_id: int = 0,
                            exclude_patents: bool = True,
                            per_source_cap: int | None = None) -> list[dict]:
    """Get raw entries that haven't been processed yet.

    `min_id` restricts to re.id > min_id — used to scope the RSS pipeline to
    freshly-polled entries so it doesn't pick up a large backfill backlog that
    shares the unprocessed pool (the backfill is classified separately, locally).

    `exclude_patents` (default True) skips patent rows (pub_number IS NOT NULL).
    This is the RSS content-generation pipeline; the 18M-patent backfill shares
    the unprocessed pool AND overlaps the RSS id range, so min_id alone can't
    keep it out — content-gen must never run on patents. Patents are embedded/
    classified separately by signal_batch.

    `per_source_cap` (default CYCLE_MAX_PER_SOURCE) bounds how many entries ONE
    source contributes per call. Owner rule 2026-08-20: funding news may become
    articles through the regular cycle — what must never happen is a mass ingest
    (235k SBIR/CORDIS rows) flooding content generation. Normal RSS sources run
    at p95 ≈ 70 entries/day, so the default 200 never touches regular operation;
    a dump contributes its oldest `cap` entries per run and the rest waits for
    signal_batch. Sources flagged llm_pipeline=FALSE stay excluded entirely
    (manual kill switch; COALESCE keeps NULL from pre-migration DBs flowing).

    An entry with `open_licence` set is admitted even from a signal-only source
    (#97 Weg B, 2026-09-09): the article itself is licensed CC BY/CC0, so the
    host's TDM reservation does not reach it. Only scripts/resolve_open_licence.py
    ever sets that column, and only after verifying the licence against OpenAlex.

    Inactive sources (`active = FALSE`) are excluded too (#97, 2026-09-09).
    Deactivating a source used to stop only the polling — its already-fetched
    backlog kept flowing into content generation. That is how the 33 TDM-reserved
    journals, switched off on 2026-09-04, still produced 187 published articles
    on 2026-09-08."""
    if per_source_cap is None:
        from pipeline.config import CYCLE_MAX_PER_SOURCE
        per_source_cap = CYCLE_MAX_PER_SOURCE
    patent_clause = "AND re.pub_number IS NULL " if exclude_patents else ""
    with get_connection() as conn:
        # rank on a slim id-only scan first — the outer join fetches full rows
        # (raw_content!) only for the ≤ cap×sources winners, so a 200k dump does
        # not get materialised just to be discarded.
        rows = conn.execute(
            "WITH ranked AS ("
            "  SELECT re.id AS rid, ROW_NUMBER() OVER ("
            "           PARTITION BY re.source_id ORDER BY re.fetched_at ASC, re.id ASC"
            "         ) AS rn "
            "    FROM raw_entries re JOIN sources s ON re.source_id = s.id "
            "   WHERE re.processed = FALSE AND re.filtered_out = FALSE AND re.id > ? "
            "     AND (COALESCE(s.llm_pipeline, TRUE) = TRUE OR re.open_licence IS NOT NULL) "
            "     AND COALESCE(s.active, TRUE) = TRUE "
            + patent_clause +
            ") "
            "SELECT re.*, s.name as source_name, s.vertical as source_vertical, "
            "       s.source_type as source_type "
            "  FROM ranked JOIN raw_entries re ON re.id = ranked.rid "
            "  JOIN sources s ON re.source_id = s.id "
            " WHERE ranked.rn <= ? "
            " ORDER BY re.fetched_at ASC LIMIT ?",
            (min_id, per_source_cap, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_filtered(entry_id: int, reason: str, embedding_blob: bytes | None = None):
    """Mark an entry as filtered out.

    embedding_blob: if the caller already computed the entry's embedding (the
    distill path embeds BEFORE the relevance gate), persist it here instead of
    discarding it — the drift-hedge policy (owner 2026-07-02) wants embeddings
    for filtered signals too, and at this point the vector is free."""
    with get_connection() as conn:
        if embedding_blob is not None:
            conn.execute(
                "UPDATE raw_entries SET processed = TRUE, filtered_out = TRUE, "
                "filter_reason = ?, embedding_blob = ? WHERE id = ?",
                (reason, embedding_blob, entry_id),
            )
        else:
            conn.execute(
                "UPDATE raw_entries SET processed = TRUE, filtered_out = TRUE, filter_reason = ? WHERE id = ?",
                (reason, entry_id),
            )


def mark_processed(entry_id: int):
    """Mark an entry as processed."""
    with get_connection() as conn:
        conn.execute("UPDATE raw_entries SET processed = TRUE WHERE id = ?", (entry_id,))


_STAGE_TO_COLUMN = {
    "relevance": "relevance_json",
    "extraction": "extraction_json",
    "classification": "classification_json",
    "embedding": "embedding_blob",
    "content_en": "content_en_json",
}


def save_stage_result(entry_id: int, stage: str, result):
    """Persist an LLM stage result so a crash mid-pipeline doesn't waste GPU work.

    `result` is either a Pydantic model (json-serialised) or raw bytes for embedding.
    """
    if stage not in _STAGE_TO_COLUMN:
        raise ValueError(f"Unknown stage: {stage}")
    col = _STAGE_TO_COLUMN[stage]
    if stage == "embedding":
        value = result
    elif hasattr(result, "model_dump_json"):
        value = result.model_dump_json()
    else:
        value = json.dumps(result)
    with get_connection() as conn:
        conn.execute(f"UPDATE raw_entries SET {col} = ? WHERE id = ?", (value, entry_id))


# --- Trend Operations ---

def insert_trend(entry_id: int, data: dict) -> int:
    """Insert a processed trend article."""
    with get_connection() as conn:
        if USE_POSTGRES:
            embedding_val = data.get("embedding")
            if isinstance(embedding_val, bytes):
                # Convert bytes to list for pgvector
                import struct
                n = len(embedding_val) // 4
                embedding_val = list(struct.unpack(f"{n}f", embedding_val))
            # embedding_1024 = Matryoshka prefix for the ANN search column
            # (partial HNSW index; the 4096-dim col can't be HNSW-indexed).
            # Without this, new trends would be invisible to /api/search.
            emb_1024 = embedding_val[:1024] if embedding_val else None
            cursor = conn.execute(
                """INSERT INTO trends (
                    raw_entry_id, title_en, title_de, slug,
                    summary_en, summary_de, body_en, body_de,
                    verticals, primary_vertical, pestel, tags,
                    trend_signal_type, mega_trend, trend_level,
                    brands, regions, trend_score, confidence,
                    source_url, source_name, embedding, embedding_1024, status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id""",
                (
                    entry_id,
                    data["title_en"], data.get("title_de"), data["slug"],
                    data.get("summary_en"), data.get("summary_de"),
                    data.get("body_en"), data.get("body_de"),
                    json.dumps(data.get("verticals", [])),
                    data.get("primary_vertical"),
                    json.dumps(data.get("pestel", [])),
                    json.dumps(data.get("tags", [])),
                    data.get("trend_signal_type"),
                    data.get("mega_trend"),
                    data.get("trend_level"),
                    json.dumps(data.get("brands", [])),
                    json.dumps(data.get("regions", [])),
                    data.get("trend_score"),
                    data.get("confidence"),
                    data["source_url"],
                    data.get("source_name"),
                    str(embedding_val) if embedding_val else None,
                    str(emb_1024) if emb_1024 else None,
                    # signal-mode rows must keep status='signal' — landing as
                    # 'draft' would let auto_publish push content-less rows live
                    data.get("status") or "draft",
                ),
            )
            return cursor.lastrowid
        else:
            cursor = conn.execute(
                """INSERT INTO trends (
                    raw_entry_id, title_en, title_de, slug,
                    summary_en, summary_de, body_en, body_de,
                    verticals, primary_vertical, pestel, tags,
                    trend_signal_type, mega_trend, trend_level,
                    brands, regions, trend_score, confidence,
                    source_url, source_name, embedding
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    data["title_en"], data.get("title_de"), data["slug"],
                    data.get("summary_en"), data.get("summary_de"),
                    data.get("body_en"), data.get("body_de"),
                    json.dumps(data.get("verticals", [])),
                    data.get("primary_vertical"),
                    json.dumps(data.get("pestel", [])),
                    json.dumps(data.get("tags", [])),
                    data.get("trend_signal_type"),
                    data.get("mega_trend"),
                    data.get("trend_level"),
                    json.dumps(data.get("brands", [])),
                    json.dumps(data.get("regions", [])),
                    data.get("trend_score"),
                    data.get("confidence"),
                    data["source_url"],
                    data.get("source_name"),
                    data.get("embedding"),
                ),
            )
            new_id = cursor.lastrowid
            # signal-mode inserts a content-less trend as status='signal'
            # (excluded from auto-publish + public grid, included in foresight).
            st = data.get("status")
            if st and st != "draft":
                conn.execute("UPDATE trends SET status = ? WHERE id = ?", (st, new_id))
            return new_id


def get_trends(status: str | None = None, vertical: str | None = None,
               limit: int = 50, offset: int = 0) -> list[dict]:
    """Get trends with optional filters."""
    query = "SELECT * FROM trends WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if vertical:
        query += " AND primary_vertical = ?"
        params.append(vertical)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.append(limit)
    params.append(offset)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            # Parse JSON fields
            for field in ("verticals", "pestel", "tags", "brands", "companies", "regions"):
                if field in d:
                    d[field] = _json_loads(d[field])
            # Remove embedding from results (binary blob, not needed in API)
            d.pop("embedding", None)
            results.append(d)
        return results


def slug_exists(slug: str) -> bool:
    """True if a trend row already carries this slug (UNIQUE column)."""
    with get_connection() as conn:
        return conn.execute("SELECT 1 FROM trends WHERE slug = ? LIMIT 1", (slug,)).fetchone() is not None


def get_trend_by_slug(slug: str) -> dict | None:
    """Get a single trend by slug."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM trends WHERE slug = ?", (slug,)).fetchone()
        if not row:
            return None
        d = dict(row)
        for field in ("verticals", "pestel", "tags", "brands", "companies", "regions"):
            if field in d:
                d[field] = _json_loads(d[field])
        d.pop("embedding", None)
        return d


def get_trend_by_id(trend_id: int) -> dict | None:
    """Get a single trend by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM trends WHERE id = ?", (trend_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        for field in ("verticals", "pestel", "tags", "brands", "companies", "regions"):
            if field in d:
                d[field] = _json_loads(d[field])
        d.pop("embedding", None)
        return d


def update_trend_status(trend_id: int, status: str, auto_published: bool = False):
    """Update trend status."""
    with get_connection() as conn:
        if status == "published":
            # Python bool adapts correctly on both backends (SQLite stores 0/1,
            # psycopg2 maps to boolean — an int literal would fail on PG).
            conn.execute(
                "UPDATE trends SET status = ?, published_at = ?, auto_published = ? WHERE id = ?",
                (status, _now_iso(), bool(auto_published), trend_id),
            )
        else:
            conn.execute(
                "UPDATE trends SET status = ? WHERE id = ?",
                (status, trend_id),
            )


def get_trends_count(status: str | None = None, vertical: str | None = None) -> int:
    """Get count of trends with optional filters."""
    query = "SELECT COUNT(*) as cnt FROM trends WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if vertical:
        query += " AND primary_vertical = ?"
        params.append(vertical)
    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()
        return row["cnt"] if isinstance(row, dict) else row[0]


def get_vertical_counts(status: str | None = None) -> dict[str, int]:
    """Get trend count per vertical."""
    query = "SELECT primary_vertical, COUNT(*) as cnt FROM trends WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " GROUP BY primary_vertical ORDER BY cnt DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return {row["primary_vertical"]: row["cnt"] for row in rows
                if (row["primary_vertical"] if isinstance(row, dict) else row[0])}


# --- Embedding Operations ---

def get_recent_titles(days: int = 30) -> list[str]:
    """Get recent trend titles (EN) for fast title-level dedup.

    Used by the batch LLM processor to filter out raw entries whose title
    closely matches an existing trend before any LLM call is spent on them.

    Hand-rejected rows are excluded, for the same reason as in
    get_recent_embeddings: "Write again" on the review desk retires the old
    article (rejected + reviewed_at) and re-queues its raw entry — the retired
    title must not kill the rewrite as a duplicate of itself. Sweep rejections
    (reviewed_at IS NULL) keep blocking.
    """
    reviewed_clause = "AND NOT (status = 'rejected' AND reviewed_at IS NOT NULL) "
    with get_connection() as conn:
        if USE_POSTGRES:
            rows = conn.execute(
                "SELECT title_en FROM trends "
                "WHERE title_en IS NOT NULL AND created_at > NOW() - make_interval(days => %s) "
                + reviewed_clause,
                (days,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT title_en FROM trends "
                "WHERE title_en IS NOT NULL AND created_at > datetime('now', ?) "
                + reviewed_clause,
                (f"-{days} days",),
            ).fetchall()
        return [row["title_en"] if isinstance(row, dict) else row[0] for row in rows]


def _vector_to_bytes(v) -> bytes | None:
    """Normalize an embedding to a float32 buffer. SQLite already stores bytes;
    Postgres/pgvector returns a text literal '[f1,f2,…]' — parse + pack so that
    downstream np.frombuffer consumers (dedup matrices) work on both backends."""
    if v is None or isinstance(v, (bytes, bytearray)):
        return v
    if isinstance(v, memoryview):
        return v.tobytes()
    s = str(v).strip().strip("[]")
    if not s:
        return None
    import numpy as _np
    return _np.array(s.split(","), dtype=_np.float32).tobytes()


def get_recent_embeddings(days: int = 30, limit: int = 120_000) -> list[tuple[int, bytes]]:
    """Get embeddings from the last N days for dedup checking, newest first and
    capped at `limit` rows. The cap bounds RAM: a mass backfill can insert 500k+
    signals in a day, and loading them all as a 4096-d matrix (~8 GB at 500k)
    OOM-killed the run under concurrent load. The newest `limit` rows are more
    than enough to catch duplicates of a fresh batch (dups are recent).

    Hand-rejected articles are excluded. A reviewer rejects the TEXT (an invented
    figure, a truncated body), not the story — but their embedding used to sit in
    this window for 30 days and silently killed the next outlet's coverage of the
    same event as a duplicate, so the story was lost entirely. Sweep rejections
    (advertorials, reviewed_at IS NULL) DO stay: there the source is the problem
    and suppressing follow-ups is the point. reviewed_at is what separates them.
    """
    reviewed_clause = "AND NOT (status = 'rejected' AND reviewed_at IS NOT NULL) "
    with get_connection() as conn:
        if USE_POSTGRES:
            rows = conn.execute(
                "SELECT id, embedding::text AS embedding FROM trends "
                "WHERE embedding IS NOT NULL AND created_at > NOW() - make_interval(days => %s) "
                + reviewed_clause +
                "ORDER BY id DESC LIMIT %s",
                (days, limit),
            ).fetchall()
            return [(row["id"], _vector_to_bytes(row["embedding"])) for row in rows]
        rows = conn.execute(
            "SELECT id, embedding FROM trends "
            "WHERE embedding IS NOT NULL AND created_at > datetime('now', ?) "
            + reviewed_clause +
            "ORDER BY id DESC LIMIT ?",
            (f"-{days} days", limit),
        ).fetchall()
        return [(row["id"] if isinstance(row, dict) else row[0],
                 row["embedding"] if isinstance(row, dict) else row[1])
                for row in rows]


# --- Source Operations ---

def update_source_last_fetched(source_id: int):
    """Update last_fetched timestamp for a source."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE sources SET last_fetched = ? WHERE id = ?",
            (_now_iso(), source_id),
        )


def insert_source_discovery(data: dict) -> int:
    """Log a source discovery from radar."""
    with get_connection() as conn:
        if USE_POSTGRES:
            cursor = conn.execute(
                "INSERT INTO source_discoveries "
                "(radar_source, radar_vertical, original_title, extracted_brand, "
                "discovered_url, discovered_domain) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    data.get("radar_source", "trendhunter"),
                    data.get("radar_vertical"),
                    data.get("original_title"),
                    data.get("extracted_brand"),
                    data.get("discovered_url"),
                    data.get("discovered_domain"),
                ),
            )
            return cursor.lastrowid
        else:
            cursor = conn.execute(
                "INSERT INTO source_discoveries "
                "(radar_source, radar_vertical, original_title, extracted_brand, "
                "discovered_url, discovered_domain) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    data.get("radar_source", "trendhunter"),
                    data.get("radar_vertical"),
                    data.get("original_title"),
                    data.get("extracted_brand"),
                    data.get("discovered_url"),
                    data.get("discovered_domain"),
                ),
            )
            return cursor.lastrowid


def get_discovery_count(domain: str) -> int:
    """Get number of times a domain has been discovered."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM source_discoveries WHERE discovered_domain = ?",
            (domain,),
        ).fetchone()
        return row["cnt"] if isinstance(row, dict) else row[0]
