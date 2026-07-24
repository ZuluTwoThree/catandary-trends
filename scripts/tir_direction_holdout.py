#!/usr/bin/env python3
"""Richtungs-Holdout-Auswertung (Paper-Pflichtanalyse #11).

Wertet die in docs/tir_direction_holdout.md VORAB fixierten und committeten
Erwartungen einmalig auf dem aktiven Prod-Pfad aus (Defaults, keine Overrides).
Disjunkt von Band-Tuning, 11er-Kontrollgruppe und curated-23. Ergebnisse werden
unverändert berichtet — inklusive Fehlschlägen.

    python scripts/tir_direction_holdout.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.tir_trajectory import PREDICTOR, SUBSTRATE, trajectory

OUT_MD = Path(__file__).parent.parent / "data" / "tir_direction_holdout_result.md"
OUT_JSON = Path(__file__).parent.parent / "data" / "mit_benchmark" / "direction_holdout_result.json"

# Exakt die Liste aus docs/tir_direction_holdout.md (Erwartungen vorab committet).
HOLDOUT = [
    ("LiDAR-Systeme",                        ["G01S17%"], "up"),
    ("Wärmepumpen-Heizung",                  ["F25B30%"], "up"),
    ("Wasserstoff-Erzeugung/-Speicherung",   ["C01B3%"],  "up"),
    ("Optische Datenspeicher",               ["G11B7%"],  "down"),
    ("Fotografischer Film",                  ["G03C%"],   "down"),
    ("Verbrennungsmotor-Einspritzung",       ["F02M%"],   "down"),
    ("Schlösser/Schließtechnik",             ["E05B%"],   "not_up"),
    ("Schreibgeräte",                        ["B43K%"],   "not_up"),
    ("Sanitär-Installationen",               ["E03C%"],   "not_up"),
    ("Mechanische Uhrwerke",                 ["G04B%"],   "not_up"),
]

UP = {"accelerating"}
DOWN = {"maturing", "decelerating"}


def check(direction: str, tier: str) -> bool:
    if tier == "up":
        return direction in UP
    if tier == "down":
        return direction in DOWN
    if tier == "not_up":
        return direction not in UP
    return False


def main() -> int:
    rows, passed = [], 0
    for name, patterns, tier in HOLDOUT:
        t0 = time.time()
        tj = trajectory(patterns)
        d = tj.get("direction")
        ok = check(d, tier)
        passed += ok
        rows.append({"name": name, "patterns": patterns, "tier": tier,
                     "direction": d, "rel_change": tj.get("rel_change"),
                     "K_median": tj.get("K_median"), "n_total": tj.get("n_total"),
                     "passed": ok, "s": round(time.time() - t0, 1)})
        print(f"{'PASS' if ok else 'FAIL'}  {name:38s} [{tier:6s}] → {d} "
              f"(rel={tj.get('rel_change')}, K_med={tj.get('K_median')}, "
              f"n={tj.get('n_total'):,})", flush=True)
    total = len(HOLDOUT)
    print(f"\n{passed}/{total} bestanden ({SUBSTRATE}+{PREDICTOR})")
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"substrate": SUBSTRATE, "predictor": PREDICTOR,
               "passed": passed, "total": total, "rows": rows},
              open(OUT_JSON, "w"), indent=2)
    lines = ["# TIR-Richtungs-Holdout — Ergebnis (Erwartungen vorab committet)\n",
             f"Pfad: {SUBSTRATE}+{PREDICTOR} · Ergebnis: **{passed}/{total}**\n",
             "| Technologie | Tier | Richtung | rel | K_med | n | Ergebnis |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['name']} | {r['tier']} | {r['direction']} | "
                     f"{r['rel_change']} | {r['K_median']} | {r['n_total']:,} | "
                     f"{'✅' if r['passed'] else '❌'} |")
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"→ {OUT_MD}\n→ {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
