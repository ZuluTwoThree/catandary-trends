"""Worker-Plumbing (scripts/dossier_worker.py) — ohne GPU, ohne Modell.

Geprüft wird der Kontrakt, nicht die Recherche: Aufträge enden in 'review'
mit gespeicherter Dossier-Version und Endkontrolle; Fehler enden in 'failed';
der Identitäts-Guard bei --assume-model-up verweigert das falsche Modell.
"""
from contextlib import contextmanager, nullcontext

import pytest

import scripts.dossier_worker as w
from pipeline import dossier_orders as m
from pipeline.db import get_connection

RESULT = {
    "question": "q", "report": "Retention was 84% after 350 cycles.",
    "evidence": ["retention of 84% after 350 cycles"],
    "sources": [{"title": "s", "snippet": "84% / 350", "date": "", "outlet": ""}],
    "cited": ["T1"], "stripped_citations": 0, "ledger": [],
    "model": "Qwen3.8-27B", "seconds": 1.0,
}

QUANT_FAIL = {"ok": False, "reason": "no embedding endpoint",
              "sources": [], "note": None, "summary": None}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    with get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS dossier_orders")
        conn.execute("DROP TABLE IF EXISTS dossiers")
    m.ensure_schema()
    monkeypatch.setattr(w.gpu_handover, "embed_on_llamacpp",
                        lambda *a, **k: nullcontext())
    monkeypatch.setattr(w.gpu_handover, "model_on_llamacpp",
                        lambda *a, **k: nullcontext())
    monkeypatch.setattr(w, "build_quant_evidence", lambda t: dict(QUANT_FAIL))
    # Tests fassen systemd nie an: Ausgangszustand "nicht aktiv" → kein Neustart.
    monkeypatch.setattr(w, "_llama_unit_active", lambda: False)
    yield


def _dossier_rows():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT slug, version FROM dossiers ORDER BY slug").fetchall()]


