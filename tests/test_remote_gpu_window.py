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


class TestRunStopsAtWindowClose:
    def test_the_loop_rechecks_the_window(self):
        import inspect
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import embed_full_text as eft
        src = inspect.getsource(eft.run)
        assert "window_open()" in src, "Fenster muss im Chunk-Loop geprueft werden"
        assert "window_closed" in src

    def test_a_remote_failure_falls_back_locally(self):
        """Seit 2394bba (2026-09-11) lebt der Fallback in embed_remote_or_fallback:
        run() ruft ihn je Block, lokal geht es nur mit bestaetigtem Embedding-Modell
        weiter (Details: tests/test_embed_full_text.py::TestRemoteFallback)."""
        import inspect
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import embed_full_text as eft
        assert "embed_remote_or_fallback" in inspect.getsource(eft.run)
        src = inspect.getsource(eft.embed_remote_or_fallback)
        assert "ab hier lokal" in src and "assert_embedding_model" in src


class TestWrapperSkipsLocalHandover:
    """Steht die fremde GPU bereit, ist der lokale Handover Verschwendung
    (2026-09-11).

    Er würde das 8B von der Karte verdrängen, das Embedding-Modell laden, es
    NICHT benutzen — `embed_full_text` greift dann nach bequiet — und alles
    zurückstellen. Rund eine Minute GPU-Unruhe für nichts, jede Nacht um 09:00.
    """

    def _wrapper(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import embed_full_text_gpu as w
        return w

    def test_remote_available_means_no_handover(self, monkeypatch):
        w = self._wrapper()
        called = {"handover": False, "run": False}
        monkeypatch.setattr(w.remote_gpu, "available", lambda: "http://h:11434")
        monkeypatch.setattr(w, "embed_on_llamacpp",
                            lambda m: called.__setitem__("handover", True))
        monkeypatch.setattr(w.subprocess, "call",
                            lambda *a, **k: called.__setitem__("run", True) or 0)
        monkeypatch.setattr(w.sys, "argv", ["x"])
        assert w.main() == 0
        assert called["run"] is True
        assert called["handover"] is False, "lokaler Handover trotz freier Fremd-GPU"

    def test_no_remote_means_handover(self, monkeypatch):
        w = self._wrapper()
        from contextlib import contextmanager
        called = {"handover": False}

        @contextmanager
        def _fake(model):
            called["handover"] = True
            yield

        monkeypatch.setattr(w.remote_gpu, "available", lambda: None)
        monkeypatch.setattr(w, "embed_on_llamacpp", _fake)
        monkeypatch.setattr(w, "_server_active", lambda: False)
        monkeypatch.setattr(w, "_restore_resting_server", lambda a: None)
        monkeypatch.setattr(w.subprocess, "call", lambda *a, **k: 0)
        monkeypatch.setattr(w.sys, "argv", ["x"])
        assert w.main() == 0
        assert called["handover"] is True, "ohne Fremd-GPU muss lokal uebernommen werden"

    def test_the_resting_server_is_restored_on_the_local_path(self, monkeypatch):
        """Der Handover startet den ruhenden Server nicht neu — das muss der
        eigene Einstiegspunkt tun."""
        w = self._wrapper()
        from contextlib import contextmanager
        restored = []

        @contextmanager
        def _fake(model):
            yield

        monkeypatch.setattr(w.remote_gpu, "available", lambda: None)
        monkeypatch.setattr(w, "embed_on_llamacpp", _fake)
        monkeypatch.setattr(w, "_server_active", lambda: True)
        monkeypatch.setattr(w, "_restore_resting_server", lambda a: restored.append(a))
        monkeypatch.setattr(w.subprocess, "call", lambda *a, **k: 0)
        monkeypatch.setattr(w.sys, "argv", ["x"])
        w.main()
        assert restored == [True]
