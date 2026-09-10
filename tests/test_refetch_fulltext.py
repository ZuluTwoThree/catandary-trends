"""Volltext-Nachhollauf (#102, 2026-09-10).

Die 14-Tage-Regel hat 17.665 Volltexte gelöscht; die Quell-URL steht noch in
jeder Zeile, der erneute Abruf ist nach §44b zulässig und seit der Frist von
60 Monaten auch haltbar.

Der Altersfilter ist der Kern des Ganzen: im 0–14-Tage-Band haben 70 % der
Einträge ihren Text noch, und die übrigen 30 % sind genau die, bei denen der
Abruf schon damals scheiterte. Ein Lauf ohne Filter zieht also die
Fehlschläge — gemessen 3 von 60 (5 %) gegen 54 von 60 (90 %) mit Filter.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import refetch_fulltext as rf
from pipeline import article_fetcher as af


class TestAgeFilter:
    def test_default_is_fifteen_days(self):
        assert rf.MIN_AGE_DAYS == 15

    def test_the_filter_reaches_the_query(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(rf.af, "fulltext_source_names", lambda: {"S"})
        monkeypatch.setattr(rf, "get_connection", lambda: _Conn(seen))
        rf.candidates(10)
        assert "fetched_at <" in seen["sql"]
        assert 15 in seen["params"]

    def test_zero_disables_it(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(rf.af, "fulltext_source_names", lambda: {"S"})
        monkeypatch.setattr(rf, "get_connection", lambda: _Conn(seen))
        rf.candidates(10, min_age_days=0)
        assert "fetched_at <" not in seen["sql"]

    def test_already_tried_rows_are_skipped(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(rf.af, "fulltext_source_names", lambda: {"S"})
        monkeypatch.setattr(rf, "get_connection", lambda: _Conn(seen))
        rf.candidates(10)
        assert "fulltext_refetched_at IS NULL" in seen["sql"]

    def test_rows_that_still_have_text_are_skipped(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(rf.af, "fulltext_source_names", lambda: {"S"})
        monkeypatch.setattr(rf, "get_connection", lambda: _Conn(seen))
        rf.candidates(10)
        assert "raw_content IS NULL" in seen["sql"]

    def test_no_fulltext_sources_means_no_candidates(self, monkeypatch):
        monkeypatch.setattr(rf.af, "fulltext_source_names", lambda: set())
        assert rf.candidates(10) == []


class _Conn:
    def __init__(self, sink):
        self.sink = sink
    def execute(self, sql, params=None):
        self.sink["sql"], self.sink["params"] = sql, list(params or [])
        return self
    def fetchall(self):
        return []
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class TestOutcomeHandling:
    def _run(self, monkeypatch, text, reason=None):
        writes = []
        monkeypatch.setattr(rf, "_write", lambda i, t: writes.append((i, t)))
        monkeypatch.setattr(rf.af, "fetch_fulltext_result",
                            lambda url, client=None: af.FetchResult(text, reason))
        stat = rf.run([{"id": 7, "url": "https://x.example/a", "source_name": "S"}],
                      apply=True, workers=1)
        return stat, writes

    def test_a_real_article_is_stored(self, monkeypatch):
        stat, writes = self._run(monkeypatch, "x" * 900)
        assert stat["recovered"] == 1 and writes == [(7, "x" * 900)]

    def test_a_paywall_stub_is_not_stored_but_stamped(self, monkeypatch):
        """Kurz heisst Teaser hinter der Paywall — nicht speichern, aber merken,
        damit der naechste Lauf ihn nicht erneut zieht."""
        stat, writes = self._run(monkeypatch, "kurz")
        assert stat["failed"] == 1 and writes == [(7, None)]

    def test_a_tdm_refusal_is_stamped_too(self, monkeypatch):
        stat, writes = self._run(monkeypatch, None, "tdm:tdmrep.json")
        assert stat["failed"] == 1 and writes == [(7, None)]
        assert stat["reason:tdm"] == 1

    def test_dry_run_writes_nothing(self, monkeypatch):
        writes = []
        monkeypatch.setattr(rf, "_write", lambda i, t: writes.append((i, t)))
        monkeypatch.setattr(rf.af, "fetch_fulltext_result",
                            lambda url, client=None: af.FetchResult("x" * 900))
        rf.run([{"id": 7, "url": "https://x.example/a", "source_name": "S"}],
               apply=False, workers=1)
        assert writes == []


class TestThrottleIsThreadSafe:
    def test_per_host_locks_exist(self):
        """Ohne Schloss war _throttle ein ungeschuetztes read-modify-write —
        zwei Threads haetten denselben Host gleichzeitig getroffen."""
        assert hasattr(af, "_host_locks") and hasattr(af, "_throttle_registry_lock")

    def test_the_same_host_is_serialised(self):
        import threading
        import time
        af._last_hit.clear()
        af._host_locks.clear()
        old = af.PER_HOST_DELAY
        af.PER_HOST_DELAY = 0.15
        try:
            t0 = time.time()
            threads = [threading.Thread(target=af._throttle, args=("h.example",)) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert time.time() - t0 >= 0.25, "drei Anfragen auf einen Host duerfen nicht gleichzeitig raus"
        finally:
            af.PER_HOST_DELAY = old
            af._last_hit.clear()
            af._host_locks.clear()
