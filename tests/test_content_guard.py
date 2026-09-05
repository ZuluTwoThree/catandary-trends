"""Garbage detector (pipeline.content_guard, #11 / 2026-09-05).

The fixture holds the REAL bodies of the incident: the 22 consecutive token-soup
drafts a backlog cycle stored on 2026-09-05, six published April–June articles
with leaked CJK tokens, three articles whose CJK character legitimately stands
in the source, and 20 clean published bodies from 20 different sources. The
detector must catch every garbage row and raise no alarm on the clean ones.
"""
import json
from pathlib import Path

import pytest

from pipeline.content_guard import garbage_reasons, is_garbled

FIX = json.loads((Path(__file__).parent / "fixtures"
                  / "content_guard_bodies_2026-09-05.json").read_text())


def _kinds(reasons: list[str]) -> set[str]:
    return {r.split(":")[0] for r in reasons}


@pytest.mark.parametrize("row", FIX["garbage"], ids=lambda r: str(r["id"]))
def test_real_garbage_is_caught_without_source(row):
    """Stage 6 sees the body first — body-intrinsic rules must suffice."""
    assert garbage_reasons(row["body"]), row["body"][:80]


def test_all_22_incident_bodies_caught():
    assert len(FIX["garbage"]) == 22
    assert all(is_garbled(r["body"]) for r in FIX["garbage"])


@pytest.mark.parametrize("row", FIX["clean"], ids=lambda r: str(r["id"]))
def test_clean_published_bodies_pass(row):
    """20 sources, 0 false alarms — with and without the source."""
    assert garbage_reasons(row["body"]) == []
    assert garbage_reasons(row["body"], row["source"]) == []


@pytest.mark.parametrize("row", FIX["cjk_leak"], ids=lambda r: str(r["id"]))
def test_cjk_leak_is_only_visible_against_the_source(row):
    """'more than a simple续约' — two leaked characters in 1,500 are far below
    the 0.5 % share rule; only the source comparison (g) sees them."""
    reasons = garbage_reasons(row["body"], row["source"])
    assert "script_leak" in _kinds(reasons), reasons


@pytest.mark.parametrize("row", FIX["legit_cjk"], ids=lambda r: str(r["id"]))
def test_cjk_that_stands_in_the_source_is_not_a_leak(row):
    """'Chopstick 箸' exhibition, ByteDance's '您' — the source uses the character,
    so the body may too. The owner's SQL sweep had these in the garbage set."""
    assert garbage_reasons(row["body"], row["source"]) == []


# --- rule-level unit tests ---------------------------------------------------

PROSE = ("The company reported a measurable shift in procurement behaviour, with "
         "buyers favouring suppliers that publish verified emissions data. Analysts "
         "attribute the change to new disclosure rules and to pressure from lenders, "
         "who increasingly price climate risk into credit terms. The report notes "
         "that smaller manufacturers struggle to produce the required documentation "
         "and may lose contracts as a result, while larger groups absorb the cost.")


def test_prose_passes_every_rule():
    assert garbage_reasons(PROSE) == []
    assert len(PROSE.split()) >= 60


def test_empty_body():
    assert garbage_reasons("") == ["empty"]
    assert garbage_reasons(None) == ["empty"]
    assert garbage_reasons("   \n ") == ["empty"]


def test_non_latin_share():
    body = PROSE + " 仪器 文章 函数"
    assert "non_latin_script" in _kinds(garbage_reasons(body))


def test_greek_letters_are_not_non_latin():
    """α-synuclein, β-cells, µm are normal science vocabulary."""
    body = PROSE.replace("procurement", "α-synuclein and β-cell µm-scale")
    assert "non_latin_script" not in _kinds(garbage_reasons(body))
    assert "script_leak" not in _kinds(garbage_reasons(body, "no greek here"))


def test_word_repetition_four_in_a_row():
    assert "word_repetition" in _kinds(garbage_reasons(PROSE + " fig fig fig fig"))
    # three is still English ("no, no, no")
    assert "word_repetition" not in _kinds(garbage_reasons(PROSE + " fig fig fig"))


def test_glued_repetition():
    assert "glued_repetition" in _kinds(garbage_reasons(PROSE + " URLURLURL"))
    assert "glued_repetition" in _kinds(garbage_reasons(PROSE + " ineineine"))
    # digits never count: money and years are legitimately repetitive
    assert "glued_repetition" not in _kinds(garbage_reasons(PROSE + " $1,000,000 in 2000."))


def test_low_lexical_diversity():
    body = " ".join(["original", "fig"] * 30) + "."
    kinds = _kinds(garbage_reasons(body))
    assert "low_diversity" in kinds


def test_too_short():
    reasons = garbage_reasons("Poor because of Moore.")
    assert any(r.startswith("too_short") for r in reasons)
    assert garbage_reasons(PROSE) == []


def test_non_word_chars():
    body = PROSE + " " + "{}[]\\|<>{}[]\\|<>" * 40
    assert "non_word_chars" in _kinds(garbage_reasons(body))


def test_whitespace_run():
    assert "whitespace_run" in _kinds(garbage_reasons(PROSE + "         end."))
    # paragraph breaks are newlines, not space runs
    assert "whitespace_run" not in _kinds(garbage_reasons(PROSE + "\n\n\n" + PROSE))


def test_script_leak_needs_source_and_ignores_source_scripts():
    body = PROSE + " " + PROSE + " Nintendo (任天堂) raised prices."
    assert garbage_reasons(body) == []                       # 0.3 % share, body-only
    assert "script_leak" in _kinds(garbage_reasons(body, "Nintendo raised prices."))
    assert garbage_reasons(body, "任天堂 raised prices in Japan.") == []