class TestRunWorker:
    def test_orders_end_in_review_with_stored_version(self, monkeypatch):
        monkeypatch.setattr(w.corpus_research, "run",
                            lambda *a, **k: dict(RESULT))
        a = m.create_order("alpha topic")
        b = m.create_order("beta topic")
        assert w.run_worker() == 0
        oa, ob = m.get_order(a), m.get_order(b)
        assert oa["status"] == ob["status"] == "review"
        assert oa["dossier_version"] == 1
        assert _dossier_rows() == [{"slug": "alpha-topic", "version": 1},
                                   {"slug": "beta-topic", "version": 1}]
        # Endkontrolle gespeichert, Quant-Ausfall als Befund sichtbar
        assert oa["check"]["ok"] is True
        assert oa["check"]["quant_ok"] is False
        assert any("Quant-Vorstufe entfiel" in f for f in oa["check"]["findings"])

    def test_same_topic_becomes_next_version(self, monkeypatch):
        monkeypatch.setattr(w.corpus_research, "run",
                            lambda *a, **k: dict(RESULT))
        m.create_order("alpha topic")
        assert w.run_worker() == 0
        m.create_order("alpha topic")
        assert w.run_worker() == 0
        assert _dossier_rows() == [{"slug": "alpha-topic", "version": 1},
                                   {"slug": "alpha-topic", "version": 2}]

    def test_failure_marks_failed_and_rc2(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("model down")
        monkeypatch.setattr(w.corpus_research, "run", boom)
        oid = m.create_order("t")
        assert w.run_worker() == 2
        o = m.get_order(oid)
        assert o["status"] == "failed"
        assert "model down" in o["error"]

    def test_quant_result_reaches_run(self, monkeypatch):
        seen = {}
        def fake_run(*a, **k):
            seen["quant"] = k.get("quant")
            return dict(RESULT)
        monkeypatch.setattr(w.corpus_research, "run", fake_run)
        good = {"ok": True, "reason": None, "sources": [{"id": "Q1"}],
                "note": "measured", "summary": {"off_topic": False}}
        monkeypatch.setattr(w, "build_quant_evidence", lambda t, **k: good)
        m.create_order("t")
        assert w.run_worker() == 0
        assert seen["quant"] is good

    def test_skip_quant_param_per_order(self, monkeypatch):
        called = []
        monkeypatch.setattr(w, "build_quant_evidence",
                            lambda t, **k: called.append(t) or dict(QUANT_FAIL))
        monkeypatch.setattr(w.corpus_research, "run",
                            lambda *a, **k: dict(RESULT))
        m.create_order("with quant")
        m.create_order("without", params={"quant": False})
        assert w.run_worker() == 0
        assert called == ["with quant"]

    def test_assume_model_up_identity_guard(self, monkeypatch):
        monkeypatch.setattr(w.gpu_handover, "_served_model",
                            lambda: "Qwen3-8B-UD-Q4_K_XL")
        oid = m.create_order("t")
        assert w.run_worker(assume_model_up=True) == 1
        assert m.get_order(oid)["status"] == "queued"   # unangetastet

    def test_resting_server_restored_when_it_was_active(self, monkeypatch):
        # Lief llama-server vorher, muss er nach dem Lauf wieder laufen —
        # auch wenn der GPU-Guard den Lauf verweigert hat (die Handover
        # stoppen die Unit VOR dem VRAM-Check).
        calls: list[list[str]] = []
        class _R:
            stdout = "active\n"
        def fake_run(cmd, timeout=60):
            calls.append(list(cmd))
            return _R()
        monkeypatch.setattr(w.gpu_handover, "_run", fake_run)
        monkeypatch.setattr(w, "_llama_unit_active", lambda: True)
        @contextmanager
        def refuse(*a, **k):
            # wie der echte Handover: die Ablehnung passiert beim Betreten
            raise RuntimeError("VRAM pre-check failed")
            yield                                   # pragma: no cover
        monkeypatch.setattr(w.gpu_handover, "model_on_llamacpp", refuse)
        oid = m.create_order("t")
        assert w.run_worker() == 1
        assert m.get_order(oid)["status"] == "queued"
        assert ["systemctl", "--user", "start", w.gpu_handover.LLAMA_UNIT] in calls

    def test_resting_server_left_alone_when_it_was_down(self, monkeypatch):
        calls: list[list[str]] = []
        monkeypatch.setattr(w.gpu_handover, "_run",
                            lambda cmd, timeout=60: calls.append(list(cmd)))
        monkeypatch.setattr(w.corpus_research, "run",
                            lambda *a, **k: dict(RESULT))
        m.create_order("t")
        assert w.run_worker() == 0
        assert not any("start" in c for c in calls)

    def test_only_order_requeues_failed(self, monkeypatch):
        monkeypatch.setattr(w.corpus_research, "run",
                            lambda *a, **k: dict(RESULT))
        oid = m.create_order("t")
        m.mark_running(oid)
        m.mark_failed(oid, "old error")
        assert w.run_worker(only_order=oid) == 0
        assert m.get_order(oid)["status"] == "review"


def test_dr_prepass_is_on_by_default_and_cpc_is_a_known_param(monkeypatch):
    import importlib
    monkeypatch.delenv("DOSSIER_DR", raising=False)
    import scripts.dossier_worker as w
    importlib.reload(w)
    assert w.RUN_DEFAULTS["dr"] is True and w.RUN_DEFAULTS["cpc"] is None
    assert w._params({"params": {"dr": False, "cpc": "H01M4/5825"}})["dr"] is False
    assert w._params({"params": {"cpc": "H01M4/5825"}})["cpc"] == "H01M4/5825"
    monkeypatch.setenv("DOSSIER_DR", "0")
    importlib.reload(w)
    assert w.RUN_DEFAULTS["dr"] is False
    monkeypatch.delenv("DOSSIER_DR", raising=False)
    importlib.reload(w)
