#!/usr/bin/env python3
"""On-demand TIR for a single CPC subclass — MIT SPNP method (issue #33).

Thin wrapper over scripts/spnp_centrality.domain_k: mean normalized SPNP
centrality of the domain's patents → K via the refit Singh/Triulzi/Magee
regression. Reads the prebuilt patent_spnp table, so it's ~1-2s (the old
II×cycle-time cohort scan was ~55s).

    python scripts/tir_for_cpc.py C12P --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection
from scripts.spnp_centrality import domain_k


def main() -> int:
    ap = argparse.ArgumentParser(description="On-demand SPNP TIR for one CPC subclass (#33)")
    ap.add_argument("cpc")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    cpc = args.cpc.upper()
    if not re.fullmatch(r"[A-H][0-9]{2}[A-Z]", cpc):
        print(json.dumps({"error": "invalid CPC subclass"}) if args.json else "invalid CPC")
        return 1
    if not USE_POSTGRES:
        print("targets Postgres"); return 1

    t0 = time.time()
    with get_connection() as c:
        r = c.execute("SELECT title FROM cpc_definitions WHERE symbol = ?", (cpc,)).fetchone()
    title = ((r["title"] if isinstance(r, dict) else r[0]) if r else "").split("(")[0].strip()
    dk = domain_k(cpc)
    out = {"cpc": cpc, "title": title, "tir_pct": dk["K_pct"], "X": dk["X"],
           "n_patents": dk["n"], "method": "SPNP centrality (Singh/Triulzi/Magee 2021)",
           "computed_in_s": round(time.time() - t0, 1)}
    if args.json:
        print(json.dumps(out))
    else:
        print(f"{cpc} {title}\n  X={dk['X']} n={dk['n']:,} → TIR ≈ {dk['K_pct']} %/yr "
              f"(SPNP method, {out['computed_in_s']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
