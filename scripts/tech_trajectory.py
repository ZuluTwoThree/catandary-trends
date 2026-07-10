#!/usr/bin/env python3
"""On-demand technology → fine CPC domain → TIR trajectory (issues #42 + #36 + #43).

The end-to-end path the product promises: a free-text technology description is
embedded, matched to the nearest FINE CPC codes (cpc_fine, #42), those codes form
the technology DOMAIN, and the domain's year-by-year improvement rate K(t) +
S-curve direction is computed (#36).

    python scripts/tech_trajectory.py "protein recovery by electrodialysis"
    python scripts/tech_trajectory.py "lithium battery electrode" --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from scripts.tech_query import embed_query
from scripts.tir_trajectory import trajectory

# Domain selection: the technology domain is the union of the nearest fine CPC
# codes within DIST_GATE (cosine). Two-stage, density-aware:
#   1. always take the semantic CORE (the CORE_CODES nearest codes in-gate) — the
#      identity of the technology;
#   2. keep extending in distance order (still in-gate) until the domain carries
#      enough patents for a measurable trajectory (DENSITY_TARGET), capped at
#      MAX_CODES.
# Why: the tightest-matching fine codes can be a data-thin sub-facet (e.g. "solar
# cell" → the H10F10/* cell-physics subgroups, ~1.7k patents) while the dense
# sibling codes that make the same domain measurable (H02S* solar components/
# modules, tens of thousands) sit just a hair further out. Distance-only top-N
# then starves an otherwise-rich domain. Extending by density recovers it without
# semantic drift — the gate still bounds "still the same technology". A genuinely
# thin query never reaches DENSITY_TARGET and stays honestly "insufficient".
# n_patents sums overlap (parent⊃child), so the target is deliberately generous;
# the real per-window MIN_N in the trajectory is the honest final arbiter.
DIST_GATE = 0.55
CORE_CODES = 6
MAX_CODES = 25
DENSITY_TARGET = 12000
CODE_MIN_PATENTS = 50


def resolve_domain(vec1024: list[float], dist_gate: float = DIST_GATE,
                   max_codes: int = MAX_CODES) -> list[dict]:
    """Nearest fine CPC codes to the query vector → the technology domain."""
    vlit = "[" + ",".join(f"{x:.6f}" for x in vec1024) + "]"
    with get_connection() as c:
        rows = c.execute(
            "SELECT symbol, title, n_patents, vertical, "
            f"       (embedding_1024 <=> '{vlit}'::vector) AS dist "
            "FROM cpc_fine WHERE embedding_1024 IS NOT NULL "
            f"  AND n_patents >= {CODE_MIN_PATENTS} "
            f"ORDER BY embedding_1024 <=> '{vlit}'::vector LIMIT {max(max_codes * 3, 60)}"
        ).fetchall()
    out: list[dict] = []
    density = 0
    for r in rows:
        d = dict(r)
        if d["dist"] is None or d["dist"] > dist_gate:
            continue
        out.append({"symbol": d["symbol"], "title": d["title"],
                    "n_patents": d["n_patents"], "vertical": d["vertical"],
                    "dist": round(float(d["dist"]), 3)})
        density += d["n_patents"] or 0
        # stop once the domain is both semantically anchored and dense enough
        if len(out) >= CORE_CODES and density >= DENSITY_TARGET:
            break
        if len(out) >= max_codes:
            break
    return out


def on_demand(query: str) -> dict:
    vec = embed_query(query)
    codes = resolve_domain(vec)
    if not codes:
        return {"query": query, "codes": [], "direction": "insufficient_data",
                "direction_de": "keine passende Technologie gefunden",
                "reason": "no fine CPC code within the distance gate"}
    patterns = [c["symbol"] + "%" for c in codes]
    traj = trajectory(patterns)
    traj["query"] = query
    traj["codes"] = codes
    return traj


def main() -> int:
    ap = argparse.ArgumentParser(description="Free-text technology → TIR trajectory")
    ap.add_argument("query")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = on_demand(args.query)
    if args.json:
        # single line so the API route can take the last stdout line as payload
        print(json.dumps(res))
        return 0
    print(f"\nQuery: {res['query']}")
    print("Resolved fine CPC domain:")
    for c in res["codes"]:
        print(f"  {c['symbol']:14s} n={c['n_patents']:>7,} d={c['dist']}  {(c['title'] or '')[:60]}")
    if res["direction"] == "insufficient_data":
        print(f"  → {res.get('direction_de')} ({res.get('reason')})")
        return 0
    kv = f"{res['K_latest']}%/yr" if res.get("calibrated") else "n/a (außer Kalibrierung)"
    print(f"  → Richtung: {res['direction_de']} (rel. Δ {res['rel_change']:+.0%}); "
          f"TIR aktuell: {kv}  [{res['n_total']:,} Patente]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
