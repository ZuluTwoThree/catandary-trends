#!/usr/bin/env python3
"""Eine Messung fuer das Ops-Dashboard (#104) — vom systemd-Timer minuetlich.

    .venv/bin/python -m scripts.ops_sampler            # messen + schreiben
    .venv/bin/python -m scripts.ops_sampler --print    # nur anzeigen, nichts schreiben
    .venv/bin/python -m scripts.ops_sampler --full     # volle Messung erzwingen

Der Timer: deploy/systemd/catandary-ops-sampler.{service,timer} (User-Unit,
laeuft aus dem main-Worktree). Jede zehnte Minute ist eine VOLLE Messung
(teure Zaehlungen, SMART, Tabellengroessen) und raeumt zugleich Zeilen aelter
als OPS_RETENTION_DAYS (7) ab. Alles Weitere: pipeline/ops_probe.py.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import ops_probe  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print", action="store_true", help="Messung ausgeben, nicht schreiben")
    ap.add_argument("--full", action="store_true", help="volle Messung erzwingen")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    t0 = time.time()
    sample = ops_probe.take_sample(full=True if args.full else None)
    if args.print:
        print(json.dumps(sample, indent=2, default=lambda o: o.isoformat() if isinstance(o, datetime) else str(o)))
        print(f"-- {time.time() - t0:.2f}s, full={sample['is_full']}", file=sys.stderr)
        return 0
    ops_probe.write_sample(sample)
    if sample["is_full"]:
        pruned = ops_probe.prune_samples()
        if pruned:
            logging.getLogger(__name__).info("pruned %d samples older than %d days",
                                             pruned, ops_probe.RETENTION_DAYS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
