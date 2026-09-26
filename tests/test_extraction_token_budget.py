"""Die Extraktion darf den Slot des 8B nicht mit dem Prompt allein füllen.

`EXTRACT_CHARS = 12_000` ist eine ZEICHEN-Kappe, der Slot fasst 8.960 TOKEN, und
`chat_structured` will darin noch bis 2.048 Ausgabe-Token unterbringen. Bei lateinischer
Schrift ist das nie knapp (gemessen: 3,43–6,39 Zeichen je Token). Bei CJK sind 12.000
Zeichen 8.302–8.442 Token: der Prompt füllt den Slot, die Ausgabe wird abgeschnitten,
die Budget-Verdopplung nützt nichts (der Slot ist voll), und nach drei Versuchen endet
der Eintrag als `extraction_error`. Sonde am 2026-09-25: 24 von 24 Antworten abgeschnitten.

Diese Tests pinnen die beiden Eigenschaften, auf die es ankommt: lateinischer Text wird
NICHT angetastet (sonst verliert die Extraktion Zahlen aus dem hinteren Teil), und
dichter Text landet unter dem Budget.
"""
from __future__ import annotations

import pytest

from pipeline.llm_processor import (EXTRACT_CHARS, EXTRACT_TOKEN_BUDGET,
                                    clip_to_token_budget, estimate_tokens)

LATIN = ("The company said the plant will produce 45,000 tonnes a year from 2027, "
         "an investment of 320 million euros. ")
CJK = "これは日本語の記事です。売上は前年比で二十パーセント増加しました。"
HANGUL = "이것은 한국어 기사입니다. 매출이 전년 대비 증가했습니다."


def test_latin_fulltext_is_never_clipped():
    """12.000 Zeichen Latein sind höchstens ~3.500 Token — die Kappe darf nicht greifen."""
    text = (LATIN * 200)[:EXTRACT_CHARS]
    assert len(text) == EXTRACT_CHARS
    assert clip_to_token_budget(text) == text


@pytest.mark.parametrize("sample", [CJK, HANGUL])
def test_dense_script_is_clipped_under_budget(sample: str):
    text = (sample * 500)[:EXTRACT_CHARS]
    out = clip_to_token_budget(text)
    assert len(out) < len(text), "dichter Text muss gekappt werden"
    assert estimate_tokens(out) <= EXTRACT_TOKEN_BUDGET


def test_clipped_prompt_leaves_room_for_the_output_budget():
    """Der Kern: Prompt + Ausgabebudget müssen in den 8.960-Token-Slot passen."""
    slot, output_budget, system_and_template = 8960, 2048, 200
    text = (CJK * 500)[:EXTRACT_CHARS]
    assert estimate_tokens(clip_to_token_budget(text)) + output_budget + system_and_template < slot


def test_estimator_is_conservative_for_dense_text():
    """Der Schätzer darf unterschätzen NIE — sonst sprengt er den Slot.
    Für CJK rechnet er ~1 Token je Zeichen; echt gemessen sind es 0,69 (8.302/12.000)."""
    text = CJK * 100
    assert estimate_tokens(text) >= len(text) * 0.69


def test_short_text_and_edge_cases_pass_through():
    assert clip_to_token_budget("") == ""
    assert clip_to_token_budget("kurz") == "kurz"
    assert estimate_tokens("") == 0
    # Budget 0 heisst "keine Kappe", nicht "alles weg"
    assert clip_to_token_budget(CJK * 100, budget=0) == CJK * 100


def test_clip_is_idempotent():
    text = (CJK * 500)[:EXTRACT_CHARS]
    once = clip_to_token_budget(text)
    assert clip_to_token_budget(once) == once


def test_extraction_prompt_uses_the_clip():
    """Regression: ohne den Aufruf im Prompt ist die Funktion wirkungslos."""
    import inspect

    from pipeline import llm_processor
    src = inspect.getsource(llm_processor.step_extraction)
    assert "clip_to_token_budget" in src
