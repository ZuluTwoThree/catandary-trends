#!/usr/bin/env python3
"""Google-Trends-Validierungsebene (#4/#15, gefaltet): Nachfrage vs. SoV-Momentum.

Bewusst KEIN raw_entries-Ingest — pytrends ist eine inoffizielle API und dient
nur als Batch-Kreuzvalidierung: stimmt die öffentliche Suchnachfrage mit dem
gemessenen Share-of-Voice-Momentum unserer Top-Cluster überein? Ergebnis ist
ein Report unter data/ (+ stdout-Tabelle); die Methodik-Seite nennt Google
Trends als Validierungs-, nicht als Signalquelle.

Regeln:
  - Top-N Cluster nach Größe aus foresight_clusters (Label-Kopf als Suchbegriff)
  - Interest-over-Time 12 Monate; Nachfrage-Trend = Mittel der letzten 90 Tage
    vs. Mittel der 90 davor (±15 % — dieselbe Schwelle wie das Momentum-Badge)
  - 10 s Pause je Query, Abbruch-tolerant (429 → Begriff wird übersprungen und
    im Report als 'rate-limited' geführt; pytrends nie im Request-Pfad)

    python scripts/validate_demand.py                 # Top 12
    python scripts/validate_demand.py --top 6 --sleep 12
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection

THRESHOLD = 0.15  # wie frontend/src/lib/momentum.ts / pipeline/mega_momentum.py


def demand_trend(series) -> tuple[str, float]:
    """rising/stable/declining aus einer wöchentlichen Interest-Serie (52 Punkte)."""
    vals = [float(v) for v in series if v is not None]
    if len(vals) < 26:
        return "unknown", 0.0
    recent, prior = vals[-13:], vals[-26:-13]  # 13 Wochen ≈ 90 Tage
    m_r = sum(recent) / len(recent)
    m_p = sum(prior) / len(prior)
    if m_p == 0:
        return ("rising" if m_r > 0 else "unknown"), 0.0
    ch = (m_r - m_p) / m_p
    if ch > THRESHOLD:
        return "rising", ch
    if ch < -THRESHOLD:
        return "declining", ch
    return "stable", ch


def main() -> int:
    ap = argparse.ArgumentParser(description="Google-Trends-Kreuzvalidierung der Cluster-Momenta")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--sleep", type=float, default=10.0)
    ap.add_argument("--geo", default="", help="'' = weltweit")
    args = ap.parse_args()

    with get_connection() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT label, momentum, sov_delta_pp, size FROM foresight_clusters "
            "WHERE momentum IN ('rising','declining','stable') "
            "ORDER BY size DESC LIMIT ?", (args.top,)).fetchall()]
    if not rows:
        print("keine foresight_clusters gefunden")
        return 1

    from pytrends.request import TrendReq
    pt = TrendReq(hl="en-US", tz=0)

    results = []
    for r in rows:
        kw = r["label"].split("·")[0].strip()
        try:
            pt.build_payload([kw], timeframe="today 12-m", geo=args.geo)
            df = pt.interest_over_time()
            if df is None or df.empty:
                results.append({**r, "kw": kw, "demand": "no-data", "change": 0.0})
            else:
                trend, ch = demand_trend(df[kw].tolist())
                results.append({**r, "kw": kw, "demand": trend, "change": ch})
        except Exception as exc:  # noqa: BLE001 — 429 etc. tolerieren
            results.append({**r, "kw": kw, "demand": f"rate-limited ({type(exc).__name__})",
                            "change": 0.0})
        time.sleep(args.sleep)

    ok = sum(1 for x in results if x["demand"] == x["momentum"])
    judged = sum(1 for x in results if x["demand"] in ("rising", "stable", "declining"))
    lines = [
        "# Nachfrage-Validierung (Google Trends vs. SoV-Momentum)",
        "",
        f"Lauf {date.today().isoformat()} · Top {len(results)} Cluster · "
        f"Übereinstimmung {ok}/{judged} der bewertbaren",
        "",
        f"| Cluster | Suchbegriff | SoV-Momentum (Δpp) | Nachfrage (Δ) |",
        f"|---|---|---|---|",
    ]
    for x in results:
        agree = "✓" if x["demand"] == x["momentum"] else ("·" if x["demand"] not in
                ("rising", "stable", "declining") else "✗")
        lines.append(f"| {x['label'][:42]} | {x['kw']} | {x['momentum']} "
                     f"({x['sov_delta_pp']:+.1f}) | {x['demand']} "
                     f"({x['change']:+.0%}) {agree} |")
    report = "\n".join(lines)
    print(report)
    out = Path("data") / f"demand_validation_{date.today().isoformat()}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report + "\n", encoding="utf-8")
    print(f"\n→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
