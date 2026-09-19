"""Unit-Besitz im GPU-Handover (#98 c, 2026-09-05): Cleanup nur eigene Server.

Am 05.09. stoppte die Aufräumroutine des Cycles den Embedding-Server, den
inzwischen der Samstags-Ingester gestartet hatte. Seitdem vermerkt
llama_server_start "MAINPID OWNERPID" in data/llama-server.<job>.pid,
llama_server_stop stoppt nur noch die vermerkte MainPID, und ein Handover
übernimmt keinen Server, den ein lebender anderer Job vermerkt hat.
Alle systemctl-/nvidia-smi-Aufrufe sind gemockt.
"""
import os
from types import SimpleNamespace

import pytest

import pipeline.gpu_handover as gh

MODEL = "Qwen3-Embedding-8B-Q4_K_M.gguf"


@pytest.fixture
def harness(monkeypatch, tmp_path):
    """Fake systemctl: MainPID aus state['main_pid'], Aufrufe in calls."""
    state = {"main_pid": 0}
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=60):
        calls.append(list(cmd))
        if cmd[:3] == ["systemctl", "--user", "show"]:
            return SimpleNamespace(stdout=f"{state['main_pid']}\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(gh, "_run", fake_run)
    monkeypatch.setattr(gh, "PID_DIR", tmp_path)
    monkeypatch.setenv("GPU_JOB_NAME", "run_full_cycle")
    monkeypatch.setattr(gh, "_wait_vram_below", lambda *a, **k: True)
    monkeypatch.setattr(gh, "ollama_unload", lambda: None)
    monkeypatch.setattr(gh, "_served_model", lambda: MODEL)
    monkeypatch.setattr(gh.time, "sleep", lambda s: None)
    return state, calls, tmp_path


def _stops(calls):
    return [c for c in calls if c[:3] == ["systemctl", "--user", "stop"]]


class TestRecord:
    def test_start_records_main_pid_and_owner(self, harness, monkeypatch):
        state, calls, d = harness
        state["main_pid"] = 4242
        ready = iter([False, True])            # erst nicht bereit, nach Start bereit
        monkeypatch.setattr(gh, "_model_ready", lambda m: next(ready))
        monkeypatch.setattr(gh, "_preflight_model_matches", lambda m: True)
        monkeypatch.setattr(gh, "swap_active_symlink", lambda m: None)
        gh.llama_server_start(MODEL, swap_symlink=True)
        rec = (d / "llama-server.run_full_cycle.pid").read_text().split()
        assert rec == ["4242", str(os.getpid())]

    def test_job_name_is_sanitised(self, monkeypatch):
        monkeypatch.delenv("GPU_JOB_NAME", raising=False)
        monkeypatch.setattr(gh.sys, "argv", ["-c"])
        assert gh._job_name() == "c" or gh._job_name() == "python"
        monkeypatch.setattr(gh.sys, "argv", ["/x/scripts/signal_batch_embedded.py"])
        assert gh._job_name() == "signal_batch_embedded"


class TestStop:
    def test_own_server_is_stopped_and_record_removed(self, harness):
        state, calls, d = harness
        state["main_pid"] = 4242
        (d / "llama-server.run_full_cycle.pid").write_text(f"4242 {os.getpid()}\n")
        assert gh.llama_server_stop() is True
        assert len(_stops(calls)) == 1
        assert not (d / "llama-server.run_full_cycle.pid").exists()

    def test_foreign_server_is_left_running(self, harness, caplog):
        """Der Vorfall: unser Server (4242) wurde vom Ingester durch 5151 ersetzt."""
        state, calls, d = harness
        state["main_pid"] = 5151
        (d / "llama-server.run_full_cycle.pid").write_text(f"4242 {os.getpid()}\n")
        assert gh.llama_server_stop() is False
        assert _stops(calls) == []
        assert "not the one this job started" in caplog.text
        assert not (d / "llama-server.run_full_cycle.pid").exists()

    def test_no_record_keeps_legacy_stop(self, harness):
        state, calls, d = harness
        state["main_pid"] = 4242
        assert gh.llama_server_stop() is True
        assert len(_stops(calls)) == 1

    def test_teardown_skips_symlink_restore_for_foreign_server(self, harness, monkeypatch):
        state, calls, d = harness
        state["main_pid"] = 5151
        (d / "llama-server.run_full_cycle.pid").write_text(f"4242 {os.getpid()}\n")
        restored = []
        monkeypatch.setattr(gh, "_restore_symlink", lambda t: restored.append(t))
        gh._teardown("start-qwen3-8b-208k.sh")
        assert restored == []                  # der andere Job stellt den Ruhezustand her
        state["main_pid"] = 4242
        (d / "llama-server.run_full_cycle.pid").write_text(f"4242 {os.getpid()}\n")
        gh._teardown("start-qwen3-8b-208k.sh")
        assert restored == ["start-qwen3-8b-208k.sh"]


class TestTakeoverGuard:
    def _arm_start(self, monkeypatch):
        monkeypatch.setattr(gh, "_model_ready", lambda m: False)
        monkeypatch.setattr(gh, "_preflight_model_matches", lambda m: True)
        monkeypatch.setattr(gh, "swap_active_symlink", lambda m: None)

    def test_refuses_server_of_alive_foreign_job(self, harness, monkeypatch):
        """Umgekehrter Vorfall: der Ingester darf den Gemma-Server des laufenden
        Cycles nicht übernehmen."""
        state, calls, d = harness
        state["main_pid"] = 4242
        (d / "llama-server.signal_batch_embedded.pid").write_text("4242 999999\n")
        monkeypatch.setattr(gh, "_pid_alive", lambda pid: pid == 999999)
        self._arm_start(monkeypatch)
        with pytest.raises(RuntimeError, match="belongs to running job signal_batch_embedded"):
            gh.llama_server_start(MODEL, swap_symlink=True, timeout=0)
        assert _stops(calls) == []            # nichts angefasst

    def test_stale_record_of_dead_job_is_ignored_and_removed(self, harness, monkeypatch):
        state, calls, d = harness
        state["main_pid"] = 4242
        stale = d / "llama-server.old_job.pid"
        stale.write_text("4242 999999\n")
        monkeypatch.setattr(gh, "_pid_alive", lambda pid: False)
        self._arm_start(monkeypatch)
        with pytest.raises(RuntimeError, match="did not serve"):   # timeout=0 → kein Ready
            gh.llama_server_start(MODEL, swap_symlink=True, timeout=0)
        assert len(_stops(calls)) == 1        # Übernahme lief
        assert not stale.exists()

    def test_own_older_record_does_not_block(self, harness, monkeypatch):
        state, calls, d = harness
        state["main_pid"] = 4242
        (d / "llama-server.run_full_cycle.pid").write_text(f"4242 {os.getpid()}\n")
        self._arm_start(monkeypatch)
        with pytest.raises(RuntimeError, match="did not serve"):
            gh.llama_server_start(MODEL, swap_symlink=True, timeout=0)
        assert len(_stops(calls)) == 1
