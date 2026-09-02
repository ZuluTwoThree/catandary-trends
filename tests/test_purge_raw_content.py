"""Retention script for fetched full text (scripts/purge_raw_content.py).

§44b Abs. 2 S. 2 UrhG: the TDM copy must go once it is no longer needed. The
script must NULL raw_content only for processed entries older than the window,
leave everything else (fresh, unprocessed, already empty) untouched, keep the
feed excerpt, and write nothing in dry-run mode.
"""
import os
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_purge_raw_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db

from scripts import purge_raw_content as prc


@pytest.fixture()
def seeded(monkeypatch):
    monkeypatch.setattr(pdb, "DATABASE_PATH", TEST_DB)
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    with get_connection() as c:
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) VALUES "
                  "(1, 'Fulltext Pub', 'https://a.test/feed', 'trade_media', 'TECH'),"
                  "(2, 'Teaser Pub', 'https://b.test/feed', 'trade_media', 'FOOD')")
        rows = [
            # id, source, processed, fetched_at, raw_content
            (1, 1, 1, "2026-01-01 04:00:00", "old processed fulltext " * 50),   # purge
            (2, 1, 0, "2026-01-01 04:00:00", "old but unprocessed " * 50),      # keep
            (3, 1, 1, "2026-09-01 04:00:00", "fresh processed " * 50),          # keep
            (4, 1, 1, "2026-01-01 04:00:00", None),                             # nothing to do
            (5, 2, 1, "2026-01-01 04:00:00", "old processed, teaser source " * 50),  # purge unless --fulltext-sources-only
        ]
        for rid, sid, proc, fetched, raw in rows:
            c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt, raw_content, "
                      "fetched_at, processed) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (rid, sid, f"https://x.test/{rid}", f"t{rid}", f"teaser {rid}", raw, fetched, proc))
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def _raw(rid: int):
    with get_connection() as c:
        return c.execute("SELECT raw_content, excerpt FROM raw_entries WHERE id = ?", (rid,)).fetchone()


CUTOFF = "2026-06-03 00:00:00"   # 90 days before 2026-09-01


class TestSelection:
    def test_counts_only_old_processed_with_text(self, seeded):
        with get_connection() as c:
            st = prc.count_candidates(c, CUTOFF, None)
        assert st["n"] == 2 and st["bytes"] > 0
        assert (st["min_id"], st["max_id"]) == (1, 5)

    def test_fulltext_sources_only_narrows_scope(self, seeded, monkeypatch):
        import pipeline.article_fetcher as af
        monkeypatch.setattr(af, "fulltext_source_names", lambda: {"Fulltext Pub"})
        with get_connection() as c:
            ids = prc.fulltext_source_ids(c)
            st = prc.count_candidates(c, CUTOFF, ids)
        assert ids == [1] and st["n"] == 1

    def test_by_source_breakdown(self, seeded):
        with get_connection() as c:
            top = prc.by_source(c, CUTOFF, None)
        assert {r["name"] for r in top} == {"Fulltext Pub", "Teaser Pub"}

    def test_cutoff_is_days_before_now(self):
        from datetime import datetime, timezone
        now = datetime(2026, 9, 1, tzinfo=timezone.utc)
        assert prc.cutoff_iso(90, now) == CUTOFF


class TestWrite:
    def test_dry_run_writes_nothing(self, seeded, capsys):
        assert prc.main(["--days", "90"]) == 0
        out = capsys.readouterr().out
        assert "dry run" in out and "candidates:" in out
        assert _raw(1)["raw_content"] is not None

    def test_apply_nulls_exactly_the_candidates(self, seeded):
        assert prc.main(["--days", "90", "--apply", "--batch", "2"]) == 0
        assert _raw(1)["raw_content"] is None and _raw(1)["excerpt"] == "teaser 1"
        assert _raw(5)["raw_content"] is None
        assert _raw(2)["raw_content"] is not None      # unprocessed
        assert _raw(3)["raw_content"] is not None      # fresh
        # idempotent
        assert prc.main(["--days", "90", "--apply"]) == 0

    def test_max_rows_stops_early(self, seeded):
        n = prc.purge(CUTOFF, None, 1, 5, batch_ids=1, max_rows=1)
        assert n == 1
        assert sum(1 for rid in (1, 5) if _raw(rid)["raw_content"] is None) == 1

    def test_fulltext_only_apply_keeps_teaser_source(self, seeded, monkeypatch):
        import pipeline.article_fetcher as af
        monkeypatch.setattr(af, "fulltext_source_names", lambda: {"Fulltext Pub"})
        assert prc.main(["--days", "90", "--apply", "--fulltext-sources-only"]) == 0
        assert _raw(1)["raw_content"] is None
        assert _raw(5)["raw_content"] is not None
