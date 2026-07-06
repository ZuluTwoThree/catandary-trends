#!/usr/bin/env python3
"""Ad-hoc technology query: free text → TIR + market lead time (issue #28).

The curated Technology Explorer covers ~23 CPC subclasses. This answers the
same questions for ANY search phrase — "recombinant food protein for
cheesemaking", "solid-state electrolyte", "mRNA vaccine manufacturing" — the
Super Pro+ / on-demand scope: embed the query, project it onto the four
lead-time tiers by embedding similarity (per-tier takeoff years → lead time),
and read TIR/cycle-time off the nearest CPC technology class.

    python scripts/tech_query.py "recombinant food protein for cheesemaking"
    python scripts/tech_query.py "solid-state battery electrolyte" --threshold 0.6
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod, gpu_handover, llamacpp_client
from pipeline.config import EMBED_MODEL
from pipeline.db import get_connection
from scripts.cpc_leadtime import median_year, sparkline, tier_expr

BARS_Y0, BARS_Y1 = 1990, 2026


def ramp_takeoff(years: Counter, frac: float = 0.15) -> int | None:
    """First year the activity reaches `frac` of its peak year — the real ramp
    start. More honest than 'first year with >=3' for a niche query, where a
    handful of old tangential matches would otherwise drag the takeoff decades
    back and inflate the lead time."""
    if not years:
        return None
    peak = max(years.values())
    for y in sorted(years):
        if years[y] >= max(3, frac * peak):
            return y
    return None


def embed_query(text: str) -> list[float]:
    with gpu_handover.embed_on_llamacpp(EMBED_MODEL):
        emb = llamacpp_client.generate_embedding(text, model=EMBED_MODEL)
    if not emb:
        raise SystemExit("embedding failed")
    return list(emb)[:1024]


def tier_years_for_vec(vec1024: list[float], threshold: float) -> dict[str, Counter]:
    """science/funding/market year histograms for signals within `threshold`
    cosine distance of the query vector (patents are added separately, native)."""
    out: dict[str, Counter] = {"science": Counter(), "funding": Counter(), "market": Counter()}
    vlit = "[" + ",".join(f"{x:.6f}" for x in vec1024) + "]"
    sql = (f"SELECT {tier_expr()} AS tier, substr(r.published_date::text,1,4) AS yr "
           "FROM trends t JOIN raw_entries r ON t.raw_entry_id=r.id "
           "JOIN sources s ON r.source_id=s.id "
           "WHERE t.embedding_1024 IS NOT NULL AND r.published_date IS NOT NULL "
           "AND r.pub_number IS NULL "
           f"AND t.embedding_1024 <=> '{vlit}'::vector < ?")
    with get_connection() as c:
        for r in c.execute(sql, (threshold,)).fetchall():
            tier = r["tier"] if isinstance(r, dict) else r[0]
            yr = r["yr"] if isinstance(r, dict) else r[1]
            try:
                y = int(yr)
            except (TypeError, ValueError):
                continue
            if BARS_Y0 <= y <= BARS_Y1 and tier in out:
                out[tier][y] += 1
    return out


def nearest_cpcs(vec1024: list[float], k: int = 3) -> list[dict]:
    """Nearest CPC subclasses (by embedded definition) → carry their TIR."""
    vlit = "[" + ",".join(f"{x:.6f}" for x in vec1024) + "]"
    rows_out = []
    with get_connection() as c:
        rows = c.execute(
            "SELECT d.symbol, d.title, d.vertical, "
            f"       (d.embedding_1024 <=> '{vlit}'::vector) AS dist, "
            "       i.name AS tech_name, i.payload AS payload "
            "FROM cpc_definitions d "
            "LEFT JOIN cpc_insights i ON i.symbol = d.symbol "
            "WHERE d.embedding_1024 IS NOT NULL "
            f"ORDER BY d.embedding_1024 <=> '{vlit}'::vector LIMIT {k}").fetchall()
        for r in rows:
            r = dict(r)
            pd = (r.get("payload") or {}).get("patent_dynamics", {}) if r.get("payload") else {}
            rows_out.append({
                "symbol": r["symbol"], "title": (r["title"] or "").split("(")[0].strip(),
                "vertical": r["vertical"], "dist": round(float(r["dist"]), 3),
                "tir_pct": pd.get("tir_pct"), "cycle": pd.get("cycle_time_years"),
                "curated": r.get("tech_name")})
    return rows_out


def patent_years_for_cpc(cpc: str) -> Counter:
    years: Counter = Counter()
    with get_connection() as c:
        for r in c.execute(
                "SELECT substr(r.published_date::text,1,4) AS yr, COUNT(*) AS n "
                "FROM patent_cpc pc JOIN raw_entries r ON r.pub_number=pc.pub_number "
                "WHERE substr(pc.cpc,1,4)=? AND r.published_date IS NOT NULL GROUP BY yr",
                (cpc,)).fetchall():
            yr = r["yr"] if isinstance(r, dict) else r[0]
            n = r["n"] if isinstance(r, dict) else r[1]
            try:
                y = int(yr)
            except (TypeError, ValueError):
                continue
            if BARS_Y0 <= y <= BARS_Y1:
                years[y] += int(n)
    return years


def compute(query: str, threshold: float) -> dict:
    """Structured result: nearest CPCs, per-tier year series + ramp takeoff,
    and the derived TIR / lead-time findings."""
    vec = embed_query(query)
    cpcs = nearest_cpcs(vec, k=12)
    tiers = tier_years_for_vec(vec, threshold)
    tiers["patent"] = patent_years_for_cpc(cpcs[0]["symbol"]) if cpcs else Counter()

    tier_out: dict[str, dict] = {}
    takeoffs: dict[str, int | None] = {}
    for tier in ("science", "patent", "funding", "market"):
        ys = tiers.get(tier) or Counter()
        to = ramp_takeoff(ys)
        takeoffs[tier] = to
        med = median_year(ys)
        tier_out[tier] = {
            "n": sum(ys.values()), "first": min(ys) if ys else None,
            "takeoff": to, "median": round(med) if med else None,
            "series": {str(y): int(n) for y, n in sorted(ys.items())},
        }

    sci, mkt, pat = takeoffs["science"], takeoffs["market"], takeoffs["patent"]
    # TIR is precomputed only for the curated classes; use the NEAREST modeled
    # class (first hit carrying a tir_pct), and flag when it isn't the very
    # nearest so the UI can say "via <class>".
    tir_src = next((c for c in cpcs if c.get("tir_pct") is not None), None)
    return {
        "query": query, "threshold": threshold,
        "nearest_cpcs": cpcs[:6], "tiers": tier_out,
        "tir_pct": tir_src["tir_pct"] if tir_src else None,
        "tir_cpc": tir_src["symbol"] if tir_src else None,
        "tir_via": (tir_src["curated"] or tir_src["symbol"]) if tir_src else None,
        "tir_is_nearest": bool(tir_src and cpcs and tir_src["symbol"] == cpcs[0]["symbol"]),
        "cycle_time_years": tir_src["cycle"] if tir_src else None,
        "lead_science_market": (mkt - sci) if (sci and mkt and mkt >= 2003) else None,
        "lead_patent_market": (mkt - pat) if (pat and mkt and mkt >= 2003) else None,
        "market_floored": bool(mkt and mkt < 2003),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Ad-hoc technology TIR + lead-time query (#28)")
    ap.add_argument("query", help="free-text technology phrase")
    ap.add_argument("--threshold", type=float, default=0.60,
                    help="max cosine distance signal↔query (default 0.60)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()
    if not db_mod.USE_POSTGRES:
        print("targets Postgres (pgvector)"); return 1

    res = compute(args.query, args.threshold)
    if args.json:
        import json
        print(json.dumps(res))
        return 0

    print(f"\n━━━━━ Query: \"{args.query}\"  (threshold {args.threshold})")
    print("\nNearest technology classes (CPC):")
    for c in res["nearest_cpcs"]:
        tir = f"TIR ≈ {c['tir_pct']}%/yr" if c["tir_pct"] else "TIR n/a"
        print(f"  {c['symbol']} · {c['vertical']:9s} d={c['dist']}  {c['title'][:52]}  [{tir}]")
    print("\nLead-time tiers (signals matching the query):")
    for tier in ("science", "patent", "funding", "market"):
        t = res["tiers"][tier]
        ys = Counter({int(y): n for y, n in t["series"].items()})
        print(f"  {tier:8s} n={t['n']:>8,}  first={t['first'] or '—'}  "
              f"takeoff={t['takeoff'] or '—'}  median={t['median'] or '—'}")
        print(f"           {BARS_Y0}–{BARS_Y1}  {sparkline(ys, BARS_Y0, BARS_Y1)}")
    print("\nFindings:")
    if res["tir_pct"]:
        print(f"  • Predicted TIR ≈ {res['tir_pct']} %/yr "
              f"(cycle {res['cycle_time_years']}y, via {res['tir_cpc']})")
    if res["lead_science_market"]:
        print(f"  • Research ran ~{res['lead_science_market']}+ years ahead of market")
    elif res["market_floored"]:
        print("  • Market coverage near the corpus floor; lead-time is a lower bound only")
    if res["lead_patent_market"]:
        print(f"  • Patents ran ~{res['lead_patent_market']}+ years ahead of market")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
