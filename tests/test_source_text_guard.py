"""Content generation must never run on a bare title (#97, 2026-09-09).

Background: the purge of 2026-09-04 emptied `excerpt`/`raw_content` for the 33
TDM-reserved sources but left their unprocessed rows in the pool. On 2026-09-08
the cycle wrote 187 published articles from those titles alone — fluent, freely
invented study content with **0 grounding flags**, because the grounding gate can
only check specifics AGAINST the source and there was no source to check against.

Two guards close that: a minimum source-text length before any LLM call, and the
batch path finally reading the fetched full text the way `process_entry` does.
"""
from __future__ import annotations

import pipeline.llm_processor as lp


class TestMinimumSourceText:
    def test_threshold_default(self):
        assert lp.MIN_SOURCE_TEXT_CHARS == 80

    def test_bare_title_is_filtered_before_any_llm_call(self, monkeypatch):
        """process_entry must bail out before the relevance filter."""
        called = []
        monkeypatch.setattr(lp, "step_relevance_filter",
                            lambda *a, **k: called.append("relevance"))
        marked: list[tuple[int, str]] = []
        monkeypatch.setattr(lp, "mark_filtered",
                            lambda eid, reason, *a, **k: marked.append((eid, reason)))
        out = lp.process_entry({"id": 7, "title": "A paper title", "excerpt": "",
                                "url": "https://example.org/x", "source_name": "J",
                                "source_vertical": "FOOD"})
        assert out is None
        assert called == [], "no LLM stage may run without source text"
        assert marked == [(7, "insufficient_source_text")]

    def test_whitespace_only_excerpt_counts_as_empty(self, monkeypatch):
        marked: list[tuple[int, str]] = []
        monkeypatch.setattr(lp, "mark_filtered",
                            lambda eid, reason, *a, **k: marked.append((eid, reason)))
        monkeypatch.setattr(lp, "step_relevance_filter",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("reached LLM")))
        assert lp.process_entry({"id": 8, "title": "T", "excerpt": "   \n  ",
                                 "url": "https://example.org/y", "source_name": "J",
                                 "source_vertical": "FOOD"}) is None
        assert marked == [(8, "insufficient_source_text")]

    def test_normal_teaser_passes_the_guard(self, monkeypatch):
        """A regular RSS teaser must not be caught — median is ~508 chars."""
        teaser = ("Researchers report a fermentation process that cuts energy use "
                  "in dairy processing by a fifth, according to the study published today.")
        assert len(teaser) >= lp.MIN_SOURCE_TEXT_CHARS
        reached = []
        monkeypatch.setattr(lp, "mark_filtered", lambda *a, **k: None)
        monkeypatch.setattr(lp, "step_relevance_filter",
                            lambda *a, **k: reached.append("relevance"))
        lp.process_entry({"id": 9, "title": "T", "excerpt": teaser,
                          "url": "https://example.org/z", "source_name": "J",
                          "source_vertical": "FOOD"})
        assert reached == ["relevance"]


class TestBatchPathReadsFullText:
    """run_pipeline_batch used only entry["excerpt"] — the full text that
    article_fetcher.fetch_batch writes to raw_content never reached the model."""

    def test_normalisation_prefers_the_longer_full_text(self):
        import inspect
        src = inspect.getsource(lp.run_pipeline_batch)
        assert 'entry.get("raw_content")' in src, \
            "batch path must read the fetched full text, not just the teaser"
        assert 'entry["excerpt"] = full' in src

    def test_guard_runs_in_the_batch_path_too(self):
        import inspect
        src = inspect.getsource(lp.run_pipeline_batch)
        assert "MIN_SOURCE_TEXT_CHARS" in src
        assert "insufficient_source_text" in src
