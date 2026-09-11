"""Fremde GPU nur im vereinbarten Fenster (Owner 2026-09-10).

Auf `bequiet` steckt eine RTX 5080. Owner-Regel: **01:00–17:00 frei nutzbar,
17:00–01:00 gehört sie dem Owner.** Das Fenster ist keine Optimierung, sondern
eine Zusage — deshalb wird es vor JEDEM Chunk neu geprüft und nicht nur beim
Start, sonst liefe ein um 16:50 gestarteter Lauf in die Zeit des Owners hinein.

Gemessen 10.09.: bequiet 12,4 Texte/s gegen 6,6/s lokal, und derselbe Text
ergibt hier wie dort cos 0,9995 — die Räume sind austauschbar.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from pipeline import remote_gpu as rg


class TestWindow:
    @pytest.mark.parametrize("hour,expected", [
        (0, False), (1, True), (2, True), (12, True), (16, True),
        (17, False), (18, False), (23, False),
    ])
    def test_default_window(self, hour, expected):
        assert rg.window_open(datetime(2026, 9, 10, hour, 30)) is expected

    def test_boundaries_are_inclusive_at_the_start(self):
        assert rg.window_open(datetime(2026, 9, 10, 1, 0)) is True

    def test_boundaries_are_exclusive_at_the_end(self):
        """Um Punkt 17:00 gehoert die Karte dem Owner."""
        assert rg.window_open(datetime(2026, 9, 10, 17, 0)) is False

    def test_a_window_across_midnight_works(self):
        spec = "22:00-06:00"
        assert rg.window_open(datetime(2026, 9, 10, 23, 0), spec) is True
        assert rg.window_open(datetime(2026, 9, 10, 3, 0), spec) is True
        assert rg.window_open(datetime(2026, 9, 10, 12, 0), spec) is False


class TestAvailability:
    def test_unconfigured_means_unavailable(self, monkeypatch):
        monkeypatch.setattr(rg, "REMOTE_EMBED_HOST", "")
        assert rg.available() is None

    def test_closed_window_means_unavailable(self, monkeypatch):
        monkeypatch.setattr(rg, "REMOTE_EMBED_HOST", "http://h:11434")
        assert rg.available(datetime(2026, 9, 10, 20, 0)) is None

    def test_unreachable_host_means_unavailable(self, monkeypatch):
        """Der Rechner ist ein Arbeitsplatz, kein Server — aus ist ein Normalfall."""
        monkeypatch.setattr(rg, "REMOTE_EMBED_HOST", "http://127.0.0.1:9")
        assert rg.available(datetime(2026, 9, 10, 9, 0)) is None

    def test_open_and_reachable_returns_the_host(self, monkeypatch):
        monkeypatch.setattr(rg, "REMOTE_EMBED_HOST", "http://h:11434")
        monkeypatch.setattr(rg.httpx, "get", lambda *a, **k: _Resp(200))
        assert rg.available(datetime(2026, 9, 10, 9, 0)) == "http://h:11434"


class _Resp:
    def __init__(self, code, payload=None):
        self.status_code = code
        self._p = payload or {}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)
    def json(self):
        return self._p


class TestBatchEmbed:
    def test_returns_one_vector_per_text(self, monkeypatch):
        monkeypatch.setattr(rg.httpx, "post",
                            lambda *a, **k: _Resp(200, {"embeddings": [[0.1] * 4096] * 2}))
        assert len(rg.embed_batch_remote(["a", "b"], host="http://h")) == 2

    def test_a_short_answer_raises(self, monkeypatch):
        """Lieber laut scheitern als stillschweigend Zeilen ueberspringen."""
        monkeypatch.setattr(rg.httpx, "post",
                            lambda *a, **k: _Resp(200, {"embeddings": [[0.1] * 4096]}))
        with pytest.raises(RuntimeError, match="1 Vektoren fuer 2 Texte"):
            rg.embed_batch_remote(["a", "b"], host="http://h")
