#!/usr/bin/env python3
"""On-demand TIR for a single CPC subclass (issue #28, Super Pro+ deep analysis).

The ad-hoc query shows a proxy TIR from the nearest CURATED class (instant).
This computes the real TIR for the ACTUAL nearest class — patent_dynamics on
the citation graph (fixed 2000-2015 cohort) + the same calibration used for the
curated set. ~40-70s; meant to be triggered by an explicit "Deep analysis"
button, not the initial query.

    python scripts/tir_for_cpc.py C12P --json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection
from scripts.build_cpc_insights import (TIR_ANCHORS, fit_tir_calibration,
                                        patent_dynamics)


def calibration() -> tuple[float, float] | None:
    """(a, b) for ln(k)=a+b·ln(index), refit on the anchors' stored indices."""
    metrics: dict[str, dict] = {}
    with get_connection() as c:
        for sym in TIR_ANCHORS:
            r = c.execute("SELECT payload->'patent_dynamics'->>'tir_index' AS i "
                          "FROM cpc_insights WHERE symbol = ?", (sym,)).fetchone()
            v = (r["i"] if isinstance(r, dict) else r[0]) if r else None
            if v:
                metrics.setdefault(sym, {})["tir_index"] = float(v)
    return fit_tir_calibration(metrics)


def main() -> int:
    ap = argparse.ArgumentParser(description="On-demand TIR for one CPC subclass (#28)")
    ap.add_argument("cpc", help="CPC subclass symbol, e.g. C12P")
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

    dyn = patent_dynamics(cpc)
    ii, ct = dyn.get("immediate_importance"), dyn.get("cycle_time_years")
    idx = (ii / ct) if (ii and ct and ct > 0) else None
    cal = calibration()
    tir = None
    if idx and idx > 0 and cal:
        a, b = cal
        tir = round(max(0.5, min(80.0, math.exp(a + b * math.log(idx)))), 1)

    out = {
        "cpc": cpc, "title": title,
        "immediate_importance": ii, "cycle_time_years": ct,
        "tir_index": round(idx, 4) if idx else None,
        "tir_pct": tir, "computed_in_s": round(time.time() - t0, 1),
    }
    if args.json:
        print(json.dumps(out))
    else:
        print(f"{cpc} {title}\n  II={ii} cycle={ct}y index={out['tir_index']} "
              f"→ TIR ≈ {tir} %/yr  ({out['computed_in_s']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
