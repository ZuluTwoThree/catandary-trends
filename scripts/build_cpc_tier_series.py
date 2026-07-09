#!/usr/bin/env python3
"""Materialize the cross-tier fusion (#9, on the #28 CPC backbone).

Builds two tables that put all four lead-time tiers on the shared CPC axis,
for EVERY CPC subclass (not just the ~23 curated Explorer axes):

  cpc_tier_series   one row per (cpc, tier, year): how many signals of that
                    tier talked about that technology in that year.
                    - science/funding/market: from the materialized signal_cpc
                      projection (confident matches, dist < 0.55), tier derived
                      from the source; retracted OpenAlex works excluded where
                      mappable (is_retracted negative signal, #9)
                    - patent: NATIVE CPC over the 18.7M back-file (no embedding)

  cpc_leadtime_summary   one row per cpc: per-tier n + takeoff year (first year
                    with >= 3 signals) and the science→market / patent→market
                    lead-time in years — THE dataset behind the lead-time claim.

Full rebuild each run (idempotent). GPU-free, pure SQL + a small Python pass.

    python scripts/build_cpc_tier_series.py            # build both tables
    python scripts/build_cpc_tier_series.py --summary  # only recompute summary
    python scripts/build_cpc_tier_series.py --show A23C G06N
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection

# Same gates as the rest of the CPC layer (assign_cpc / cpc_leadtime).
CONFIDENT_DIST = 0.55
YEAR_MIN, YEAR_MAX = 1980, 2026
TAKEOFF_MIN_N = 3

# Tier routing (mirrors cpc_leadtime.tier_expr, but with lower()+LIKE so the
# expression is backend-portable). Patent tier never goes through this: it is
# keyed on r.pub_number and uses native CPC. Literal % is doubled — psycopg2
# treats single % as a placeholder under the ?→%s wrapper (same trap as
# cpc_leadtime.tier_expr / train_distill_heads).
TIER_CASE = (
    "CASE WHEN s.source_type='research' OR lower(s.name) LIKE '%%openalex%%' "
    "  OR lower(s.name) LIKE '%%rxiv%%' THEN 'science' "
    "WHEN lower(s.name) LIKE '%%nsf%%' OR lower(s.name) LIKE '%%nih%%' "
    "  OR lower(s.name) LIKE '%%openaire%%' OR lower(s.name) LIKE '%%ukri%%' "
    "  OR lower(s.name) LIKE '%%form d%%' THEN 'funding' "
    "ELSE 'market' END"
)


def migrate() -> None:
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cpc_tier_series ("
            " cpc TEXT NOT NULL, tier TEXT NOT NULL, year INTEGER NOT NULL,"
            " n INTEGER NOT NULL, PRIMARY KEY (cpc, tier, year))")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cts_cpc ON cpc_tier_series (cpc)")
        # Per-tier per-year TOTAL (distinct entities that carry ANY confident CPC)
        # — the SoV denominator, so a tier's overall corpus growth / acquisition
        # window is normalized out (#2: "SoV statt Roh-Counts").
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cpc_tier_totals ("
            " tier TEXT NOT NULL, year INTEGER NOT NULL, total INTEGER NOT NULL,"
            " PRIMARY KEY (tier, year))")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cpc_leadtime_summary ("
            " cpc TEXT PRIMARY KEY,"
            " science_n INTEGER, patent_n INTEGER, funding_n INTEGER, market_n INTEGER,"
            " science_takeoff INTEGER, patent_takeoff INTEGER,"
            " funding_takeoff INTEGER, market_takeoff INTEGER,"
            " lead_science_vs_market INTEGER, lead_patent_vs_market INTEGER,"
            " reliable INTEGER DEFAULT 0,"          # 1 = SoV rise sits inside the support window
            " window_start INTEGER, window_end INTEGER,"
            " updated_at TEXT)")


def build_series() -> None:
    t0 = time.time()
    with get_connection() as conn:
        conn.execute("DELETE FROM cpc_tier_series")
        # --- science / funding / market: embedding projection (signal_cpc) ---
        # Retracted OpenAlex works are a negative signal (#9): exclude them where
        # the raw entry is mappable to a work (openalex.org/W… canonical URLs).
        print("building science/funding/market from signal_cpc …", flush=True)
        conn.execute(
            "INSERT INTO cpc_tier_series (cpc, tier, year, n) "
            f"SELECT sc.cpc, {TIER_CASE} AS tier, "
            "       substr(r.published_date::text, 1, 4)::int AS year, COUNT(*) AS n "
            "FROM signal_cpc sc "
            "JOIN trends t ON t.id = sc.trend_id "
            "JOIN raw_entries r ON r.id = t.raw_entry_id "
            "JOIN sources s ON s.id = r.source_id "
            f"WHERE sc.dist < {CONFIDENT_DIST} AND r.pub_number IS NULL "
            "  AND r.published_date IS NOT NULL "
            f"  AND substr(r.published_date::text, 1, 4)::int BETWEEN {YEAR_MIN} AND {YEAR_MAX} "
            "  AND NOT EXISTS (SELECT 1 FROM openalex_meta m WHERE m.is_retracted = 1 "
            "                  AND r.url = 'https://openalex.org/' || m.work_id) "
            "GROUP BY sc.cpc, tier, year")
        print(f"  done in {time.time() - t0:.0f}s", flush=True)

        # --- patent: native CPC over the full back-file ---
        t1 = time.time()
        print("building patent tier from native CPC (131.7M rows — takes a while) …",
              flush=True)
        conn.execute(
            "INSERT INTO cpc_tier_series (cpc, tier, year, n) "
            "SELECT pc.subclass, 'patent', "
            "       substr(r.published_date::text, 1, 4)::int AS year, "
            "       COUNT(DISTINCT pc.pub_number) AS n "
            "FROM patent_cpc pc "
            "JOIN raw_entries r ON r.pub_number = pc.pub_number "
            "WHERE r.published_date IS NOT NULL AND pc.subclass IS NOT NULL "
            f"  AND substr(r.published_date::text, 1, 4)::int BETWEEN {YEAR_MIN} AND {YEAR_MAX} "
            "GROUP BY pc.subclass, year "
            "ON CONFLICT (cpc, tier, year) DO NOTHING")
        print(f"  done in {time.time() - t1:.0f}s", flush=True)
        build_totals(conn)


def build_totals(conn) -> None:
    """SoV denominators: distinct entities per tier/year that carry any confident
    CPC. Patent total = distinct patents with a pub-year (native CPC universe)."""
    t0 = time.time()
    print("building cpc_tier_totals (SoV denominators) …", flush=True)
    conn.execute("DELETE FROM cpc_tier_totals")
    conn.execute(
        "INSERT INTO cpc_tier_totals (tier, year, total) "
        f"SELECT {TIER_CASE} AS tier, substr(r.published_date::text,1,4)::int AS year, "
        "       COUNT(DISTINCT t.id) "
        "FROM signal_cpc sc JOIN trends t ON t.id = sc.trend_id "
        "JOIN raw_entries r ON r.id = t.raw_entry_id JOIN sources s ON s.id = r.source_id "
        f"WHERE sc.dist < {CONFIDENT_DIST} AND r.pub_number IS NULL AND r.published_date IS NOT NULL "
        f"  AND substr(r.published_date::text,1,4)::int BETWEEN {YEAR_MIN} AND {YEAR_MAX} "
        "GROUP BY tier, year")
    conn.execute(
        "INSERT INTO cpc_tier_totals (tier, year, total) "
        "SELECT 'patent', substr(r.published_date::text,1,4)::int AS year, COUNT(*) "
        "FROM raw_entries r WHERE r.pub_number IS NOT NULL AND r.published_date IS NOT NULL "
        f"  AND substr(r.published_date::text,1,4)::int BETWEEN {YEAR_MIN} AND {YEAR_MAX} "
        "GROUP BY year ON CONFLICT (tier, year) DO NOTHING")
    print(f"  done in {time.time() - t0:.0f}s", flush=True)


# A tier's SoV series is only trustworthy where the tier has enough total volume
# to form a stable share. Below this the SoV is noise (1 signal / 3 total = 33%).
MIN_TIER_TOTAL = 30
# S-curve takeoff: the year SoV first reaches this fraction of the CPC's own peak
# SoV *within the support window*. Measures the SHAPE of the rise, not an absolute
# floor year, so tiers with different acquisition depth are comparable.
TAKEOFF_FRACTION = 0.5
# Emergence gate: a lead-time is only meaningful for a technology that genuinely
# APPEARED during the window — its SoV must start near zero (below this fraction
# of its peak in the first years) and rise later. Established fields (batteries,
# pharma, dairy science — present since the window start) fail this and are marked
# unreliable: "research led market by N years" is undefined for them, and SoV-of-
# total peaks late for old-but-accelerating fields, which would fabricate a lead.
EMERGENCE_MAX_START = 0.20
EMERGENCE_START_YEARS = 3  # SoV averaged over the first N support years
# Numerator floor: below this many signals in a tier, that CPC's SoV series is
# 1-2 signals/year — pure noise, not a takeoff. A trustworthy lead-time needs
# real signal in BOTH compared tiers (kills the thin-science bicycle/furniture
# false positives).
MIN_CPC_TIER_N = 200


def _sov_takeoff(series: dict[int, float], lo: int, hi: int) -> tuple[int | None, bool]:
    """(takeoff_year, genuine_emergence). SoV = share within tier; series is
    year→SoV over the support window [lo, hi]."""
    pts = sorted((y, v) for y, v in series.items() if lo <= y <= hi and v is not None)
    if len(pts) < 4:
        return None, False
    peak = max(v for _, v in pts)
    if peak <= 0:
        return None, False
    thresh = peak * TAKEOFF_FRACTION
    takeoff = next((y for y, v in pts if v >= thresh), None)
    # genuine emergence: mean SoV over the first few window years is near zero
    # (the technology was absent early and rose later — not present all along)
    head = [v for _, v in pts[:EMERGENCE_START_YEARS]]
    start_level = (sum(head) / len(head)) if head else peak
    genuine = takeoff is not None and start_level < peak * EMERGENCE_MAX_START
    return takeoff, genuine


def build_summary() -> None:
    t0 = time.time()
    with get_connection() as conn:
        series_rows = conn.execute(
            "SELECT cpc, tier, year, n FROM cpc_tier_series").fetchall()
        total_rows = conn.execute(
            "SELECT tier, year, total FROM cpc_tier_totals").fetchall()

    def g(r, i, k):
        return r[k] if isinstance(r, dict) else r[i]

    totals: dict[tuple[str, int], int] = {}
    for r in total_rows:
        totals[(g(r, 0, "tier"), g(r, 1, "year"))] = g(r, 2, "total")
    # years where a tier has enough volume to trust its SoV
    tier_support: dict[str, set[int]] = {}
    for (tier, year), tot in totals.items():
        if tot >= MIN_TIER_TOTAL:
            tier_support.setdefault(tier, set()).add(year)

    per: dict[str, dict[str, dict[int, int]]] = {}
    for r in series_rows:
        cpc, tier, year, n = g(r, 0, "cpc"), g(r, 1, "tier"), g(r, 2, "year"), g(r, 3, "n")
        per.setdefault(cpc, {}).setdefault(tier, {})[year] = n

    def sov_of(counts: dict[int, int], tier: str, window: set[int]) -> dict[int, float]:
        return {y: counts.get(y, 0) / totals[(tier, y)]
                for y in window if totals.get((tier, y))}

    out = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for cpc, tiers in per.items():
        rec = {"cpc": cpc, "updated_at": now}
        for tier in ("science", "patent", "funding", "market"):
            rec[f"{tier}_n"] = sum(tiers.get(tier, {}).values())

        # Compare each pair over their COMMON support window, so tiers with
        # different acquisition depth (market ~2006+, science/patents 1990+) are
        # measured over identical years — otherwise "science is older data" fakes
        # a long lead. The takeoff for the headline is the in-common-window one.
        def lead(a: str, b: str) -> tuple[int | None, int | None, int | None, bool]:
            """(a_takeoff, b_takeoff, b−a lead, reliable) over a∩b support."""
            sa, sb = tier_support.get(a, set()), tier_support.get(b, set())
            common = sa & sb
            if len(common) < 4:
                return None, None, None, False
            lo, hi = min(common), max(common)
            ta, oka = _sov_takeoff(sov_of(tiers.get(a, {}), a, common), lo, hi)
            tb, okb = _sov_takeoff(sov_of(tiers.get(b, {}), b, common), lo, hi)
            enough = rec[f"{a}_n"] >= MIN_CPC_TIER_N and rec[f"{b}_n"] >= MIN_CPC_TIER_N
            ok = bool(ta and tb and oka and okb and enough)
            return ta, tb, ((tb - ta) if (ta and tb) else None), ok

        st, mt, lead_sm, ok_sm = lead("science", "market")
        pt, mt2, lead_pm, ok_pm = lead("patent", "market")
        rec["science_takeoff"] = st
        rec["market_takeoff"] = mt or mt2
        rec["patent_takeoff"] = pt
        rec["funding_takeoff"] = None
        rec["lead_science_vs_market"] = lead_sm
        rec["lead_patent_vs_market"] = lead_pm
        rec["reliable"] = int(ok_sm)  # headline reliability = the science→market claim
        common_sm = tier_support.get("science", set()) & tier_support.get("market", set())
        rec["window_start"] = min(common_sm) if common_sm else None
        rec["window_end"] = max(common_sm) if common_sm else None
        out.append(rec)

    with get_connection() as conn:
        conn.execute("DELETE FROM cpc_leadtime_summary")
        for r in out:
            conn.execute(
                "INSERT INTO cpc_leadtime_summary (cpc, science_n, patent_n, funding_n,"
                " market_n, science_takeoff, patent_takeoff, funding_takeoff,"
                " market_takeoff, lead_science_vs_market, lead_patent_vs_market,"
                " reliable, window_start, window_end, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r["cpc"], r["science_n"], r["patent_n"], r["funding_n"], r["market_n"],
                 r["science_takeoff"], r["patent_takeoff"], r["funding_takeoff"],
                 r["market_takeoff"], r["lead_science_vs_market"],
                 r["lead_patent_vs_market"], r["reliable"],
                 r["window_start"], r["window_end"], now))
    reliable = sum(r["reliable"] for r in out)
    print(f"summary: {len(out)} CPCs in {time.time() - t0:.0f}s "
          f"({reliable} with a reliable SoV-based lead-time)", flush=True)


def show(cpcs: list[str]) -> None:
    with get_connection() as conn:
        for cpc in cpcs:
            row = conn.execute(
                "SELECT * FROM cpc_leadtime_summary WHERE cpc = ?", (cpc.upper(),)
            ).fetchone()
            if not row:
                print(f"{cpc}: no summary row")
                continue
            d = dict(row)
            print(f"\n{cpc.upper()}  (SoV window {d['window_start']}–{d['window_end']}):")
            for tier in ("science", "patent", "funding", "market"):
                print(f"  {tier:8s} n={d[f'{tier}_n'] or 0:>9,}  SoV-takeoff={d[f'{tier}_takeoff'] or '—'}")
            flag = "RELIABLE" if d["reliable"] else "unreliable (rise near/before window edge)"
            print(f"  → lead science vs market: {d['lead_science_vs_market']} y, "
                  f"patent vs market: {d['lead_patent_vs_market']} y  [{flag}]")


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-tier fusion tables (#9/#28)")
    ap.add_argument("--summary", action="store_true", help="recompute summary only")
    ap.add_argument("--show", nargs="*", help="print summary for CPC symbols")
    args = ap.parse_args()
    if not USE_POSTGRES:
        print("cross-tier fusion targets Postgres")
        return 1
    migrate()
    if args.show:
        show(args.show)
        return 0
    if not args.summary:
        build_series()
    build_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
