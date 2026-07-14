#!/usr/bin/env python3
"""Source Foresight-Value report — what is each source worth to our products?

Owner brief (2026-07-14): foresight value dominates; give an action per source.

Scoring (0..1 each, weighted):
  FORESIGHT (70%) — does it feed the paid engine?
    F1 lead_time_tier   future 1.0 | market 0.5 | now 0.2      (sources.yaml)
    F2 signal-type mix  research/patent 1.0, funding .9, regulation .7,
                        product_launch .6, partnership .5, consumer_behavior .4,
                        market_shift .3  -> volume-weighted mean
    F3 mega coverage    1 - share of signals with mega_trend NULL
    F4 corroboration    share of the source's mega-trends that >= 3 other
                        sources also cover (proxy: per-trend cluster membership
                        is NOT stored, only 5 reps per cluster — honest limit)
    F5 novelty          1 - duplicate share of its filtered entries
  CONTENT (30%) — does it feed the free lead-magnet layer?
    C1 pass rate        signals / processed
    C2 publish rate     published / signals
    C3 confidence       mean confidence

Action: keep+ (>=.60) | keep (>=.45) | cap (<.45 with volume) | review (<.30)

    python scripts/source_value_report.py            # all sources with signals
    python scripts/source_value_report.py --min-signals 50
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from pipeline.db import get_connection

TYPE_W = {"research": 1.0, "patent": 1.0, "funding": 0.9, "regulation": 0.7,
          "product_launch": 0.6, "partnership": 0.5, "consumer_behavior": 0.4,
          "market_shift": 0.3}
TIER_W = {"future": 1.0, "market": 0.5, "now": 0.2}
W_FORESIGHT, W_CONTENT = 0.70, 0.30


def tiers_from_yaml() -> dict[str, str]:
    """name -> lead_time_tier. A few sources are listed twice (e.g. Nation's
    Restaurant News under two verticals) with different tiers; on conflict keep
    the WEAKEST tier — a source is only as early as its least-early listing."""
    cfg = yaml.safe_load(open(Path(__file__).parent.parent / "sources.yaml"))
    out: dict[str, str] = {}

    def put(name: str, tier: str) -> None:
        prev = out.get(name)
        if prev is None or TIER_W.get(tier, 0.5) < TIER_W.get(prev, 0.5):
            out[name] = tier

    for _v, g in (cfg.get("verticals") or {}).items():
        for k in ("sources", "science"):
            for s in g.get(k) or []:
                put(s["name"], s.get("lead_time_tier", "market"))
    for _g, e in (cfg.get("cross_industry") or {}).items():
        for s in e or []:
            put(s["name"], s.get("lead_time_tier", "market"))
    return out


def collect(min_signals: int) -> list[dict]:
    tiers = tiers_from_yaml()
    with get_connection() as c:
        # per-source signal aggregates
        rows = c.execute(
            "SELECT s.name AS source, s.vertical, "
            "  COUNT(t.id) AS signals, "
            "  COUNT(*) FILTER (WHERE t.mega_trend IS NULL) AS mega_null, "
            "  COUNT(*) FILTER (WHERE t.status = 'published') AS published, "
            "  AVG(t.confidence) AS conf "
            "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
            "JOIN sources s ON r.source_id = s.id GROUP BY s.name, s.vertical"
        ).fetchall()
        agg = {r["source"]: dict(r) for r in rows if r["signals"] >= min_signals}

        # signal-type mix
        for r in c.execute(
            "SELECT s.name AS source, t.trend_signal_type AS ty, COUNT(*) AS n "
            "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
            "JOIN sources s ON r.source_id = s.id GROUP BY s.name, t.trend_signal_type"
        ).fetchall():
            d = agg.get(r["source"])
            if d is not None:
                d.setdefault("types", {})[r["ty"] or "?"] = r["n"]

        # processed + duplicate share (pass rate / novelty)
        for r in c.execute(
            "SELECT s.name AS source, "
            "  COUNT(*) FILTER (WHERE r.processed) AS processed, "
            "  COUNT(*) FILTER (WHERE r.filter_reason LIKE ?) AS dups, "
            "  COUNT(*) FILTER (WHERE r.filtered_out) AS filtered "
            "FROM raw_entries r JOIN sources s ON r.source_id = s.id GROUP BY s.name",
            ("%duplicate%",)
        ).fetchall():
            d = agg.get(r["source"])
            if d is not None:
                d.update(processed=r["processed"] or 0, dups=r["dups"] or 0,
                         filtered=r["filtered"] or 0)

        # corroboration proxy: mega-trends covered by >=3 other sources
        mega_src = {}
        for r in c.execute(
            "SELECT t.mega_trend AS mt, COUNT(DISTINCT s.name) AS nsrc "
            "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
            "JOIN sources s ON r.source_id = s.id "
            "WHERE t.mega_trend IS NOT NULL GROUP BY t.mega_trend"
        ).fetchall():
            mega_src[r["mt"]] = r["nsrc"]
        for r in c.execute(
            "SELECT s.name AS source, t.mega_trend AS mt, COUNT(*) AS n "
            "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
            "JOIN sources s ON r.source_id = s.id "
            "WHERE t.mega_trend IS NOT NULL GROUP BY s.name, t.mega_trend"
        ).fetchall():
            d = agg.get(r["source"])
            if d is not None:
                d.setdefault("megas", {})[r["mt"]] = r["n"]

    out = []
    for name, d in agg.items():
        sig = d["signals"] or 1
        types = d.get("types", {})
        tv = sum(TYPE_W.get(t, 0.3) * n for t, n in types.items())
        f2 = tv / max(sum(types.values()), 1)
        f1 = TIER_W.get(tiers.get(name, "market"), 0.5)
        f3 = 1 - (d["mega_null"] or 0) / sig
        megas = d.get("megas", {})
        corro_n = sum(n for mt, n in megas.items() if mega_src.get(mt, 0) >= 4)
        f4 = corro_n / max(sum(megas.values()), 1) if megas else 0.0
        f5 = 1 - (d.get("dups", 0) / max(d.get("filtered", 0) + sig, 1))
        proc = d.get("processed", 0)
        c1 = sig / proc if proc else 0.0
        c2 = (d["published"] or 0) / sig
        c3 = float(d["conf"] or 0)
        # Foresight score from the components that actually CARRY INFORMATION.
        # Measured across all sources: f4 (corroboration) is constant 1.00 — with
        # only 21 broad mega-trends every mega is covered by >=4 sources, so it
        # discriminates nothing and is excluded. f3 (mega coverage) and f5
        # (novelty) barely vary (p25 0.90 / 0.96) — demoted to penalty flags.
        # f1 (tier 0.20-1.00) and f2 (type mix 0.30-1.00) are the real signal:
        # early-stage vs. market confirmation, which is exactly the foresight
        # question. Averaging all five squeezed every source to >=0.68 -> useless.
        fore = 0.5 * f1 + 0.5 * f2
        if f3 < 0.85:
            fore -= 0.05      # many signals not strategically placeable
        if f5 < 0.90:
            fore -= 0.05      # duplicate-heavy (echoes the wires)
        fore = max(fore, 0.0)
        cont = (min(c1, 1.0) + c2 + c3) / 3
        score = W_FORESIGHT * fore + W_CONTENT * cont
        if score >= 0.65:
            action = "keep+"
        elif score >= 0.50:
            action = "keep"
        elif sig >= 200 or proc >= 500:
            action = "cap"      # enough volume to be worth capping, low value
        else:
            action = "review"
        out.append(dict(source=name, vertical=d["vertical"], tier=tiers.get(name, "?"),
                        signals=sig, fore=fore, cont=cont, score=score, action=action,
                        f1=f1, f2=f2, f3=f3, f4=f4, f5=f5, c1=min(c1, 1.0), c2=c2, c3=c3,
                        top_type=max(types, key=types.get) if types else "?"))
    return sorted(out, key=lambda d: -d["score"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-signals", type=int, default=30)
    ap.add_argument("--only", help="substring filter on source name")
    args = ap.parse_args()

    rows = collect(args.min_signals)
    if args.only:
        rows = [r for r in rows if args.only.lower() in r["source"].lower()]
    print(f"{'SOURCE':<34}{'VERT':<10}{'TIER':<8}{'SIG':>7}{'FORE':>6}{'CONT':>6}{'SCORE':>7}  {'ACTION':<7} top-type")
    print("-" * 108)
    for r in rows:
        print(f"{r['source'][:33]:<34}{(r['vertical'] or '-'):<10}{r['tier']:<8}{r['signals']:>7}"
              f"{r['fore']:>6.2f}{r['cont']:>6.2f}{r['score']:>7.2f}  {r['action']:<7} {r['top_type']}")
    from collections import Counter
    print("\n" + " · ".join(f"{a}: {n}" for a, n in Counter(r["action"] for r in rows).most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
