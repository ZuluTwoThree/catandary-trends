#!/usr/bin/env python3
"""Survey every source for the cheapest historical-ingest path.

Per source decides: WordPress REST API (free dated content), academic/OpenAlex
(science journals), or OTHER (sitemap/Firecrawl fallback). Read-only.
"""
from __future__ import annotations
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline.config import load_sources
from pipeline.radar_discovery import domain_of

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CatandaryBot/1.0)"}
ACADEMIC_HOSTS = ("onlinelibrary.wiley.com", "nature.com", "sciencedirect", "frontiersin.org",
                  "mdpi.com", "springer", "tandfonline.com", "sagepub", "academic.oup.com",
                  "cell.com", "pnas.org", "bmj.com", "thelancet.com", "acs.org",
                  "iopscience", "rsc.org", "plos.org", "ssrn.com", "arxiv.org")


def collect_sources(cfg):
    out = []
    for vert, groups in cfg.get("verticals", {}).items():
        for key in ("sources", "science"):
            for s in groups.get(key, []) or []:
                if isinstance(s, dict) and s.get("active") is not False:
                    out.append({**s, "vertical": vert, "group": key})
    for grp, lst in cfg.get("cross_industry", {}).items():
        if isinstance(lst, list):
            for s in lst:
                if isinstance(s, dict) and s.get("active") is not False:
                    out.append({**s, "vertical": "CROSS", "group": grp})
    return out


def classify(src):
    domain = domain_of(src.get("feed_url", ""))
    typ = (src.get("type") or "").lower()
    is_academic = (src.get("group") in ("science",) or typ in ("science", "research")
                   or any(h in domain for h in ACADEMIC_HOSTS))
    # An explicit `ingest_via` in sources.yaml overrides the heuristic.
    forced = (src.get("ingest_via") or "").upper()
    if forced in ("WP", "ACADEMIC", "OTHER"):
        return forced, domain, None
    # Probe WordPress FIRST — a WP-backed outlet gives full dated content and beats
    # OpenAlex even when tagged research/science (e.g. Science News: 733 WP posts in
    # 2024 vs 0 OpenAlex works). Real journals (Nature, Lancet, PNAS …) run on
    # publisher platforms with no /wp-json, so they fall through to ACADEMIC.
    try:
        r = httpx.get(f"https://{domain}/wp-json/wp/v2/posts",
                      params={"per_page": 1}, headers=HEADERS, timeout=8, follow_redirects=True)
        if r.status_code == 200 and r.headers.get("X-WP-Total"):
            return "WP", domain, int(r.headers["X-WP-Total"])
    except Exception:
        pass
    if is_academic:
        return "ACADEMIC", domain, None
    return "OTHER", domain, None


def main():
    sources = collect_sources(load_sources())
    print(f"Probe {len(sources)} aktive Quellen ...\n")
    results = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(classify, s): s for s in sources}
        for fut in as_completed(futs):
            s = futs[fut]
            cat, domain, total = fut.result()
            results.append((s["vertical"], s.get("name", "?"), cat, total))

    # Per-vertical summary
    verts = {}
    for vert, name, cat, total in results:
        d = verts.setdefault(vert, {"WP": 0, "ACADEMIC": 0, "OTHER": 0, "wp_posts": 0})
        d[cat] += 1
        if cat == "WP" and total:
            d["wp_posts"] += total

    print(f"{'Vertical':<10}{'WP':>4}{'WP-Posts':>10}{'Akadem.':>9}{'Sonst.':>8}")
    print("-" * 41)
    tot = {"WP": 0, "ACADEMIC": 0, "OTHER": 0, "wp_posts": 0}
    for vert in sorted(verts):
        d = verts[vert]
        print(f"{vert:<10}{d['WP']:>4}{d['wp_posts']:>10}{d['ACADEMIC']:>9}{d['OTHER']:>8}")
        for k in tot:
            tot[k] += d[k]
    print("-" * 41)
    print(f"{'SUMME':<10}{tot['WP']:>4}{tot['wp_posts']:>10}{tot['ACADEMIC']:>9}{tot['OTHER']:>8}")

    print("\nGrößte WP-Quellen (gratis dated Volltext via REST API):")
    wp = sorted([r for r in results if r[2] == "WP" and r[3]], key=lambda r: -r[3])
    for vert, name, cat, total in wp[:20]:
        print(f"  {vert:<10}{name[:34]:<34}{total:>8} Posts")


if __name__ == "__main__":
    main()
