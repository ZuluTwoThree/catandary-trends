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


class TestDayAppsAreEvictedOnlyByPattern:
    """Owner 04.10.2026: nemo-speech und whisper-server werden fuer den Nachtlauf beendet
    (das 24-Slot-8B braucht ~22 GB). Nur Prozesse, die laut nvidia-smi VRAM halten UND
    auf GPU_EVICT_PATTERNS passen — kein pkill auf Namen, nichts ausserhalb der Karte."""

    def test_eviction_reads_the_vram_holders_from_nvidia_smi(self, wrapper):
        assert "--query-compute-apps=pid,process_name,used_memory" in wrapper

    def test_eviction_is_gated_by_the_pattern_variable(self, wrapper):
        # seit 09.10.2026 zusätzlich hinter GPU_EVICT_DAY_APPS (Default 0: 8B mit 16 Fächern passt daneben)
        assert 'if [ "${GPU_EVICT_DAY_APPS:-0}" = "1" ] && [ -n "${GPU_EVICT_PATTERNS:-}" ]' in wrapper
        assert 'grep -Eq "$GPU_EVICT_PATTERNS"' in wrapper
        assert "pkill" not in wrapper.split("GPU_EVICT_PATTERNS", 1)[1].split("waiting for VRAM", 1)[0]

    def test_default_pattern_names_the_owner_apps(self):
        guard = (Path(__file__).parent.parent / "scripts" / "lib" / "gpu_guard.sh").read_text()
        assert 'GPU_EVICT_PATTERNS="${GPU_EVICT_PATTERNS:-nemo-speech|whisper-server}"' in guard

    def test_day_apps_stay_on_by_default_since_16_slots(self):
        """Owner 09.10.2026: das 8B läuft nachts mit 16 Fächern (16,2 GB) — die Mitschrift bleibt an."""
        guard = (Path(__file__).parent.parent / "scripts" / "lib" / "gpu_guard.sh").read_text()
        assert 'GPU_EVICT_DAY_APPS="${GPU_EVICT_DAY_APPS:-0}"' in guard
        from pipeline import config, gpu_handover
        assert config.CLASSIFY_WORKERS == 16
        assert gpu_handover.MODEL_START_SCRIPTS["Qwen3-8B-UD-Q4_K_XL.gguf"].name == "start-qwen3-8b-16slot.sh"
