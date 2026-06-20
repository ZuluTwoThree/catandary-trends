"""Brave Search Radar — discovery layer for signals outside the RSS network.

Runs curated search queries per vertical (sources.yaml -> radar:), filters
results for trend relevance with the local LLM, and feeds hits into
raw_entries where the regular llm_processor picks them up. Discovered
domains are tracked; after 3+ hits a domain becomes an RSS-onboarding
candidate (organic source growth).

Usage:
    python -m pipeline.radar_discovery                 # all verticals, past week
    python -m pipeline.radar_discovery --vertical FOOD # single vertical
    python -m pipeline.radar_discovery --dry-run       # no DB writes, no LLM
    python -m pipeline.radar_discovery --backfill      # freshness: past month

Cron: daily 08:00 (normal), Sunday 10:00 with --backfill.
Budget: 32 queries/day (~960/month, Brave free tier: 2,000).
"""

import argparse
import logging
import time
from urllib.parse import urlparse

import httpx

from pipeline import db
from pipeline.config import (
    BRAVE_SEARCH_API_KEY,
    LOG_LEVEL,
    MODEL_FILTER,
    load_sources,
)
from pipeline.ollama_client import chat

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
RESULTS_PER_QUERY = 10
RATE_LIMIT_SECONDS = 1.1  # free tier: 1 req/s
DOMAIN_PROMOTION_THRESHOLD = 3

# Aggregators, socials and platforms we never ingest from.
SKIP_DOMAINS = {
    "trendhunter.com", "springwise.com", "trendwatching.com",
    "youtube.com", "reddit.com", "pinterest.com", "tiktok.com",
    "facebook.com", "instagram.com", "x.com", "twitter.com",
    "linkedin.com", "medium.com", "substack.com",
    "wikipedia.org", "en.wikipedia.org", "amazon.com",
    "google.com", "news.google.com", "msn.com", "yahoo.com",
}

RELEVANCE_SYSTEM = (
    "You are a trend-signal filter for a cross-industry trend intelligence "
    "platform. Given a search result (title + snippet) and an industry "
    "vertical, answer with exactly one word: YES if it describes a concrete, "
    "recent trend signal (product launch, research finding, market shift, "
    "funding, regulation, consumer behavior) relevant to that vertical — "
    "NO otherwise (listicles, evergreen guides, job ads, pure opinion, ads)."
)


def brave_search(query: str, count: int = RESULTS_PER_QUERY,
                 freshness: str = "pw") -> list[dict]:
    """Search Brave and return [{title, url, description}]. freshness: pd/pw/pm/py."""
    if not BRAVE_SEARCH_API_KEY:
        logger.warning("BRAVE_SEARCH_API_KEY not set, skipping web search")
        return []
    try:
        resp = httpx.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": count, "freshness": freshness},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "page_age": item.get("page_age", ""),
            }
            for item in data.get("web", {}).get("results", [])
        ]
    except Exception as exc:
        logger.error("brave search failed for '%s': %s", query[:60], exc)
        return []


def domain_of(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc.removeprefix("www.")


def url_exists(url: str) -> bool:
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM raw_entries WHERE url = ? LIMIT 1", (url,)
        ).fetchone()
    return row is not None


def ensure_radar_source(vertical: str) -> int:
    """Get or create the per-vertical radar source row."""
    return db.upsert_source(
        name=f"Brave Radar — {vertical}",
        feed_url=f"brave-radar://{vertical.lower()}",
        source_type="radar",
        vertical=vertical,
    )


def is_relevant(title: str, description: str, vertical: str) -> bool:
    prompt = (f"Vertical: {vertical}\nTitle: {title}\nSnippet: {description}\n\n"
              f"Trend signal for this vertical? Answer YES or NO.")
    try:
        answer = chat(MODEL_FILTER, prompt, system=RELEVANCE_SYSTEM)
    except Exception as exc:
        logger.error("relevance filter failed: %s", exc)
        return False
    return (answer or "").strip().upper().startswith("YES")


