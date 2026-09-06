"""The AI disclosure must be one sentence, not two versions of one (#99).

It exists twice by necessity: the mail is rendered in Python
(pipeline/newsletter_generator.py), the website edition and the release view in
TypeScript (frontend/src/lib/aiDisclosure.ts). This test fails the moment the
two drift apart — the alternative is a briefing whose website copy claims
something its mail does not, which is exactly the kind of gap the legal review
of issue #99 (EU AI Act Art. 50) is about.
"""
from __future__ import annotations

import re
from pathlib import Path

from pipeline.newsletter_generator import AI_DISCLOSURE_EN, generate_html

TS_FILE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "aiDisclosure.ts"

EDITION = {
    "id": 1, "year": 2026, "week": 36, "editorial": "A line.",
    "vertical_summaries": {"TECH": "Tech moved."},
    "mega_trend_radar": [], "trend_refs": {}, "total_signals": 7,
}


def _ts_disclosure() -> str:
    """The concatenated string literal of AI_DISCLOSURE_EN in the TS mirror."""
    src = TS_FILE.read_text(encoding="utf-8")
    # The literal itself contains a semicolon, so match the concatenation of
    # string literals rather than "everything up to the next ;".
    m = re.search(
        r'export const AI_DISCLOSURE_EN\s*=\s*((?:\s*"[^"]*"\s*\+?)+)\s*;', src)
    assert m, "AI_DISCLOSURE_EN not found in aiDisclosure.ts"
    return "".join(re.findall(r'"([^"]*)"', m.group(1)))


def test_python_and_typescript_say_the_same_thing():
    assert _ts_disclosure() == AI_DISCLOSURE_EN


def test_the_mail_carries_it():
    assert AI_DISCLOSURE_EN in generate_html(EDITION)


def test_it_states_the_human_release():
    # The sentence is the public form of the release gate — if the gate is
    # ever loosened, this wording would become false.
    assert "released by a person" in AI_DISCLOSURE_EN
    assert "checked automatically" in AI_DISCLOSURE_EN
