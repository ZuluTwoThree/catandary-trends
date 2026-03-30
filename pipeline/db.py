"""SQLite database layer for Catandary Trends."""

import json
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from pipeline.config import DATABASE_PATH

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    source_type TEXT CHECK (source_type IN ('trade_media', 'press_wire', 'brand', 'api', 'radar')),
    vertical TEXT CHECK (vertical IN ('FOOD','TECH','HEALTH','ECO','DESIGN','FASHION','BIZ','CULTURE','SOCIAL','LUXURY','CROSS')),
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

CREATE INDEX IF NOT EXISTS idx_raw_entries_url ON raw_entries(url);
CREATE INDEX IF NOT EXISTS idx_raw_entries_processed ON raw_entries(processed);
CREATE INDEX IF NOT EXISTS idx_trends_slug ON trends(slug);
CREATE INDEX IF NOT EXISTS idx_trends_status ON trends(status);
CREATE INDEX IF NOT EXISTS idx_trends_vertical ON trends(primary_vertical);
"""


def get_db_path() -> str:
    path = Path(DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


@contextmanager
def get_connection():
    """Get a database connection with row factory."""
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


def init_db():
    """Initialize database schema."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    logger.info("Database initialized at %s", get_db_path())


def upsert_source(name: str, feed_url: str, source_type: str, vertical: str) -> int:
    """Insert or update a source. Returns source id."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM sources WHERE feed_url = ?", (feed_url,)
        ).fetchone()
        if row:
            return row["id"]
        cursor = conn.execute(
            "INSERT INTO sources (name, feed_url, source_type, vertical) VALUES (?, ?, ?, ?)",
            (name, feed_url, source_type, vertical),
        )
        return cursor.lastrowid


def insert_raw_entry(source_id: int, url: str, title: str, excerpt: str,
                     published_date: str | None = None) -> int | None:
    """Insert a raw entry. Returns id or None if duplicate URL."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO raw_entries (source_id, url, title, excerpt, published_date) "
                "VALUES (?, ?, ?, ?, ?)",
                (source_id, url, title, excerpt, published_date),
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_unprocessed_entries(limit: int = 50) -> list[dict]:
    """Get raw entries that haven't been processed yet."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT re.*, s.name as source_name, s.vertical as source_vertical "
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


def insert_trend(entry_id: int, data: dict) -> int:
    """Insert a processed trend article."""
    with get_connection() as conn:
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
               limit: int = 50) -> list[dict]:
    """Get trends with optional filters."""
    query = "SELECT * FROM trends WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if vertical:
        query += " AND primary_vertical = ?"
        params.append(vertical)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def update_trend_status(trend_id: int, status: str):
    """Update trend status."""
    with get_connection() as conn:
        extra = ""
        params = [status]
        if status == "published":
            extra = ", published_at = ?"
            params.append(datetime.utcnow().isoformat())
        params.append(trend_id)
        conn.execute(f"UPDATE trends SET status = ?{extra} WHERE id = ?", params)


def get_recent_embeddings(days: int = 30) -> list[tuple[int, bytes]]:
    """Get embeddings from the last N days for dedup checking."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, embedding FROM trends "
            "WHERE embedding IS NOT NULL AND created_at > datetime('now', ?)",
            (f"-{days} days",),
        ).fetchall()
        return [(row["id"], row["embedding"]) for row in rows]


def update_source_last_fetched(source_id: int):
    """Update last_fetched timestamp for a source."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE sources SET last_fetched = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), source_id),
        )


def insert_source_discovery(data: dict) -> int:
    """Log a source discovery from radar."""
    with get_connection() as conn:
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
        return row["cnt"]
