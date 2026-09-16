"""Pure helpers of the emerging backtest (no DB, no embedder)."""

import importlib.util
import os
import sys

import numpy as np
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "validate_emerging", os.path.join(_ROOT, "scripts", "validate_emerging.py"))
V = importlib.util.module_from_spec(_spec)
sys.modules["validate_emerging"] = V
_spec.loader.exec_module(V)


def test_month_iter_walks_in_steps_and_stops_at_the_end():
    assert V.month_iter("2024-01", "2024-12", 3) == ["2024-01", "2024-04", "2024-07", "2024-10"]
    assert V.month_iter("2025-11", "2026-03", 2) == ["2025-11", "2026-01", "2026-03"]
    assert V.month_iter("2026-01", "2025-12", 3) == []


def test_months_between_is_signed():
    assert V.months_between("2024-01", "2024-07") == 6      # detected before mainstream
    assert V.months_between("2025-06", "2024-06") == -12    # detected after the fact
    assert V.months_between("2024-03", "2024-03") == 0


def test_the_known_trends_file_is_usable_as_written():
    trends, controls = V.load_known(os.path.join(_ROOT, "known_trends.yaml"))
    assert len(trends) >= 15, "too few trends to conclude anything"
    assert len(controls) >= 3, "controls are half the test"
    keys = [t["key"] for t in trends]
    assert len(keys) == len(set(keys))
    for t in trends:
        assert t["query"] and len(t["query"]) > 25
        assert len(t["mainstream"]) == 7 and t["mainstream"][4] == "-"
        assert t.get("basis"), f"{t['key']} has no stated basis for its date"
    for c in controls:
        assert c["query"] and c["key"]


def test_the_trend_dates_are_inside_the_period_the_corpus_can_speak_about():
    """The corpus carries 61k signals in 2019 and 96k in 2020; before that it
    thins out into the patent and OpenAlex back-file."""
    trends, _ = V.load_known(os.path.join(_ROOT, "known_trends.yaml"))
    for t in trends:
        assert "2019-01" <= t["mainstream"] <= "2026-09", t["key"]


def test_the_backtest_starts_early_enough_to_give_every_trend_a_chance():
    """A trend whose market date precedes the first test date can never show a
    positive lead — the window, not the detector, would be the finding. The
    default start therefore has to move when an early trend enters the set
    (precision fermentation moved to 2020-05 on 2026-09-16)."""
    trends, _ = V.load_known(os.path.join(_ROOT, "known_trends.yaml"))
    earliest = min(t["mainstream"] for t in trends)
    import argparse, contextlib, io
    ap_default = None
    parser_src = open(os.path.join(_ROOT, "scripts", "validate_emerging.py")).read()
    for line in parser_src.splitlines():
        if '"--from"' in line and "default=" in line:
            ap_default = line.split('default="')[1].split('"')[0]
    assert ap_default, "could not read the default --from"
    assert ap_default < earliest, (
        f"backtest starts {ap_default} but {earliest} is already in the set")


def test_embed_refuses_a_chat_model_answering_the_embedding_endpoint(monkeypatch):
    monkeypatch.setattr(V.llamacpp_client, "generate_embedding", lambda *a, **k: [0.1] * 8)
    with pytest.raises(RuntimeError, match="chat model"):
        V.embed("x", "http://127.0.0.1:8091")


def test_embed_refuses_an_empty_answer(monkeypatch):
    monkeypatch.setattr(V.llamacpp_client, "generate_embedding", lambda *a, **k: [])
    with pytest.raises(RuntimeError, match="embedder"):
        V.embed("x", "http://127.0.0.1:8091")


def test_embed_returns_a_unit_vector_of_the_index_width(monkeypatch):
    monkeypatch.setattr(V.llamacpp_client, "generate_embedding",
                        lambda *a, **k: [3.0] * 4096)
    v = V.embed("x", "http://127.0.0.1:8091")
    assert v.shape == (V.DIM,)
    assert np.isclose(np.linalg.norm(v), 1.0, atol=1e-5)


def test_match_threshold_sits_between_the_measured_populations():
    # measured 2026-09-15: true topics 0.82-0.86, nonsense controls 0.53-0.60
    assert 0.62 < V.MATCH_SIM < 0.80


def _nest(tags, titles=()):
    return {"top_tags": list(tags), "name_titles": list(titles)}


def test_a_pocket_must_say_one_of_the_trends_own_words():
    """One 134-document pocket called "Machine Learning · Neural Networks" was
    close enough to three different AI trends to hand each a 26-month lead
    (2026-09-15). Semantic closeness measures the field, not the trend."""
    field = _nest(["machine learning", "neural networks", "deep learning"])
    real = _nest(["retrieval augmented generation", "llm"],
                 ["Improving RAG pipelines with hybrid retrieval"])
    terms = ["retrieval augmented", "retrieval-augmented", " rag "]
    assert V.has_term(real, terms) is True
    assert V.has_term(field, terms) is False


def test_underscored_tags_still_match_a_spaced_term():
    assert V.has_term(_nest(["vision_language_action"]), ["vision language action"])


def test_a_trend_without_declared_terms_falls_back_to_semantics_only():
    assert V.has_term(_nest(["anything"]), []) is True


def test_every_known_trend_declares_its_terms():
    trends, _ = V.load_known(os.path.join(_ROOT, "known_trends.yaml"))
    for t in trends:
        assert t.get("terms"), f"{t['key']} has no terms — it would match its field"
        assert all(isinstance(x, str) and x.strip() for x in t["terms"])
