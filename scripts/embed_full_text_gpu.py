#!/usr/bin/env python3
"""embed_full_text.py mit GPU-Handover — analog scripts/signal_batch_embedded.py.

Die Volltexte sind rund elfmal so lang wie der Dedup-Ausschnitt; auf der CPU
dauert ein Text ~20 s (gemessen 2026-09-10), auf der GPU laeuft eine Nacht
Material in Minuten. Der Handover holt den Embedding-Server auf :8090 und
stellt danach den Ruhezustand wieder her.

    python scripts/embed_full_text_gpu.py --limit 5000 --apply
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pipeline import gpu_handover, remote_gpu  # noqa: E402
from pipeline.config import EMBED_MODEL  # noqa: E402
from pipeline.gpu_handover import embed_on_llamacpp  # noqa: E402


def _server_active() -> bool:
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", gpu_handover.LLAMA_UNIT],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() == "active"
    except Exception:                                               # noqa: BLE001
        return False


def _restore_resting_server(was_active: bool) -> None:
    """Ruhezustand wiederherstellen — wie im Dossier-Worker.

    `_teardown` der Handover stoppt den Server und haengt den Symlink zurueck,
    startet aber NICHT neu: in scheduled_cycle.sh und weekly_ingesters.sh macht
    das der Wrapper am Ende. Dieses Skript ist ein eigener Einstiegspunkt, also
    muss es das selbst tun — sonst liegt die Karte danach leer da (beobachtet
    2026-09-10 beim ersten Testlauf).
    """
    if not was_active:
        return
    print(f"Ruhezustand: llama-server wieder starten "
          f"(start-active.sh → {gpu_handover._current_symlink_target()})", flush=True)
    try:
        gpu_handover._run(["systemctl", "--user", "start", gpu_handover.LLAMA_UNIT], timeout=60)
    except Exception as exc:                                        # noqa: BLE001
        print(f"WARN: llama-server konnte nicht neu gestartet werden: {exc}", flush=True)


def main() -> int:
    # RESEARCH_EMBED_HOST bewusst NICHT durchreichen: unter dem Handover ist
    # :8090 der Embedding-Server, und der CPU-Server auf :8091 waere hier die
    # falsche (und viel langsamere) Adresse.
    env = dict(os.environ, EMBED_BACKEND="llamacpp")
    env.pop("RESEARCH_EMBED_HOST", None)
    cmd = [str(REPO / ".venv/bin/python"), "-u", "scripts/embed_full_text.py", *sys.argv[1:]]

    # Steht die fremde GPU im Fenster bereit, ist der lokale Handover reine
    # Verschwendung: er wuerde das 8B von der Karte verdraengen, das
    # Embedding-Modell laden, es NICHT benutzen (embed_full_text greift dann
    # nach bequiet) und alles zurueckstellen — rund eine Minute GPU-Unruhe fuer
    # nichts. Also vorher fragen (2026-09-11).
    remote = remote_gpu.available()
    if remote:
        print(f"fremde GPU im Fenster ({remote}) — lokaler Handover entfaellt", flush=True)
        return subprocess.call(cmd, env=env, cwd=str(REPO))

    was_active = _server_active()
    try:
        with embed_on_llamacpp(EMBED_MODEL):
            rc = subprocess.call(cmd, env=env, cwd=str(REPO))
    finally:
        _restore_resting_server(was_active)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
