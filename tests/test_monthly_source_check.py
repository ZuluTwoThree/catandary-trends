"""Tests for the three new monthly_source_check.py guards (#81): OpenAlex
density watch, PATSTAT/TIP editions reminder, brand-PR balance.

The pure evaluator functions (_evaluate_*, check_patstat_reminder,
_month_bounds) need no DB and are tested directly. The two DB-facing wrapper
functions (check_openalex_density, check_brand_balance) are tested against a
seeded temp SQLite DB via the conftest SQLite guard — including the case where
the Postgres-only openalex_snap_state/research_corpus_meta tables don't exist
(SQLite never has them), which must degrade gracefully, not crash.
"""
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_monthly_source_check_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db, insert_raw_entry, upsert_source

import monthly_source_check as m


# --------------------------------------------------------------- pure logic

def test_month_bounds_mid_year():
    prior, last, this = m._month_bounds(datetime(2026, 8, 28, tzinfo=timezone.utc))
    assert (prior, last, this) == ("2026-06-01", "2026-07-01", "2026-08-01")


def test_month_bounds_year_rollover():
    prior, last, this = m._month_bounds(datetime(2026, 1, 15, tzinfo=timezone.utc))
    assert (prior, last, this) == ("2025-11-01", "2025-12-01", "2026-01-01")


def test_openalex_intake_zero_alerts():
    lines, alerts = m._evaluate_openalex_intake(1000, 0, "2026-07", "2026-08")
    assert len(alerts) == 1
    assert "0 raw_entries in 2026-08" in alerts[0]


def test_openalex_intake_drop_alerts():
    lines, alerts = m._evaluate_openalex_intake(1000, 400, "2026-07", "2026-08")
    assert len(alerts) == 1
    assert "40%" in alerts[0]


def test_openalex_intake_healthy_no_alert():
    lines, alerts = m._evaluate_openalex_intake(1000, 900, "2026-07", "2026-08")
    assert alerts == []


def test_openalex_intake_small_prior_is_noise_floor():
    """A near-zero prior month (a channel that just launched) must not trigger
    the drop alert — division against ~0 is meaningless, not a real collapse.
    This is the real production shape: OpenAlex topic shards launched
    2026-08-07, so June 2026 intake is 0 and July is the first full month."""
    lines, alerts = m._evaluate_openalex_intake(0, 179367, "2026-06", "2026-07")
    assert alerts == []
    lines, alerts = m._evaluate_openalex_intake(10, 3, "2026-06", "2026-07")
    assert alerts == []  # prior < OA_MIN_PRIOR (50) => not judged


def test_corpus_sync_fresh_no_alert():
    lines, alerts = m._evaluate_corpus_sync(5, 45_000_000)
    assert alerts == []
    assert "45,000,000" in lines[0]


def test_corpus_sync_overdue_alerts():
    lines, alerts = m._evaluate_corpus_sync(45, 45_000_000)
    assert len(alerts) == 1
    assert "overdue" in alerts[0]


def test_corpus_sync_never_synced_alerts():
    lines, alerts = m._evaluate_corpus_sync(None, None)
    assert len(alerts) == 1
    assert "no recorded snapshot-sync" in alerts[0]


@pytest.mark.parametrize("month,edition", [
    (4, "Spring"), (5, "Spring"), (10, "Autumn"), (11, "Autumn"),
])
def test_patstat_reminder_fires_in_window(month, edition):
    lines, alerts = m.check_patstat_reminder(datetime(2026, month, 10, tzinfo=timezone.utc))
    assert alerts == lines  # the reminder line doubles as the alert
    assert edition in alerts[0]
    assert "#76" in alerts[0]


@pytest.mark.parametrize("month", [1, 2, 3, 6, 7, 8, 9, 12])
def test_patstat_reminder_silent_outside_window(month):
    lines, alerts = m.check_patstat_reminder(datetime(2026, month, 10, tzinfo=timezone.utc))
    assert alerts == []
    assert lines  # still reports a status line


def test_brand_balance_below_threshold_no_alert():
    lines, alerts = m._evaluate_brand_balance(434, 690776)
    assert alerts == []
    assert "0.1%" in lines[0]


def test_brand_balance_over_threshold_alerts():
    lines, alerts = m._evaluate_brand_balance(150000, 690776)
    assert len(alerts) == 1
    assert "22%" in alerts[0]


def test_brand_balance_zero_total_no_crash():
    lines, alerts = m._evaluate_brand_balance(0, 0)
    assert alerts == []
    assert "0/0" in lines[0]


# ------------------------------------------------------------ DB-facing

@pytest.fixture()
def seeded_db():
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    try:
        yield
    finally:
        pdb.DATABASE_PATH = old
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)


def _seed_entry(source_id: int, url: str, fetched_at: str) -> None:
    entry_id = insert_raw_entry(source_id=source_id, url=url, title="t", excerpt="e")
    assert entry_id is not None
    with get_connection() as c:
        c.execute("UPDATE raw_entries SET fetched_at = ? WHERE id = ?", (fetched_at, entry_id))


def test_check_openalex_density_no_snap_state_table_degrades_gracefully(seeded_db):
    """SQLite never has openalex_snap_state/research_corpus_meta (Postgres-only,
    #80) — the check must report that instead of raising."""
    oa = upsert_source("OpenAlex Science (FOOD)", "https://openalex.example/food", "research", "FOOD")
    for i in range(5):
        _seed_entry(oa, f"https://openalex.example/food/{i}", "2026-07-15T00:00:00")

    lines, alerts = m.check_openalex_density(datetime(2026, 8, 28, tzinfo=timezone.utc))
    assert any("not available" in l for l in lines)
    assert any("2026-07=5" in l for l in lines)
    # prior (June) is 0, below the noise floor -> no false drop alert
    assert alerts == []


def test_check_openalex_density_zero_last_month_alerts(seeded_db):
    oa = upsert_source("OpenAlex fresh: Fermentation", "https://openalex.example/ferm", "research", "FOOD")
    for i in range(60):
        _seed_entry(oa, f"https://openalex.example/ferm/{i}", "2026-06-15T00:00:00")
    # nothing in July -> zero-intake alert

    lines, alerts = m.check_openalex_density(datetime(2026, 8, 28, tzinfo=timezone.utc))
    assert len(alerts) == 1
    assert "0 raw_entries in 2026-07" in alerts[0]


def test_check_brand_balance_matches_manual_count(seeded_db):
    brand = upsert_source("Stripe Blog", "https://stripe.example/feed", "brand", "BIZ")
    other = upsert_source("TechCrunch", "https://tc.example/feed", "trade_media", "TECH")
    since = "2026-07-29"
    for i in range(3):
        _seed_entry(brand, f"https://stripe.example/{i}", "2026-08-01T00:00:00")
    for i in range(17):
        _seed_entry(other, f"https://tc.example/{i}", "2026-08-01T00:00:00")
    # one old entry outside the 30d window must not count
    _seed_entry(other, "https://tc.example/old", "2026-01-01T00:00:00")

    lines, alerts = m.check_brand_balance(since)
    assert "3/20" in lines[0]
    assert alerts == []  # 15% exactly is not > 15%
