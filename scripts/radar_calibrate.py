#!/usr/bin/env python3
"""Batch-Kalibrierung des Horizont-Radars über viele Suchbegriffe.

Warum ein eigenes Skript und nicht `radar_query.py` in einer Schleife: die
Kalibrierung braucht etwas anderes als die API — nicht die Render-Form, sondern
die **prüfbare Behauptung**. Für jede Zelle also Horizont, Methode, Signalzahl,
Begründung UND die Titel der Evidenz, an denen ein Fachprüfer die Aussage gegen
die Wirklichkeit halten kann. Ohne die Titel ist eine Zelle nicht widerlegbar,
und eine nicht widerlegbare Aussage ist keine Messung.

Ausgabe:
  --out  <json>  vollständig, maschinenlesbar (Eingabe für die Scout-Prüfung)
  --md   <md>    kompaktes Raster pro Begriff, für den Menschen

Aufruf:
    scripts/radar_calibrate.py --terms docs/radar_calibration_terms.txt \
        --out data/radar_calibration.json --md data/radar_calibration.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from pipeline.radar_horizons import (
    MAX_SCOPE_ROWS,
    MIN_SCOPE_ROWS,
    compute_query_radar,
    count_query_signals,
)

STATEMENT_TIMEOUT_MS = 60_000  # großzügiger als die Route: hier zählt Vollständigkeit


def parse_terms(path: Path) -> list[dict]:
    """Zeilenformat: `term | domain | regulated(0/1)`; # ist Kommentar."""
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        out.append({
            "term": parts[0],
            "domain": parts[1] if len(parts) > 1 else "",
            "regulated": bool(int(parts[2])) if len(parts) > 2 and parts[2] else False,
        })
    return out


def run_term(conn, spec: dict, regions: list[str], today: date) -> dict:
    term = spec["term"]
    t0 = time.time()
    n = count_query_signals(conn, term)
    if n > MAX_SCOPE_ROWS:
        return {**spec, "status": "too_broad", "n_signals": n,
                "seconds": round(time.time() - t0, 2), "cells": []}
    if n < MIN_SCOPE_ROWS:
        return {**spec, "status": "too_thin", "n_signals": n,
                "seconds": round(time.time() - t0, 2), "cells": []}

    view = compute_query_radar(
        conn, term, regions=regions, dimension_set="strategic",
        regulated=spec["regulated"], today=today,
    )
    ev_map = view.get("evidence") or {}
    cells = []
    for c in view["cells"]:
        cells.append({
            "dimension": c["dimension"],
            "region": c["region"],
            "horizon": c["horizon"],
            "method": c["method"],
            "n_signals": c["n_signals"],
            "rationale": c["rationale"],
            # Die Titel SIND der Prüfhebel: ohne sie ist eine Zelle nicht
            # widerlegbar. Quelle mitgeben, damit ein Scout die Meldung findet.
            "evidence": [
                {"id": i,
                 "title": (ev_map.get(str(i)) or {}).get("title"),
                 "source": (ev_map.get(str(i)) or {}).get("source_name"),
                 "url": (ev_map.get(str(i)) or {}).get("source_url")}
                for i in (c["evidence"] or [])
            ],
        })
    return {**spec, "status": "ok", "n_signals": view["n_signals"],
            "seconds": round(time.time() - t0, 2), "cells": cells}


GRID_DIMS = ("technology", "regulatory", "market", "adoption")


def to_markdown(results: list[dict], regions: list[str]) -> str:
    lines = ["# Radar-Kalibrierung", ""]
    ok = [r for r in results if r["status"] == "ok"]
    lines.append(f"{len(ok)} von {len(results)} Begriffen ergeben ein Radar. "
                 f"Jurisdiktionen: {', '.join(regions)}.")
    lines.append("")
    lines.append("| # | Begriff | n | TEC | " +
                 " | ".join(f"REG {r} | MKT {r} | ADO {r}" for r in regions) + " |")
    lines.append("|---|" + "---|" * (3 + 3 * len(regions)))
    for i, r in enumerate(results, 1):
        if r["status"] != "ok":
            lines.append(f"| {i} | {r['term']} | {r['n_signals']} | "
                         f"*{r['status']}* |" + " |" * (3 * len(regions)))
            continue
        by = {(c["dimension"], c["region"]): c for c in r["cells"]}
        tech = by.get(("technology", "*"), {}).get("horizon") or "—"
        cols = [tech]
        for reg in regions:
            for dim in ("regulatory", "market", "adoption"):
                cols.append(by.get((dim, reg), {}).get("horizon") or "—")
        lines.append(f"| {i} | {r['term']} | {r['n_signals']} | " +
                     " | ".join(cols) + " |")
    lines.append("")
    for i, r in enumerate(results, 1):
        if r["status"] != "ok":
            continue
        lines.append(f"## {i}. {r['term']}  ·  {r['n_signals']} Signale"
                     + ("  ·  reguliert" if r["regulated"] else ""))
        for c in r["cells"]:
            head = (f"**{c['dimension']}"
                    + (f" / {c['region']}" if c["region"] != "*" else "")
                    + f"** → {c['horizon'] or '—'}  "
                    f"({c['method']}, n={c['n_signals']})")
            lines.append(head)
            lines.append(f"  {c['rationale']}")
            for e in c["evidence"][:5]:
                lines.append(f"    - [{e['id']}] {e['title']} ({e['source']})")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--terms", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--md", type=Path)
    ap.add_argument("--regions", default="US,EU,GLOBAL")
    ap.add_argument("--only", default=None,
                    help="Kommaliste: nur diese Begriffe rechnen")
    ap.add_argument("--count-only", action="store_true",
                    help="nur Treffermengen zählen (~6 ms je Begriff)")
    args = ap.parse_args()

    regions = [r.strip().upper() for r in args.regions.split(",") if r.strip()]
    specs = parse_terms(args.terms)
    if args.only:
        want = {s.strip().lower() for s in args.only.split(",")}
        specs = [s for s in specs if s["term"].lower() in want]

    today = date.today()
    results = []
    with get_connection() as conn:
        conn.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
        for i, spec in enumerate(specs, 1):
            if args.count_only:
                n = count_query_signals(conn, spec["term"])
                flag = ("too_broad" if n > MAX_SCOPE_ROWS
                        else "too_thin" if n < MIN_SCOPE_ROWS else "ok")
                print(f"{i:3d}. {spec['term']:<34} {n:>6}  {flag}", flush=True)
                results.append({**spec, "status": flag, "n_signals": n, "cells": []})
                continue
            r = run_term(conn, spec, regions, today)
            results.append(r)
            print(f"{i:3d}. {spec['term']:<34} n={r['n_signals']:>6} "
                  f"{r['status']:<9} {r['seconds']:>5.1f}s", flush=True)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(
            {"generated": today.isoformat(), "regions": regions,
             "results": results}, indent=1, default=str), encoding="utf-8")
        print(f"\n→ {args.out}")
    if args.md and not args.count_only:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(to_markdown(results, regions), encoding="utf-8")
        print(f"→ {args.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
