"""pull_unprocessed-Scoping (#Owner 2026-08-28): der --patents-only-Pass darf
nur Patente MIT Abstract im Publikationsfenster ziehen; --no-patents bleibt
das exakte Komplement; published_after wirkt auch ohne Patent-Scope."""

import os
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_sigscope_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db

from scripts.signal_batch import pull_unprocessed


@pytest.fixture()
def seeded_db():
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    long_abs = "A" * 200
    with get_connection() as c:
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) "
                  "VALUES (1, 'EPO DOCDB (TECH)', 'http://epo', 'api', 'TECH')")
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) "
                  "VALUES (2, 'NSF Awards', 'http://nsf', 'api', 'CROSS')")
        # 1: Patent, Abstract, frisch — der Soll-Treffer des Patent-Passes
        c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt, "
                  "pub_number, published_date) VALUES (1, 1, 'http://p/1', 'Patent A', "
                  f"'{long_abs}', 'EP-1-A1', '2026-08-20')")
        # 2: Patent, Abstract, aber ALT — fällt aus dem Publikationsfenster
        c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt, "
                  "pub_number, published_date) VALUES (2, 1, 'http://p/2', 'Patent B', "
                  f"'{long_abs}', 'EP-2-A1', '2026-01-05')")
        # 3: Patent, frisch, aber OHNE Abstract — bleibt außerhalb des Scopes
        c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt, "
                  "pub_number, published_date) VALUES (3, 1, 'http://p/3', 'Patent C', "
                  "'', 'EP-3-A1', '2026-08-21')")
        # 4: Funding-Zeile (kein Patent) — gehört dem --no-patents-Pass
        c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt, "
                  "published_date) VALUES (4, 2, 'http://f/4', 'Award', "
                  f"'{long_abs}', '2026-08-22')")
        c.commit()
    yield
    pdb.DATABASE_PATH = old


def _ids(rows):
    return sorted(r["id"] for r in rows)


def test_patents_only_requires_abstract_and_window(seeded_db):
    rows = pull_unprocessed(0, [], [], source_type="api",
                            patents_only=True, published_after="2026-07-08")
    assert _ids(rows) == [1]  # alt (2) und abstract-los (3) bleiben draußen


def test_patents_only_without_window_takes_old_ones_too(seeded_db):
    rows = pull_unprocessed(0, [], [], source_type="api", patents_only=True)
    assert _ids(rows) == [1, 2]


def test_no_patents_is_the_exact_complement(seeded_db):
    rows = pull_unprocessed(0, [], [], source_type="api", no_patents=True)
    assert _ids(rows) == [4]


def test_published_after_applies_without_patent_scope(seeded_db):
    rows = pull_unprocessed(0, [], [], source_type="api",
                            published_after="2026-08-21")
    assert _ids(rows) == [3, 4]


def test_out_of_scope_rows_stay_unprocessed(seeded_db):
    pull_unprocessed(0, [], [], source_type="api",
                     patents_only=True, published_after="2026-07-08")
    with get_connection() as c:
        n = c.execute("SELECT count(*) AS n FROM raw_entries "
                      "WHERE processed = FALSE").fetchone()["n"]
    assert n == 4  # pull markiert nichts — Scope-Filter verlieren keine Zeilen
