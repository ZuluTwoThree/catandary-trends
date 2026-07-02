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
            typ = pg_type if USE_POSTGRES else sqlite_type
            try:
                conn.execute(f"ALTER TABLE raw_entries ADD COLUMN {col} {typ}")
            except Exception as e:
                msg = str(e).lower()
                if "duplicate column" in msg or "already exists" in msg:
                    continue
                raise


def _migrate_trends_sort_date():
    """Add the indexed sort_date column (capped published date) + its indexes and
    auto-maintaining trigger to existing trends tables, and backfill rows. Idempotent.
    sort_date lets the frontend ORDER BY an index instead of a temp-b-tree over the
    trends⋈raw_entries join (the /trends slowness). SQLite only."""
    if USE_POSTGRES:
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
_CPC_SUBCLASS = _re_cpc.compile(r"^([A-HY]\d{2}[A-Z])")


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
    _migrate_patent_graph()
    _migrate_patent_cpc()


# --- Source Operations ---

def upsert_source(name: str, feed_url: str, source_type: str, vertical: str) -> int:
    """Insert or update a source. Returns source id."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM sources WHERE feed_url = ?", (feed_url,)
        ).fetchone()
        if row:
            return row["id"] if isinstance(row, dict) else row[0]

        if USE_POSTGRES:
            cursor = conn.execute(
                "INSERT INTO sources (name, feed_url, source_type, vertical) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (name, feed_url, source_type, vertical),
            )
            return cursor.lastrowid
        else:
            cursor = conn.execute(
                "INSERT INTO sources (name, feed_url, source_type, vertical) VALUES (?, ?, ?, ?)",
                (name, feed_url, source_type, vertical),
            )
            return cursor.lastrowid


# --- Raw Entry Operations ---

def insert_raw_entry(source_id: int, url: str, title: str, excerpt: str,
                     published_date: str | None = None, pub_number: str | None = None,
                     kind_code: str | None = None) -> int | None:
    """Insert a raw entry. Returns id or None if duplicate URL.

    `pub_number` (patent publication number) is the node key for the citation/
    family graph; `kind_code` (A1/B2/…) flags application vs grant. Both NULL for
    non-patent entries."""
    with get_connection() as conn:
        try:
            if USE_POSTGRES:
                cursor = conn.execute(
                    "INSERT INTO raw_entries (source_id, url, title, excerpt, published_date, pub_number, kind_code) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (url) DO NOTHING RETURNING id",
                    (source_id, url, title, excerpt, published_date, pub_number, kind_code),
                )
                result = cursor.fetchone()
                return result["id"] if result else None
            else:
                cursor = conn.execute(
                    "INSERT INTO raw_entries (source_id, url, title, excerpt, published_date, pub_number, kind_code) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (source_id, url, title, excerpt, published_date, pub_number, kind_code),
                )
                return cursor.lastrowid
        except (sqlite3.IntegrityError, Exception) as e:
            if "IntegrityError" in type(e).__name__ or "unique" in str(e).lower() or "duplicate" in str(e).lower():
                return None
            raise


def get_unprocessed_entries(limit: int = 50, min_id: int = 0) -> list[dict]:
    """Get raw entries that haven't been processed yet.

    `min_id` restricts to re.id > min_id — used to scope the RSS pipeline to
    freshly-polled entries so it doesn't pick up a large backfill backlog that
    shares the unprocessed pool (the backfill is classified separately, locally)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT re.*, s.name as source_name, s.vertical as source_vertical, s.source_type as source_type "
            "FROM raw_entries re JOIN sources s ON re.source_id = s.id "
            "WHERE re.processed = 0 AND re.filtered_out = 0 AND re.id > ? "
            "ORDER BY re.fetched_at ASC LIMIT ?",
            (min_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_filtered(entry_id: int, reason: str):
    """Mark an entry as filtered out."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE raw_entries SET processed = 1, filtered_out = 1, filter_reason = ? WHERE id = ?",
            (reason, entry_id),
        )


def mark_processed(entry_id: int):
    """Mark an entry as processed."""
    with get_connection() as conn:
        conn.execute("UPDATE raw_entries SET processed = 1 WHERE id = ?", (entry_id,))


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
            cursor = conn.execute(
                """INSERT INTO trends (
                    raw_entry_id, title_en, title_de, slug,
                    summary_en, summary_de, body_en, body_de,
                    verticals, primary_vertical, pestel, tags,
                    trend_signal_type, mega_trend, trend_level,
                    brands, regions, trend_score, confidence,
                    source_url, source_name, embedding, status
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
            conn.execute(
                "UPDATE trends SET status = ?, published_at = ?, auto_published = ? WHERE id = ?",
                (status, _now_iso(), 1 if auto_published else 0, trend_id),
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
    """
    with get_connection() as conn:
        if USE_POSTGRES:
            rows = conn.execute(
                "SELECT title_en FROM trends "
                "WHERE title_en IS NOT NULL AND created_at > NOW() - INTERVAL '%s days'",
                (days,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT title_en FROM trends "
                "WHERE title_en IS NOT NULL AND created_at > datetime('now', ?)",
                (f"-{days} days",),
            ).fetchall()
        return [row["title_en"] if isinstance(row, dict) else row[0] for row in rows]


def get_recent_embeddings(days: int = 30) -> list[tuple[int, bytes]]:
    """Get embeddings from the last N days for dedup checking."""
    with get_connection() as conn:
        if USE_POSTGRES:
            rows = conn.execute(
                "SELECT id, embedding FROM trends "
                "WHERE embedding IS NOT NULL AND created_at > NOW() - INTERVAL '%s days'",
                (days,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, embedding FROM trends "
                "WHERE embedding IS NOT NULL AND created_at > datetime('now', ?)",
                (f"-{days} days",),
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
