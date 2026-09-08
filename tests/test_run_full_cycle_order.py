"""Full-text enrichment must run immediately before EVERY LLM run of the cycle.

Until 2026-09-08 `fetch_batch` sat between feed polling and Phase 3 only, so the
backlog of Phase 1 — including every entry the review desk sends back with
"Write again" — reached content generation with the RSS teaser instead of the
article (803 of the 813 re-queued rows had a purged raw_content).
"""
from __future__ import annotations

import sys

from pipeline import run_full_cycle as rfc


def _drive(monkeypatch, argv: list[str], counts: list[int]) -> list[tuple[str, object]]:
    calls: list[tuple[str, object]] = []
    it = iter(counts)
    monkeypatch.setattr(sys, "argv", ["run_full_cycle", *argv])
    monkeypatch.setattr(rfc, "check_ollama", lambda: True)
    monkeypatch.setattr(rfc, "check_gpu", lambda: True)
    monkeypatch.setattr(rfc, "check_gpu_nvidia_smi", lambda: True)
    monkeypatch.setattr(rfc, "get_unprocessed_count", lambda min_id=0: next(it))
    monkeypatch.setattr(rfc, "run_llm", lambda batch, min_id=0: (
        calls.append(("llm", batch)) or {"processed": batch, "created": 0, "filtered": 0, "errors": 0}))
    monkeypatch.setattr(rfc, "run_poll", lambda: calls.append(("poll", None)) or {"new": 3, "duplicate": 0})
    monkeypatch.setattr(rfc, "write_cycle_log", lambda result: None)
    import pipeline.article_fetcher as af
    monkeypatch.setattr(af, "fetch_batch", lambda limit=100: calls.append(("enrich", limit)) or 0)
    rfc.main()
    return calls


def test_backlog_is_enriched_before_its_llm_run(monkeypatch):
    calls = _drive(monkeypatch, [], counts=[5, 3])
    assert calls == [("enrich", 5), ("llm", 5), ("poll", None), ("enrich", 3), ("llm", 3)]


def test_skip_poll_drain_enriches_first(monkeypatch):
    calls = _drive(monkeypatch, ["--skip-poll", "--batch", "1500"], counts=[825, 0])
    assert calls == [("enrich", 825), ("llm", 825)]


def test_enrichment_scope_follows_the_batch_cap(monkeypatch):
    calls = _drive(monkeypatch, ["--skip-poll", "--batch", "10"], counts=[825, 0])
    assert calls == [("enrich", 10), ("llm", 10)]


def test_enrichment_failure_is_not_fatal(monkeypatch):
    import pipeline.article_fetcher as af

    def boom(limit=100):
        raise RuntimeError("network down")

    monkeypatch.setattr(af, "fetch_batch", boom)
    assert rfc.enrich_fulltext(5) == 0
