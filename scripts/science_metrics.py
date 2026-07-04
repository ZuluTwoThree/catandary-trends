#!/usr/bin/env python3
"""Field-normalized science indicators on the OpenAlex graph layer (issue #9 WP4).

The science analog of tir_metrics.py, but the forward metrics are native (no
citation-graph inversion, no back-file): OpenAlex gives cited_by_count +
counts_by_year per work. The semantic unit is the OpenAlex Topic (itself an
embedding-derived clustering of the literature), so domains here are topics, not
KMeans clusters.

Per topic (within a scope), it computes:
  - Impact (field-normalized) : median subfield×year citation percentile — citation
                                rates vary ~10× between fields, so a raw count is
                                not comparable across subfields.
  - Velocity                  : citations in the last 2 years / total — a rising
                                share = an accelerating research front (momentum).
  - Recency                   : mean publication year.
  - Front hub                 : highest-cited work (the field-defining paper).
  - Integrity                 : retraction rate (is_retracted — a negative signal).

Ranking: by Velocity (which front is heating up NOW) by default, or --by impact.

Reusable by a later cross-tier script (science → technology → funding → market):
load_science_works() + subfield_year_reference() + the per-work helpers are the
importable pieces.

    python scripts/science_metrics.py --search "fermentation dairy probiotics"
    python scripts/science_metrics.py --subfield "Food Science" --by impact
    python scripts/science_metrics.py --vertical FOOD --min-works 8
"""
from __future__ import annotations

import argparse
import bisect
import json
import statistics as stats
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection

NOW_YEAR = datetime.now(timezone.utc).year
RECENT_WINDOW = 2  # years counted as "recent" for velocity


def _row(r, *keys):
    return tuple(r[k] if isinstance(r, dict) else r[i] for i, k in enumerate(keys))


def load_science_works(subfield: str = "", search: str = "", vertical: str = "",
                       topic: str = "") -> list[dict]:
    """Load OpenAlex graph-layer works in a scope with their native metrics.
    Scope: one of --subfield (name), --search (title/topic substring),
    --vertical, --topic (T-id). Reusable by the cross-tier script."""
    where = ["m.work_id IS NOT NULL"]
    params: list = []
    join_src = ""
    if topic:
        where.append("pt.topic_id = ?"); params.append(topic)
    if subfield:
        where.append("LOWER(pt.subfield) = LOWER(?)"); params.append(subfield)
    if search:
        # match works whose title OR topic contains ANY of the search words
        # (whole-phrase substring matching never hits multi-word queries)
        clauses = []
        for w in search.lower().split():
            clauses.append("(LOWER(r.title) LIKE ? OR LOWER(pt.topic) LIKE ?)")
            params += [f"%{w}%", f"%{w}%"]
        where.append("(" + " OR ".join(clauses) + ")")
    if vertical:
        join_src = "JOIN sources s ON r.source_id = s.id"
        where.append("s.vertical = ?"); params.append(vertical.upper())
    sql = (
        "SELECT m.work_id, m.cited_by_count, m.counts_by_year, m.work_type, "
        "       m.is_retracted, r.title, substr(r.published_date::text,1,4) AS yr, "
        "       pt.topic_id, pt.topic, pt.subfield, pt.field "
        "FROM openalex_meta m "
        "JOIN raw_entries r ON r.openalex_id = m.work_id "
        f"{join_src} "
        "LEFT JOIN openalex_topics pt ON pt.work_id = m.work_id AND pt.is_primary = 1 "
        f"WHERE {' AND '.join(where)}")
    out = []
    with get_connection() as c:
        for r in c.execute(sql, params).fetchall():
            (wid, cbc, cby, wtype, retr, title, yr, tid, topic_n, subf, field) = _row(
                r, "work_id", "cited_by_count", "counts_by_year", "work_type",
                "is_retracted", "title", "yr", "topic_id", "topic", "subfield", "field")
            try:
                counts = json.loads(cby) if isinstance(cby, str) else (cby or [])
            except Exception:
                counts = []
            out.append({
                "id": wid, "cites": cbc or 0, "counts": counts, "type": wtype,
                "retracted": bool(retr), "title": title or "",
                "year": int(yr) if yr else None, "topic_id": tid,
                "topic": topic_n or "—", "subfield": subf or "—", "field": field or "—",
            })
    return out


def subfield_year_reference() -> dict[tuple, list[int]]:
    """(subfield, year) -> sorted citation counts across the WHOLE openalex corpus.
    The reference distribution for field-normalization (percentile), so a work is
    judged against its own subfield+year, not globally."""
    ref: dict[tuple, list[int]] = defaultdict(list)
    with get_connection() as c:
        rows = c.execute(
            "SELECT pt.subfield AS subfield, substr(r.published_date::text,1,4) AS yr, "
            "       m.cited_by_count AS cbc "
            "FROM openalex_meta m JOIN raw_entries r ON r.openalex_id = m.work_id "
            "LEFT JOIN openalex_topics pt ON pt.work_id = m.work_id AND pt.is_primary = 1 "
            "WHERE m.cited_by_count IS NOT NULL").fetchall()
    for r in rows:
        subf, yr, cbc = _row(r, "subfield", "yr", "cbc")
        if subf and yr:
            ref[(subf, int(yr))].append(cbc or 0)
    for k in ref:
        ref[k].sort()
    return ref


