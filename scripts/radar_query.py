#!/usr/bin/env python3
"""Prozessgrenze für das Query-Radar — von der API-Route via execFile aufgerufen.

Warum ein Subprozess statt einer TypeScript-Portierung: die Zellenlogik
(`reg_subtype`, `reg_authority`, die Gates) kodiert drei real gefundene
Fehlklassifikationen (docs/radar_redesign_proposal.md §7.2) und ist in
tests/test_radar_horizons.py fixiert. Eine zweite Implementierung in einer
zweiten Sprache garantiert Drift — und zwar stille, weil beide Seiten
plausibel aussehen. Der Prozessstart kostet ~50 ms; das Argument für einen Port
existiert schlicht nicht.

Kein GPU, kein Modell-Handover: der ganze Pfad ist Postgres-FTS + reines Python.

Aufruf:
    radar_query.py --query "carbon capture" [--regions US,EU,GLOBAL]
                   [--dim strategic|pestel] [--regulated] --json

Gibt genau eine JSON-Zeile auf stdout aus (die Route liest die letzte
nicht-leere Zeile), damit Log-Rauschen nie mit der Nutzlast kollidiert.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from pipeline.radar_horizons import (
    JURISDICTIONS,
    MAX_SCOPE_ROWS,
    MIN_SCOPE_ROWS,
    compute_query_radar,
    count_query_signals,
)

# Ein kalter Treffer kostet 8-20 s (der raw_entries-Join); ohne Deckel würde er
# das Concurrency-Gate der Route so lange blockieren.
STATEMENT_TIMEOUT_MS = 20_000


def main() -> int:
    ap = argparse.ArgumentParser(description="Horizont-Radar für eine Freitext-Query")
    ap.add_argument("--query", required=True)
    ap.add_argument("--regions", default="US,EU,GLOBAL")
    ap.add_argument("--dim", default="strategic", choices=["strategic", "pestel"])
    ap.add_argument("--regulated", action="store_true")
    ap.add_argument("--name", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    query = args.query.strip()
    if len(query) < 3 or len(query) > 120:
        print(json.dumps({"error": "query_length"}))
        return 0

    regions = [r.strip().upper() for r in args.regions.split(",") if r.strip()]
    regions = [r for r in regions if r in JURISDICTIONS][:6] or ["GLOBAL"]

    with get_connection() as conn:
        conn.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")

        # Vorab-Flug (~6 ms): entscheidet über zu breit / zu dünn, BEVOR
        # irgendetwas gerechnet wird.
        n = count_query_signals(conn, query)
        if n > MAX_SCOPE_ROWS:
            print(json.dumps({
                "error": "too_broad", "n_signals": n, "cap": MAX_SCOPE_ROWS,
                "message": (f"Diese Query umfasst {n:,} Signale — zu breit, um als "
                            "ein Feld gelesen zu werden. Grenze sie enger ein.")
                           .replace(",", "."),
            }))
            return 0
        if n < MIN_SCOPE_ROWS:
            print(json.dumps({
                "error": "too_thin", "n_signals": n, "floor": MIN_SCOPE_ROWS,
                "message": (f"Nur {n} Signale — zu wenig für eine belastbare "
                            "Einordnung. Das Radar verweigert die Aussage lieber, "
                            "als sie zu raten."),
            }))
            return 0

        view = compute_query_radar(
            conn, query,
            regions=regions,
            dimension_set=args.dim,
            regulated=args.regulated,
            name=args.name,
        )

    print(json.dumps(view, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
