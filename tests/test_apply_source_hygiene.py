"""Tests for scripts/apply_source_hygiene.py (#81): the sync of sources.yaml
`active: false` (+ known DB-only orphans) into the DB's sources.active column.

Root cause under test: pipeline.feed_poller skips a source with `active:
false` in sources.yaml *before* ever calling upsert_source, and upsert_source
itself never UPDATEs an existing row's `active` flag — so a source marked
inactive in config can sit `active=true` in the DB forever. All logic here is
pure (yaml scanning + planning), so it's tested without a DB connection.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from apply_source_hygiene import (EXTRA_DEACTIVATE, plan_deactivations, plan_flag_syncs,
                                  yaml_flag_targets, yaml_inactive_feed_urls)


def _cfg(*, active_false_sources=(), active_false_cross=()):
    """Build a minimal sources.yaml-shaped dict for yaml_inactive_feed_urls()."""
    verticals = {"ECO": {"sources": list(active_false_sources), "science": []}}
    cross = {"press_wires": list(active_false_cross)}
    return {"verticals": verticals, "cross_industry": cross}


def test_yaml_inactive_feed_urls_finds_vertical_and_cross_industry_entries():
    cfg = _cfg(
        active_false_sources=[
            {"name": "Dead Vertical Feed", "feed_url": "https://dead.example/feed", "active": False},
            {"name": "Live Vertical Feed", "feed_url": "https://live.example/feed"},
        ],
        active_false_cross=[
            {"name": "Dead Cross Feed", "feed_url": "https://deadcross.example/feed", "active": False},
        ],
    )
    out = yaml_inactive_feed_urls(cfg)
    names = {name for _url, name in out}
    assert names == {"Dead Vertical Feed", "Dead Cross Feed"}


def test_yaml_inactive_feed_urls_ignores_active_true_and_missing_field():
    cfg = _cfg(active_false_sources=[
        {"name": "Explicitly Active", "feed_url": "https://a.example/feed", "active": True},
        {"name": "No Active Field", "feed_url": "https://b.example/feed"},
    ])
    assert yaml_inactive_feed_urls(cfg) == []


def test_yaml_inactive_feed_urls_requires_feed_url():
    """A malformed entry (active:false but no feed_url) must be skipped, not crash."""
    cfg = _cfg(active_false_sources=[{"name": "No URL", "active": False}])
    assert yaml_inactive_feed_urls(cfg) == []


def test_extra_deactivate_has_environmental_leader():
    urls = [u for u, _reason in EXTRA_DEACTIVATE]
    assert "https://www.environmentalleader.com/feed/" in urls


def test_plan_deactivations_splits_by_db_state():
    targets = [
        ("https://active.example/feed", "should deactivate"),
        ("https://already.example/feed", "already off"),
        ("https://missing.example/feed", "not in db"),
    ]
    db_rows = {
        "https://active.example/feed": {"id": 1, "name": "Active One", "active": True},
        "https://already.example/feed": {"id": 2, "name": "Already Off", "active": False},
    }
    plan = plan_deactivations(targets, db_rows)

    assert [row["name"] for _u, _r, row in plan["deactivate"]] == ["Active One"]
    assert [row["name"] for _u, _r, row in plan["already_inactive"]] == ["Already Off"]
    assert [u for u, _r, _row in plan["missing"]] == ["https://missing.example/feed"]


def test_plan_deactivations_is_idempotent_when_rerun():
    """Simulates running the script twice: the second run sees everything
    already inactive and plans no further changes."""
    targets = [("https://x.example/feed", "reason")]
    first_pass_db = {"https://x.example/feed": {"id": 9, "name": "X", "active": True}}
    plan1 = plan_deactivations(targets, first_pass_db)
    assert len(plan1["deactivate"]) == 1

    second_pass_db = {"https://x.example/feed": {"id": 9, "name": "X", "active": False}}
    plan2 = plan_deactivations(targets, second_pass_db)
    assert plan2["deactivate"] == []
    assert len(plan2["already_inactive"]) == 1


def test_real_sources_yaml_yields_expected_deactivations():
    """Sanity-check against the real sources.yaml touched by #81: the six dead
    feeds from issue #81 should all show up as active:false (Environmental
    Leader is a DB-only orphan, never in sources.yaml, so it is NOT expected
    here — it's covered separately via EXTRA_DEACTIVATE)."""
    from pipeline.config import load_sources

    out = yaml_inactive_feed_urls(load_sources())
    names = {name for _url, name in out}
    expected_from_81 = {"Euractiv", "Rock Health Blog", "WorkLife", "Shopify News",
                        "Förderinfo Bund – Mobilität"}
    assert expected_from_81.issubset(names)
    # pre-existing drift found during the audit (not part of #81's six, but the
    # same yaml/DB sync gap) should also still be there
    assert {"MobiHealthNews", "Healthcare IT News", "BMJ"}.issubset(names)


