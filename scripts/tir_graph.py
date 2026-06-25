#!/usr/bin/env python3
"""GPU-free TIR on the patent GRAPH layer — no embeddings required.

This is the "lazy" half of the patent foresight architecture: domains are defined
*top-down by CPC subclass* (e.g. A61K, G06N, H01M) instead of bottom-up embedding
clusters, so the citation metrics run on the cheap, language-agnostic graph layer
(raw_entries + patent_links) over EVERY ingested patent — embedded or not. The
expensive embedding clustering (scripts/tir_metrics.py) is then only needed to
sub-divide a *hot* CPC domain, and can be computed lazily on demand.

Per CPC subclass domain it computes the same validated metrics as tir_metrics.py:
  - Immediate Importance = ø within-corpus forward citations within 3y of publication
  - Forward-rate         = ø within-corpus forward citations / patent
  - Cycle Time           = median(citing_year − cited_year) over backward cites
  - Recency              = ø publication year
  - Hub patent           = most forward-cited member

Read-only, zero GPU, zero writes — safe to run while the pipeline holds the GPU.

    python scripts/tir_graph.py                 # all verticals
    python scripts/tir_graph.py --vertical TECH --min-patents 40 --top 20
"""
from __future__ import annotations

import argparse
import re
import sys
import statistics as stats
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db import get_connection

_YEAR_RE = re.compile(r"(19|20)\d{2}")
# CPC code → subclass: section(1) + class(2 digits) + subclass(1 letter), e.g. "A61K9/00" → "A61K"
_CPC_SUB = re.compile(r"\b([A-HY]\d{2}[A-Z])")
_CPC_FIELD = re.compile(r"CPC:\s*([^.]+)", re.IGNORECASE)


def year_of(pub_number: str, corpus_year: dict[str, int]) -> int | None:
    if pub_number in corpus_year:
        return corpus_year[pub_number]
    m = _YEAR_RE.search(pub_number.replace("-", ""))
    if m:
        y = int(m.group(0))
        if 1900 <= y <= 2030:
            return y
    return None


def cpc_subclasses(excerpt: str | None) -> list[str]:
    """Parse the CPC subclasses out of the excerpt's 'CPC: ...' field."""
    if not excerpt:
        return []
    m = _CPC_FIELD.search(excerpt)
    field = m.group(1) if m else excerpt  # fall back to whole text if no explicit field
    return sorted({s for s in _CPC_SUB.findall(field)})


def load_patents(vertical: str | None) -> list[dict]:
    sql = ("SELECT re.pub_number AS pub, substr(re.published_date,1,4) AS yr, re.excerpt AS ex, "
           "       s.vertical AS vert "
           "FROM raw_entries re JOIN sources s ON re.source_id = s.id "
           "WHERE re.pub_number IS NOT NULL")
    params: list = []
    if vertical:
        sql += " AND s.vertical = ?"
        params.append(vertical)
    out = []
    with get_connection() as c:
        for r in c.execute(sql, params).fetchall():
            out.append({"pub": r["pub"], "year": int(r["yr"]) if r["yr"] else None,
                        "subs": cpc_subclasses(r["ex"]), "vert": r["vert"]})
    return out


def citation_indices(examiner_only: bool):
    """Return (forward: dst→[src], backward: src→[dst]) from patent_links."""
    fwd: dict[str, list[str]] = defaultdict(list)
    bwd: dict[str, list[str]] = defaultdict(list)
    q = "SELECT src_pub, dst_pub FROM patent_links WHERE link_type='cites'"
    if examiner_only:
        q += " AND category='EXA'"
    with get_connection() as c:
        for src, dst in c.execute(q).fetchall():
            fwd[dst].append(src)
            bwd[src].append(dst)
    return fwd, bwd


