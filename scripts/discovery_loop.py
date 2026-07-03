#!/usr/bin/env python3
"""Discovery loop (issue #10, final piece): keeps the distilled classifier's
taxonomy alive without putting an LLM back into the ingest path.

The distill heads are taxonomy-bounded — they can only assign mega-trends that
existed at training time. Novelty is recovered here, periodically:

  1. DISCOVER   run the mega-layer discovery (scripts/discover_trends.py) over
                the full corpus → NEW/SPLIT candidates + canonical orphans,
                written to mega_discovery.candidate.yaml (read-only, Sonnet-
                labelled). A human curates accepted changes into mega_trends.yaml.
  2. RETRAIN    if mega_trends.yaml changed since the heads were trained
                (taxonomy grew/merged), retrain the distill heads so the new
                classes become assignable.
  3. REPORT     one-line status to stdout/log for the cron mail.

Safe by design: step 1 never touches mega_trends.yaml; step 2 only runs when a
human actually curated something. CPU-only except the Sonnet labels (API).

Cron (weekly, Sunday 06:00 — GPU-frei):
    0 6 * * 0  cd /home/dirk/projects/catandary-trends && .venv/bin/python \
        scripts/discovery_loop.py >> ~/logs/catandary-discovery-loop.log 2>&1

    python scripts/discovery_loop.py                # full loop
    python scripts/discovery_loop.py --no-discover  # only check-and-retrain
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import PROJECT_ROOT
from pipeline.distill import MODELS_DIR

PY = str(Path(PROJECT_ROOT) / ".venv" / "bin" / "python")
CANDIDATE = Path(PROJECT_ROOT) / "mega_discovery.candidate.yaml"
TAXONOMY = Path(PROJECT_ROOT) / "mega_trends.yaml"


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}", flush=True)


def run_discovery() -> bool:
    """Mega-layer discovery over the full corpus → candidate YAML. Returns ok."""
    log("discovery: running mega-layer over the full corpus …")
    r = subprocess.run(
        [PY, "scripts/discover_trends.py", "--layer", "mega", "--out", str(CANDIDATE)],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=3600)
    tail = "\n".join((r.stdout or "").strip().splitlines()[-6:])
    log(f"discovery rc={r.returncode}\n{tail}")
    return r.returncode == 0


def needs_retrain() -> bool:
    """True if the curated taxonomy changed after the heads were trained."""
    meta_path = MODELS_DIR / "meta.json"
    if not meta_path.exists():
        return True  # no heads at all
    trained = json.loads(meta_path.read_text()).get("trained", "")
    if not trained:
        return True
    trained_ts = datetime.fromisoformat(trained).timestamp()
    return TAXONOMY.stat().st_mtime > trained_ts


def retrain() -> bool:
    log("retrain: mega_trends.yaml newer than trained heads — retraining …")
    r = subprocess.run(
        [PY, "scripts/train_distill_heads.py"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=7200)
    tail = "\n".join((r.stdout or "").strip().splitlines()[-5:])
    log(f"retrain rc={r.returncode}\n{tail}")
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Discovery loop: discover → (curate) → retrain")
    ap.add_argument("--no-discover", action="store_true",
                    help="skip the discovery run; only check taxonomy → retrain")
    ap.add_argument("--force-retrain", action="store_true")
    args = ap.parse_args()

    ok = True
    if not args.no_discover:
        ok = run_discovery()
        if CANDIDATE.exists():
            log(f"candidates in {CANDIDATE.name} — curate into {TAXONOMY.name} by hand.")

    if args.force_retrain or needs_retrain():
        ok = retrain() and ok
    else:
        log("retrain: taxonomy unchanged since last training — skipping.")

    log("loop done." if ok else "loop finished WITH ERRORS.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
