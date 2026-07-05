#!/usr/bin/env python3
"""Run signal_batch --backend distill with the embedding-server GPU handover.

signal_batch expects /v1/embeddings on :8090; this wrapper brings the embedding
server up (and restores the previous GPU state after) so the distill mass-ingest
can run standalone — same handover as embed_filtered/embed_cpc.

    python scripts/run_distill_batch.py --source-type research --limit 2000
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline import gpu_handover
from pipeline.config import EMBED_MODEL

with gpu_handover.embed_on_llamacpp(EMBED_MODEL):
    rc = subprocess.run(
        [sys.executable, "scripts/signal_batch.py", "--backend", "distill",
         "--execute", *sys.argv[1:]]).returncode
sys.exit(rc)
