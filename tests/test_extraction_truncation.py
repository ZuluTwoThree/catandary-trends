"""Truncated extractions (2026-08-20).

`ExtractionResult` had six uncapped lists. On a long article the model
enumerated every place and date and ran past max_tokens mid-JSON: 55 truncated
extractions in one run, 14 of which gave up after three attempts and fell back
to an EMPTY result — which then shrinks the grounding source and makes
correctly-cited figures look invented.

Two defences, tested here: the schema bounds the OUTPUT, and a truncated
attempt raises the budget instead of replaying an identical request.
"""
import pytest

from pipeline.models import ExtractionResult


class TestSchemaCaps:
    def test_every_list_is_bounded(self):
        """An unbounded list is what let the enumeration run away."""
        props = ExtractionResult.model_json_schema()["properties"]
        for field in ("key_claims", "key_figures", "quotes", "dates", "geography"):
            assert props[field].get("maxItems"), f"{field} must be capped"

    def test_caps_sit_far_above_real_usage(self):
        """Measured in production: median 0 items, p95 0-3. A cap of 10 must
        never clip real content — it only stops the runaway case."""
        props = ExtractionResult.model_json_schema()["properties"]
        assert props["key_figures"]["maxItems"] >= 8
        assert props["geography"]["maxItems"] >= 8

    def test_overlong_list_is_rejected(self):
        with pytest.raises(Exception):
            ExtractionResult(geography=[f"City{i}" for i in range(40)])

    def test_normal_extraction_still_validates(self):
        e = ExtractionResult(brand_name="Nestlé", key_figures=["£478M", "29,5 %"],
                             geography=["Italy", "UK"], dates=["2027"])
        assert e.key_figures == ["£478M", "29,5 %"]


class TestTruncationRetry:
    """The retry must CHANGE something. Replaying an identical temperature-0
    payload only worked because llama.cpp is not bit-deterministic."""

    def _run(self, monkeypatch, finish_reasons, captured):
        import pipeline.llamacpp_client as m

        class FakeResp:
            def __init__(self, fr):
                self._fr = fr
            def raise_for_status(self): pass
            def json(self):
                return {"choices": [{"finish_reason": self._fr,
                                     "message": {"content": '{"brand_name": "X"}'}}]}

        seq = list(finish_reasons)

        class FakeClient:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, url, json):
                captured.append(json["max_tokens"])
                return FakeResp(seq.pop(0))

        monkeypatch.setattr(m.httpx, "Client", lambda **kw: FakeClient())
        monkeypatch.setattr(m.time, "sleep", lambda s: None)
        return m

    def test_budget_grows_after_a_truncated_attempt(self, monkeypatch):
        captured = []
        m = self._run(monkeypatch, ["length", "stop"], captured)
        # first attempt truncates -> parse of the (valid) stub still succeeds,
        # so force a parse failure by demanding a field the stub lacks
        from pydantic import BaseModel
        class Strict(BaseModel):
            brand_name: str
            required_field: int
        m.chat_structured(model="m", prompt="p", schema=Strict)
        assert len(captured) >= 2, "should have retried"
        assert captured[1] > captured[0], (
            f"retry must raise the token budget, got {captured}")

    def test_budget_never_exceeds_the_ceiling(self, monkeypatch):
        captured = []
        m = self._run(monkeypatch, ["length"] * 3, captured)
        from pydantic import BaseModel
        class Strict(BaseModel):
            required_field: int
        m.chat_structured(model="m", prompt="p", schema=Strict)
        assert max(captured) <= m.TRUNCATION_MAX_TOKENS, (
            f"one pathological input must not trigger unbounded generation: {captured}")


class TestDeterministicFigures:
    """key_figures come from the source via regex, not from the model.

    Measured 2026-08-21: of 44 model-produced key_figures exactly ONE was both
    verbatim and a number — it writes summarising sentences, not tokens. The
    regex found 188 across the same articles, verbatim by construction.
    """

    def test_every_snippet_is_verbatim(self):
        from pipeline.grounding import figures_with_context
        src = ("Revenue rose to $16.7 billion in Q2, up 16.3%. "
               "The company hired 7,980 people. No numbers here at all.")
        for snip in figures_with_context(src):
            core = snip.strip("…").split("…")[0]
            assert core in " ".join(src.split()), f"not verbatim: {snip!r}"

    def test_sentences_without_figures_are_skipped(self):
        from pipeline.grounding import figures_with_context
        out = figures_with_context("Nothing quantitative is said here. Or here.")
        assert out == []

    def test_denser_sentences_come_first(self):
        """A writer should see the richest evidence first when the list is cut."""
        from pipeline.grounding import figures_with_context
        src = "One mention of 2026. Revenue hit $5 billion, up 12% across 30 markets."
        assert "5" in figures_with_context(src, limit=1)[0]

    def test_empty_input_is_safe(self):
        from pipeline.grounding import figures_with_context
        assert figures_with_context("") == []
        assert figures_with_context(None) == []


class TestVerbatimFilter:
    def test_keeps_only_what_the_source_contains(self):
        from pipeline.grounding import verbatim_only
        src = "Chancellor Olaf Scholz spoke in Berlin about the plan."
        assert verbatim_only(["Berlin", "Munich"], src) == ["Berlin"]

    def test_tolerates_whitespace_and_typography(self):
        """Must fail on real divergence, not on a line break or curly quote."""
        from pipeline.grounding import verbatim_only
        src = "He said:\n  “the plan   works”."
        assert verbatim_only(['"the plan works"'], src) == ['"the plan works"']

    def test_empty_inputs(self):
        from pipeline.grounding import verbatim_only
        assert verbatim_only([], "text") == []
        assert verbatim_only(["x"], "") == []
