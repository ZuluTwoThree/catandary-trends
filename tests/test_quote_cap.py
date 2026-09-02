"""Quotation cap in the extraction schema (compliance review 2026-09-02).

Every stored quote reaches the content prompt (llm_processor.step_generate_content_en
forwards `extraction.quotes`), so the schema must bound how much verbatim source
text can travel that way: at most 3 quotes, at most 200 characters each — applied
by truncation, never by rejecting the extraction (a rejected extraction retries
and can end up empty, which shrinks the grounding source).
"""
from pipeline.grounding import verbatim_only
from pipeline.models import (QUOTE_MAX_CHARS, QUOTE_MAX_COUNT, ExtractionResult,
                             cap_quotes)

LONG = ("The regulator said the approval marks a turning point for precision "
        "fermentation in Europe and that further applications are under review "
        "with decisions expected before the end of the year according to the agency "
        "spokesperson who briefed reporters on Tuesday afternoon in Brussels.")


class TestCapQuotes:
    def test_count_is_capped_to_three(self):
        e = ExtractionResult(quotes=[f"quote {i}" for i in range(5)])
        assert e.quotes == ["quote 0", "quote 1", "quote 2"]
        assert ExtractionResult.model_json_schema()["properties"]["quotes"]["maxItems"] == QUOTE_MAX_COUNT == 3

    def test_length_is_capped_at_a_word_boundary(self):
        assert len(LONG) > QUOTE_MAX_CHARS
        e = ExtractionResult(quotes=[LONG])
        q = e.quotes[0]
        assert len(q) <= QUOTE_MAX_CHARS
        assert LONG.startswith(q)               # verbatim prefix, nothing rephrased
        assert not q.endswith(" ") and LONG[len(q)] == " "   # cut between words

    def test_capped_quote_still_passes_verbatim_filter(self):
        source = "Intro. " + LONG + " Outro."
        e = ExtractionResult(quotes=[LONG])
        assert verbatim_only(e.quotes, source) == e.quotes

    def test_short_quotes_are_untouched(self):
        e = ExtractionResult(quotes=["Short one.", "Another short."])
        assert e.quotes == ["Short one.", "Another short."]

    def test_empty_and_blank_entries_are_dropped(self):
        assert cap_quotes(None) == []
        assert cap_quotes([]) == []
        assert cap_quotes(["", "  ", "x", 42, "y"]) == ["x", "y"]

    def test_over_long_list_is_trimmed_not_rejected(self):
        # 5 long quotes — the pre-cap schema would have kept 5 × unbounded text.
        e = ExtractionResult(quotes=[LONG + f" {i}" for i in range(5)])
        assert len(e.quotes) == 3
        assert all(len(q) <= QUOTE_MAX_CHARS for q in e.quotes)

    def test_stored_json_from_before_the_cap_is_capped_on_load(self):
        raw = ExtractionResult.model_construct(quotes=[LONG] * 5).model_dump_json()
        e = ExtractionResult.model_validate_json(raw)
        assert len(e.quotes) == 3 and all(len(q) <= QUOTE_MAX_CHARS for q in e.quotes)
