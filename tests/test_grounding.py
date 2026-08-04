"""Unit tests for the fabrication detector (pipeline.grounding, #11)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.grounding import ungrounded_specifics, source_from_parts


def test_flags_invented_year_and_number():
    src = "The Ministry published a circular economy strategy to cut waste."
    body = "The strategy sets a 2027 deadline affecting 10,000 suppliers."
    flagged = set(ungrounded_specifics(body, src))
    assert "2027" in flagged and "10,000" in flagged


def test_grounded_numbers_pass():
    src = "The programme created 7,980 jobs across 36 firms in 2024."
    body = "It created 7,980 jobs across 36 firms, per the 2024 review."
    assert ungrounded_specifics(body, src) == []


def test_german_number_format_not_flagged():
    # German thousands '.' / decimal ',' must equal English formatting
    src = "Bastler baut GPU mit 8.192 Chips; DE-CIX misst 29,5 TBit/s."
    body = "A GPU with 8,192 chips; the exchange measured 29.5 Tbit/s."
    assert ungrounded_specifics(body, src) == []


def test_empty_and_missing():
    assert ungrounded_specifics("", "anything") == []
    assert ungrounded_specifics("no numbers here", "") == []


# --- source_from_parts (#11): the shared source assembly for both the content
# re-roll guard and the auto-publish gate. ---

def test_source_from_parts_joins_title_excerpt_and_lists():
    s = source_from_parts("Title 2027", "excerpt text",
                          ["a claim"], ["7,980 jobs"], ["by Q3 2025"])
    for token in ("Title 2027", "excerpt text", "a claim", "7,980 jobs", "by Q3 2025"):
        assert token in s


def test_source_from_parts_tolerates_none_and_empty():
    # None title/excerpt and empty/None lists must not raise or inject "None"
    s = source_from_parts(None, None, None, [], ["2030"])
    assert "None" not in s
    assert "2030" in s


def test_figure_in_fulltext_not_flagged_via_extraction():
    # The false-hold #11 fixes: the RSS excerpt omits a figure that the full text
    # (and the extracted key_figures) contains. Rebuilding the gate source from
    # the extracted specifics grounds the body's figure instead of flagging it.
    rss_excerpt = "The ministry announced a new circular economy strategy."
    key_figures = ["10,000 suppliers"]
    dates = ["2027"]
    body = "The 2027 strategy will affect 10,000 suppliers."
    narrow = source_from_parts("Circular strategy", rss_excerpt)          # excerpt only
    assert set(ungrounded_specifics(body, narrow)) == {"2027", "10,000"}  # falsely flagged
    wide = source_from_parts("Circular strategy", rss_excerpt, [], key_figures, dates)
    assert ungrounded_specifics(body, wide) == []                          # now grounded

def test_cjk_source_numbers_are_seen():
    """Regression 2026-08-04: a figure stated in a Japanese/Korean source was
    flagged as fabricated because \b finds no boundary between a digit and a
    CJK character, so the number stayed invisible to the check."""
    src = "140以上の通貨、180以上の国・地域をカバーし"
    body = "covering 140 currencies across 180 countries."
    assert ungrounded_specifics(body, src) == []


def test_korean_grouped_number_not_mangled():
    """'2,900만' used to be read as the garbage token '2,'."""
    src = "약 2,900만 명의 고객을 보유"
    body = "The bank serves 2,900 万 customers."
    assert "2,900" not in ungrounded_specifics(body, src)


def test_percent_still_matches_across_formats():
    src = "Registrations rose 50% to a 26% share."
    body = "BEV registrations rose by 50%, reaching 26% of the market."
    assert ungrounded_specifics(body, src) == []
