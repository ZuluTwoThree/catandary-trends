"""Tests for selective content generation (#12): the pre-gen score and the
Stage-6 routing decision that keeps low-value survivors as foresight signals
instead of paying for an article."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.llm_processor import pre_gen_score
from pipeline.models import ClassificationResult, RelevanceResult


def _entry(conf, verticals, pestel, sig_type, source_type="trade_media"):
    return {
        "_relevance": RelevanceResult(is_relevant=True, confidence=conf,
                                      primary_vertical=verticals[0], reason="x"),
        "_classification": ClassificationResult(verticals=verticals, pestel=pestel,
                                                tags=[], trend_signal_type=sig_type),
        "source_type": source_type,
    }


def test_pre_gen_score_in_unit_range_and_ordered():
    hi = pre_gen_score(_entry(0.95, ["TECH", "BIZ"], ["T", "E"], "funding"))
    lo = pre_gen_score(_entry(0.55, ["TECH"], [], "market_shift"))
    assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0
    assert hi > lo  # a stronger signal scores higher


def test_pre_gen_score_is_cached():
    e = _entry(0.9, ["TECH"], ["T"], "research")
    s1 = pre_gen_score(e)
    # mutate the inputs; cached value must be returned unchanged
    e["_relevance"].confidence = 0.1
    assert pre_gen_score(e) == s1
    assert e["_score"] == s1


def _routes_to_signal(entry, min_score):
    """Mirror the Stage-6 gate condition (no cached content)."""
    return min_score > 0 and pre_gen_score(entry) < min_score


def test_gate_routes_low_score_to_signal_only():
    low = _entry(0.55, ["TECH"], [], "market_shift")
    high = _entry(0.95, ["TECH", "BIZ"], ["T", "E"], "funding")
    # threshold between the two scores
    thr = (pre_gen_score(low) + pre_gen_score(high)) / 2
    assert _routes_to_signal(low, thr) is True
    assert _routes_to_signal(high, thr) is False


def test_gate_off_by_default_generates_all():
    low = _entry(0.30, ["TECH"], [], "market_shift")
    assert _routes_to_signal(low, 0.0) is False  # min_score=0 → never gated
