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


class TestPgHygieneFixes:
    """Regression guards for the P1 Postgres-schema/query fixes (#52/#53/#54).

    The Postgres-specific behaviour is validated against live Postgres; the test
    harness forces SQLite (conftest sets DATABASE_URL=""), so here we lock in the
    query shape + migration wiring that regressed before, and confirm the migrations
    no-op cleanly on SQLite."""

    def test_recent_dedup_use_safe_interval_binding(self):
        # #54: the fragile `INTERVAL '%s days'` (placeholder inside a string literal)
        # must not come back — the Postgres path uses make_interval(days => %s).
        import inspect
        from pipeline import db as _db
        src = inspect.getsource(_db.get_recent_titles) + inspect.getsource(_db.get_recent_embeddings)
        assert "INTERVAL '%s" not in src, "reverted to unsafe interval literal (#54)"
        assert "make_interval(days => %s)" in src

    def test_recent_getters_run_on_sqlite(self):
        # both getters must work on the SQLite path (no crash, list result)
        from pipeline.db import get_recent_titles, get_recent_embeddings
        assert isinstance(get_recent_titles(7), list)
        assert isinstance(get_recent_embeddings(7, limit=10), list)

    def test_schema_migrations_are_wired_and_noop_on_sqlite(self):
        # #52/#53: init_db must call the new idempotent migrations, and they must be
        # safe no-ops under SQLite (USE_POSTGRES guard).
        import inspect
        from pipeline import db as _db
        init_src = inspect.getsource(_db.init_db)
        assert "_migrate_embedding_1024()" in init_src
        assert "_migrate_source_lead_time_tier()" in init_src
        _db._migrate_embedding_1024()          # no-op on SQLite, must not raise
        _db._migrate_source_lead_time_tier()


class TestLlmPipelineFlag:
    """Signal-only sources must never reach the content cycle (2026-08-20).

    A 235k SBIR/CORDIS funding ingest landed in the unprocessed pool and
    aborted the nightly run on the 50k sanity cap. Funding entries are signal
    data, not article material — the source-level flag is the analogue of the
    entry-level pub_number exclusion for patents.
    """

    def _mk_source(self, name, flag):
        from pipeline.db import upsert_source
        return upsert_source(name, f"https://example.com/{name}", "api", "BIZ",
                             llm_pipeline=flag)

    def _mk_entry(self, conn, sid, url):
        conn.execute(
            "INSERT INTO raw_entries (source_id, url, title, excerpt) "
            "VALUES (?, ?, ?, ?)", (sid, url, "T", "E"))

    def test_flagged_source_entries_never_reach_the_cycle(self):
        from pipeline.db import get_connection, get_unprocessed_entries, init_db
        init_db()
        funding = self._mk_source("sbir-test", False)
        rss = self._mk_source("hn-test", True)
        with get_connection() as conn:
            self._mk_entry(conn, funding, "https://example.com/award/1")
            self._mk_entry(conn, rss, "https://example.com/story/1")
        got = {e["source_name"] for e in get_unprocessed_entries(limit=100)}
        assert "hn-test" in got, "normal api sources (Hacker News) must keep flowing"
        assert "sbir-test" not in got, "funding entries must be invisible to the cycle"

    def test_null_flag_counts_as_true(self):
        """Rows from a pre-migration DB have NULL — they must keep flowing,
        otherwise the migration would silently stop the whole pipeline."""
        from pipeline.db import get_connection, get_unprocessed_entries, init_db
        init_db()
        sid = self._mk_source("legacy-test", True)
        with get_connection() as conn:
            conn.execute("UPDATE sources SET llm_pipeline = NULL WHERE id = ?", (sid,))
            self._mk_entry(conn, sid, "https://example.com/legacy/1")
        got = {e["source_name"] for e in get_unprocessed_entries(limit=100)}
        assert "legacy-test" in got

    def test_migration_is_idempotent(self):
        from pipeline import db as m
        m.init_db()
        m._migrate_sources_llm_pipeline()
        m._migrate_sources_llm_pipeline()   # second run must not raise

