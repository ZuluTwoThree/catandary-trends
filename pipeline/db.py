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
    source_type TEXT CHECK (source_type IN ('trade_media', 'press_wire', 'brand', 'api', 'radar')),
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
    filter_reason TEXT
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
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'rejected')),
    auto_published INTEGER DEFAULT 0,
    published_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
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
    source_type TEXT CHECK (source_type IN ('trade_media', 'press_wire', 'brand', 'api', 'radar')),
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
    filter_reason TEXT
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
    embedding VECTOR(1024),
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'review', 'published', 'rejected')),
    auto_published BOOLEAN DEFAULT false,
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

CREATE INDEX IF NOT EXISTS idx_raw_entries_url ON raw_entries(url);
CREATE INDEX IF NOT EXISTS idx_raw_entries_processed ON raw_entries(processed);
CREATE INDEX IF NOT EXISTS idx_trends_slug ON trends(slug);
CREATE INDEX IF NOT EXISTS idx_trends_status ON trends(status);
CREATE INDEX IF NOT EXISTS idx_trends_vertical ON trends(primary_vertical);
CREATE INDEX IF NOT EXISTS idx_trends_created ON trends(created_at);

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
                     published_date: str | None = None) -> int | None:
    """Insert a raw entry. Returns id or None if duplicate URL."""
    with get_connection() as conn:
        try:
            if USE_POSTGRES:
                cursor = conn.execute(
                    "INSERT INTO raw_entries (source_id, url, title, excerpt, published_date) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (url) DO NOTHING RETURNING id",
                    (source_id, url, title, excerpt, published_date),
                )
                result = cursor.fetchone()
                return result["id"] if result else None
            else:
                cursor = conn.execute(
                    "INSERT INTO raw_entries (source_id, url, title, excerpt, published_date) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (source_id, url, title, excerpt, published_date),
                )
                return cursor.lastrowid
        except (sqlite3.IntegrityError, Exception) as e:
            if "IntegrityError" in type(e).__name__ or "unique" in str(e).lower() or "duplicate" in str(e).lower():
                return None
            raise


def get_unprocessed_entries(limit: int = 50) -> list[dict]:
    """Get raw entries that haven't been processed yet."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT re.*, s.name as source_name, s.vertical as source_vertical, s.source_type as source_type "
            "FROM raw_entries re JOIN sources s ON re.source_id = s.id "
            "WHERE re.processed = 0 AND re.filtered_out = 0 "
            "ORDER BY re.fetched_at ASC LIMIT ?",
            (limit,),
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
                    source_url, source_name, embedding
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
            return cursor.lastrowid


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
