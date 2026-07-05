#!/usr/bin/env python3
"""Precompute per-technology foresight insights for the frontend (issue #3/#28).

For a curated set of CPC subclasses (~3 per vertical) this persists one JSON
payload per technology into `cpc_insights`:

  • lead-time chain    — per-tier yearly series + takeoff/median (cpc_leadtime)
  • patent dynamics    — domain cycle time, immediate importance, hub patent
                         (scoped SQL on the citation graph; never full-graph)
  • convergence        — top co-occurring CPC partners with recent-share trend

The frontend (`/trends/foresight/technology`) only reads these snapshots —
finished default views, no on-demand computation (owner UX directive).

    python scripts/build_cpc_insights.py                 # all curated
    python scripts/build_cpc_insights.py --cpc H02S      # one
"""
from __future__ import annotations

import argparse
import json
import statistics as stats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection
from scripts.cpc_leadtime import (median_year, patent_years, projected_tier_years,
                                  takeoff)

# Curated technology axes: (cpc, display name, vertical). Klartext names — the
# frontend shows these, not the CPC legalese.
CURATED: list[tuple[str, str, str]] = [
    ("G06N", "Artificial Intelligence & Machine Learning", "TECH"),
    ("B25J", "Robotics", "TECH"),
    ("G16Y", "Internet of Things", "TECH"),
    ("G06Q", "Digital Business Models & Fintech", "BIZ"),
    ("H04W", "Wireless Networks & 5G/6G", "TECH"),
    ("H02S", "Solar Photovoltaics", "ECO"),
    ("H01M", "Batteries & Energy Storage", "ECO"),
    ("C25B", "Electrolysis & Green Hydrogen", "ECO"),
    ("F03D", "Wind Power", "ECO"),
    ("B09B", "Recycling & Circular Economy", "ECO"),
    ("A61K", "Pharmaceuticals & Active Compounds", "HEALTH"),
    ("C12N", "Genetic Engineering & Cell Biology", "HEALTH"),
    ("G16H", "Digital Health", "HEALTH"),
    ("A61B", "Diagnostics & Medical Devices", "HEALTH"),
    ("A23L", "Functional Foods", "FOOD"),
    ("A23C", "Dairy & Dairy Alternatives", "FOOD"),
    ("A01H", "Plant Breeding & New Varieties", "FOOD"),
    ("A23J", "Alternative Proteins", "FOOD"),
    ("B33Y", "Additive Manufacturing (3D Printing)", "DESIGN"),
    ("E04B", "Construction & Modular Building", "DESIGN"),
    ("D01F", "High-Tech Fibers & Materials", "FASHION"),
    ("A63F", "Gaming & Interactive Media", "LIFESTYLE"),
    ("G09B", "EdTech & Learning Systems", "LIFESTYLE"),
]

LEADTIME_THRESHOLD = 0.55


def migrate() -> None:
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cpc_insights ("
            " symbol TEXT PRIMARY KEY, name TEXT, vertical TEXT,"
            " payload JSONB, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")


def _counter_to_series(years: dict) -> dict[str, int]:
    return {str(y): int(n) for y, n in sorted(years.items())}