def percentile(ref: dict, subfield: str, year: int | None, cites: int) -> float | None:
    """Field-normalized impact: percentile of `cites` within its (subfield, year)
    reference. None if the reference bucket is too thin to be meaningful."""
    if year is None:
        return None
    arr = ref.get((subfield, year))
    if not arr or len(arr) < 5:
        return None
    return bisect.bisect_right(arr, cites) / len(arr)


def velocity(work: dict) -> tuple[int, float | None]:
    """(recent citations, recent share). Recent = the last RECENT_WINDOW years.
    A high share of a work's citations landing recently = an accelerating front."""
    recent = sum(e.get("cited_by_count", 0) for e in work["counts"]
                 if e.get("year", 0) >= NOW_YEAR - RECENT_WINDOW)
    share = (recent / work["cites"]) if work["cites"] else None
    return recent, share


def main() -> int:
    ap = argparse.ArgumentParser(description="Field-normalized science indicators (#9 WP4)")
    ap.add_argument("--subfield", default="")
    ap.add_argument("--search", default="")
    ap.add_argument("--vertical", default="")
    ap.add_argument("--topic", default="", help="OpenAlex topic id (T#####)")
    ap.add_argument("--min-works", type=int, default=5, help="min works for a topic to rank")
    ap.add_argument("--by", choices=["velocity", "impact", "cites"], default="velocity")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    works = load_science_works(args.subfield, args.search, args.vertical, args.topic)
    scope = args.topic or args.subfield or args.search or args.vertical or "ALL"
    print(f"science works in scope [{scope}]: {len(works)}")
    if len(works) < args.min_works:
        print("too few works"); return 1
    ref = subfield_year_reference()
    print(f"field-normalization reference: {len(ref)} (subfield×year) buckets\n")

    # group by topic = the semantic domain (OpenAlex's own literature clustering)
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for w in works:
        by_topic[w["topic"]].append(w)

    rows = []
    for topic, members in by_topic.items():
        if len(members) < args.min_works:
            continue
        pcts = [p for w in members if (p := percentile(ref, w["subfield"], w["year"], w["cites"])) is not None]
        vels = [v for w in members if (v := velocity(w)[1]) is not None]
        recent_abs = [velocity(w)[0] for w in members]
        years = [w["year"] for w in members if w["year"]]
        hub = max(members, key=lambda w: w["cites"])
        rows.append({
            "topic": topic, "n": len(members),
            "subfield": stats.mode([w["subfield"] for w in members]),
            "impact_pct": stats.median(pcts) if pcts else None,
            "velocity": stats.median(vels) if vels else None,
            "recent_cites": stats.median(recent_abs) if recent_abs else 0,
            "recency": stats.mean(years) if years else None,
            "retract_rate": sum(w["retracted"] for w in members) / len(members),
            "hub_title": hub["title"], "hub_cites": hub["cites"],
        })

    keyf = {
        "velocity": lambda r: -(r["velocity"] or -1),
        "impact": lambda r: -(r["impact_pct"] or -1),
        "cites": lambda r: -r["recent_cites"],
    }[args.by]
    rows.sort(key=keyf)

    print(f"Topic-Ranking nach {args.by} (Research-Fronts):\n")
    for i, r in enumerate(rows[:args.top], 1):
        imp = f"{r['impact_pct']*100:.0f}. Perzentil" if r["impact_pct"] is not None else "n/a"
        vel = f"{r['velocity']*100:.0f}%" if r["velocity"] is not None else "n/a"
        rec = f"{r['recency']:.0f}" if r["recency"] else "?"
        retr = f" · ⚠ {r['retract_rate']*100:.0f}% retracted" if r["retract_rate"] > 0 else ""
        print(f"━━ #{i}  {r['topic'][:52]}  ·  {r['n']} Works  ·  {r['subfield']}")
        print(f"   Velocity (Zitate letzte {RECENT_WINDOW}J-Anteil): {vel}   | "
              f"Impact (feld-norm.): {imp}   | Recency: {rec} · Ø {r['recent_cites']:.0f} recent cites{retr}")
        print(f"   Front-Hub: {r['hub_title'][:70]} ({r['hub_cites']} Zitate)\n")

    print("Lesart: hohe Velocity (Zitate konzentrieren sich auf die letzten Jahre) +")
    print("        hohes feld-normiertes Impact-Perzentil ⇒ heiße, etablierte Research-Front.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
