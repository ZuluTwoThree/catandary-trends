"""Set up FTS5 virtual table and lead_time_tier lookup for the Foresight Cockpit.

Creates:
  1. `trends_fts` — FTS5 virtual table over title_de, summary_de, title_en, summary_en, tags
  2. Triggers to keep FTS5 in sync on INSERT/UPDATE/DELETE
  3. `source_lead_time_tier` — lookup table mapping source_name → lead_time_tier

Idempotent: safe to re-run.

Usage:
    python scripts/setup_fts5.py
"""
import json
import sqlite3
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.config import DATABASE_PATH

DB_PATH = DATABASE_PATH
SOURCES_YAML = ROOT / "sources.yaml"


def setup_fts5(db: sqlite3.Connection) -> int:
    """Create FTS5 virtual table and sync triggers. Returns rows populated."""
    # Drop old triggers/table if they exist (idempotent)
    db.executescript("""
        DROP TRIGGER IF EXISTS trends_fts_insert;
        DROP TRIGGER IF EXISTS trends_fts_update;
        DROP TRIGGER IF EXISTS trends_fts_delete;
    """)
    try:
        db.execute("DROP TABLE IF EXISTS trends_fts")
    except sqlite3.OperationalError:
        pass

    db.execute("""
        CREATE VIRTUAL TABLE trends_fts USING fts5(
            title_de,
            summary_de,
            title_en,
            summary_en,
            tags,
            content='trends',
            content_rowid='id'
        )
    """)

    # Populate from existing published trends
    db.execute("""
        INSERT INTO trends_fts(rowid, title_de, summary_de, title_en, summary_en, tags)
        SELECT id,
               COALESCE(title_de, ''),
               COALESCE(summary_de, ''),
               COALESCE(title_en, ''),
               COALESCE(summary_en, ''),
               COALESCE(tags, '')
        FROM trends
        WHERE status = 'published'
    """)
    count = db.execute("SELECT COUNT(*) FROM trends_fts").fetchone()[0]

    # Sync triggers
    db.executescript("""
        CREATE TRIGGER trends_fts_insert AFTER INSERT ON trends
        WHEN NEW.status = 'published'
        BEGIN
            INSERT INTO trends_fts(rowid, title_de, summary_de, title_en, summary_en, tags)
            VALUES (NEW.id,
                    COALESCE(NEW.title_de, ''),
                    COALESCE(NEW.summary_de, ''),
                    COALESCE(NEW.title_en, ''),
                    COALESCE(NEW.summary_en, ''),
                    COALESCE(NEW.tags, ''));
        END;

        CREATE TRIGGER trends_fts_update AFTER UPDATE ON trends
        WHEN NEW.status = 'published'
        BEGIN
            INSERT INTO trends_fts(trends_fts, rowid, title_de, summary_de, title_en, summary_en, tags)
            VALUES ('delete', OLD.id,
                    COALESCE(OLD.title_de, ''),
                    COALESCE(OLD.summary_de, ''),
                    COALESCE(OLD.title_en, ''),
                    COALESCE(OLD.summary_en, ''),
                    COALESCE(OLD.tags, ''));
            INSERT INTO trends_fts(rowid, title_de, summary_de, title_en, summary_en, tags)
            VALUES (NEW.id,
                    COALESCE(NEW.title_de, ''),
                    COALESCE(NEW.summary_de, ''),
                    COALESCE(NEW.title_en, ''),
                    COALESCE(NEW.summary_en, ''),
                    COALESCE(NEW.tags, ''));
        END;

        CREATE TRIGGER trends_fts_delete AFTER DELETE ON trends
        BEGIN
            INSERT INTO trends_fts(trends_fts, rowid, title_de, summary_de, title_en, summary_en, tags)
            VALUES ('delete', OLD.id,
                    COALESCE(OLD.title_de, ''),
                    COALESCE(OLD.summary_de, ''),
                    COALESCE(OLD.title_en, ''),
                    COALESCE(OLD.summary_en, ''),
                    COALESCE(OLD.tags, ''));
        END;
    """)
    return count


def setup_lead_time_tier(db: sqlite3.Connection) -> int:
    """Create source_lead_time_tier lookup table from sources.yaml."""
    db.execute("DROP TABLE IF EXISTS source_lead_time_tier")
    db.execute("""
        CREATE TABLE source_lead_time_tier (
            source_name TEXT PRIMARY KEY,
            lead_time_tier TEXT CHECK (lead_time_tier IN ('future', 'market', 'now'))
        )
    """)

    data = yaml.safe_load(SOURCES_YAML.read_text(encoding="utf-8"))
    tier_map: dict[str, str] = {}

    def walk(node):
        if isinstance(node, list):
            for i in node:
                walk(i)
        elif isinstance(node, dict):
            if "name" in node and "lead_time_tier" in node:
                tier_map[node["name"]] = node["lead_time_tier"]
            for v in node.values():
                walk(v)

    walk(data)

    db.executemany(
        "INSERT OR REPLACE INTO source_lead_time_tier (source_name, lead_time_tier) VALUES (?, ?)",
        tier_map.items(),
    )
    return len(tier_map)


def main():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")

    fts_count = setup_fts5(db)
    print(f"FTS5: indexed {fts_count} published trends")

    tier_count = setup_lead_time_tier(db)
    print(f"Lead-time tiers: {tier_count} sources tagged")

    # Quick verification
    test = db.execute("SELECT COUNT(*) FROM trends_fts WHERE trends_fts MATCH 'protein'").fetchone()[0]
    print(f"FTS5 smoke test: 'protein' → {test} hits")

    tiers = db.execute("SELECT lead_time_tier, COUNT(*) FROM source_lead_time_tier GROUP BY lead_time_tier").fetchall()
    print(f"Tier distribution: {dict(tiers)}")

    db.commit()
    db.close()
    print("Done.")


if __name__ == "__main__":
    main()
