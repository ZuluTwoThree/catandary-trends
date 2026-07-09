#!/usr/bin/env python3
"""Direction-validation for the TIR trajectory (issue #36) → report + pass/fail.

The acceptance criterion: the direction classifier must label known technologies
correctly — accelerating for fields that are still climbing their S-curve, and
maturing/decelerating for fields past the inflection. Honest by design: where the
patent corpus is too thin or too recent (citation-maturity horizon ~7y), the
system says "insufficient data" instead of guessing — those cases are reported,
not counted as failures.

    python scripts/tir_trajectory_validate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.tir_trajectory import trajectory

OUT = Path(__file__).parent.parent / "data" / "tir_trajectory_validation.md"

# (name, cpc LIKE patterns, expected) — expected ∈ {"up","down"}.
# up  = accelerating; down = maturing | decelerating.
KNOWN = [
    ("CRISPR / gene editing",      ["C12N15/11%"],              "up"),
    ("Plant-based dairy",          ["A23C11/%", "A23C20/%"],   "up"),
    ("Wind power",                 ["Y02E10/7%"],               "down"),
    ("Smart grid",                 ["Y04S%"],                   "down"),
    ("Solar photovoltaics",        ["Y02E10/5%"],               "down"),
    ("Cryptography",               ["H04L9/%"],                 "down"),
]

UP = {"accelerating"}
DOWN = {"maturing", "decelerating"}


def check(direction: str, expected: str) -> bool:
    return (expected == "up" and direction in UP) or (expected == "down" and direction in DOWN)


def main() -> int:
    lines = ["# TIR-Trajektorie — Richtungs-Validierung\n",
             "Bekannte Technologien; der Klassifikator muss steigend/fallend korrekt "
             "labeln. 'Zu wenig Daten' (Korpus-Tiefe/-Abdeckung) zaehlt nicht als "
             "Fehler - es ist die Ehrlichkeits-Regel.\n",
             "| Technologie | erwartet | Richtung | rel. Δ | TIR (aktuell) | Patente | ok |",
             "|---|---|---|---|---|---|---|"]
    ok = tot = 0
    insufficient = []
    for name, pats, exp in KNOWN:
        r = trajectory(pats)
        d = r["direction"]
        if d == "insufficient_data":
            insufficient.append((name, r["reason"]))
            lines.append(f"| {name} | {exp} | zu wenig Daten | — | — | "
                         f"{r['n_total']:,} | — |")
            continue
        tot += 1
        good = check(d, exp)
        ok += 1 if good else 0
        kv = f"{r['K_latest']}%/yr" if r["calibrated"] else "n/a (unkalibriert)"
        lines.append(f"| {name} | {exp} | {r['direction_de']} | {r['rel_change']:+.0%} "
                     f"| {kv} | {r['n_total']:,} | {'✅' if good else '❌'} |")

    lines.append(f"\n**Richtungs-Treffer: {ok}/{tot}** (von {len(KNOWN)} Fällen; "
                 f"{len(insufficient)} 'zu wenig Daten').\n")
    if insufficient:
        lines.append("Ehrlich zurückgehalten (zu jung/dünn im CPC-gescopten Korpus):")
        for name, reason in insufficient:
            lines.append(f"- **{name}** — {reason}")
    lines.append("\n_Hinweis: absolute TIR nur im kalibrierten Bereich (Median ≤ 50 %/yr); "
                 "Software-/KI-Domänen liegen darüber → nur Richtung. Die letzten ~7 Jahre "
                 "sind wegen unreifer Vorwärts-Zitationen ausgeschlossen (Zitations-Horizont)._")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT}")
    print(f"direction hits: {ok}/{tot}  ({len(insufficient)} insufficient-data)")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    raise SystemExit(main())
