"""Stage 8 asks the LLM only about drafts it has not classified yet (2026-09-24).

Before this, reclassify_drafts() re-asked about EVERY row with status='draft'
on every pass, twice a night. At temperature 0 over an unchanged title+summary
that returns the verdict the draft already has: measured on four consecutive
nights the pass over the standing pool changed 0 of ~9.6k rows, while all 380
changes of the 2026-09-24 run fell inside that night's own id range.
"""

import os
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_reclassify_stamp_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pytest

import pipeline.db as pdb
import pipeline.reclassify as rc
from pipeline.db import get_connection, init_db


def _mk_db(n_old: int = 3, n_new: int = 2):
    """A pool of already-stamped drafts plus some freshly inserted ones."""
    pdb.DATABASE_PATH = TEST_DB
    rc.DATABASE_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    with get_connection() as c:
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) "
                  "VALUES (1, 'S', 'http://s', 'trade_media', 'TECH')")
        i = 0
        for k in range(n_old):
            i += 1
            c.execute("INSERT INTO raw_entries (id, source_id, url, title) "
                      f"VALUES ({i}, 1, 'http://e/{i}', 'T{i}')")
            c.execute("INSERT INTO trends (id, raw_entry_id, title_en, slug, summary_en, "
                      "source_url, status, primary_vertical, reclassified_at) "
                      f"VALUES ({i}, {i}, 'Old {k}', 'old-{k}', 's', 'http://s', "
                      "'draft', 'TECH', '2026-09-01T00:00:00')")
        for k in range(n_new):
            i += 1
            c.execute("INSERT INTO raw_entries (id, source_id, url, title) "
                      f"VALUES ({i}, 1, 'http://e/{i}', 'T{i}')")
            c.execute("INSERT INTO trends (id, raw_entry_id, title_en, slug, summary_en, "
                      "source_url, status, primary_vertical) "
                      f"VALUES ({i}, {i}, 'New {k}', 'new-{k}', 's', 'http://s', "
                      "'draft', 'TECH')")


def _stamps():
    with get_connection() as c:
        return {r["id"]: r["reclassified_at"] for r in c.execute(
            "SELECT id, reclassified_at FROM trends ORDER BY id").fetchall()}


def test_only_unstamped_drafts_are_classified(monkeypatch):
    _mk_db(n_old=3, n_new=2)
    seen = []

    def fake(title, summary):
        seen.append(title)
        return {"primary": "TECH", "verticals": ["TECH"]}

    monkeypatch.setattr(rc, "_classify_one", fake)
    stats = rc.reclassify_drafts()

    assert stats["total"] == 2 and stats["pool"] == 5
    assert sorted(seen) == ["New 0", "New 1"]
    stamps = _stamps()
    assert all(stamps[i] is not None for i in (1, 2, 3, 4, 5))
    assert stamps[1] == "2026-09-01T00:00:00"          # old stamp untouched


def test_second_pass_in_the_same_night_is_a_no_op(monkeypatch):
    _mk_db(n_old=3, n_new=2)
    calls = []
    monkeypatch.setattr(rc, "_classify_one",
                        lambda t, s: calls.append(t) or {"primary": "TECH", "verticals": ["TECH"]})
    rc.reclassify_drafts()
    n_first = len(calls)
    stats = rc.reclassify_drafts()
    assert n_first == 2
    assert len(calls) == 2          # the cycle's second pass asks about nothing
    assert stats["total"] == 0 and stats["pool"] == 5


def test_force_takes_the_whole_pool(monkeypatch):
    _mk_db(n_old=3, n_new=2)
    calls = []
    monkeypatch.setattr(rc, "_classify_one",
                        lambda t, s: calls.append(t) or {"primary": "TECH", "verticals": ["TECH"]})
    stats = rc.reclassify_drafts(force=True)
    assert stats["total"] == 5 and len(calls) == 5


def test_classification_error_leaves_the_draft_unstamped(monkeypatch):
    _mk_db(n_old=0, n_new=2)
    monkeypatch.setattr(rc, "_classify_one", lambda t, s: None)
    stats = rc.reclassify_drafts()
    assert stats["total"] == 2 and stats["errors"] == 2
    assert all(v is None for v in _stamps().values())   # comes back next pass


def test_published_rows_are_never_touched(monkeypatch):
    _mk_db(n_old=0, n_new=1)
    with get_connection() as c:
        c.execute("UPDATE trends SET status = 'published' WHERE id = 1")
    monkeypatch.setattr(rc, "_classify_one",
                        lambda t, s: pytest.fail("published rows must not be classified"))
    assert rc.reclassify_drafts()["total"] == 0


def test_migration_backfills_once_and_then_leaves_fresh_drafts_alone():
    """The backfill must not run again: it would stamp exactly the drafts a
    crashed run still owes work on, marking them done unclassified."""
    _mk_db(n_old=0, n_new=1)
    with get_connection() as c:
        c.execute("UPDATE trends SET reclassified_at = NULL WHERE id = 1")
    pdb._migrate_reclassified_at()          # column exists → must be a no-op
    assert _stamps()[1] is None
