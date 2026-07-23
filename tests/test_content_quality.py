"""Tests for the content-quality prompt v2 (#11): signal-type framing and the
brevity/cliché content guard. Pure functions — no LLM, no DB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_signal_type_framing_known_types():
    from pipeline.llm_processor import SIGNAL_TYPE_FRAMING, signal_type_framing

    for t in ("product_launch", "research", "regulation", "funding",
              "market_shift", "consumer_behavior", "partnership", "patent"):
        f = signal_type_framing(t)
        assert f and f == SIGNAL_TYPE_FRAMING[t]
    # case/whitespace tolerant
    assert signal_type_framing(" Funding ") == SIGNAL_TYPE_FRAMING["funding"]


def test_signal_type_framing_unknown_is_none():
    from pipeline.llm_processor import signal_type_framing

    assert signal_type_framing(None) is None
    assert signal_type_framing("nonsense_type") is None


def test_v2_extends_v1_with_concreteness():
    from pipeline.llm_processor import CONTENT_EN_SYSTEM, CONTENT_EN_SYSTEM_V2

    assert CONTENT_EN_SYSTEM_V2.startswith(CONTENT_EN_SYSTEM)
    lower = CONTENT_EN_SYSTEM_V2.lower()
    assert "grounding" in lower
    # the no-fabrication clause is the load-bearing guard against invented specifics
    assert "never introduce" in lower
    assert "not present in the source" in lower


def _content(body: str, summary: str = "A clean summary of the trend."):
    from pipeline.models import GeneratedContent
    return GeneratedContent(title="T", summary=summary, body=body,
                            source_attribution="src")


def test_content_guard_rejects_stub_and_midsentence():
    from pipeline.llm_processor import content_is_clean

    assert content_is_clean(_content("too short")) is False       # under min words
    assert content_is_clean(_content("word " * 200 + "and then")) is False  # no terminator


def test_content_guard_rejects_cliche_opener():
    from pipeline.llm_processor import content_is_clean

    body = ("This shift signals a broader move toward automation. " + "word " * 140).strip() + "."
    assert content_is_clean(_content(body)) is False


def test_content_guard_accepts_clean_long_body():
    from pipeline.llm_processor import content_is_clean

    body = ("Maersk rerouted 12 vessels around the congested port of Rotterdam on "
            "Tuesday, cutting average dwell time by nine hours. " + "detail " * 140).strip() + "."
    assert content_is_clean(_content(body)) is True


def test_content_guard_rejects_runaway_body():
    # #11 symmetric max-word guard: a runaway body far over STAGE5_MAX_BODY_WORDS
    # is re-rolled (bounded by retries at the call site, then accepted).
    from pipeline import llm_processor
    from pipeline.llm_processor import content_is_clean

    long_ok = ("Detail one. " + "word " * (llm_processor.STAGE5_MAX_BODY_WORDS - 20)).strip() + "."
    assert content_is_clean(_content(long_ok)) is True
    runaway = ("Detail one. " + "word " * (llm_processor.STAGE5_MAX_BODY_WORDS + 50)).strip() + "."
    assert content_is_clean(_content(runaway)) is False


def test_fabrication_detector_flags_ungrounded_year():
    from scripts.ab_test_prompt import fabricated_specifics

    src = "X's new History tab combines bookmarks, likes and read articles into one place."
    body = "The feature rolled out in early May 2026 to all users."
    assert "2026" in fabricated_specifics(body, src)


def test_fabrication_detector_passes_grounded_numbers():
    from scripts.ab_test_prompt import fabricated_specifics

    src = "The program generated 7,980 jobs with 36 corporations in its 2024 review."
    body = "It created 7,980 jobs across 36 corporations, per the 2024 review."
    assert fabricated_specifics(body, src) == []
