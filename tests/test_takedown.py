"""Takedown tool (scripts/takedown.py): a removal request must reject the
article, stamp reviewed_at, delete the stored full-text copy, and — in source
mode — take the source out of article generation. Dry run must write nothing."""
import json
import os
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_takedown_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db

from scripts import takedown as td

PUB_URL = "https://publisher.test/2026/09/story"


@pytest.fixture()
def seeded(monkeypatch, tmp_path):
    monkeypatch.setattr(pdb, "DATABASE_PATH", TEST_DB)
    monkeypatch.setattr(td, "LOG_PATH", tmp_path / "takedown_log.jsonl")
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    with get_connection() as c:
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) VALUES "
                  "(1, 'Publisher Test', 'https://www.publisher.test/feed/', 'trade_media', 'TECH')")
        c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt, raw_content, processed) "
                  "VALUES (1, 1, ?, 'Story', 'teaser', 'full text copy', 1)", (PUB_URL,))
        c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt, raw_content, processed) "
                  "VALUES (2, 1, 'https://publisher.test/other', 'Other', 'teaser', 'another copy', 1)")
        c.execute("INSERT INTO trends (id, raw_entry_id, title_en, slug, source_url, source_name, status) "
                  "VALUES (10, 1, 'Our article', 'our-article', ?, 'Publisher Test', 'published')", (PUB_URL,))
        c.execute("INSERT INTO trends (id, raw_entry_id, title_en, slug, source_url, source_name, status) "
                  "VALUES (11, 2, 'Other article', 'other-article', 'https://publisher.test/other', "
                  "'Publisher Test', 'draft')")
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def _trend(tid):
    with get_connection() as c:
        return dict(c.execute("SELECT status, reviewed_at FROM trends WHERE id = ?", (tid,)).fetchone())


def _raw(rid):
    with get_connection() as c:
        return c.execute("SELECT raw_content, excerpt FROM raw_entries WHERE id = ?", (rid,)).fetchone()


def _source():
    with get_connection() as c:
        return dict(c.execute("SELECT active, llm_pipeline FROM sources WHERE id = 1").fetchone())


class TestLookup:
    def test_by_publisher_url_with_variants(self, seeded):
        with get_connection() as c:
            assert [t["id"] for t in td.find_trends(c, url=PUB_URL + "/")] == [10]
            assert [t["id"] for t in td.find_trends(c, url=PUB_URL.replace("https", "http"))] == [10]

    def test_by_own_slug_url(self, seeded):
        with get_connection() as c:
            assert [t["id"] for t in td.find_trends(c, url="https://catandary.de/trends/our-article")] == [10]
            assert td.find_trends(c, url="https://catandary.de/trends/nope") == []

    def test_source_by_name_or_host(self, seeded):
        with get_connection() as c:
            assert td.find_source(c, "publisher test")["id"] == 1
            assert td.find_source(c, "publisher.test")["id"] == 1
            assert td.find_source(c, "https://www.publisher.test/some/page")["id"] == 1
            assert td.find_source(c, "unknown.example") is None


class TestArticleTakedown:
    def test_dry_run_changes_nothing(self, seeded, capsys):
        assert td.main(["--url", PUB_URL]) == 0
        assert "dry run" in capsys.readouterr().out
        assert _trend(10)["status"] == "published"
        assert _raw(1)["raw_content"] == "full text copy"
        assert not td.LOG_PATH.exists()

    def test_apply_rejects_stamps_and_purges(self, seeded):
        assert td.main(["--trend-id", "10", "--apply", "--note", "mail 2026-09-02"]) == 0
        t = _trend(10)
        assert t["status"] == "rejected" and t["reviewed_at"]
        assert _raw(1)["raw_content"] is None and _raw(1)["excerpt"] == "teaser"
        assert _trend(11)["status"] == "draft"                # untouched neighbour
        rec = json.loads(td.LOG_PATH.read_text().splitlines()[-1])
        assert rec["trend_ids"] == [10] and rec["note"] == "mail 2026-09-02" and rec["applied"]

    def test_keep_raw(self, seeded):
        assert td.main(["--url", "https://catandary.de/trends/our-article", "--apply", "--keep-raw"]) == 0
        assert _trend(10)["status"] == "rejected"
        assert _raw(1)["raw_content"] == "full text copy"

    def test_unknown_request_exits_nonzero(self, seeded):
        assert td.main(["--trend-id", "999"]) == 1


class TestSourceBlock:
    def test_dry_run_reports_footprint_only(self, seeded, capsys):
        assert td.main(["--source", "Publisher Test", "--purge-raw"]) == 0
        out = capsys.readouterr().out
        assert "stored full texts: 2" in out and "'published': 1" in out
        assert _source() == {"active": 1, "llm_pipeline": 1}
        assert _raw(1)["raw_content"] == "full text copy"

    def test_apply_blocks_source(self, seeded):
        assert td.main(["--source", "publisher.test", "--apply"]) == 0
        assert _source()["llm_pipeline"] == 0 and _source()["active"] == 1
        assert _raw(1)["raw_content"] == "full text copy"    # no --purge-raw
        assert _trend(10)["status"] == "published"            # no --reject-all

    def test_apply_full_block(self, seeded):
        assert td.main(["--source", "Publisher Test", "--apply", "--deactivate",
                        "--purge-raw", "--reject-all"]) == 0
        assert _source() == {"active": 0, "llm_pipeline": 0}
        assert _raw(1)["raw_content"] is None and _raw(2)["raw_content"] is None
        assert _trend(10)["status"] == "rejected" and _trend(11)["status"] == "rejected"
        rec = json.loads(td.LOG_PATH.read_text().splitlines()[-1])
        assert rec["mode"] == "source" and rec["raw_purged"] == 2 and rec["rejected"] == 2
