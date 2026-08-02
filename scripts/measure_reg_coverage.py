#!/usr/bin/env python3
"""Misst nach, wie gut der Korpus jede Jurisdiktion beim Thema Zulassungen sieht.

Warum das eine eigene Messung braucht: `REG_COVERAGE_SHARE` in
`pipeline/radar_horizons.py` entscheidet, ob „hier ist keine Zulassung zu sehen"
als Befund ausgegeben werden darf. Steht die Zahl falsch, behauptet das Radar
entweder Blockaden, die es nicht gibt (zu hoch), oder es schweigt, wo es etwas
wüsste (zu niedrig). Die Konstante ist eine gemessene Eigenschaft des Korpus und
verschiebt sich, wenn Quellen dazukommen — deshalb nachrechenbar.

    scripts/measure_reg_coverage.py            # nur messen
    scripts/measure_reg_coverage.py --check    # gegen die Konstante prüfen (CI)

`--check` schlägt fehl, wenn eine Jurisdiktion die Schwelle
MIN_COVERAGE_FOR_ABSENCE in die andere Richtung überquert hat — nur dann ändert
sich das Verhalten des Radars tatsächlich.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from pipeline.radar_horizons import (
    MIN_COVERAGE_FOR_ABSENCE,
    REG_COVERAGE_SHARE,
    reg_authority,
    reg_subtype,
)


def measure(conn) -> tuple[dict[str, float], dict[str, int]]:
    rows = conn.execute(
        "SELECT id, title_en, summary_en, tags, regions FROM trends "
        "WHERE trend_signal_type = 'regulation'"
    ).fetchall()
    counts: dict[str, int] = {}
    unattributed = 0
    for r in rows:
        d = dict(r)
        if reg_subtype(d) != "granted":
            continue
        a = reg_authority(f"{d.get('title_en') or ''} {d.get('summary_en') or ''}")
        if a:
            counts[a] = counts.get(a, 0) + 1
        else:
            unattributed += 1
    total = sum(counts.values())
    share = {k: v / total for k, v in counts.items()} if total else {}
    counts["_unattributed"] = unattributed
    counts["_signals"] = len(rows)
    return share, counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    with get_connection() as conn:
        conn.execute("SET statement_timeout = 600000")
        share, counts = measure(conn)

    print(f"Regulatorik-Signale: {counts.pop('_signals'):,}")
    print(f"nicht zuordenbare Zulassungen: {counts.pop('_unattributed'):,}\n")
    print(f"{'Jurisdiktion':<14}{'Zulassungen':>12}{'Anteil':>9}{'hinterlegt':>12}"
          f"{'Absenz erlaubt':>16}")
    drift = []
    for k in sorted(share, key=lambda k: -share[k]):
        stored = REG_COVERAGE_SHARE.get(k)
        now_ok = share[k] >= MIN_COVERAGE_FOR_ABSENCE
        was_ok = (stored or 0.0) >= MIN_COVERAGE_FOR_ABSENCE
        print(f"{k:<14}{counts.get(k, 0):>12,}{share[k] * 100:>8.1f}%"
              f"{(f'{stored * 100:.1f}%' if stored is not None else '—'):>12}"
              f"{('ja' if now_ok else 'nein'):>16}")
        if now_ok != was_ok:
            drift.append((k, stored, share[k]))

    if args.check and drift:
        print("\nABWEICHUNG — das Radar würde sich anders verhalten:")
        for k, old, new in drift:
            print(f"  {k}: hinterlegt {old}, gemessen {new:.3f} "
                  f"(Schwelle {MIN_COVERAGE_FOR_ABSENCE})")
        print("REG_COVERAGE_SHARE in pipeline/radar_horizons.py nachziehen.")
        return 1
    if args.check:
        print("\nKeine verhaltensrelevante Abweichung.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
