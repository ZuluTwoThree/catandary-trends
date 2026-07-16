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

# (name, cpc LIKE patterns, tier). Tiers define the pass condition — a CONTROL
# GROUP, not just positive cases: a mundane mature technology must NOT falsely
# "accelerate", and a thin domain must withhold the direction. This is the #36
# follow-up acceptance gate (density-aware direction).
#   up        climbing → must be accelerating
#   down      maturing → must be maturing | decelerating
#   not_up    dense mundane → must NOT accelerate (the false-positive control)
#   uncertain thin → direction withheld (uncertain | insufficient_data)
KNOWN = [
    # --- climbing (must accelerate) ---
    ("CRISPR / gene editing",       ["C12N15/11%"],  "up"),
    ("Vaccines / immunotherapy",    ["A61K39%"],     "up"),
    ("mRNA / nucleic-acid tech",    ["C12N15%"],     "up"),
    # --- maturing (must be maturing/decelerating) ---
    ("Solar photovoltaics",         ["H02S%"],       "down"),
    ("Wind power",                  ["F03D%"],       "down"),
    # --- dense mundane (must NOT falsely accelerate) ---
    ("Screws / fasteners",          ["F16B%"],       "not_up"),
    ("Furniture",                   ["A47B%"],       "not_up"),
    ("Containers / packaging",      ["B65D%"],       "not_up"),
    # Gears/Pumps/Hand tools were "uncertain" (thin) pre-backfill; the #35 backfill +
    # gap-close (2026-07-16) lifted them to dense mundane (median recent window
    # 18k-47k), so they now belong in the not-falsely-accelerate control (the density
    # gate they used to test no longer withholds them).
    ("Gears",                       ["F16H%"],       "not_up"),
    ("Pumps",                       ["F04B%"],       "not_up"),
    ("Hand tools",                  ["B25B%"],       "not_up"),
]

UP = {"accelerating"}
DOWN = {"maturing", "decelerating"}
WITHHELD = {"uncertain", "insufficient_data"}


def check(direction: str, tier: str) -> bool:
    if tier == "up":
        return direction in UP
    if tier == "down":
        return direction in DOWN
    if tier == "not_up":            # the false-positive control
        return direction not in UP
    if tier == "uncertain":
        return direction in WITHHELD
    return False


TIER_LABEL = {
    "up": "steigend → beschleunigt",
    "down": "reifend → reift/verlangsamt",
    "not_up": "mundan-dicht → NICHT beschleunigt",
    "uncertain": "dünn → Richtung zurückgehalten",
}


def main() -> int:
    lines = ["# TIR-Trajektorie — Richtungs-Validierung (Kontrollgruppe, #36)\n",
             "Der Klassifikator muss vier Tiers korrekt behandeln — inkl. der "
             "Negativ-Kontrolle: eine mundane, reife Technologie darf **nicht** "
             "'beschleunigt' ergeben, und eine dünne Domäne muss die Richtung "
             "zurückhalten ('unsicher'/'zu wenig Daten') statt zu raten.\n",
             "| Technologie | Tier | Richtung | rel. Δ | med. Fenster-n | Patente | ok |",
             "|---|---|---|---|---|---|---|"]
    ok = tot = 0
    tier_stats: dict[str, list[int]] = {}
    for name, pats, tier in KNOWN:
        r = trajectory(pats)
        d = r["direction"]
        good = check(d, tier)
        tot += 1
        ok += 1 if good else 0
        tier_stats.setdefault(tier, [0, 0])
        tier_stats[tier][1] += 1
        tier_stats[tier][0] += 1 if good else 0
        rc = f"{r['rel_change']:+.0%}" if r.get("rel_change") is not None else "—"
        mrn = r.get("median_recent_n")
        mrn = f"{mrn:,}" if mrn is not None else "—"
        lines.append(f"| {name} | {TIER_LABEL[tier]} | {r.get('direction_de', d)} "
                     f"| {rc} | {mrn} | {r['n_total']:,} | {'✅' if good else '❌'} |")

    lines.append(f"\n**Gesamt: {ok}/{tot} Tiers-Erwartungen erfüllt.**\n")
    lines.append("Pro Tier:")
    for tier, (o, t) in tier_stats.items():
        lines.append(f"- {TIER_LABEL[tier]}: **{o}/{t}**")
    lines.append("\n_Absolute TIR nur im kalibrierten Bereich (Median ≤ 50 %/yr). Die "
                 "letzten ~7 Jahre sind wegen unreifer Vorwärts-Zitationen ausgeschlossen "
                 "(Zitations-Horizont). Richtung nur bei median Fenster-n ≥ "
                 "1000 (sonst 'unsicher'; #35-Backfill hebt dünne Domänen darüber)._")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT}")
    print(f"control-group: {ok}/{tot} tiers-expectations met")
    for tier, (o, t) in tier_stats.items():
        print(f"  {tier:10s} {o}/{t}")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    raise SystemExit(main())
