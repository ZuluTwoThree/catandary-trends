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


# --- Brevity floor only where the source can carry it (2026-09-24) ---
# Measured over 5.355 bodies (22.-24.09.2026): of the 250 that stayed under the
# 100-word floor after the retry budget, 242 came from sources below 1000 chars.
# Re-rolling those is a full 26B generation for the same short answer.

def test_brevity_floor_skipped_for_thin_sources():
    from pipeline.llm_processor import content_is_clean
    from pipeline.config import STAGE5_TARGET_BODY_WORDS

    short_body = "word " * (STAGE5_TARGET_BODY_WORDS - 20) + "end."
    # thin source → accept the short body instead of re-rolling
    assert content_is_clean(_content(short_body), source_chars=400) is True
    # enough source text → the floor still bites
    assert content_is_clean(_content(short_body), source_chars=5000) is False
    # caller that does not know the source keeps the old, unconditional floor
    assert content_is_clean(_content(short_body)) is False


def test_thin_source_does_not_disable_the_other_guards():
    from pipeline.llm_processor import content_is_clean
    from pipeline.config import STAGE5_MIN_BODY_WORDS, STAGE5_MAX_BODY_WORDS

    # a real generation failure is still a failure, however thin the source
    assert content_is_clean(_content("word " * (STAGE5_MIN_BODY_WORDS - 5) + "end."),
                            source_chars=100) is False
    # mid-sentence truncation
    assert content_is_clean(_content("word " * 60 + "and then"), source_chars=100) is False
    # runaway length
    assert content_is_clean(_content("word " * (STAGE5_MAX_BODY_WORDS + 10) + "end."),
                            source_chars=100) is False
    # cliché
    assert content_is_clean(_content("word " * 60 + "This trend signals a shift ahead."),
                            source_chars=100) is False


def test_make_content_guard_passes_source_length():
    """The guard built for a thin source must accept a short clean body."""
    from pipeline.llm_processor import make_content_guard
    from pipeline.config import STAGE5_TARGET_BODY_WORDS

    body = "alpha " * (STAGE5_TARGET_BODY_WORDS - 20) + "end."
    assert make_content_guard("tiny source text")(_content(body)) is True
    assert make_content_guard("x" * 5000)(_content(body)) is False
