"""Tests for the #41 hybrid RSS classification helpers (pure, no GPU/DB)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.llm_processor import relevance_band, _distill_signal_type
from pipeline.config import DISTILL_REL_LOW, DISTILL_REL_HIGH


def test_relevance_band_confident_keep():
    assert relevance_band(0.9, has_head=True) == "keep"
    assert relevance_band(DISTILL_REL_HIGH, has_head=True) == "keep"


def test_relevance_band_confident_drop():
    assert relevance_band(0.1, has_head=True) == "drop"
    assert relevance_band(DISTILL_REL_LOW - 0.01, has_head=True) == "drop"


def test_relevance_band_uncertain_to_llm():
    mid = (DISTILL_REL_LOW + DISTILL_REL_HIGH) / 2
    assert relevance_band(mid, has_head=True) == "llm"
    # boundary: exactly LOW is not a drop (>= low) → band
    assert relevance_band(DISTILL_REL_LOW, has_head=True) == "llm"


def test_relevance_band_no_head_always_llm():
    assert relevance_band(0.95, has_head=False) == "llm"
    assert relevance_band(None, has_head=True) == "llm"


def test_distill_signal_type_routing():
    assert _distill_signal_type({"pub_number": "US123"}) == "patent"
    assert _distill_signal_type({"source_type": "research"}) == "research"
    assert _distill_signal_type({"source_name": "arXiv preprint"}) == "research"
    assert _distill_signal_type({"source_type": "api", "source_name": "NSF Awards"}) == "funding"
    assert _distill_signal_type({"source_type": "trade_media", "source_name": "TechCrunch"}) == "market_shift"


def test_relevance_band_per_source_cap_drops_marginal():
    """Per-source cap (#13/value-report): a capped source needs a higher distill
    relevance to survive — its marginal band is dropped, not sent to the 8B,
    while its strong signals still pass unchanged."""
    from pipeline.llm_processor import relevance_band
    # default: 0.45 is the uncertain band -> 8B
    assert relevance_band(0.45, True) == "llm"
    # capped at 0.6: the same signal is now dropped outright
    assert relevance_band(0.45, True, low=0.6) == "drop"
    # a strong signal from the same source is unaffected
    assert relevance_band(0.82, True, low=0.6) == "keep"
    # just under the auto-keep bar still gets a proper 8B look
    assert relevance_band(0.65, True, low=0.6) == "llm"


def test_source_relevance_min_loads_caps():
    """sources.yaml relevance_min is read, strictest wins for duplicates."""
    from pipeline.config import source_relevance_min
    caps = source_relevance_min()
    assert caps, "expected capped sources in sources.yaml"
    assert all(0.0 < v <= 1.0 for v in caps.values())
    # an uncapped, high-value source must not appear
    assert "FoodNavigator" not in caps
