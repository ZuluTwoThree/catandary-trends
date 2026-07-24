#!/usr/bin/env python3
"""On-demand TIR for a single CPC subclass — active prod path (issue #33).

Konsolidiert (2026-07-24): dieser Endpoint lief früher über
scripts/spnp_centrality.domain_k — altes db-Substrat (patent_spnp), own-Prädiktor,
eigene Koeffizienten (−6.460/10.192) — und lieferte damit eine DRITTE, abweichend
kalibrierte TIR-Zahl neben cpc_insights und /api/foresight/trajectory. Jetzt
nutzt er dieselbe Maschinerie wie beide anderen Pfade (tir_trajectory.trajectory:
Substrat/Prädiktor/Kalibrierung aus den aktiven Defaults, aktuell fullz3+cited)
— eine Zahl, ein Codepfad. Semantik wie cpc_insights: tir_pct = K_median über die
gemessene Historie; oberhalb CALIB_MAX wird der Absolutwert zurückgehalten und
nur die Richtung gemeldet. Hintergrund: docs/tir_mit_method_comparison.md §5.

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
from scripts.tir_trajectory import PREDICTOR, SUBSTRATE, trajectory


def main() -> int:
    ap = argparse.ArgumentParser(description="On-demand TIR for one CPC subclass (#33)")
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

    tj = trajectory([cpc + "%"])
    if tj.get("direction") == "insufficient_data":
        status = "insufficient_history"
    elif tj.get("calibrated") is False:
        status = "above_calibrated_range"
    else:
        status = "ok"
    out = {"cpc": cpc, "title": title,
           "tir_pct": tj.get("K_median") if tj.get("calibrated") else None,
           "tir_recent": tj.get("K_recent"),
           "tir_status": status,
           "direction": tj.get("direction"),
           "direction_de": tj.get("direction_de"),
           "n_patents": tj.get("n_total"),
           "earliest_year": tj.get("earliest_year"),
           "method": f"SPNP centrality (Singh/Triulzi/Magee 2021) — {SUBSTRATE}+{PREDICTOR}",
           "computed_in_s": round(time.time() - t0, 1)}
    if args.json:
        print(json.dumps(out))
    else:
        k = f"{out['tir_pct']} %/yr" if out["tir_pct"] is not None else f"({status})"
        print(f"{cpc} {title}\n  n={out['n_patents']:,} → TIR ≈ {k}, "
              f"direction={out['direction']} ({SUBSTRATE}+{PREDICTOR}, "
              f"{out['computed_in_s']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
