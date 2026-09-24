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


def test_distill_signal_type_head_is_off_by_default(monkeypatch):
    """#110: without the switch the press fallback stays market_shift even when
    the head is confident — the state the owner has to opt into."""
    from pipeline import llm_processor as lp
    monkeypatch.setattr(lp, "DISTILL_SIGNAL_TYPE", False)
    pred = {"signal_type": "product_launch", "signal_type_confidence": 0.97}
    assert _distill_signal_type({"source_type": "trade_media"}, pred) == "market_shift"


def test_distill_signal_type_head_decides_press_only(monkeypatch):
    """#110: switched on, the head decides press entries above the confidence
    floor; the source-type rule keeps patent/research/funding regardless of
    what the head says; low confidence falls back to market_shift."""
    from pipeline import llm_processor as lp
    monkeypatch.setattr(lp, "DISTILL_SIGNAL_TYPE", True)
    monkeypatch.setattr(lp, "DISTILL_SIGNAL_TYPE_MIN_CONF", 0.5)
    press = {"source_type": "trade_media", "source_name": "TechCrunch"}
    assert _distill_signal_type(press, {"signal_type": "partnership", "signal_type_confidence": 0.8}) == "partnership"
    assert _distill_signal_type(press, {"signal_type": "regulation", "signal_type_confidence": 0.49}) == "market_shift"
    assert _distill_signal_type(press, {"signal_type": None, "signal_type_confidence": None}) == "market_shift"
    assert _distill_signal_type(press, {"signal_type": "patent", "signal_type_confidence": 0.99}) == "market_shift"
    assert _distill_signal_type({"pub_number": "US1"}, {"signal_type": "product_launch", "signal_type_confidence": 0.99}) == "patent"
    assert _distill_signal_type({"source_type": "research"}, {"signal_type": "product_launch", "signal_type_confidence": 0.99}) == "research"
    assert _distill_signal_type({"source_type": "api", "source_name": "NIH RePORTER"},
                                {"signal_type": "product_launch", "signal_type_confidence": 0.99}) == "funding"


def test_distill_classifier_emits_signal_type_keys_without_head():
    """Consumers can always read the two keys; None means 'no head installed'."""
    import numpy as np
    from pipeline.distill import DistillClassifier

    class _Vert:
        classes_ = np.array(["FOOD", "TECH"])
        def decision_function(self, X): return np.tile([0.2, 0.9], (len(X), 1))
    class _Mega:
        classes_ = np.array(["a", "b", "c"])
        def decision_function(self, X): return np.tile([0.5, 0.1, -2.0], (len(X), 1))
    class _Pestel:
        def predict(self, X): return np.zeros((len(X), 6), dtype=int)
    class _Head:
        classes_ = np.array(["market_shift", "product_launch"])
        def predict_proba(self, X): return np.tile([0.3, 0.7], (len(X), 1))

    X = np.ones((2, 4096), dtype=np.float32)
    clf = DistillClassifier(_Vert(), _Mega(), _Pestel(), None, {})
    out = clf.classify_batch(X)[0]
    assert out["signal_type"] is None and out["signal_type_confidence"] is None
    assert clf.has_signal_type_head is False
    clf2 = DistillClassifier(_Vert(), _Mega(), _Pestel(), None, {}, signal_type=_Head())
    out2 = clf2.classify_batch(X)[0]
    assert out2["signal_type"] == "product_launch"
    assert abs(out2["signal_type_confidence"] - 0.7) < 1e-6
    assert clf2.has_signal_type_head is True
