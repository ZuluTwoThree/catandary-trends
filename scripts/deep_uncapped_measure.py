#!/usr/bin/env python3
"""
LEGACY (2026-09-06): braucht FIRECRAWL_API_KEY — der Schluessel ist widerrufen,
der Pfad seit 2026-06 durch WP-API/OpenAlex abgeloest. Wer ihn reaktiviert, legt
bei Firecrawl einen neuen Schluessel an und traegt ihn in .env ein.

Measure the uncapped deep-crawl potential per FOOD source (no writes/scrapes).

For each source: one Firecrawl /map call (uncapped), then break the article
URLs down into:
  - total article URLs exposed by /map
  - free   = carry a description in /map  -> ingestable at 0 scrape credits
  - scrape = no description               -> 1 scrape credit each to get content
  - dated  = publication date derivable straight from the URL path (/YYYY/MM/)

Lets us decide where uncapping is nearly free vs expensive. ~30 map credits.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import FIRECRAWL_API_KEY, load_sources
from pipeline.radar_discovery import domain_of
from scripts.backfill_sources import (
    iter_sources, is_article_url, _extract_link, _date_from_url, DEEP_MAP_RATE_SECONDS,
)

from firecrawl import FirecrawlApp


def map_links(app, domain):
    for attempt in range(2):
        try:
            mr = app.map_url(f"https://{domain}")
            if hasattr(mr, "links"):
                return mr.links or []
            if isinstance(mr, dict):
                return mr.get("links", [])
            if isinstance(mr, list):
                return mr
            return []
        except Exception as exc:
            if "rate limit" in str(exc).lower() and attempt == 0:
                time.sleep(12); continue
            print(f"    map failed: {str(exc)[:80]}")
            return []
    return []


def main():
    if not FIRECRAWL_API_KEY:
        print("FIRECRAWL_API_KEY not set"); sys.exit(1)
    app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    sources = iter_sources(load_sources(), "FOOD", None, skip_noisy=True)

    print(f"Uncapped /map-Messung über {len(sources)} FOOD-Quellen\n")
    print(f"{'Quelle':<26}{'art-URLs':>9}{'gratis':>8}{'scrape':>8}{'datierbar':>10}")
    print("-" * 61)
    tot = {"art": 0, "free": 0, "scrape": 0, "dated": 0}
    rows = []
    for src in sources:
        domain = domain_of(src.get("feed_url", ""))
        links = map_links(app, domain)
        time.sleep(DEEP_MAP_RATE_SECONDS)
        art = free = scrape = dated = 0
        seen = set()
        for item in links:
            url, title, desc = _extract_link(item)
            if not url or not is_article_url(url, domain) or url in seen:
                continue
            seen.add(url)
            art += 1
            if desc:
                free += 1
            else:
                scrape += 1
            if _date_from_url(url):
                dated += 1
        name = src.get("name", "?")
        print(f"{name[:26]:<26}{art:>9}{free:>8}{scrape:>8}{dated:>10}")
        rows.append((name, art, free, scrape, dated))
        for k, v in zip(("art", "free", "scrape", "dated"), (art, free, scrape, dated)):
            tot[k] += v

    print("-" * 61)
    print(f"{'SUMME':<26}{tot['art']:>9}{tot['free']:>8}{tot['scrape']:>8}{tot['dated']:>10}")
    print(f"\nGesamt Artikel-URLs (uncapped): {tot['art']}")
    print(f"  davon gratis ingestierbar (Beschreibung): {tot['free']}  -> 0 Scrape-Credits")
    print(f"  davon scrape-pflichtig (kein Teaser):     {tot['scrape']}  -> {tot['scrape']} Credits + Rate-Limit-Zeit")
    print(f"  davon direkt URL-datierbar:               {tot['dated']}  ({100*tot['dated']//(tot['art'] or 1)}%)")
    print(f"\nTop-Quellen nach gratis+datierbar-Potenzial:")
    for name, art, free, scrape, dated in sorted(rows, key=lambda r: -min(r[2], r[4]))[:10]:
        print(f"  {name[:26]:<26} gratis={free:>4}  datierbar={dated:>4}  (scrape-nötig={scrape})")


if __name__ == "__main__":
    main()
