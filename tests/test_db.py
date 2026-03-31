"""Tests for database layer."""

import os
import tempfile
import pytest

# Override DB path before importing db module
os.environ["DATABASE_PATH"] = os.path.join(tempfile.gettempdir(), "catandary_test.db")

from pipeline.db import (
    get_connection,
    get_discovery_count,
    get_trends,
    get_unprocessed_entries,
    init_db,
    insert_raw_entry,
    insert_source_discovery,
    insert_trend,
    mark_filtered,
    mark_processed,
    update_trend_status,
    upsert_source,
)


@pytest.fixture(autouse=True)
def clean_db():
    """Initialize a fresh test DB for each test."""
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM trends")
        conn.execute("DELETE FROM raw_entries")
        conn.execute("DELETE FROM sources")
        conn.execute("DELETE FROM source_discoveries")
    yield
    # Cleanup after tests
    with get_connection() as conn:
        conn.execute("DELETE FROM trends")
        conn.execute("DELETE FROM raw_entries")
        conn.execute("DELETE FROM sources")
        conn.execute("DELETE FROM source_discoveries")


class TestSources:
    def test_upsert_source_new(self):
        sid = upsert_source("Test Source", "https://example.com/feed", "trade_media", "FOOD")
        assert sid > 0

    def test_upsert_source_duplicate(self):
        sid1 = upsert_source("Test", "https://example.com/feed", "trade_media", "FOOD")
        sid2 = upsert_source("Test", "https://example.com/feed", "trade_media", "FOOD")
        assert sid1 == sid2

    def test_upsert_source_different_urls(self):
        sid1 = upsert_source("Test1", "https://example.com/feed1", "trade_media", "FOOD")
        sid2 = upsert_source("Test2", "https://example.com/feed2", "trade_media", "TECH")
        assert sid1 != sid2


class TestRawEntries:
    def test_insert_raw_entry(self):
        sid = upsert_source("Test", "https://example.com/feed", "trade_media", "FOOD")
        eid = insert_raw_entry(sid, "https://example.com/article1", "Title", "Excerpt")
        assert eid is not None
        assert eid > 0

    def test_insert_duplicate_url(self):
        sid = upsert_source("Test", "https://example.com/feed", "trade_media", "FOOD")
        eid1 = insert_raw_entry(sid, "https://example.com/article1", "Title", "Excerpt")
        eid2 = insert_raw_entry(sid, "https://example.com/article1", "Title2", "Excerpt2")
        assert eid1 is not None
        assert eid2 is None  # Duplicate URL

    def test_get_unprocessed(self):
        sid = upsert_source("Test", "https://example.com/feed", "trade_media", "FOOD")
        insert_raw_entry(sid, "https://example.com/1", "Title 1", "Excerpt 1")
        insert_raw_entry(sid, "https://example.com/2", "Title 2", "Excerpt 2")
        entries = get_unprocessed_entries(limit=10)
        assert len(entries) == 2

    def test_mark_filtered(self):
        sid = upsert_source("Test", "https://example.com/feed", "trade_media", "FOOD")
        eid = insert_raw_entry(sid, "https://example.com/1", "Title", "Excerpt")
        mark_filtered(eid, "not_relevant")
        entries = get_unprocessed_entries()
        assert len(entries) == 0

    def test_mark_processed(self):
        sid = upsert_source("Test", "https://example.com/feed", "trade_media", "FOOD")
        eid = insert_raw_entry(sid, "https://example.com/1", "Title", "Excerpt")
        mark_processed(eid)
        entries = get_unprocessed_entries()
        assert len(entries) == 0


class TestTrends:
    def test_insert_and_get(self):
        sid = upsert_source("Test", "https://example.com/feed", "trade_media", "FOOD")
        eid = insert_raw_entry(sid, "https://example.com/1", "Title", "Excerpt")
        trend_data = {
            "title_en": "Test Trend",
            "slug": "test-trend",
            "source_url": "https://example.com/1",
            "source_name": "Test",
            "verticals": ["FOOD"],
            "primary_vertical": "FOOD",
            "pestel": ["T"],
            "tags": ["test"],
        }
        tid = insert_trend(eid, trend_data)
        assert tid > 0

        trends = get_trends()
        assert len(trends) == 1
        assert trends[0]["title_en"] == "Test Trend"

    def test_filter_by_status(self):
        sid = upsert_source("Test", "https://example.com/feed", "trade_media", "FOOD")
        eid = insert_raw_entry(sid, "https://example.com/1", "Title", "Excerpt")
        trend_data = {
            "title_en": "Draft Trend",
            "slug": "draft-trend",
            "source_url": "https://example.com/1",
            "source_name": "Test",
        }
        tid = insert_trend(eid, trend_data)

        drafts = get_trends(status="draft")
        assert len(drafts) == 1

        published = get_trends(status="published")
        assert len(published) == 0

    def test_update_status(self):
        sid = upsert_source("Test", "https://example.com/feed", "trade_media", "FOOD")
        eid = insert_raw_entry(sid, "https://example.com/1", "Title", "Excerpt")
        tid = insert_trend(eid, {
            "title_en": "Test",
            "slug": "test",
            "source_url": "https://example.com/1",
        })
        update_trend_status(tid, "published")
        trends = get_trends(status="published")
        assert len(trends) == 1
        assert trends[0]["published_at"] is not None


class TestSourceDiscovery:
    def test_insert_and_count(self):
        insert_source_discovery({
            "radar_vertical": "FOOD",
            "original_title": "Test",
            "extracted_brand": "TestBrand",
            "discovered_url": "https://test.com/article",
            "discovered_domain": "test.com",
        })
        assert get_discovery_count("test.com") == 1

    def test_multiple_discoveries(self):
        for i in range(5):
            insert_source_discovery({
                "radar_vertical": "FOOD",
                "original_title": f"Test {i}",
                "extracted_brand": "TestBrand",
                "discovered_url": f"https://test.com/article{i}",
                "discovered_domain": "test.com",
            })
        assert get_discovery_count("test.com") == 5
        assert get_discovery_count("other.com") == 0
