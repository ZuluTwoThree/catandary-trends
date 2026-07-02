#!/usr/bin/env python3
"""Scoped lead-time discoverer — the foresight engine's core measurement (issue #2 A).

Turns the manual lead-time probes from the validation (GLP-1: funding 2015 →
science 2020 → market 2021) into an automated, corpus-wide signal. The method
avoids fragile cross-tier cluster matching:

  1. cluster the signal space ONCE, tier-agnostic (pipeline.foresight core)
  2. split each cluster's members by lead-time tier (science / patent / funding
     / market) via a source→tier map
  3. per tier, find the cluster's ONSET month (when the theme's cumulative
     signal count in that tier first reaches `onset_frac` of its tier total)
  4. the ordering of onsets = the lead-time chain; the gap from the earliest
     early-tier onset to the market onset = the measured lead time

Read-only, GPU-free. Writes a ranked JSON + Markdown report; no DB writes and
no taxonomy changes (mirrors propose_mega_trends' philosophy).

    python scripts/lead_time_discoverer.py --vertical HEALTH
    python scripts/lead_time_discoverer.py --vertical ALL --k 24
    python scripts/lead_time_discoverer.py --vertical FOOD --min-lead 6

Caveat (from docs/foresight_validation.md): the `research` tier only reaches
~2020; clusters whose market onset predates the science-tier data floor have
their science→market lead UNDER-stated and are flagged `truncated`.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from pipeline.config import DATA_DIR
from pipeline.db import get_connection
from pipeline.foresight import build_matrix, cluster_signals, derive_label, month_key

# --- lead-time tiers (earliest → latest); the canonical research→patent→funding
# →market chain. science and patent are both "future"; funding is early-mid;
# market (trade media / press wire) is confirmation. ---
TIER_ORDER = {"science": 0, "patent": 1, "funding": 2, "market": 3}
EARLY_TIERS = ("science", "patent", "funding")

PREPRINT_MARKERS = ("arxiv", "biorxiv", "medrxiv", "preprint")
FUNDING_MARKERS = ("nsf", "nih", "reporter", "openaire", "ukri", "gateway to research")


def tier_of(source_type: str | None, source_name: str | None, pub_number) -> str:
    """Map a signal to its lead-time tier. pub_number wins (patents are ingested
    as source_type='api' too), then research, then the api split (preprint vs
    funding by source name), else market."""
    if pub_number:
        return "patent"
    st = (source_type or "").lower()
    sn = (source_name or "").lower()
    if st == "research":
        return "science"
    if st == "api":
        if any(m in sn for m in PREPRINT_MARKERS):
            return "science"
        if any(m in sn for m in FUNDING_MARKERS):
            return "funding"
        return "market"  # Hacker News etc. — treat as market-adjacent
    return "market"  # trade_media, press_wire, brand


def load(vertical: str | None, status: str, limit: int) -> list[dict]:
    where = ["t.embedding IS NOT NULL",
             "(r.published_date IS NULL OR r.published_date <= datetime('now'))"]
    params: list = []
    if status and status.lower() != "all":
        sts = [s.strip() for s in status.split(",")]
        where.append(f"t.status IN ({','.join('?' * len(sts))})")
        params += sts
    if vertical and vertical.upper() != "ALL":
        where.append("t.primary_vertical = ?")
        params.append(vertical)
    sql = ("SELECT t.id, t.title_en, t.tags, t.source_name, t.primary_vertical, "
           "       r.published_date, r.pub_number, s.source_type, t.embedding "
           "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
           "JOIN sources s ON r.source_id = s.id "
           f"WHERE {' AND '.join(where)}")
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
    out = []
    for r in rows:
        emb = r["embedding"]
        if not isinstance(emb, (bytes, bytearray)) or len(emb) < 4:
            continue
        r["_emb"] = bytes(emb)
        r["embedding"] = None
        r["_tier"] = tier_of(r["source_type"], r["source_name"], r["pub_number"])
        try:
            r["tags"] = json.loads(r["tags"]) if r["tags"] else []
        except Exception:
            r["tags"] = []
        out.append(r)
    return out


def onset_month(members: list[dict], onset_frac: float, min_signals: int) -> tuple[str | None, int]:
    """Month at which cumulative count first reaches onset_frac of this group's
    total, chronologically. Returns (month|None, total). None if too sparse."""
    months = sorted(m for x in members if (m := month_key(x["published_date"])))
    total = len(months)
    if total < min_signals:
        return None, total
    # Require at least 3 signals before declaring onset, so a single mis-clustered
    # old patent/paper can't set the tier's onset month (robustness over the raw
    # earliest-signal date).
    target = max(3, int(onset_frac * total))
    counts: Counter = Counter(months)
    cum = 0
    for mo in sorted(counts):
        cum += counts[mo]
        if cum >= target:
            return mo, total
    return months[-1], total


def months_between(a: str, b: str) -> int:
    ya, ma = int(a[:4]), int(a[5:7])
    yb, mb = int(b[:4]), int(b[5:7])
    return (yb - ya) * 12 + (mb - ma)


def main() -> int:
    ap = argparse.ArgumentParser(description="Scoped lead-time discoverer (read-only)")
    ap.add_argument("--vertical", default="ALL", help="primary_vertical or ALL")
    ap.add_argument("--status", default="signal,published")
    ap.add_argument("--k", type=int, help="cluster count (default silhouette in range)")
    ap.add_argument("--k-range", default="14,26")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--onset-frac", type=float, default=0.10,
                    help="cumulative fraction defining a tier's onset month")
    ap.add_argument("--min-tier-signals", type=int, default=10,
                    help="min signals of a tier in a cluster to compute its onset")
    ap.add_argument("--min-lead", type=int, default=6,
                    help="min early→market lead (months) to call a cluster PREDICTIVE")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows = load(None if args.vertical.upper() == "ALL" else args.vertical,
                args.status, args.limit)
    print(f"{args.vertical} signals with embedding: {len(rows)}")
    tier_counts = Counter(r["_tier"] for r in rows)
    print("  tiers:", dict(tier_counts))
    if len(rows) < 200:
        print("Too few signals.")
        return 0

    # research-tier data floor for the truncation caveat
    sci_months = sorted(m for r in rows if r["_tier"] == "science"
                        and (m := month_key(r["published_date"])))
    sci_floor = sci_months[0] if sci_months else None

    X = build_matrix(rows)
    lo, hi = (int(x) for x in args.k_range.split(","))
    labels, centroids, k = cluster_signals(X, k=args.k, k_range=(lo, hi))
    print(f"clustered {X.shape[0]}×{X.shape[1]} into k={k}\n")

    by_cluster: dict[int, list[dict]] = defaultdict(list)
    for i, lab in enumerate(labels):
        by_cluster[int(lab)].append(rows[i])

    results = []
    for cid, members in by_cluster.items():
        tags = [t for t, _ in Counter(t for m in members for t in m["tags"]).most_common(10)]
        onsets: dict[str, str | None] = {}
        totals: dict[str, int] = {}
        for tier in TIER_ORDER:
            grp = [m for m in members if m["_tier"] == tier]
            onset, tot = onset_month(grp, args.onset_frac, args.min_tier_signals)
            onsets[tier] = onset
            totals[tier] = tot
        market = onsets["market"]
        # earliest early-tier onset present
        early = [(onsets[t], t) for t in EARLY_TIERS if onsets[t]]
        early.sort()
        lead_months = None
        lead_tier = None
        truncated = False
        if early and market:
            first_onset, lead_tier = early[0]
            lead_months = months_between(first_onset, market)
            # truncation: market predates the science data floor → science lead understated
            if sci_floor and market < sci_floor:
                truncated = True
        verdict = "PREDICTIVE" if (lead_months is not None and lead_months >= args.min_lead
                                   and not truncated) else \
                  "TRUNCATED" if truncated else \
                  "SYNC" if (lead_months is not None) else "SPARSE"
        results.append({
            "cluster": cid, "size": len(members),
            "label": derive_label(tags, fallback=f"Cluster {cid}"),
            "tiers": {t: {"onset": onsets[t], "signals": totals[t]} for t in TIER_ORDER},
            "lead_tier": lead_tier, "lead_months": lead_months,
            "market_onset": market, "verdict": verdict,
            "truncated": truncated, "top_tags": tags[:6],
        })

    # rank: PREDICTIVE by lead desc, then others
    order = {"PREDICTIVE": 0, "SYNC": 1, "TRUNCATED": 2, "SPARSE": 3}
    results.sort(key=lambda r: (order[r["verdict"]],
                                -(r["lead_months"] or -999), -r["size"]))

    # aggregate: median measurable lead per early tier → market
    leads = defaultdict(list)
    for r in results:
        if r["lead_months"] is not None and not r["truncated"] and r["lead_tier"]:
            leads[r["lead_tier"]].append(r["lead_months"])
    agg = {t: {"n": len(v), "median_lead_months": int(np.median(v))}
           for t, v in leads.items() if v}

    # ---- report ----
    print("=" * 80)
    print(f"LEAD-TIME DISCOVERER — {args.vertical} · {len(rows)} signals · k={k}")
    print("=" * 80)
    counts = Counter(r["verdict"] for r in results)
    print("verdicts:", dict(counts))
    print("median early→market lead (months):", agg or "— (insufficient cross-tier depth)")
    if sci_floor:
        print(f"science-tier data floor: {sci_floor} (clusters with earlier market onset flagged TRUNCATED)")
    print()
    for r in results:
        chain = "  ".join(
            f"{t}:{r['tiers'][t]['onset']}({r['tiers'][t]['signals']})"
            for t in TIER_ORDER if r['tiers'][t]['onset'])
        lead = f"{r['lead_tier']}→market {r['lead_months']}mo" if r['lead_months'] is not None else "—"
        print(f"━━ [{r['verdict']:10s}] {r['label'][:40]:<40} n={r['size']:<6} lead={lead}")
        print(f"     {chain}")
        print(f"     tags: {', '.join(r['top_tags'])}")
        print()

    out = Path(args.out) if args.out else DATA_DIR / f"lead_time_{args.vertical.lower()}.json"
    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "vertical": args.vertical, "signals": len(rows), "k": k,
        "tier_counts": dict(tier_counts), "science_floor": sci_floor,
        "aggregate_lead": agg, "verdicts": dict(counts), "clusters": results,
    }
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