def main() -> int:
    ap = argparse.ArgumentParser(description="GPU-free TIR on the patent graph layer (CPC-domain)")
    ap.add_argument("--vertical", help="restrict to one vertical (else all)")
    ap.add_argument("--min-patents", type=int, default=30, help="min patents per CPC subclass")
    ap.add_argument("--top", type=int, default=25, help="how many domains to print")
    ap.add_argument("--examiner-only", action="store_true",
                    help="count only examiner (EXA) citations — drops applicant self-cites")
    ap.add_argument("--rank", choices=["imm", "cycle", "recency"], default="cycle",
                    help="imm=Immediate Importance (needs back-file), cycle=Cycle Time (live "
                         "metric on current data, shorter=faster), recency=newest first")
    args = ap.parse_args()

    pats = load_patents(args.vertical)
    print(f"patents (graph layer, embedding NOT required): {len(pats)}"
          f"{' · ' + args.vertical if args.vertical else ''}")
    with_cpc = sum(1 for p in pats if p["subs"])
    print(f"  with parseable CPC subclass: {with_cpc} ({100*with_cpc/max(1,len(pats)):.0f}%)")
    corpus_year = {p["pub"]: p["year"] for p in pats if p["year"]}
    fwd, bwd = citation_indices(args.examiner_only)
    print(f"  citation graph: {sum(len(v) for v in fwd.values())} edges"
          f"{' (examiner-only)' if args.examiner_only else ''}\n")

    # group patents by CPC subclass (a patent counts in each of its subclasses)
    domains: dict[str, list[dict]] = defaultdict(list)
    for p in pats:
        for sub in p["subs"]:
            domains[sub].append(p)

    rows = []
    for sub, members in domains.items():
        if len(members) < args.min_patents:
            continue
        years = [m["year"] for m in members if m["year"]]
        imm_list, fwd_list, cyc_list = [], [], []
        hub = (None, -1)
        for m in members:
            citers = fwd.get(m["pub"], [])
            fwd_list.append(len(citers))
            if len(citers) > hub[1]:
                hub = (m["pub"], len(citers))
            my = m["year"]
            if my:
                imm_list.append(sum(1 for s in citers
                                    if (sy := year_of(s, corpus_year)) and 0 <= sy - my <= 3))
                for dst in bwd.get(m["pub"], []):
                    dy = year_of(dst, corpus_year)
                    if dy and 0 <= my - dy <= 60:
                        cyc_list.append(my - dy)
        # dominant vertical of the subclass (subclasses can straddle verticals)
        vcount = defaultdict(int)
        for m in members:
            vcount[m["vert"]] += 1
        rows.append({
            "sub": sub, "n": len(members),
            "imm": stats.mean(imm_list) if imm_list else 0.0,
            "fwd": stats.mean(fwd_list) if fwd_list else 0.0,
            "recency": stats.mean(years) if years else None,
            "cycle": stats.median(cyc_list) if cyc_list else None,
            "cyc_cov": len(cyc_list),
            "hub": hub[0], "hub_cites": hub[1],
            "vert": max(vcount, key=vcount.get),
        })

    if args.rank == "cycle":  # shorter Cycle Time ⇒ faster TIR; domains w/o coverage last
        rows.sort(key=lambda r: (r["cycle"] is None, r["cycle"] if r["cycle"] is not None else 1e9))
        rank_label = "Cycle Time aufsteigend (kürzer ⇒ schneller verbesserndes Feld)"
    elif args.rank == "recency":
        rows.sort(key=lambda r: -(r["recency"] or 0))
        rank_label = "Recency (neueste Domains zuerst)"
    else:
        rows.sort(key=lambda r: -r["imm"])
        rank_label = "Immediate Importance (⚠ aktuell ~0 — braucht Back-File)"
    print(f"CPC-Subklassen-Domains nach {rank_label}, "
          f"min {args.min_patents} Patente — Top {args.top}:\n")
    for i, r in enumerate(rows[:args.top], 1):
        cyc = f"{r['cycle']:.0f}J" if r["cycle"] is not None else "n/a"
        rec = f"{r['recency']:.0f}" if r["recency"] else "?"
        print(f"━━ #{i}  CPC {r['sub']}  [{r['vert']}]  ·  {r['n']} Patente")
        print(f"   ⭐ Immediate Importance: {r['imm']:.3f}  | Forward-Rate: {r['fwd']:.3f}"
              f"  | Recency: {rec}  | Cycle Time: {cyc} (cov {r['cyc_cov']})")
        print(f"   Hub-Patent: {r['hub']} ({r['hub_cites']} Forward-Zitate)\n")

    print(f"Domains insgesamt (≥{args.min_patents} Patente): {len(rows)}")
    print("Lesart: GPU-frei, rein aus CPC + Zitationsgraph. Embedding-Cluster (tir_metrics.py)")
    print("        verfeinern eine *heiße* Domain bottom-up — lazy, nur bei Bedarf.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
