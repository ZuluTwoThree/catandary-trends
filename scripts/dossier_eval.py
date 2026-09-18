#!/usr/bin/env python3
"""Messlatte für Dossier-Läufe (Stufe 0, docs/plan_dossier_agent_2026-09-18.md).

Rechnet den Nutzen U und alle Komponenten (pipeline/dossier_utility.py) für
gespeicherte Läufe nach — Replay über dossiers.result + dossier_orders.check_json,
kein Modell, kein Netz, keine GPU — und zeigt das Scoreboard je Serie.

    .venv/bin/python scripts/dossier_eval.py --backfill      # alle dossiers → dossier_run_outcomes (Upsert)
    .venv/bin/python scripts/dossier_eval.py --scoreboard    # eine Zeile je Lauf + Zusammenfassung
    .venv/bin/python scripts/dossier_eval.py --scoreboard --json
    .venv/bin/python scripts/dossier_eval.py --backfill --preset evidence

Ohne Schalter: --scoreboard. Voraussetzung: scripts/migrate_dossier_run_outcomes.py
einmal auf der Live-DB (der Backfill legt die Tabelle zur Not selbst an).
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import dossier_utility as du
from pipeline.db import get_connection

logger = logging.getLogger("dossier_eval")

# Die drei vom Owner abgenommenen Dossiers (Stand 18.09.2026) — der Plan
# fragt, ob sie nach U im oberen Drittel liegen. Ausgabe, kein Assert.
SIGNED_OFF_REFERENCE = (("perovskite-tandem-photovoltaics", 1),
                        ("perovskite-tandem-photovoltaics", 2),
                        ("iron-phosphate-battery", 9))


def _order_for(conn, slug: str, version: int) -> dict | None:
    row = conn.execute(
        "SELECT id, check_json, reviewed_at FROM dossier_orders"
        " WHERE slug = ? AND dossier_version = ? ORDER BY id DESC LIMIT 1",
        (slug, int(version))).fetchone()
    return dict(row) if row else None


def backfill(preset: str) -> int:
    du.ensure_schema()
    with get_connection() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, slug, version, result FROM dossiers ORDER BY id").fetchall()]
        orders = {(r["slug"], r["version"]): _order_for(conn, r["slug"], r["version"])
                  for r in rows}
    n = 0
    for r in rows:
        o = orders.get((r["slug"], r["version"])) or {}
        ev = du.evaluate(r["result"], o.get("check_json"), o.get("reviewed_at"), preset)
        du.record_outcome(r["id"], o.get("id"), r["slug"], r["version"], ev)
        n += 1
        logger.info("%s v%d: U=%.3f ready=%s reader=%s signed=%s", r["slug"],
                    r["version"], ev["utility"], ev["delivery_ready"],
                    ev["reader_answers"], ev["signed_off"])
    print(f"backfill: {n} Lauf/Läufe → dossier_run_outcomes (preset {preset})")
    return n


def _fmt(v, nd=2, pct=False):
    if v is None:
        return "—"
    return f"{v * 100:.0f}%" if pct else f"{v:.{nd}f}"


def _writer_short(m: str | None) -> str:
    if not m:
        return "—"
    m = m.replace(".gguf", "")
    if "Flash" in m:
        return "Flash-Next"
    if "27B" in m:
        return "27B"
    return m[:14]


def scoreboard(as_json: bool) -> dict:
    rows = du.list_outcomes()
    by_series: dict[str, list[dict]] = {}
    for r in rows:
        by_series.setdefault(r["slug"], []).append(r)
    ranked = sorted(rows, key=lambda r: (-(r["utility"] or 0.0), r["slug"], r["version"]))
    top_third = max(1, len(ranked) // 3) if ranked else 0
    positions = {}
    for slug, ver in SIGNED_OFF_REFERENCE:
        pos = next((i + 1 for i, r in enumerate(ranked)
                    if r["slug"] == slug and int(r["version"]) == ver), None)
        hit = ranked[pos - 1] if pos else None
        positions[f"{slug} v{ver}"] = {
            "rank": pos, "of": len(ranked),
            "top_third": (pos is not None and pos <= top_third),
            "has_structure": bool(hit and hit["components"].get("has_structure"))}
    summary = {
        "runs": len(rows),
        "delivery_ready": sum(1 for r in rows if r["delivery_ready"]),
        "with_reader": sum(1 for r in rows if r["reader_answers"] is not None),
        "reader_answers": sum(1 for r in rows if r["reader_answers"] is True),
        "signed_off": sum(1 for r in rows if r["signed_off"]),
        # Läufe vor der Strukturprüfung (07.09.) tragen kein Protokoll: U dort
        # kommt aus den Defaults (Dichte 0, Primäranteil 0 %) — eine Aussage
        # über das Gespeicherte, nicht über den Text.
        "without_structure_protocol": sum(
            1 for r in rows if not r["components"].get("has_structure")),
        "mean_utility": (round(statistics.fmean(r["utility"] for r in rows), 3)
                         if rows else None),
        "mean_utility_by_series": {
            s: round(statistics.fmean(r["utility"] for r in rs), 3)
            for s, rs in by_series.items()},
        "top_third_size": top_third,
        "signed_off_positions": positions,
    }
    if as_json:
        print(json.dumps({"runs": [
            {k: v for k, v in r.items() if k not in ("weights",)} for r in rows],
            "summary": summary}, ensure_ascii=False, indent=1, default=str))
        return summary
    hdr = (f"{'date':16} {'slug':34} {'v':>3} {'writer':10} {'U':>6} {'dens':>5} "
           f"{'prim':>5} {'reader':>6} {'ready':>5} {'signed':>6}")
    for slug, rs in sorted(by_series.items(),
                           key=lambda kv: max(str(r["dossier_created_at"]) for r in kv[1]),
                           reverse=True):
        print(f"\n== {slug}  (mean U {summary['mean_utility_by_series'][slug]:.3f}, "
              f"{len(rs)} Lauf/Läufe)")
        print(hdr)
        for r in sorted(rs, key=lambda r: int(r["version"])):
            c = r["components"]
            ra = c.get("reader_answers")
            print(f"{str(r['dossier_created_at'])[:16]:16} {slug[:34]:34} {int(r['version']):>3} "
                  f"{_writer_short(r['writer_model']):10} {r['utility']:>6.3f} "
                  f"{_fmt(c.get('density_norm')):>5} {_fmt(c.get('primary_share'), pct=True):>5} "
                  f"{('—' if ra is None else ('yes' if ra else 'no')):>6} "
                  f"{('yes' if r['delivery_ready'] else 'no'):>5} "
                  f"{('yes' if r['signed_off'] else ''):>6}"
                  f"{'' if c.get('has_structure') else '  * kein Strukturprotokoll'}")
    print("\n== Zusammenfassung")
    print(f"Läufe {summary['runs']} · abgabereif {summary['delivery_ready']} · "
          f"mit Leser {summary['with_reader']} (beantwortet {summary['reader_answers']}) · "
          f"abgenommen {summary['signed_off']} · mean U {summary['mean_utility']} · "
          f"ohne Strukturprotokoll {summary['without_structure_protocol']} (U aus Defaults)")
    for s, u in sorted(summary["mean_utility_by_series"].items(), key=lambda kv: -kv[1]):
        print(f"  {s:40} mean U {u:.3f}")
    print(f"oberes Drittel = Plätze 1–{top_third} von {len(ranked)}")
    for name, p in positions.items():
        print(f"  {name:40} Platz {p['rank']} von {p['of']} → "
              f"{'im oberen Drittel' if p['top_third'] else 'NICHT im oberen Drittel'}"
              f"{'' if p['has_structure'] else ' (kein Strukturprotokoll — U aus Defaults)'}")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backfill", action="store_true",
                    help="U für alle dossiers-Zeilen rechnen und speichern (Upsert)")
    ap.add_argument("--scoreboard", action="store_true", help="Scoreboard je Serie zeigen")
    ap.add_argument("--json", action="store_true", help="Scoreboard als JSON")
    ap.add_argument("--preset", default=du.DEFAULT_PRESET, choices=sorted(du.WEIGHT_PRESETS),
                    help=f"Gewichtssatz (Default {du.DEFAULT_PRESET})")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s",
                        stream=sys.stderr)
    if args.backfill:
        backfill(args.preset)
    if args.scoreboard or not args.backfill:
        scoreboard(args.json)
    return 0


if __name__ == "__main__":
    try:
        from pipeline.ops_events import record  # Laufprotokoll fuer /trends/ops (#104)
    except ImportError:  # Protokoll ist optional, der Lauf nicht
        from contextlib import nullcontext as record
    with record("dossier_eval"):
        raise SystemExit(main())
