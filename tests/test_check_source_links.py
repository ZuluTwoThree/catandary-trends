"""dead_links persistence for source-link-rot monitoring (#48).

Covers the --mark logic in scripts/check_source_links.py: the 2-strike rule
(a single blip must not flag a healthy link), that 403/429 (bot-block) is
never marked dead, and that a link resolving alive again is removed from
dead_links ("resurrection")."""
import os
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_deadlinks_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db

from scripts.check_source_links import apply_marks, classify_dead_status
from scripts.migrate_dead_links import migrate as migrate_dead_links


def _row(url: str) -> dict:
    return {"id": 1, "source_name": "S", "source_url": url}


@pytest.fixture()
def seeded_db():
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    migrate_dead_links()
    try:
        yield
    finally:
        pdb.DATABASE_PATH = old


def _dead_link_rows() -> dict[str, dict]:
    with get_connection() as c:
        rows = c.execute(
            "SELECT url, status, check_count FROM dead_links").fetchall()
    return {r["url"]: dict(r) for r in rows}


class TestClassifyDeadStatus:
    def test_404_is_dead(self):
        assert classify_dead_status(404, "") == "404"

    def test_410_is_dead(self):
        assert classify_dead_status(410, "") == "410"

    def test_connection_error_is_dead(self):
        assert classify_dead_status(None, "ConnectError") == "conn_error"

    def test_403_is_never_dead(self):
        assert classify_dead_status(403, "") is None

    def test_429_is_never_dead(self):
        assert classify_dead_status(429, "") is None

    def test_200_is_alive(self):
        assert classify_dead_status(200, "") is None


class TestApplyMarksTwoStrikeRule:
    def test_single_failure_is_not_yet_confirmed(self, seeded_db):
        url = "https://example.com/a"
        with get_connection() as c:
            stats = apply_marks(c, [(_row(url), 404, "")])
        assert stats == {"first_strike": 1, "confirmed": 0, "resurrected": 0}
        rows = _dead_link_rows()
        assert rows[url]["check_count"] == 1
        assert rows[url]["status"] == "404"

    def test_second_consecutive_failure_confirms(self, seeded_db):
        url = "https://example.com/a"
        with get_connection() as c:
            apply_marks(c, [(_row(url), 404, "")])
        with get_connection() as c:
            stats = apply_marks(c, [(_row(url), 404, "")])
        assert stats == {"first_strike": 0, "confirmed": 1, "resurrected": 0}
        rows = _dead_link_rows()
        assert rows[url]["check_count"] == 2

    def test_status_updates_across_strikes(self, seeded_db):
        """First strike a connection error, second strike a hard 410 — the
        stored status reflects the latest check, not the first."""
        url = "https://example.com/a"
        with get_connection() as c:
            apply_marks(c, [(_row(url), None, "ConnectError")])
        with get_connection() as c:
            apply_marks(c, [(_row(url), 410, "")])
        rows = _dead_link_rows()
        assert rows[url]["status"] == "410"
        assert rows[url]["check_count"] == 2


class TestApplyMarksNeverMarksBotBlock:
    def test_403_never_creates_a_row(self, seeded_db):
        url = "https://example.com/blocked"
        with get_connection() as c:
            stats = apply_marks(c, [(_row(url), 403, "")])
        assert stats == {"first_strike": 0, "confirmed": 0, "resurrected": 0}
        assert url not in _dead_link_rows()

    def test_429_never_creates_a_row(self, seeded_db):
        url = "https://example.com/ratelimited"
        with get_connection() as c:
            stats = apply_marks(c, [(_row(url), 429, "")])
        assert stats == {"first_strike": 0, "confirmed": 0, "resurrected": 0}
        assert url not in _dead_link_rows()


class TestApplyMarksResurrection:
    def test_link_alive_again_is_removed(self, seeded_db):
        url = "https://example.com/a"
        with get_connection() as c:
            apply_marks(c, [(_row(url), 404, "")])
            apply_marks(c, [(_row(url), 404, "")])
        assert url in _dead_link_rows()
        with get_connection() as c:
            stats = apply_marks(c, [(_row(url), 200, "")])
        assert stats == {"first_strike": 0, "confirmed": 0, "resurrected": 1}
        assert url not in _dead_link_rows()

    def test_bot_block_after_dead_also_resurrects(self, seeded_db):
        """A 403 is presumed alive, so it clears a prior dead strike too —
        the site is just fending off the bot, not gone."""
        url = "https://example.com/a"
        with get_connection() as c:
            apply_marks(c, [(_row(url), 404, "")])
        with get_connection() as c:
            stats = apply_marks(c, [(_row(url), 403, "")])
        assert stats["resurrected"] == 1
        assert url not in _dead_link_rows()

    def test_alive_link_with_no_prior_row_is_a_noop(self, seeded_db):
        url = "https://example.com/always-fine"
        with get_connection() as c:
            stats = apply_marks(c, [(_row(url), 200, "")])
        assert stats == {"first_strike": 0, "confirmed": 0, "resurrected": 0}
        assert url not in _dead_link_rows()


class TestApplyMarksBatch:
    def test_mixed_batch_counts_each_bucket(self, seeded_db):
        alive = _row("https://example.com/alive")
        dead_first = _row("https://example.com/dead-first")
        bot = _row("https://example.com/bot")
        with get_connection() as c:
            stats = apply_marks(c, [
                (alive, 200, ""),
                (dead_first, 404, ""),
                (bot, 403, ""),
            ])
        assert stats == {"first_strike": 1, "confirmed": 0, "resurrected": 0}
        rows = _dead_link_rows()
        assert "https://example.com/dead-first" in rows
        assert "https://example.com/alive" not in rows
        assert "https://example.com/bot" not in rows
