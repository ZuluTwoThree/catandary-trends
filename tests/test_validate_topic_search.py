"""Stage-4 backtest of the topic search — the judging rules, no DB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import validate_topic_search as V  # noqa: E402


def test_term_rule_needs_a_keyword_in_a_hit_title():
    rows = [{"title_en": "Semaglutide cuts weight in trial"}, {"title_en": "Other"}]
    assert V.has_term(rows, ["glp-1", "semaglutide"])
    assert not V.has_term(rows, ["tirzepatide"])
    assert V.has_term(rows, [])  # no keywords → nothing to demand


def test_lead_is_positive_when_the_tier_spoke_first():
    assert V.lead_months("2020-01", "2020-05") == 4
    assert V.lead_months("2023-08", "2020-05") == -39
    assert V.lead_months(None, "2020-05") is None


def _tier(status="ok", hits=20, term_ok=True, first_hit="2019-01", sustained="2020-01"):
    return {"status": status, "hits": hits, "head": 0.8, "cut": 0.72, "term_ok": term_ok,
            "first_hit": first_hit, "first_month": sustained}


def test_judge_marks_found_only_when_answered_and_keyworded():
    tr = {"key": "x", "mainstream": "2021-01", "research_institutional": "2019-06", "terms": ["x"]}
    j = V.judge(tr, {"market": _tier(), "science": _tier(term_ok=False)})
    assert j["tiers"]["market"]["found"] is True
    assert j["tiers"]["market"]["lead_sustained"] == 12
    assert j["tiers"]["science"]["found"] is False
    assert j["tiers"]["science"]["reference"] == "2019-06"


def test_summary_counts_hit_rate_on_certain_trends_only_and_lists_answering_controls():
    a = V.judge({"key": "a", "mainstream": "2021-01"}, {"market": _tier()})
    b = V.judge({"key": "b", "mainstream": "2021-01"}, {"market": _tier(status="none", hits=0, term_ok=False, sustained=None, first_hit=None)})
    u = V.judge({"key": "u", "mainstream": "2021-01", "uncertain": True}, {"market": _tier()})
    controls = [{"key": "c1", "tiers": {"market": {"status": "none", "hits": 0, "head": 0.5}}},
                {"key": "c2", "tiers": {"market": {"status": "thin", "hits": 3, "head": 0.7}}}]
    s = V.summarise([a, b, u], controls)
    assert s["counted"] == 2
    assert s["tiers"]["market"]["found"] == 1 and s["tiers"]["market"]["hit_rate"] == 0.5
    assert s["tiers"]["market"]["median_lead_sustained"] == 12
    assert s["controls"]["answered"] == ["c2"]
