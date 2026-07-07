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
import re
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


def embedded_tier_totals() -> dict[str, dict[int, int]]:
    """Corpus-wide signals per embedded tier per year (science/funding/market) —
    the denominator for share normalization, which removes the 2020 RSS-onset
    density cliff. Patents are native (no cliff) so they stay raw. Fast: one
    GROUP BY over trends, no 18M-patent scan."""
    totals: dict[str, dict[int, int]] = {"science": {}, "funding": {}, "market": {}}
    sql = (f"SELECT {tier_expr()} AS tier, substr(r.published_date::text,1,4) AS yr, "
           "COUNT(*) AS n FROM trends t JOIN raw_entries r ON t.raw_entry_id=r.id "
           "JOIN sources s ON r.source_id=s.id "
           "WHERE t.embedding_1024 IS NOT NULL AND r.published_date IS NOT NULL "
           "AND r.pub_number IS NULL GROUP BY tier, yr")
    with get_connection() as c:
        for r in c.execute(sql).fetchall():
            tier = r["tier"] if isinstance(r, dict) else r[0]
            yr = r["yr"] if isinstance(r, dict) else r[1]
            n = r["n"] if isinstance(r, dict) else r[2]
            try:
                if tier in totals:
                    totals[tier][int(yr)] = int(n)
            except (TypeError, ValueError):
                pass
    return totals


def share_series(years: Counter, tier_totals: dict[int, int]) -> Counter:
    """Per-year share of the tier (parts per 10,000); years with a tiny
    denominator (<30, pre-coverage) are dropped as noise."""
    out: Counter = Counter()
    for y, n in years.items():
        tot = tier_totals.get(y, 0)
        if tot >= 30:
            out[y] = round(10000 * n / tot, 1)
    return out


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


_STOP = {"for", "the", "and", "with", "from", "into", "via", "using", "based",
         "new", "novel", "food", "foods", "system", "systems", "method", "methods"}


def _espacenet(pub: str) -> str:
    return ("https://worldwide.espacenet.com/patent/search?q=pn%3D%22"
            + pub.replace("-", "") + "%22")


