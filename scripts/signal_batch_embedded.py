#!/usr/bin/env python3
"""signal_batch --backend distill mit GPU-Handover auf den Embedding-Server.

Der Distill-Pfad ist GPU-frei — bis auf die Embeddings, die einen llama-server
im --embedding-Modus brauchen. Dieser Runner kapselt genau das: Symlink auf das
Embedding-Startskript umhängen, Server starten, signal_batch fahren, danach den
vorherigen Zustand wiederherstellen (embed_on_llamacpp macht das auch bei
Fehlern). Erstmals genutzt für den 128k-OpenAlex-Batch am 2026-08-08, jetzt der
Standard-Runner für die wöchentlichen Ingester-Neuzugänge.

Alle Argumente werden 1:1 an scripts/signal_batch.py durchgereicht;
--backend distill und --execute werden erzwungen.

    python scripts/signal_batch_embedded.py --source-type research --min-id 21600000
    python scripts/signal_batch_embedded.py --source-type api --no-patents --min-id 21600000
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pipeline.config import EMBED_MODEL  # noqa: E402
from pipeline.gpu_handover import embed_on_llamacpp  # noqa: E402


def main() -> int:
    passthrough = [a for a in sys.argv[1:] if a not in ("--backend", "distill", "--execute")]
    env = dict(os.environ, EMBED_BACKEND="llamacpp")
    with embed_on_llamacpp(EMBED_MODEL):
        return subprocess.call(
            [str(REPO / ".venv/bin/python"), "-u", "scripts/signal_batch.py",
             "--backend", "distill", "--execute", *passthrough],
            env=env, cwd=str(REPO))


if __name__ == "__main__":
    raise SystemExit(main())
