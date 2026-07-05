#!/usr/bin/env python3
"""CPC lead-time prototype (issue #28): the four tiers on one technology axis.

For a CPC subclass (e.g. H02S photovoltaics) this overlays WHEN each lead-time
tier talked about that technology:

  science  → embedded research signals projected onto CPC (ANN vs. the embedded
             CPC definition, distance-gated)
  patent   → NATIVE CPC on the full back-file corpus (18.7M patents, to 1990 —
             no embedding needed)
  funding  → embedded funding signals, same projection
  market   → embedded trade/press signals, same projection

Output per tier: signal count, first year, takeoff year (first year with >=3
signals — robust against a lone outlier), median year, and a yearly sparkline;
plus the science→market lead-time estimate. This is THE sales claim in data
form: "research ran N years ahead of the market for this technology".

    python scripts/cpc_leadtime.py --cpc H02S
    python scripts/cpc_leadtime.py --cpc A23C --cpc G06N --threshold 0.6
"""
from __future__ import annotations

import argparse
import statistics as stats
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline.db import get_connection

BARS = " ▁▂▃▄▅▆▇█"


def sparkline(years: Counter, y0: int, y1: int) -> str:
    if not years:
        return ""
    mx = max(years.values())
    return "".join(BARS[min(8, round(8 * years.get(y, 0) / mx))] for y in range(y0, y1 + 1))


def takeoff(years: Counter, min_n: int = 3) -> int | None:
    for y in sorted(years):
        if years[y] >= min_n:
            return y
    return None


def tier_expr() -> str:
    """SQL CASE mapping a joined (r, s) row to its lead-time tier. Literal %
    is doubled — psycopg2 treats single % as a placeholder when params are given."""
    return ("CASE WHEN r.pub_number IS NOT NULL THEN 'patent' "
            "WHEN s.source_type='research' OR s.name ILIKE '%%openalex%%' "
            "  OR s.name ILIKE '%%rxiv%%' THEN 'science' "
            "WHEN s.name ILIKE '%%nsf%%' OR s.name ILIKE '%%nih%%' OR s.name ILIKE '%%openaire%%' "
            "  OR s.name ILIKE '%%ukri%%' OR s.name ILIKE '%%form d%%' THEN 'funding' "
            "ELSE 'market' END")


def projected_tier_years(cpc: str, threshold: float) -> dict[str, Counter]:
    """science/funding/market years via embedding projection onto the CPC class."""
    out: dict[str, Counter] = {"science": Counter(), "funding": Counter(), "market": Counter()}
    sql = (
        f"SELECT {tier_expr()} AS tier, substr(r.published_date::text,1,4) AS yr "
        "FROM trends t "
        "JOIN raw_entries r ON t.raw_entry_id = r.id "
        "JOIN sources s ON r.source_id = s.id "
        "WHERE t.embedding_1024 IS NOT NULL AND r.published_date IS NOT NULL "
        "  AND r.pub_number IS NULL "
        "  AND t.embedding_1024 <=> (SELECT embedding_1024 FROM cpc_definitions "
        "                            WHERE symbol = ?) < ?")
    with get_connection() as c:
        for r in c.execute(sql, (cpc, threshold)).fetchall():
            tier = r["tier"] if isinstance(r, dict) else r[0]
            yr = r["yr"] if isinstance(r, dict) else r[1]
            try:
                y = int(yr)
            except (TypeError, ValueError):
                continue
            if 1980 <= y <= 2026 and tier in out:
                out[tier][y] += 1
    return out


def patent_years(cpc: str) -> Counter:
    """Patent years from NATIVE CPC over the full back-file corpus."""
    years: Counter = Counter()
    sql = ("SELECT substr(r.published_date::text,1,4) AS yr, COUNT(*) AS n "
           "FROM patent_cpc pc JOIN raw_entries r ON r.pub_number = pc.pub_number "
           "WHERE pc.cpc LIKE ? AND r.published_date IS NOT NULL "
           "GROUP BY yr")
    with get_connection() as c:
        for r in c.execute(sql, (cpc + "%",)).fetchall():
            yr = r["yr"] if isinstance(r, dict) else r[0]
            n = r["n"] if isinstance(r, dict) else r[1]
            try:
                y = int(yr)
            except (TypeError, ValueError):
                continue
            if 1980 <= y <= 2026:
                years[y] += int(n)
    return years


def median_year(years: Counter) -> float | None:
    flat = [y for y, n in years.items() for _ in range(n)]
    return stats.median(flat) if flat else None


def report(cpc: str, threshold: float) -> None:
    with get_connection() as c:
        row = c.execute("SELECT title FROM cpc_definitions WHERE symbol = ?", (cpc,)).fetchone()
    title = (row["title"] if isinstance(row, dict) else row[0]) if row else "?"
    print(f"\n━━━━━ {cpc} — {title[:70]}")
    tiers = projected_tier_years(cpc, threshold)
    tiers["patent"] = patent_years(cpc)

    y0 = min((min(v) for v in tiers.values() if v), default=2010)
    y1 = max((max(v) for v in tiers.values() if v), default=2026)
    y0 = max(y0, 1990)

    takeoffs: dict[str, int | None] = {}
    for tier in ("science", "patent", "funding", "market"):
        ys = tiers.get(tier) or Counter()
        n = sum(ys.values())
        to = takeoff(ys)
        takeoffs[tier] = to
        med = median_year(ys)
        first = min(ys) if ys else None
        note = ""
        if tier == "funding" and n < 50:
            note = "  (dünn — tiefer Funding-Backfill noch nicht klassifiziert/embedded)"
        print(f"  {tier:8s} n={n:>7,}  first={first or '—'}  takeoff={to or '—'}  "
              f"median={f'{med:.0f}' if med else '—'}{note}")
        print(f"           {y0}–{y1}  {sparkline(ys, y0, y1)}")

    st, mt = takeoffs.get("science"), takeoffs.get("market")
    pt = takeoffs.get("patent")
    if st and mt:
        print(f"  → Lead-Time (takeoff): Science {mt - st:+d} J vor Market"
              + (f", Patente {mt - pt:+d} J vor Market" if pt else ""))
    print("  Hinweis: first/takeoff sind durch das Akquise-Fenster je Tier begrenzt "
          "(Science-Signale ab ~2009 embedded, Market ab ~2010 tief, Patente ab 1990).")


def main() -> int:
    ap = argparse.ArgumentParser(description="CPC cross-tier lead-time prototype (#28)")
    ap.add_argument("--cpc", action="append", required=True,
                    help="CPC subclass symbol (repeatable), e.g. H02S")
    ap.add_argument("--threshold", type=float, default=0.55,
                    help="max cosine distance signal↔CPC definition (default 0.55)")
    args = ap.parse_args()
    if not db_mod.USE_POSTGRES:
        print("prototype targets Postgres (pgvector)"); return 1
    print(f"CPC-Lead-Time-Prototyp — Projektions-Schwelle: Distanz < {args.threshold}")
    for cpc in args.cpc:
        report(cpc.upper(), args.threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
