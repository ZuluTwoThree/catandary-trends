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
