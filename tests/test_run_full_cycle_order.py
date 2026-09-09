"""run_full_cycle phase logic.

- Full-text enrichment runs immediately before EVERY LLM run (2026-09-08): until
  then `fetch_batch` sat between polling and Phase 3 only, so the Phase-1 backlog
  (every "Write again" entry) reached content generation with the RSS teaser.
- Entries Stage 6 left garbled in this cycle are not retried in Phase 3, and a
  drain run whose backlog is only such entries is not started (2026-09-09: one
  entry, four reclassify passes, 1.5 h).
"""
from __future__ import annotations

import json
import sys

from pipeline import run_full_cycle as rfc


def _drive(monkeypatch, argv: list[str], backlog: int, new_ids: list[int],
           garbled: dict[str, list[int]] | None = None):
    """Run main() with everything external stubbed. `garbled` maps the phase
    ('backlog' | 'new') to the ids run_llm reports as left garbled."""
    calls: list[tuple[str, object]] = []
    results: list[dict] = []
    garbled = garbled or {}
    phase = iter(["backlog", "new"])
    monkeypatch.setattr(sys, "argv", ["run_full_cycle", *argv])
    monkeypatch.setattr(rfc, "check_ollama", lambda: True)
    monkeypatch.setattr(rfc, "check_gpu", lambda: True)
    monkeypatch.setattr(rfc, "check_gpu_nvidia_smi", lambda: True)
    monkeypatch.setattr(rfc, "get_unprocessed_count", lambda min_id=0: backlog)
    monkeypatch.setattr(rfc, "get_unprocessed_ids", lambda min_id=0: list(new_ids))

    def run_llm(batch, min_id=0):
        calls.append(("llm", batch))
        return {"processed": batch, "created": 0, "filtered": 0, "errors": 0,
                "garbled_ids": garbled.get(next(phase), [])}

    monkeypatch.setattr(rfc, "run_llm", run_llm)
    monkeypatch.setattr(rfc, "run_poll", lambda: calls.append(("poll", None)) or {"new": 3, "duplicate": 0})
    monkeypatch.setattr(rfc, "write_cycle_log", lambda result: results.append(result))
    import pipeline.article_fetcher as af
    monkeypatch.setattr(af, "fetch_batch", lambda limit=100: calls.append(("enrich", limit)) or 0)
    rfc.main()
    return calls, results[-1]


def test_backlog_is_enriched_before_its_llm_run(monkeypatch):
    calls, _ = _drive(monkeypatch, [], backlog=5, new_ids=[1, 2, 3])
    assert calls == [("enrich", 5), ("llm", 5), ("poll", None), ("enrich", 3), ("llm", 3)]


def test_skip_poll_drain_enriches_first(monkeypatch):
    calls, _ = _drive(monkeypatch, ["--skip-poll", "--batch", "1500"], backlog=825, new_ids=[])
    assert calls == [("enrich", 825), ("llm", 825)]


def test_enrichment_scope_follows_the_batch_cap(monkeypatch):
    calls, _ = _drive(monkeypatch, ["--skip-poll", "--batch", "10"], backlog=825, new_ids=[])
    assert calls == [("enrich", 10), ("llm", 10)]


def test_phase3_not_run_when_only_garbled_entries_remain(monkeypatch):
    # Phase 1 left entry 42 garbled; after polling it is the only thing waiting.
    calls, result = _drive(monkeypatch, [], backlog=1, new_ids=[42], garbled={"backlog": [42]})
    assert calls == [("enrich", 1), ("llm", 1), ("poll", None)]
    assert result["garbled_ids"] == [42]


def test_phase3_runs_for_real_entries_with_batch_sized_to_the_pool(monkeypatch):
    # 42 is garbled, 7 is new: Phase 3 runs, and its batch covers both so the
    # garbled row cannot crowd the real one out at the LIMIT.
    calls, result = _drive(monkeypatch, [], backlog=1, new_ids=[42, 7],
                           garbled={"backlog": [42], "new": [42]})
    assert calls[-2:] == [("enrich", 2), ("llm", 2)]
    assert result["garbled_ids"] == [42]


def test_enrichment_failure_is_not_fatal(monkeypatch):
    import pipeline.article_fetcher as af

    def boom(limit=100):
        raise RuntimeError("network down")

    monkeypatch.setattr(af, "fetch_batch", boom)
    assert rfc.enrich_fulltext(5) == 0


def test_remaining_backlog_excludes_last_cycles_garbled_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(rfc, "DATA_DIR", tmp_path)
    (tmp_path / "cycle_log.jsonl").write_text(
        json.dumps({"status": "ok", "garbled_ids": [42]}) + "\n", encoding="utf-8")
    monkeypatch.setattr(rfc, "get_unprocessed_ids", lambda min_id=0: [42, 7, 9])
    assert rfc.remaining_backlog() == (2, 3)
    monkeypatch.setattr(rfc, "get_unprocessed_ids", lambda min_id=0: [42])
    assert rfc.remaining_backlog() == (0, 1)


def test_remaining_backlog_without_a_cycle_log(monkeypatch, tmp_path):
    monkeypatch.setattr(rfc, "DATA_DIR", tmp_path)
    monkeypatch.setattr(rfc, "get_unprocessed_ids", lambda min_id=0: [1, 2])
    assert rfc.remaining_backlog() == (2, 2)


def test_publish_stages_only_when_something_was_created():
    from pipeline.llm_processor import publish_stages_needed
    assert publish_stages_needed(1)
    assert not publish_stages_needed(0)
