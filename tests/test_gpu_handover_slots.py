"""Ruhezustand schlank (4 Slots), Arbeit mit 24 (Owner 04.10.2026).

Beide Konfigurationen servieren dasselbe GGUF. Ein Handover, der nur den Namen
prüft, sagt beim 1-Slot-Server "serviert schon" — und 24 Worker der Stufen 2-4
stünden auf vier Slots Schlange (gemessen 16 statt 58 Anfragen/min). Deshalb
vergleicht _model_ready die Slot-Zahl aus GET /props, wenn der Aufrufer eine
verlangt.
"""
from __future__ import annotations

import pipeline.gpu_handover as gh

MODEL = "Qwen3-8B-UD-Q4_K_XL.gguf"


def test_name_match_alone_is_ready_without_a_slot_requirement(monkeypatch):
    monkeypatch.setattr(gh, "_served_model", lambda: MODEL)
    monkeypatch.setattr(gh, "_served_slots", lambda: 1)
    assert gh._model_ready(MODEL) is True


def test_too_few_slots_means_not_ready(monkeypatch):
    monkeypatch.setattr(gh, "_served_model", lambda: MODEL)
    monkeypatch.setattr(gh, "_served_slots", lambda: 1)
    assert gh._model_ready(MODEL, 16) is False
    monkeypatch.setattr(gh, "_served_slots", lambda: 24)
    assert gh._model_ready(MODEL, 16) is True
    monkeypatch.setattr(gh, "_served_slots", lambda: 16)
    assert gh._model_ready(MODEL, 16) is True


def test_unknown_slot_count_does_not_force_a_restart(monkeypatch):
    """Ein Server, der /props nicht beantwortet, ist kein Grund für einen Neustart."""
    monkeypatch.setattr(gh, "_served_model", lambda: MODEL)
    monkeypatch.setattr(gh, "_served_slots", lambda: None)
    assert gh._model_ready(MODEL, 16) is True


def test_wrong_model_is_never_ready(monkeypatch):
    monkeypatch.setattr(gh, "_served_model", lambda: "Qwen3-Embedding-8B-Q4_K_M.gguf")
    monkeypatch.setattr(gh, "_served_slots", lambda: 24)
    assert gh._model_ready(MODEL, 16) is False
    assert gh._model_ready(MODEL) is False


def test_eight_b_handover_restarts_the_one_slot_resting_server(monkeypatch):
    monkeypatch.setattr(gh, "_served_model", lambda: MODEL)
    monkeypatch.setattr(gh, "_served_slots", lambda: 1)
    monkeypatch.setattr(gh, "_safe_saved_target", lambda: gh.CANONICAL_RESTING_SCRIPT)
    started, torn = [], []
    monkeypatch.setattr(gh, "llama_server_start",
                        lambda model, timeout=240, swap_symlink=False, min_slots=None:
                        started.append((model, swap_symlink, min_slots)))
    monkeypatch.setattr(gh, "_teardown", lambda saved: torn.append(saved))
    with gh.eight_b_on_llamacpp(MODEL):
        pass
    assert started == [(MODEL, True, gh.EIGHT_B_MIN_SLOTS)]
    assert torn == [gh.CANONICAL_RESTING_SCRIPT]


def test_eight_b_handover_leaves_a_parallel_server_alone(monkeypatch):
    monkeypatch.setattr(gh, "_served_model", lambda: MODEL)
    monkeypatch.setattr(gh, "_served_slots", lambda: 24)
    started = []
    monkeypatch.setattr(gh, "llama_server_start",
                        lambda *a, **k: started.append(a))
    with gh.eight_b_on_llamacpp(MODEL):
        pass
    assert started == []


def test_resting_and_working_script_differ_but_share_the_model():
    work = gh.MODEL_START_SCRIPTS[gh.CANONICAL_RESTING_MODEL]
    assert gh.RESTING_START_SCRIPT.name == gh.CANONICAL_RESTING_SCRIPT
    assert gh.RESTING_START_SCRIPT != work
    assert gh.EIGHT_B_MIN_SLOTS >= 2
