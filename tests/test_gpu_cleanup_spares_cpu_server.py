"""Der VRAM-Cleanup des Nachtlaufs darf nur töten, was VRAM hält
(#97, 2026-09-10).

`pkill -f 'build/bin/llama-server'` traf auch den CPU-Embedder auf :8091
(`CUDA_VISIBLE_DEVICES=""`, 0 MiB VRAM), der die Vektorsuche des Korpus-
Rechercheurs bedient — nach dem ersten Nachtlauf mit dem neuen Dienst lag er
tot da. Der Zweck des Blocks ist die Karte, nicht der Prozessname; die
PID-Liste kommt deshalb aus `nvidia-smi --query-compute-apps`.

Prüft den Text des Wrappers (Drift-Wächter) — ein echter Lauf würde GPU-Jobs
abschießen.
"""
from __future__ import annotations

from pathlib import Path

import pytest

WRAPPER = Path(__file__).parent.parent / "scripts" / "full_cycle_cron.sh"
UNIT = Path(__file__).parent.parent / "deploy" / "systemd" / "catandary-embed-cpu.service"


@pytest.fixture(scope="module")
def wrapper() -> str:
    return WRAPPER.read_text()


class TestCleanupIsVramScoped:
    def test_no_blanket_pkill_on_the_process_name(self, wrapper):
        assert "pkill -f 'build/bin/llama-server'" not in wrapper, \
            "blanket pkill also kills the CPU-only embedder"

    def test_pid_list_comes_from_nvidia_smi(self, wrapper):
        assert "--query-compute-apps=pid" in wrapper

    def test_processes_without_vram_are_spared_explicitly(self, wrapper):
        assert "holds no VRAM" in wrapper

    def test_the_systemd_unit_is_still_stopped_first(self, wrapper):
        """Die eigene GPU-Unit gehört weiterhin gestoppt — nur der Blindschuss
        auf fremde Prozesse ist weg."""
        assert "systemctl --user stop llama-server.service" in wrapper


class TestEmbedUnit:
    def test_cpu_server_restarts_always(self):
        assert "Restart=always" in UNIT.read_text()

    def test_cpu_server_runs_on_its_own_port(self):
        assert "start-qwen3-emb-cpu.sh" in UNIT.read_text()
