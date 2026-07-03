"""Auto-publish truncation gate (#18): a mid-sentence body must never be
auto-published — it stays 'draft' for review even at high confidence."""

import os
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_autopub_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db, insert_trend
from pipeline.auto_publisher import _body_complete, auto_publish


def test_body_complete_unit():
    assert _body_complete("A finished sentence.")
    assert _body_complete('Ends with a quote."')
    assert _body_complete("Rhetorical question?")
    assert not _body_complete("The industry's initial focus on creating")
    assert not _body_complete("")
    assert not _body_complete(None)


@pytest.fixture()
def seeded_db():
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    with get_connection() as c:
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) "
                  "VALUES (1, 'S', 'http://s', 'trade_media', 'TECH')")
        c.execute("INSERT INTO raw_entries (id, source_id, url, title) "
                  "VALUES (1, 1, 'http://x/1', 't1')")
        c.execute("INSERT INTO raw_entries (id, source_id, url, title) "
                  "VALUES (2, 1, 'http://x/2', 't2')")
    base = {"title_de": None, "summary_en": "s", "summary_de": None, "body_de": None,
            "verticals": ["TECH"], "primary_vertical": "TECH", "pestel": ["T"],
            "tags": ["x"], "trend_signal_type": "research", "mega_trend": None,
            "trend_level": "micro", "brands": [], "regions": ["Global"],
            "trend_score": 0.9, "confidence": 0.95, "source_url": "http://x",
            "source_name": "S", "embedding": None}
    # complete, high confidence -> should publish
    insert_trend(1, {**base, "title_en": "Complete", "slug": "complete-1",
                     "body_en": "A complete, publishable article body."})
    # truncated, high confidence -> should be HELD as draft (the #18 gate)
    insert_trend(2, {**base, "title_en": "Truncated", "slug": "truncated-2",
                     "body_en": "The industry's initial focus on creating"})
    try:
        yield
    finally:
        pdb.DATABASE_PATH = old


def test_truncated_body_is_held_not_published(seeded_db):
    stats = auto_publish(min_confidence=0.85)
    assert stats["published"] == 1
    assert stats["held_truncated"] == 1
    with get_connection() as c:
        rows = {r["slug"]: r["status"] for r in
                c.execute("SELECT slug, status FROM trends").fetchall()}
    assert rows["complete-1"] == "published"
    assert rows["truncated-2"] == "draft"   # held for review, not auto-published