def tier_year_totals() -> dict[str, dict[int, int]]:
    """Denominator for share-of-tier normalization: total signals per tier per
    year across the WHOLE corpus. Dividing a technology's per-year counts by
    these removes the acquisition-density artifact (the 2020 RSS-onset cliff) —
    a steady 2%-of-research technology then reads flat, not as a 2020 jump."""
    totals: dict[str, dict[int, int]] = {"science": {}, "funding": {}, "market": {}, "patent": {}}
    with get_connection() as c:
        # embedded non-patent tiers
        for r in c.execute(
                "SELECT CASE WHEN s.source_type='research' OR s.name ILIKE '%%openalex%%' "
                "            OR s.name ILIKE '%%rxiv%%' THEN 'science' "
                "       WHEN s.name ILIKE '%%nsf%%' OR s.name ILIKE '%%nih%%' "
                "            OR s.name ILIKE '%%openaire%%' OR s.name ILIKE '%%ukri%%' "
                "            OR s.name ILIKE '%%form d%%' THEN 'funding' "
                "       ELSE 'market' END AS tier, "
                "       substr(r.published_date::text,1,4) AS yr, COUNT(*) AS n "
                "FROM trends t JOIN raw_entries r ON t.raw_entry_id=r.id "
                "JOIN sources s ON r.source_id=s.id "
                "WHERE t.embedding_1024 IS NOT NULL AND r.published_date IS NOT NULL "
                "  AND r.pub_number IS NULL GROUP BY tier, yr").fetchall():
            tier = r["tier"] if isinstance(r, dict) else r[0]
            yr, n = (r["yr"], r["n"]) if isinstance(r, dict) else (r[1], r[2])
            try:
                totals[tier][int(yr)] = int(n)
            except (TypeError, ValueError):
                pass
        # patents: native corpus totals per year
        for r in c.execute(
                "SELECT substr(published_date::text,1,4) AS yr, COUNT(*) AS n "
                "FROM raw_entries WHERE pub_number IS NOT NULL "
                "AND published_date IS NOT NULL GROUP BY yr").fetchall():
            yr, n = (r["yr"], r["n"]) if isinstance(r, dict) else (r[0], r[1])
            try:
                totals["patent"][int(yr)] = int(n)
            except (TypeError, ValueError):
                pass
    return totals


def _share_series(years: dict, tier_totals: dict[int, int]) -> dict[str, float]:
    """Per-year share of the tier (parts per 10,000, rounded) — bounded, compact,
    and comparable across tiers whose absolute volumes differ by 10^4."""
    out: dict[str, float] = {}
    for y, n in sorted(years.items()):
        tot = tier_totals.get(y, 0)
        if tot >= 30:  # tiny denominators (pre-coverage years) are noise — skip
            out[str(y)] = round(10000 * n / tot, 1)
    return out


def patent_dynamics(cpc: str) -> dict:
    """Domain-level citation-graph metrics, computed in SQL (scoped — the
    112M-edge graph never enters RAM)."""
    out: dict = {}
    with get_connection() as c:
        # hub patent: most-cited patent WITHIN the domain (forward citations)
        r = c.execute(
            "SELECT pl.dst_pub AS pub, COUNT(*) AS n, MIN(re.title) AS title "
            "FROM patent_links pl "
            "JOIN patent_cpc pc ON pc.pub_number = pl.dst_pub AND substr(pc.cpc,1,4) = ? "
            "LEFT JOIN raw_entries re ON re.pub_number = pl.dst_pub "
            "WHERE pl.link_type = 'cites' "
            "GROUP BY pl.dst_pub ORDER BY n DESC LIMIT 1", (cpc,)).fetchone()
        if r:
            out["hub"] = {"pub": r["pub"] if isinstance(r, dict) else r[0],
                          "cites": int(r["n"] if isinstance(r, dict) else r[1]),
                          "title": (r["title"] if isinstance(r, dict) else r[2]) or ""}
        # cycle time: median backward-citation age over a domain sample
        rows = c.execute(
            "SELECT substr(rs.published_date::text,1,4)::int - "
            "       substr(rd.published_date::text,1,4)::int AS age "
            "FROM (SELECT DISTINCT pub_number FROM patent_cpc "
            "      WHERE substr(cpc,1,4) = ? LIMIT 30000) dom "
            "JOIN patent_links pl ON pl.src_pub = dom.pub_number AND pl.link_type='cites' "
            "JOIN raw_entries rs ON rs.pub_number = pl.src_pub "
            "JOIN raw_entries rd ON rd.pub_number = pl.dst_pub "
            "WHERE rs.published_date IS NOT NULL AND rd.published_date IS NOT NULL",
            (cpc,)).fetchall()
        ages = [(r["age"] if isinstance(r, dict) else r[0]) for r in rows]
        ages = [a for a in ages if a is not None and 0 <= a <= 60]
        if len(ages) >= 50:
            out["cycle_time_years"] = round(stats.median(ages), 1)
            out["cycle_cov"] = len(ages)
    return out