class TestPerSourceCap:
    """One source must not flood a cycle run (owner rule 2026-08-20).

    Funding news MAY become articles through the regular cycle — the 235k
    SBIR/CORDIS ingest aborting the whole night is what must never recur.
    The cap bounds each source's contribution per run; the remainder stays
    unprocessed for signal_batch.
    """

    def _seed(self, n_big, n_small):
        from pipeline.db import get_connection, upsert_source, init_db
        init_db()
        big = upsert_source("dump-src", "https://example.com/dump", "api", "BIZ")
        small = upsert_source("rss-src", "https://example.com/rss", "trade_media", "TECH")
        with get_connection() as conn:
            for i in range(n_big):
                conn.execute("INSERT INTO raw_entries (source_id,url,title) VALUES (?,?,?)",
                             (big, f"https://example.com/d/{i}", f"D{i}"))
            for i in range(n_small):
                conn.execute("INSERT INTO raw_entries (source_id,url,title) VALUES (?,?,?)",
                             (small, f"https://example.com/r/{i}", f"R{i}"))
        return big, small

    def test_dump_is_capped_normal_source_flows_fully(self):
        from pipeline.db import get_unprocessed_entries
        self._seed(n_big=30, n_small=5)
        got = get_unprocessed_entries(limit=1000, per_source_cap=10)
        by = {}
        for e in got:
            by[e["source_name"]] = by.get(e["source_name"], 0) + 1
        assert by.get("dump-src") == 10, "the dump contributes exactly the cap"
        assert by.get("rss-src") == 5, "a normal source keeps flowing in full"

    def test_oldest_entries_win_within_a_source(self):
        """FIFO within the source — the cap must not starve old entries by
        letting newer ones jump the queue across runs."""
        from pipeline.db import get_unprocessed_entries
        self._seed(n_big=8, n_small=0)
        got = [e["title"] for e in get_unprocessed_entries(limit=100, per_source_cap=3)
               if e["title"].startswith("D")]
        assert got == ["D0", "D1", "D2"]

    def test_default_cap_comes_from_config(self):
        from pipeline.config import CYCLE_MAX_PER_SOURCE
        from pipeline.db import get_unprocessed_entries
        self._seed(n_big=CYCLE_MAX_PER_SOURCE + 25, n_small=0)
        got = get_unprocessed_entries(limit=100000)
        assert len(got) == CYCLE_MAX_PER_SOURCE



class TestInactiveSourceBacklog:
    """Deactivating a source must stop its backlog too (#97, 2026-09-09).

    Until 2026-09-09 `active = FALSE` only stopped the poller. The 33 TDM-reserved
    journals switched off on 2026-09-04 kept feeding their already-fetched backlog
    into content generation and produced 187 published articles on 2026-09-08.
    """

    def _mk(self, name, active):
        from pipeline.db import get_connection, upsert_source
        sid = upsert_source(name, f"https://example.com/{name}", "trade_media", "FOOD")
        with get_connection() as conn:
            conn.execute("UPDATE sources SET active = ? WHERE id = ?", (active, sid))
            conn.execute(
                "INSERT INTO raw_entries (source_id, url, title, excerpt) VALUES (?, ?, ?, ?)",
                (sid, f"https://example.com/{name}/1", "T", "E"))
        return sid

    def test_inactive_source_entries_never_reach_the_cycle(self):
        from pipeline.db import get_unprocessed_entries, init_db
        init_db()
        self._mk("reserved-journal-test", False)
        self._mk("live-trade-test", True)
        got = {e["source_name"] for e in get_unprocessed_entries(limit=100)}
        assert "live-trade-test" in got
        assert "reserved-journal-test" not in got

    def test_null_active_counts_as_true(self):
        """Pre-migration rows carry NULL — they must keep flowing."""
        from pipeline.db import get_connection, get_unprocessed_entries, init_db
        init_db()
        sid = self._mk("legacy-active-test", True)
        with get_connection() as conn:
            conn.execute("UPDATE sources SET active = NULL WHERE id = ?", (sid,))
        got = {e["source_name"] for e in get_unprocessed_entries(limit=100)}
        assert "legacy-active-test" in got
