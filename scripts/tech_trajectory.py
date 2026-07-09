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

# Domain selection: take the nearest fine codes within this cosine distance, up
# to MAX_CODES. Codes must carry enough patents to be part of a measurable domain.
DIST_GATE = 0.55
MAX_CODES = 10
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
            f"ORDER BY embedding_1024 <=> '{vlit}'::vector LIMIT {max_codes * 2}"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d["dist"] is not None and d["dist"] <= dist_gate:
            out.append({"symbol": d["symbol"], "title": d["title"],
                        "n_patents": d["n_patents"], "vertical": d["vertical"],
                        "dist": round(float(d["dist"]), 3)})
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