def process_query(vertical: str, query: str, source_id: int | None,
                  freshness: str, dry_run: bool) -> dict:
    stats = {"results": 0, "skipped_domain": 0, "duplicates": 0,
             "irrelevant": 0, "inserted": 0}
    results = brave_search(query, freshness=freshness)
    stats["results"] = len(results)
    for r in results:
        url, title, desc = r["url"], r["title"], r["description"]
        if not url or not title:
            continue
        domain = domain_of(url)
        if any(domain == d or domain.endswith("." + d) for d in SKIP_DOMAINS):
            stats["skipped_domain"] += 1
            continue
        if url_exists(url):
            stats["duplicates"] += 1
            continue
        if dry_run:
            # no LLM, no writes — show what would be considered
            stats["inserted"] += 1
            print(f"    [dry-run] {domain:<28} {title[:70]}")
            continue
        if not is_relevant(title, desc, vertical):
            stats["irrelevant"] += 1
            continue
        entry_id = db.insert_raw_entry(source_id, url, title, desc)
        if entry_id is None:
            stats["duplicates"] += 1
            continue
        stats["inserted"] += 1
        db.insert_source_discovery({
            "radar_source": "brave_search",
            "radar_vertical": vertical,
            "original_title": title,
            "discovered_url": url,
            "discovered_domain": domain,
        })
    return stats


def report_domain_promotions() -> list[tuple[str, int]]:
    """Domains discovered 3+ times that are not yet RSS sources."""
    with db.get_connection() as conn:
        rows = conn.execute(
            """SELECT discovered_domain, COUNT(*) AS cnt
               FROM source_discoveries
               WHERE radar_source = 'brave_search'
                 AND COALESCE(added_to_sources, 0) = 0
                 AND discovered_domain IS NOT NULL
               GROUP BY discovered_domain
               HAVING cnt >= ?
               ORDER BY cnt DESC""",
            (DOMAIN_PROMOTION_THRESHOLD,),
        ).fetchall()
    return [(r["discovered_domain"], r["cnt"]) for r in rows]


def main():
    parser = argparse.ArgumentParser(description="Brave Search Radar")
    parser.add_argument("--vertical", help="nur diese Vertikale (z.B. FOOD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Queries + Kandidaten zeigen, kein LLM, keine DB-Writes")
    parser.add_argument("--backfill", action="store_true",
                        help="freshness=pm (Monat) statt pw (Woche)")
    args = parser.parse_args()

    radar_config = load_sources().get("radar", {})
    if not radar_config:
        logger.error("kein radar: Abschnitt in sources.yaml")
        return
    if args.vertical:
        vertical = args.vertical.upper()
        if vertical not in radar_config:
            logger.error("keine Radar-Queries für %s", vertical)
            return
        radar_config = {vertical: radar_config[vertical]}

    freshness = "pm" if args.backfill else "pw"
    totals: dict[str, int] = {}
    for vertical, queries in radar_config.items():
        source_id = None if args.dry_run else ensure_radar_source(vertical)
        print(f"\n{vertical} ({len(queries)} Queries, freshness={freshness})")
        for query in queries:
            stats = process_query(vertical, query, source_id, freshness, args.dry_run)
            print(f"  '{query[:50]}': {stats['results']} Treffer, "
                  f"{stats['inserted']} neu, {stats['duplicates']} Duplikate, "
                  f"{stats['irrelevant']} irrelevant, {stats['skipped_domain']} geblockt")
            for key, val in stats.items():
                totals[key] = totals.get(key, 0) + val
            time.sleep(RATE_LIMIT_SECONDS)

    print(f"\nRadar-Lauf: {totals.get('results', 0)} Ergebnisse | "
          f"{totals.get('inserted', 0)} neue raw_entries | "
          f"{totals.get('duplicates', 0)} Duplikate | "
          f"{totals.get('irrelevant', 0)} irrelevant | "
          f"{totals.get('skipped_domain', 0)} geblockte Domains")

    if not args.dry_run:
        promotions = report_domain_promotions()
        if promotions:
            print("\nDomain-Kandidaten für RSS-Onboarding (3+ Treffer):")
            for domain, cnt in promotions:
                print(f"  {domain}  ({cnt} Treffer)  -> RSS-Feed prüfen, dann sources.yaml")


if __name__ == "__main__":
    main()