def convergence(cpc: str, limit: int = 8) -> list[dict]:
    """Top co-occurring partner subclasses with a growth-share signal:
    partner's share of the pair total in 2020+ vs. its overall share."""
    out: list[dict] = []
    with get_connection() as c:
        rows = c.execute(
            "SELECT CASE WHEN cpc_a = ? THEN cpc_b ELSE cpc_a END AS partner, "
            "       SUM(n) AS total, SUM(n) FILTER (WHERE year >= 2020) AS recent "
            "FROM cpc_cooccurrence WHERE cpc_a = ? OR cpc_b = ? "
            "GROUP BY partner ORDER BY total DESC LIMIT ?",
            (cpc, cpc, cpc, limit)).fetchall()
        for r in rows:
            p = r["partner"] if isinstance(r, dict) else r[0]
            total = int(r["total"] if isinstance(r, dict) else r[1])
            recent = int((r["recent"] if isinstance(r, dict) else r[2]) or 0)
            t = c.execute("SELECT title FROM cpc_definitions WHERE symbol = ?", (p,)).fetchone()
            title = ((t["title"] if isinstance(t, dict) else t[0]) if t else "").split("(")[0].strip()
            out.append({"cpc": p, "title": title[:80], "total": total,
                        "recent_share": round(recent / total, 2) if total else 0})
    return out


def build_one(cpc: str, name: str, vertical: str, totals: dict[str, dict[int, int]]) -> dict:
    t0 = time.time()
    tiers = projected_tier_years(cpc, LEADTIME_THRESHOLD)
    tiers["patent"] = patent_years(cpc)
    lead: dict = {}
    for tier, years in tiers.items():
        n = sum(years.values())
        lead[tier] = {"n": n, "first": min(years) if years else None,
                      "takeoff": takeoff(years),
                      "median": (round(median_year(years)) if years else None),
                      "series": _counter_to_series(years),
                      "share_series": _share_series(years, totals.get(tier, {}))}
    sci_to, mkt_to = lead["science"]["takeoff"], lead["market"]["takeoff"]
    pat_to = lead["patent"]["takeoff"]
    payload = {
        "lead_time": lead,
        "lead_years_science_vs_market": (mkt_to - sci_to) if sci_to and mkt_to else None,
        "lead_years_patent_vs_market": (mkt_to - pat_to) if pat_to and mkt_to else None,
        "patent_dynamics": patent_dynamics(cpc),
        "convergence": convergence(cpc),
        "built_in_s": round(time.time() - t0, 1),
    }
    with get_connection() as conn:
        cur = conn._conn.cursor()
        cur.execute(
            "INSERT INTO cpc_insights (symbol, name, vertical, payload, updated_at) "
            "VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP) "
            "ON CONFLICT (symbol) DO UPDATE SET name=EXCLUDED.name, "
            "vertical=EXCLUDED.vertical, payload=EXCLUDED.payload, "
            "updated_at=CURRENT_TIMESTAMP",
            (cpc, name, vertical, json.dumps(payload)))
        conn._conn.commit()
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Precompute cpc_insights (#3/#28)")
    ap.add_argument("--cpc", help="single subclass (must be in the curated list)")
    ap.add_argument("--names-only", action="store_true",
                    help="update name/vertical from the curated list without recomputing")
    args = ap.parse_args()
    if not USE_POSTGRES:
        print("cpc_insights targets Postgres"); return 1
    migrate()
    todo = [t for t in CURATED if not args.cpc or t[0] == args.cpc.upper()]
    if not todo:
        print(f"{args.cpc} not in curated list"); return 1
    if args.names_only:
        with get_connection() as conn:
            for cpc, name, vertical in todo:
                conn.execute("UPDATE cpc_insights SET name = ?, vertical = ? WHERE symbol = ?",
                             (name, vertical, cpc))
        print(f"names refreshed for {len(todo)} technologies."); return 0
    totals = tier_year_totals()
    print(f"tier-year totals loaded (science yrs={len(totals['science'])}, "
          f"market yrs={len(totals['market'])})")
    for cpc, name, vertical in todo:
        p = build_one(cpc, name, vertical, totals)
        lt = p["lead_years_science_vs_market"]
        print(f"  {cpc} {name[:40]:42s} patents={p['lead_time']['patent']['n']:>9,} "
              f"lead(sci→mkt)={lt if lt is not None else '—'} "
              f"cycle={p['patent_dynamics'].get('cycle_time_years','—')}J "
              f"({p['built_in_s']}s)")
    print(f"\n{len(todo)} technologies persisted to cpc_insights.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