def evidence(vec1024: list[float], tier: str, threshold: float,
             year: int | None = None, limit: int = 30, query_text: str = "") -> list[dict]:
    """The underlying signals behind a tier's bar: for science/funding/market the
    nearest matching trends (title, year, source, original URL); for patent the
    query-relevant patents in the nearest CPC class (full-text on title+abstract,
    ranked by relevance × citations), falling back to the class's top-cited
    patents only when the query has no textual matches. This is the evidence a
    click on a sparkline surfaces."""
    vlit = "[" + ",".join(f"{x:.6f}" for x in vec1024) + "]"
    out: list[dict] = []
    with get_connection() as c:
        if tier == "patent":
            # Search the top-N nearest CPC classes, not just one: for "recombinant
            # casein in cheesemaking" the nearest class is A23C (dairy processing),
            # but the actual recombinant-casein patents live in C07K/C12N/A23J
            # (proteins/genetic-engineering) — a single-class scope misses them.
            cpcs = nearest_cpcs(vec1024, k=5)
            if not cpcs:
                return out
            syms = [c["symbol"] for c in cpcs]
            # Hybrid: patents across those classes whose title+abstract match the
            # query. Rank by text relevance with only a MILD citation boost, so
            # young startup patents (0 citations) aren't buried under old ones.
            words = [w for w in re.findall(r"[a-z]{4,}", query_text.lower())
                     if w not in _STOP]
            tsq = " | ".join(dict.fromkeys(words))  # OR, de-duped, order-preserving
            rows = []
            if tsq:
                # dom: text-matching patents in the classes (GIN-indexed).
                # top: keep the best ~150 by text relevance BEFORE the citation
                # count subquery, so we count links for 150 rows, not thousands.
                rows = [dict(r) for r in c.execute(
                    "WITH dom AS (SELECT DISTINCT ON (re.pub_number) re.pub_number pub, "
                    "   re.title, re.published_date pd, "
                    "   ts_rank(to_tsvector('english', coalesce(re.title,'')||' '|| "
                    "     coalesce(re.excerpt,'')), to_tsquery('english', ?)) rank "
                    " FROM raw_entries re JOIN patent_cpc pc ON pc.pub_number=re.pub_number "
                    " WHERE substr(pc.cpc,1,4) = ANY(?) AND re.pub_number IS NOT NULL "
                    "   AND to_tsvector('english', coalesce(re.title,'')||' '|| "
                    "     coalesce(re.excerpt,'')) @@ to_tsquery('english', ?) "
                    " ORDER BY re.pub_number), "
                    "top AS (SELECT * FROM dom ORDER BY rank DESC LIMIT 150), "
                    "ranked AS (SELECT pub, title, pd, rank, "
                    "   (SELECT COUNT(*) FROM patent_links pl WHERE pl.dst_pub=top.pub "
                    "     AND pl.link_type='cites') cites FROM top) "
                    "SELECT pub, title, substr(pd::text,1,4) yr, cites, rank "
                    "FROM ranked ORDER BY rank * (1 + 0.2*ln(cites+1)) DESC LIMIT ?",
                    (tsq, syms, tsq, limit)).fetchall()]
            if len(rows) >= 3:
                for r in rows:
                    out.append({"title": (r["title"] or r["pub"]), "year": r["yr"],
                                "source": "Patent", "cites": int(r["cites"] or 0),
                                "confidence": "related", "url": _espacenet(r["pub"])})
                return out
            # Fallback: no query text matches → the nearest class's most-cited
            # patents, honestly labelled as domain-central, not query-specific.
            rows = c.execute(
                "SELECT pl.dst_pub AS pub, COUNT(*) AS n, MIN(re.title) AS title, "
                "       MIN(substr(re.published_date::text,1,4)) AS yr "
                "FROM patent_links pl "
                "JOIN patent_cpc pc ON pc.pub_number=pl.dst_pub AND substr(pc.cpc,1,4)=? "
                "LEFT JOIN raw_entries re ON re.pub_number=pl.dst_pub "
                "WHERE pl.link_type='cites' GROUP BY pl.dst_pub "
                "ORDER BY n DESC LIMIT ?", (syms[0], limit)).fetchall()
            for r in rows:
                r = dict(r)
                out.append({"title": (r["title"] or r["pub"]), "year": r["yr"],
                            "source": f"Patent · {syms[0]} (most-cited in class)",
                            "cites": int(r["n"]), "url": _espacenet(r["pub"])})
            return out
        # embedded non-patent tiers.  P1: require a substantial abstract — grants
        # with only an ALL-CAPS title and no abstract (e.g. FDA feed-ban admin
        # records mis-filed in NIH RePORTER) embed on surface words and produce
        # off-topic matches. length(excerpt) > 60 keeps the ~40-char funding
        # prefix from passing while dropping the abstract-less noise.
        params: list = [threshold]
        yr_clause = ""
        if year:
            yr_clause = "AND substr(r.published_date::text,1,4)=? "
            params.append(str(year))
        params.append(tier)
        params.append(limit)
        sql = (f"SELECT t.title_en AS title, substr(r.published_date::text,1,4) AS yr, "
               "       s.name AS source, r.url AS url, "
               f"       (t.embedding_1024 <=> '{vlit}'::vector) AS dist "
               "FROM trends t JOIN raw_entries r ON t.raw_entry_id=r.id "
               "JOIN sources s ON r.source_id=s.id "
               "WHERE t.embedding_1024 IS NOT NULL AND r.published_date IS NOT NULL "
               "AND r.pub_number IS NULL AND length(r.excerpt) > 60 "
               f"AND t.embedding_1024 <=> '{vlit}'::vector < ? "
               f"{yr_clause}AND {tier_expr()} = ? "
               "ORDER BY dist LIMIT ?")
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
        # P0/P2: confidence RELATIVE to this query's best match in the tier.
        # Absolute thresholds were tried but break under embedding drift — the
        # GPU handover can shift the whole distance level (~0.15 seen), so a
        # fixed 0.32 cutoff flips a paper strong↔related between runs. Relative
        # deltas are drift-invariant: within 0.04 of the best = strong, within
        # 0.09 = related, beyond = weak (hidden). The abstract filter (P1) has
        # already removed the truly off-topic; this just grades the remainder.
        best = float(rows[0]["dist"]) if rows else 0.0
        for r in rows:
            d = float(r["dist"])
            delta = d - best
            conf = "strong" if delta < 0.04 else "related" if delta < 0.09 else "weak"
            out.append({"title": r["title"], "year": r["yr"], "source": r["source"],
                        "url": r["url"], "dist": round(d, 3), "confidence": conf})
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
    # Off-topic guard: a person/brand name or non-technical phrase has no CPC
    # anywhere near it (e.g. "Angela Merkel" → nearest 0.64 vs a real technology
    # ~0.28). Without this, a name embeds diffusely into thousands of signals and
    # the UI wrongly reports "early-stage". Bail with a clear, honest message.
    nearest_dist = float(cpcs[0]["dist"]) if cpcs else 1.0
    if nearest_dist > 0.55:
        return {"query": query, "threshold": threshold, "verdict": None,
                "off_topic": True, "nearest_dist": round(nearest_dist, 3),
                "nearest_cpcs": [], "tiers": {}, "tir_pct": None, "tir_cpc": None,
                "tir_via": None, "tir_is_nearest": False, "cycle_time_years": None,
                "lead_science_market": None, "lead_patent_market": None,
                "concurrent": False, "market_floored": False}
    tiers = tier_years_for_vec(vec, threshold)
    tiers["patent"] = patent_years_for_cpc(cpcs[0]["symbol"]) if cpcs else Counter()
    totals = embedded_tier_totals()

    tier_out: dict[str, dict] = {}
    takeoffs: dict[str, int | None] = {}
    for tier in ("science", "patent", "funding", "market"):
        ys = tiers.get(tier) or Counter()
        # patents are native (no RSS cliff) → raw; embedded tiers → share-of-tier
        # so the 2020 acquisition-density cliff doesn't masquerade as a trend
        plot = ys if tier == "patent" else share_series(ys, totals.get(tier, {}))
        to = ramp_takeoff(plot)          # takeoff on the de-cliffed series
        takeoffs[tier] = to
        med = median_year(ys)
        tier_out[tier] = {
            "n": sum(ys.values()), "first": min(ys) if ys else None,
            "takeoff": to, "median": round(med) if med else None,
            "series": {str(y): round(v, 1) for y, v in sorted(plot.items())},
            "is_share": tier != "patent",
        }

    sci, mkt, pat = takeoffs["science"], takeoffs["market"], takeoffs["patent"]
    # lead-time sanity: only claim a lead when research genuinely PRECEDES market
    # by a plausible margin; a negative/zero/tiny gap is "concurrent", not "-4y"
    lead_sm = (mkt - sci) if (sci and mkt and mkt >= 2003 and mkt - sci >= 2) else None
    lead_pm = (mkt - pat) if (pat and mkt and mkt >= 2003 and mkt - pat >= 2) else None
    concurrent = bool(sci and mkt and (mkt - sci) < 2 and not lead_sm)
    # TIR is precomputed only for the curated classes; use the NEAREST modeled
    # class (first hit carrying a tir_pct), and flag when it isn't the very
    # nearest so the UI can say "via <class>".
    tir_src = next((c for c in cpcs if c.get("tir_pct") is not None), None)
    tir = tir_src["tir_pct"] if tir_src else None

    # P1: one-sentence plain-language verdict (stage clause + speed clause)
    mkt_n = tier_out["market"]["n"]
    stage = None
    if lead_sm and lead_sm >= 8:
        stage = f"Research ran ~{lead_sm}+ years ahead of the market"
    elif concurrent:
        stage = "Research and market move closely together"
    elif mkt_n < 80:
        stage = "Early-stage — market coverage is still thin"
    speed = None
    if tir is not None:
        speed = (f"improving fast (~{tir}%/yr)" if tir >= 10
                 else f"slow-moving (~{tir}%/yr)" if tir <= 4
                 else f"~{tir}%/yr improvement")
    if stage and speed:
        verdict = f"{stage}; {speed}."
    elif stage:
        verdict = f"{stage}."
    elif speed:
        verdict = speed[0].upper() + speed[1:] + "."
    else:
        verdict = None

    return {
        "query": query, "threshold": threshold, "verdict": verdict,
        "nearest_cpcs": cpcs[:6], "tiers": tier_out,
        "tir_pct": tir_src["tir_pct"] if tir_src else None,
        "tir_cpc": tir_src["symbol"] if tir_src else None,
        "tir_via": (tir_src["curated"] or tir_src["symbol"]) if tir_src else None,
        "tir_is_nearest": bool(tir_src and cpcs and tir_src["symbol"] == cpcs[0]["symbol"]),
        "cycle_time_years": tir_src["cycle"] if tir_src else None,
        "lead_science_market": lead_sm,
        "lead_patent_market": lead_pm,
        "concurrent": concurrent,
        "market_floored": bool(mkt and mkt < 2003),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Ad-hoc technology TIR + lead-time query (#28)")
    ap.add_argument("query", help="free-text technology phrase")
    ap.add_argument("--threshold", type=float, default=0.60,
                    help="max cosine distance signal↔query (default 0.60)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--evidence", metavar="TIER",
                    help="return the underlying signals for a tier "
                         "(science|patent|funding|market) instead of the summary")
    ap.add_argument("--year", type=int, help="--evidence: restrict to one year")
    args = ap.parse_args()
    if not db_mod.USE_POSTGRES:
        print("targets Postgres (pgvector)"); return 1

    if args.evidence:
        import json
        vec = embed_query(args.query)
        ev = evidence(vec, args.evidence, args.threshold, args.year, query_text=args.query)
        print(json.dumps({"tier": args.evidence, "year": args.year, "signals": ev}))
        return 0

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
    elif res.get("concurrent"):
        print("  • Research and market move roughly together (concurrent)")
    elif res["market_floored"]:
        print("  • Market coverage near the corpus floor; lead-time is a lower bound only")
    if res["lead_patent_market"]:
        print(f"  • Patents ran ~{res['lead_patent_market']}+ years ahead of market")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