class TestFlagSync:
    """Second pass (#97, 2026-09-09): active + llm_pipeline of the sources that
    stay active. `upsert_source` only INSERTs, so a source that already has a
    DB row never picks up a later `llm_pipeline: false`, and a source
    reactivated in the YAML keeps `active=false` in the DB forever.
    """

    def test_targets_skip_inactive_and_carry_the_flag(self):
        cfg = _cfg(active_false_sources=[
            {"name": "Signal Only", "feed_url": "https://s.example/feed", "llm_pipeline": False},
            {"name": "Normal", "feed_url": "https://n.example/feed"},
            {"name": "Switched Off", "feed_url": "https://o.example/feed", "active": False},
        ])
        got = {name: want for _url, name, want in yaml_flag_targets(cfg)}
        assert got == {"Signal Only": False, "Normal": True}

    def test_plan_reports_reactivation_and_flag_change(self):
        targets = [("https://s.example/feed", "Signal Only", False)]
        rows = {"https://s.example/feed": {"id": 5, "name": "Signal Only",
                                           "active": False, "llm_pipeline": True}}
        plan = plan_flag_syncs(targets, rows)
        assert plan == [{"feed_url": "https://s.example/feed", "name": "Signal Only",
                         "id": 5, "reactivate": True, "llm": False}]

    def test_matching_row_produces_no_work(self):
        targets = [("https://n.example/feed", "Normal", True)]
        rows = {"https://n.example/feed": {"id": 1, "name": "Normal",
                                           "active": True, "llm_pipeline": True}}
        assert plan_flag_syncs(targets, rows) == []

    def test_null_llm_pipeline_counts_as_true(self):
        """Pre-migration rows carry NULL — must not be rewritten to True."""
        targets = [("https://n.example/feed", "Normal", True)]
        rows = {"https://n.example/feed": {"id": 1, "name": "Normal",
                                           "active": True, "llm_pipeline": None}}
        assert plan_flag_syncs(targets, rows) == []

    def test_row_missing_from_db_is_left_to_the_insert(self):
        targets = [("https://new.example/feed", "Never Polled", False)]
        assert plan_flag_syncs(targets, {}) == []

    def test_the_33_reserved_sources_are_signal_only_in_the_real_yaml(self):
        """Weg A: TDM-reserved sources run again, but never as article material."""
        import yaml as _yaml
        cfg = _yaml.safe_load(open(Path(__file__).parent.parent / "sources.yaml"))
        reserved = []

        def scan(entries):
            for s in entries or []:
                if s.get("tdm_status") == "reserved":
                    reserved.append(s)

        for group in (cfg.get("verticals") or {}).values():
            scan(group.get("sources"))
            scan(group.get("science"))
        for entries in (cfg.get("cross_industry") or {}).values():
            scan(entries)

        assert len(reserved) == 33
        for s in reserved:
            assert s.get("active", True) is True, f"{s['name']} should be polled again"
            assert s.get("llm_pipeline") is False, f"{s['name']} must never write articles"
            assert s.get("store_excerpt") is False, f"{s['name']} must not store the abstract"
            assert not s.get("fulltext"), f"{s['name']} must not fetch full text"
