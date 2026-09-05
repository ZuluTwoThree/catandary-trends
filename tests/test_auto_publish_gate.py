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

# Every publishable body must clear the garbage detector's 60-word floor (#11,
# 2026-09-05) — a six-word "article" is a stub, not a test fixture.
PAD = (" Analysts describe the change as gradual rather than abrupt, noting that "
       "procurement teams, lenders and regulators are each adjusting their own "
       "expectations at a different pace, so the overall picture remains mixed "
       "and any conclusion about the wider market should be read with care, "
       "since the underlying evidence is still being assembled and reviewed, "
       "and several of the firms involved have declined to comment so far.")


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
        # entry 3: source with NO date/number → a body citing "2027" is ungrounded
        c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt) "
                  "VALUES (3, 1, 'http://x/3', 'MoJ strategy', "
                  "'The Ministry published a circular economy strategy to cut waste.')")
        # entry 4: source states the figure the body uses → grounded, publishable
        c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt) "
                  "VALUES (4, 1, 'http://x/4', 'Jobs report', "
                  "'The programme created 7,980 jobs across 36 firms in 2024.')")
        # entry 5: the 2026-09-05 incident — token soup with confidence 0.95
        c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt) "
                  "VALUES (5, 1, 'http://x/5', 'Breathing study', "
                  "'Slow breathing techniques increase heart-rate variability.')")
    base = {"title_de": None, "summary_en": "s", "summary_de": None, "body_de": None,
            "verticals": ["TECH"], "primary_vertical": "TECH", "pestel": ["T"],
            "tags": ["x"], "trend_signal_type": "research", "mega_trend": None,
            "trend_level": "micro", "brands": [], "regions": ["Global"],
            "trend_score": 0.9, "confidence": 0.95, "source_url": "http://x",
            "source_name": "S", "embedding": None}
    # complete, high confidence -> should publish
    insert_trend(1, {**base, "title_en": "Complete", "slug": "complete-1",
                     "body_en": "A complete, publishable article body." + PAD})
    # truncated, high confidence -> should be HELD as draft (the #18 gate)
    insert_trend(2, {**base, "title_en": "Truncated", "slug": "truncated-2",
                     "body_en": "The industry's initial focus on creating" + PAD.rstrip(".")})
    # fabricated specific (invents "2027"), high confidence -> HELD (the #11 gate)
    insert_trend(3, {**base, "title_en": "Fabricated", "slug": "fabricated-3",
                     "body_en": "The Ministry's circular economy strategy sets a "
                                "compliance deadline of 2027 for all suppliers." + PAD})
    # grounded body (7,980 / 36 / 2024 all in source) -> publishable
    insert_trend(4, {**base, "title_en": "Grounded", "slug": "grounded-4",
                     "body_en": "The programme created 7,980 jobs across 36 firms "
                                "in its 2024 review, a concrete social outcome." + PAD})
    # garbage body (real incident text), high confidence -> HELD (garbled gate)
    insert_trend(5, {**base, "title_en": "Soup", "slug": "soup-5",
                     "body_en": ": writing writing市/address : writing M M M M M       仪器("})
    try:
        yield
    finally:
        pdb.DATABASE_PATH = old


def test_truncated_body_is_held_not_published(seeded_db):
    stats = auto_publish(min_confidence=0.85)
    assert stats["published"] == 2            # complete-1 + grounded-4
    assert stats["held_truncated"] == 1
    assert stats["held_fabricated"] == 1
    assert stats["held_garbled"] == 1
    with get_connection() as c:
        rows = {r["slug"]: r["status"] for r in
                c.execute("SELECT slug, status FROM trends").fetchall()}
    assert rows["complete-1"] == "published"
    assert rows["truncated-2"] == "draft"     # held for review, not auto-published
    assert rows["fabricated-3"] == "draft"    # #11 grounding gate holds it
    assert rows["grounded-4"] == "published"  # every specific is in the source
    assert rows["soup-5"] == "draft"          # #11 garbage gate: never live
