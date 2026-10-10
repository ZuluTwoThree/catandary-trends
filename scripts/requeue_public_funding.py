#!/usr/bin/env python3
"""Öffentliche Förderung nachholen (Owner 2026-10-10: „was von öffentlicher Hand gefördert wird, ist
ein Trendsignal — nicht verwerfen“).

1. Einträge der öffentlichen Förder-FEEDS (`tiers.is_public_funding`, ohne die Register mit
   source_type 'api'), die der Relevanzfilter verworfen hat
   (`filter_reason` 'not_relevant…'), wieder einreihen: processed/filtered_out = FALSE,
   filter_reason = 'requeued:<alt>' (nichts gelöscht). Der nächste Nachtlauf (Phase 1, Backlog)
   verarbeitet sie; seit dem Merge vom 10.10. ohne Relevanzfilter.
2. Vorhandene Trends dieser Quellen ohne Signaltyp 'funding' auf 'funding' setzen — damit zählen sie
   überall zur Ebene Förderung (wenige hundert Zeilen, eine Transaktion).

    python scripts/requeue_public_funding.py            # Probelauf: nur zählen
    python scripts/requeue_public_funding.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.db import get_connection  # noqa: E402
from pipeline.tiers import is_public_funding  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--since", default="2026-01-01", help="nur Einträge ab diesem Abrufdatum")
    a = ap.parse_args()
    with get_connection() as conn:
        srcs = [dict(r) for r in conn.execute("SELECT id, name, source_type FROM sources").fetchall()]
        # Nur die Förder-FEEDS (Förderinfo Bund, Förderdatenbank) — die Register (NIH, NSF, CORDIS …,
        # source_type 'api') laufen über den Signalpfad mit eigenen Regeln (signal_rules, 02.10.) und
        # zählen über ihren Namen schon zur Ebene Förderung. Sie hier einzureihen, ließe den Nachtlauf
        # Artikel aus Förderzeilen schreiben; ihren Signaltyp zu ändern, wäre eine Massenänderung auf
        # trends (173.101 Zeilen im Probelauf vom 10.10.).
        ids = [s["id"] for s in srcs if is_public_funding(s["name"]) and s["source_type"] != "api"]
        names = {s["id"]: s["name"] for s in srcs if s["id"] in ids}
        drop = conn.execute(
            "SELECT id, source_id, filter_reason FROM raw_entries WHERE source_id = ANY(?) AND filtered_out "
            "AND filter_reason LIKE ? AND fetched_at >= ?", (ids, "not_relevant%", a.since)).fetchall()
        relabel = conn.execute(
            "SELECT t.id FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id WHERE r.source_id = ANY(?) "
            "AND COALESCE(t.trend_signal_type, '') <> 'funding'", (ids,)).fetchall()
        by_src: dict[str, int] = {}
        for r in drop:
            by_src[names[r["source_id"]]] = by_src.get(names[r["source_id"]], 0) + 1
        print(f"öffentliche Förderquellen: {len(ids)}")
        print(f"wieder einreihen (vom Relevanzfilter verworfen, ab {a.since}): {len(drop)}")
        for n, c in sorted(by_src.items(), key=lambda kv: -kv[1]):
            print(f"   {c:5d}  {n}")
        print(f"Signaltyp → funding: {len(relabel)} Trends")
        if not a.apply:
            print("Probelauf — nichts geschrieben (--apply schreibt).")
            return 0
        for r in drop:
            conn.execute("UPDATE raw_entries SET processed = FALSE, filtered_out = FALSE, "
                         "filter_reason = ? WHERE id = ?", (f"requeued:{r['filter_reason']}"[:200], r["id"]))
        if relabel:
            conn.execute("UPDATE trends SET trend_signal_type = 'funding' WHERE id = ANY(?)",
                         ([r["id"] for r in relabel],))
        conn.commit()
        print("geschrieben.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
