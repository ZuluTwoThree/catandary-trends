#!/usr/bin/env python3
"""Unified technology analysis for the merged Technology tool (#28/#36/#42/#43).

ONE resolution, ONE TIR. A free-text phrase resolves to a ranked set of fine CPC
candidate classes (each with its real full-archive patent count); a smart default
subset is pre-selected, but the USER decides which classes to include. Both views
then run against exactly that selection:

  • the K(t) improvement-rate TRAJECTORY (tir_trajectory, full-archive substrate) —
    the single canonical TIR, no competing number anywhere else;
  • the cross-tier LEAD-TIME (research→patent→funding→market timing), a phrase-level
    semantic lens (no TIR of its own — that was the old divergence).

Two modes so a checkbox toggle is cheap:
  --query "processed cheese"      → embed once: candidates + default selection +
                                    trajectory(default) + lead-time
  --codes A23C19/08 A23C19/00     → re-run ONLY the trajectory for the explicit
                                    selection (pure SQL, no GPU)

    python scripts/tech_analyze.py --query "processed cheese" --json
    python scripts/tech_analyze.py --codes A23C19/08 A23C19/00 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from scripts.cpc_leadtime import median_year
from scripts.tech_query import (
    embed_query, embedded_tier_totals, ramp_takeoff, share_series, tier_years_for_vec,
)
from scripts.tech_trajectory import DIST_GATE, resolve_domain
from scripts.tir_trajectory import trajectory

OFF_TOPIC_DIST = 0.55       # nearest candidate beyond this → not a technology
DENSITY_TARGET = 8000       # default selection grows in distance order until the
                            # cumulative count clears this — a rich domain (battery)
                            # stops at its main class, a thin one (cheese) keeps all
                            # its candidates. The user then narrows/broadens.
MAX_CANDIDATES = 12         # how many toggleable classes to offer the user


def _counts(codes: list[str]) -> dict[str, int]:
    """Real full-archive patent count per fine CPC code (patent_cpc_full)."""
    if not codes:
        return {}
    out: dict[str, int] = {}
    with get_connection() as c:
        cur = c._conn.cursor()
        for code in codes:
            cur.execute("SELECT count(DISTINCT pub_number) FROM patent_cpc_full "
                        "WHERE cpc LIKE %s", (code + "%",))
            out[code] = int(cur.fetchone()[0])
    return out


def resolve_candidates(vec: list[float]) -> list[dict]:
    """Ranked fine CPC candidates (in the distance gate) with real full-archive
    counts and a smart default pre-selection (main class + nearest siblings until
    the measurable corpus clears DENSITY_TARGET, capped at DEFAULT_MAX)."""
    codes = resolve_domain(vec, dist_gate=DIST_GATE, max_codes=MAX_CANDIDATES)
    counts = _counts([c["symbol"] for c in codes])
    dens = 0
    out = []
    for i, c in enumerate(codes):
        n = counts.get(c["symbol"], 0)
        # default-check nearest classes (in distance order) until the running count
        # clears DENSITY_TARGET; the 1st is always checked so there is never an
        # empty default. Rich domains stop after one class; thin ones keep going.
        default = (i == 0) or (dens < DENSITY_TARGET)
        if default:
            dens += n
        out.append({"symbol": c["symbol"], "title": c["title"],
                    "dist": c["dist"], "n": n, "default": default})
    return out


def _patent_years_full(codes: list[str]) -> Counter:
    """Patent tier for the lead-time: granted-patent count per year over the SELECTED
    classes, on the same full-archive graph the trajectory measures (consistent scope)."""
    if not codes:
        return Counter()
    like = " OR ".join("pc.cpc LIKE %s" for _ in codes)
    years: Counter = Counter()
    with get_connection() as c:
        cur = c._conn.cursor()
        cur.execute(
            "SELECT sp.year, COUNT(*) FROM ("
            "  SELECT DISTINCT pc.pub_number FROM patent_cpc_full pc WHERE (" + like + ")"
            ") p JOIN patent_spnp_full sp ON sp.pub_number = p.pub_number "
            "WHERE sp.year BETWEEN 1990 AND 2026 GROUP BY sp.year",
            tuple(c + "%" for c in codes))
        for yr, n in cur.fetchall():
            years[int(yr)] = int(n)
    return years


def top_patents(sel_codes: list[str], limit: int = 8) -> list[dict]:
    """The most FORWARD-CITED patents carrying the selected classes — the domain's
    landmark/hub patents (the 'meistzitierte Patente' evidence). Counts on the DB
    citation graph (patent_links) and pulls the title from raw_entries."""
    if not sel_codes:
        return []
    like = " OR ".join("pc.cpc LIKE %s" for _ in sel_codes)
    sql = (
        "WITH dom AS (SELECT DISTINCT pc.pub_number FROM patent_cpc pc WHERE (" + like + ")) "
        "SELECT pl.dst_pub pub, COUNT(*) cites, "
        "       MIN(re.title) title, MIN(substr(re.published_date::text,1,4)) yr "
        "FROM patent_links pl JOIN dom ON dom.pub_number = pl.dst_pub "
        "LEFT JOIN raw_entries re ON re.pub_number = pl.dst_pub "
        "WHERE pl.link_type = 'cites' "
        "GROUP BY pl.dst_pub ORDER BY cites DESC LIMIT %s")
    out = []
    with get_connection() as c:
        cur = c._conn.cursor()
        cur.execute(sql, tuple(s + "%" for s in sel_codes) + (limit,))
        for pub, cites, title, yr in cur.fetchall():
            out.append({"pub": pub, "cites": int(cites),
                        "title": (title or "").strip()[:160], "year": yr,
                        "url": "https://worldwide.espacenet.com/patent/search?q=pn%3D%22"
                               + (pub or "").replace("-", "") + "%22"})
    return out


def leadtime(vec: list[float], sel_codes: list[str], threshold: float = 0.55) -> dict:
    """Cross-tier timing (research→patent→funding→market). Phrase-level semantic
    lens; NO TIR (the canonical TIR is the trajectory's). Patent tier scoped to the
    user's selected classes so it shares the trajectory's corpus."""
    tiers = tier_years_for_vec(vec, threshold)
    tiers["patent"] = _patent_years_full(sel_codes)
    totals = embedded_tier_totals()
    tier_out: dict[str, dict] = {}
    takeoffs: dict[str, int | None] = {}
    for tier in ("science", "patent", "funding", "market"):
        ys = tiers.get(tier) or Counter()
        plot = ys if tier == "patent" else share_series(ys, totals.get(tier, {}))
        to = ramp_takeoff(plot)
        takeoffs[tier] = to
        med = median_year(ys)
        tier_out[tier] = {
            "n": sum(ys.values()), "first": min(ys) if ys else None,
            "takeoff": to, "median": round(med) if med else None,
            "series": {str(y): round(v, 1) for y, v in sorted(plot.items())},
            "is_share": tier != "patent"}
    sci, mkt, pat = takeoffs["science"], takeoffs["market"], takeoffs["patent"]
    # A tier whose ramp "takes off" at the very first observable years didn't take
    # off THEN — the field predates our 1990 data window, so its takeoff is pinned
    # to the floor and any market-minus-takeoff "lead" is a boundary artifact, not a
    # real research→market lead. Only claim a lead when research/patents genuinely
    # emerge INSIDE the window (takeoff ≥ FLOOR+3).
    FLOOR = 1990
    sci_established = bool(sci and sci <= FLOOR + 3)
    pat_established = bool(pat and pat <= FLOOR + 3)
    lead_sm = (mkt - sci) if (sci and mkt and not sci_established
                              and mkt >= 2003 and mkt - sci >= 2) else None
    lead_pm = (mkt - pat) if (pat and mkt and not pat_established
                              and mkt >= 2003 and mkt - pat >= 2) else None
    concurrent = bool(sci and mkt and not sci_established and (mkt - sci) < 2 and not lead_sm)
    return {"tiers": tier_out, "lead_science_market": lead_sm,
            "lead_patent_market": lead_pm, "concurrent": concurrent,
            "established": sci_established and pat_established,
            "market_floored": bool(mkt and mkt < 2003)}


def analyze_query(query: str) -> dict:
    vec = embed_query(query)
    cands = resolve_candidates(vec)
    nearest = cands[0]["dist"] if cands else 1.0
    if not cands or nearest > OFF_TOPIC_DIST:
        return {"query": query, "off_topic": True,
                "nearest_dist": round(nearest, 3), "candidates": [],
                "selection": [], "trajectory": None, "leadtime": None}
    sel = [c["symbol"] for c in cands if c["default"]]
    traj = trajectory([s + "%" for s in sel])
    lead = leadtime(vec, sel)
    return {"query": query, "off_topic": False, "candidates": cands,
            "selection": sel, "trajectory": traj, "leadtime": lead,
            "top_patents": top_patents(sel), "verdict": _verdict(traj, lead)}


def _verdict(traj: dict, lead: dict) -> str | None:
    """Plain-language one-liner: innovation-chain stage + the single canonical TIR.
    Uses the robust K_MEDIAN (not the spike-prone last complete year — recent cohorts
    carry a citation-immaturity bump that inflates K_latest)."""
    lead_sm = lead.get("lead_science_market")
    mkt_n = (lead.get("tiers", {}).get("market") or {}).get("n", 0)
    stage = None
    if lead.get("established"):
        stage = "Established field — research and patents predate our data window"
    elif lead_sm and lead_sm >= 8:
        stage = f"Research ran ~{lead_sm}+ years ahead of the market"
    elif lead.get("concurrent"):
        stage = "Research and market move closely together"
    elif mkt_n < 80:
        stage = "Early-stage — market coverage is still thin"
    k = traj.get("K_median") if traj and traj.get("calibrated") else None
    speed = None
    if k is not None:
        # Label the figure explicitly as the median over the measured history —
        # K_latest can differ a lot (citation immaturity), and an unlabeled
        # number next to the chart's last point reads as a contradiction.
        speed = (f"improving fast (median ~{k}%/yr over the measured history)" if k >= 12
                 else f"slow-moving (median ~{k}%/yr over the measured history)" if k <= 8
                 else f"median ~{k}%/yr improvement over the measured history")
    if stage and speed:
        return f"{stage}; {speed}."
    if stage:
        return f"{stage}."
    if speed:
        return speed[0].upper() + speed[1:] + "."
    return None


def analyze_codes(codes: list[str]) -> dict:
    """Re-analyze the trajectory + hub patents for an explicit user selection (no
    embedding — pure SQL, so a checkbox toggle stays fast)."""
    traj = trajectory([c + "%" for c in codes])
    return {"selection": codes, "trajectory": traj, "top_patents": top_patents(codes)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Unified technology analysis (merged tool)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--query", help="free-text technology phrase")
    g.add_argument("--codes", nargs="+", help="explicit CPC codes (re-analyze trajectory)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = analyze_codes(args.codes) if args.codes else analyze_query(args.query)
    # compact single line: the API route (and CLI) take the last stdout line as JSON,
    # so GPU-handover logs printed earlier never collide with the payload.
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
