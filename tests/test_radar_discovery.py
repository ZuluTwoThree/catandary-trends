"""Tests for the Brave Search Radar discovery pipeline (mocked network/LLM)."""

import os
import tempfile

import pytest

os.environ["DATABASE_PATH"] = os.path.join(tempfile.gettempdir(), "catandary_radar_disc_test.db")

from pipeline import db, radar_discovery
from pipeline.db import get_connection, init_db


@pytest.fixture(autouse=True)
def clean_db():
    init_db()
    with get_connection() as conn:
        for table in ("source_discoveries", "raw_entries", "sources"):
            conn.execute(f"DELETE FROM {table}")
    yield
    with get_connection() as conn:
        for table in ("source_discoveries", "raw_entries", "sources"):
            conn.execute(f"DELETE FROM {table}")


RESULTS = [
    {"title": "Novel protein launch", "url": "https://primarysource.com/a", "description": "x"},
    {"title": "Trend listicle", "url": "https://trendhunter.com/b", "description": "x"},
    {"title": "Irrelevant guide", "url": "https://other.com/c", "description": "x"},
]


def test_domain_of():
    assert radar_discovery.domain_of("https://www.example.com/path") == "example.com"
    assert radar_discovery.domain_of("https://sub.example.co.uk/x") == "sub.example.co.uk"


def test_ensure_radar_source_idempotent():
    sid1 = radar_discovery.ensure_radar_source("FOOD")
    sid2 = radar_discovery.ensure_radar_source("FOOD")
    assert sid1 == sid2
    with get_connection() as conn:
        row = conn.execute("SELECT source_type, vertical FROM sources WHERE id=?", (sid1,)).fetchone()
    assert row["source_type"] == "radar"
    assert row["vertical"] == "FOOD"


def test_process_query_filters_and_inserts(monkeypatch):
    monkeypatch.setattr(radar_discovery, "brave_search", lambda q, **kw: RESULTS)
    # LLM: relevant only for the primary-source hit
    monkeypatch.setattr(radar_discovery, "is_relevant",
                        lambda title, desc, vert: "protein" in title.lower())
    sid = radar_discovery.ensure_radar_source("FOOD")
    stats = radar_discovery.process_query("FOOD", "q", sid, "pw", dry_run=False)
    assert stats == {"results": 3, "skipped_domain": 1, "duplicates": 0,
                     "irrelevant": 1, "inserted": 1}
    with get_connection() as conn:
        rows = conn.execute("SELECT url FROM raw_entries").fetchall()
        discoveries = conn.execute("SELECT discovered_domain FROM source_discoveries").fetchall()
    assert [r["url"] for r in rows] == ["https://primarysource.com/a"]
    assert [d["discovered_domain"] for d in discoveries] == ["primarysource.com"]


def test_process_query_dedupes_second_run(monkeypatch):
    monkeypatch.setattr(radar_discovery, "brave_search", lambda q, **kw: RESULTS)
    monkeypatch.setattr(radar_discovery, "is_relevant", lambda *a: True)
    sid = radar_discovery.ensure_radar_source("FOOD")
    radar_discovery.process_query("FOOD", "q", sid, "pw", dry_run=False)
    stats = radar_discovery.process_query("FOOD", "q", sid, "pw", dry_run=False)
    assert stats["inserted"] == 0
    assert stats["duplicates"] == 2  # both non-blocked URLs already known


def test_dry_run_writes_nothing(monkeypatch, capsys):
    monkeypatch.setattr(radar_discovery, "brave_search", lambda q, **kw: RESULTS)
    monkeypatch.setattr(radar_discovery, "is_relevant",
                        lambda *a: (_ for _ in ()).throw(AssertionError("LLM called in dry-run")))
    stats = radar_discovery.process_query("FOOD", "q", None, "pw", dry_run=True)
    assert stats["inserted"] == 2  # candidates shown, not written
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) AS c FROM raw_entries").fetchone()["c"] == 0
    assert "[dry-run]" in capsys.readouterr().out


def test_domain_promotion_threshold(monkeypatch):
    monkeypatch.setattr(radar_discovery, "is_relevant", lambda *a: True)
    sid = radar_discovery.ensure_radar_source("TECH")
    for i in range(3):
        monkeypatch.setattr(radar_discovery, "brave_search",
                            lambda q, i=i, **kw: [{"title": f"t{i}", "url": f"https://newdomain.io/{i}", "description": "x"}])
        radar_discovery.process_query("TECH", f"q{i}", sid, "pw", dry_run=False)
    promotions = radar_discovery.report_domain_promotions()
    assert promotions == [("newdomain.io", 3)]


def test_brave_search_without_key_returns_empty(monkeypatch):
    monkeypatch.setattr(radar_discovery, "BRAVE_SEARCH_API_KEY", "")
    assert radar_discovery.brave_search("query") == []
