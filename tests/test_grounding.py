"""Unit tests for the fabrication detector (pipeline.grounding, #11)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.grounding import ungrounded_specifics


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
