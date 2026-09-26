"""Der Wächter muss einen toten oder falsch beladenen llama-server melden.

Anlass (2026-09-26): `weekly_ingesters.sh` stellte den Ruhezustand nicht her — der
GPU-Handover stoppt den Server und setzt nur den Symlink zurück. Gemessen über
`ops_samples` lag die Karte danach jeden Samstag leer da (19.09.: 129 von 169 Messungen
zwischen 07:30 und 12:00 ohne Modell; 26.09.: 106 von 109). Der Wächter meldete um 07:45
„alles in Ordnung", weil er nur die Stage-Bilanz des Cycles liest und es am Wochenende
keinen Cycle gibt. Die Owner-Instanz auf :3001 hatte in dieser Zeit kein Modell.
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from scripts import cycle_watchdog as w


@pytest.fixture(autouse=True)
def _no_gpu_job(monkeypatch):
    """Standard: kein fremder GPU-Job — sonst ist ein anderes Modell erwartet."""
    class R:
        returncode = 1
        stdout = ""
    monkeypatch.setattr(w.__dict__.get("subprocess", None) or __import__("subprocess"),
                        "run", lambda *a, **k: R(), raising=False)
    yield


def _serve(monkeypatch, model_id: str):
    class Resp:
        def read(self):
            return json.dumps({"data": [{"id": model_id}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Resp())


def test_resting_model_is_ok(monkeypatch):
    _serve(monkeypatch, "./models/Qwen3-8B-UD-Q4_K_XL.gguf")
    v = w.inspect_llama_server("20260926")
    assert v["ok"] is True and v["kind"] == "llama"


def test_server_down_is_reported(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    v = w.inspect_llama_server("20260926")
    assert v["ok"] is False
    assert v["kind"] == "llama-down"
    assert "gpu-mode catandary" in v["detail"], "die Mail muss den Weg zurück nennen"


def test_wrong_model_is_reported(monkeypatch):
    """Ein hart abgebrochener Handover lässt den Embedder oder den 27B stehen."""
    _serve(monkeypatch, "./models/Qwen3-Embedding-8B-Q4_K_M.gguf")
    v = w.inspect_llama_server("20260926")
    assert v["ok"] is False and v["kind"] == "llama-wrong-model"


def test_running_gpu_job_suppresses_the_alarm(monkeypatch):
    """Während eines GPU-Jobs gehört die Karte ihm — ein anderes Modell ist dann normal."""
    import subprocess

    class R:
        returncode = 0
        stdout = "run_full_cycle (pid 123)\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    _serve(monkeypatch, "./models/gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf")
    v = w.inspect_llama_server("20260926")
    assert v["ok"] is True and v["kind"] == "llama-busy"


def test_check_is_wired_into_main():
    """Ohne den Aufruf in main() meldet die Prüfung nie etwas."""
    import inspect
    src = inspect.getsource(w.main)
    assert "inspect_llama_server" in src
    assert "llama_v" in src
