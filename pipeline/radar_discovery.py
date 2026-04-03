#!/usr/bin/env python3
"""Trendhunter Radar Discovery Pipeline.

Processes Trendhunter RSS feed entries to discover original brand sources:
1. Extract brand name from RSS title via LLM
2. Search for original source via Brave Search
3. Log discovery with domain info
4. Track domain frequency for potential RSS source addition

Radar entries without a found original source are NOT passed to the LLM pipeline.
"""

import logging
import sys
import time
from urllib.parse import urlparse

import httpx

from pipeline.config import BRAVE_SEARCH_API_KEY, LOG_LEVEL, MODEL_FILTER, load_sources
from pipeline.db import (
    get_connection,
    get_discovery_count,
    init_db,
    insert_source_discovery,
)
from pipeline.ollama_client import chat

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BRAND_EXTRACT_SYSTEM = """\
You extract brand or company names from article titles.
Return ONLY the brand/company name, nothing else.
If no brand is identifiable, return "UNKNOWN".
Do not add quotes or punctuation."""

KEYWORD_EXTRACT_SYSTEM = """\
Extract 2-4 search keywords from this article title.
Return ONLY the keywords separated by spaces, nothing else.
Omit the brand name. Focus on the product, technology, or trend described."""

# Domains to skip when looking for original sources
SKIP_DOMAINS = {
    "trendhunter.com",
    "www.trendhunter.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "reddit.com",
    "pinterest.com",
    "tiktok.com",
    "wikipedia.org",
    "en.wikipedia.org",
    "amazon.com",
}

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def brave_search(query: str, count: int = 5) -> list[dict]:
    """Search Brave and return list of {title, url, description}."""
    if not BRAVE_SEARCH_API_KEY:
        logger.warning("BRAVE_SEARCH_API_KEY not set, skipping web search")
        return []

    try:
        resp = httpx.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": count},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("web", {}).get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
            })
        return results
    except Exception as e:
        logger.error("Brave search failed for '%s': %s", query[:60], e)
        return []


def find_original_source(brand: str, title: str) -> dict | None:
    """Search for the original source of a Trendhunter radar entry.

    Returns {url, domain, title} of the best primary source, or None.
    """
    # Build search query: brand + keywords from title
    keywords = chat(
        model=MODEL_FILTER,
        prompt=f"Extract search keywords from this title:\n\n{title}",
        system=KEYWORD_EXTRACT_SYSTEM,
        temperature=0.0,
    ).strip()

    query = f'"{brand}" {keywords}'
    results = brave_search(query)

    if not results:
        # Fallback: search with just the title
        results = brave_search(title)

    # Find first result that's not TH or social media
    for result in results:
        domain = urlparse(result["url"]).netloc.replace("www.", "")
        if domain not in SKIP_DOMAINS:
            return {
                "url": result["url"],
                "domain": domain,
                "title": result["title"],
            }

    return None


def extract_brand_from_title(title: str) -> str:
    """Use LLM to extract brand/company name from a Trendhunter RSS title."""
    prompt = f"Extract the brand or company name from this title:\n\n{title}"
    result = chat(
        model=MODEL_FILTER,
        prompt=prompt,
        system=BRAND_EXTRACT_SYSTEM,
        temperature=0.0,
    )
    brand = result.strip().strip('"').strip("'")
    return brand if brand and brand != "UNKNOWN" else ""


def get_radar_entries(vertical: str) -> list[dict]:
    """Get unprocessed radar entries for a vertical from the database."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT re.id, re.url, re.title, re.excerpt, s.vertical
            FROM raw_entries re
            JOIN sources s ON re.source_id = s.id
            WHERE s.source_type = 'radar'
            AND s.vertical = ?
            AND re.processed = 0
            AND re.filtered_out = 0
            ORDER BY re.fetched_at ASC
            LIMIT 100""",
            (vertical,),
        ).fetchall()
        return [dict(row) for row in rows]


def process_radar_entry(entry: dict) -> dict | None:
    """Process a single radar entry to discover the source."""
    title = entry["title"]
    url = entry["url"]
    vertical = entry["vertical"]

    # Extract brand name
    brand = extract_brand_from_title(title)
    if not brand:
        logger.info("No brand found in: %s", title[:80])
        return None

    # Search for original source
    original = find_original_source(brand, title)

    discovered_url = original["url"] if original else url
    discovered_domain = original["domain"] if original else urlparse(url).netloc

    discovery = {
        "radar_source": "trendhunter",
        "radar_vertical": vertical,
        "original_title": title,
        "extracted_brand": brand,
        "discovered_url": discovered_url,
        "discovered_domain": discovered_domain,
        "has_rss_feed": False,
    }

    discovery_id = insert_source_discovery(discovery)
    count = get_discovery_count(discovered_domain)

    if original:
        logger.info(
            "Found original source for '%s': %s (domain: %s, seen %d times)",
            brand, original["url"][:80], discovered_domain, count,
        )

        # Update the raw_entry URL to point to the original source
        with get_connection() as conn:
            conn.execute(
                "UPDATE raw_entries SET url = ? WHERE id = ?",
                (original["url"], entry["id"]),
            )
    else:
        logger.warning(
            "No original source found for '%s' (%s) — filtering out",
            brand, title[:60],
        )
        # Filter out entries where we can't find the original source
        with get_connection() as conn:
            conn.execute(
                "UPDATE raw_entries SET filtered_out = 1, filter_reason = 'no_original_source' WHERE id = ?",
                (entry["id"],),
            )

    if count >= 3:
        logger.info(
            "Domain %s seen %d times — candidate for direct RSS source",
            discovered_domain, count,
        )

    return discovery


def run_radar(verticals: list[str] | None = None):
    """Run the radar discovery pipeline."""
    init_db()
    sources_config = load_sources()

    total_discovered = 0
    total_processed = 0
    total_found = 0

    for vertical, config in sources_config.get("verticals", {}).items():
        if verticals and vertical not in verticals:
            continue

        if not config.get("radar"):
            continue

        entries = get_radar_entries(vertical)
        if not entries:
            logger.info("%s: no unprocessed radar entries", vertical)
            continue

        logger.info("%s: processing %d radar entries", vertical, len(entries))

        for entry in entries:
            total_processed += 1
            result = process_radar_entry(entry)
            if result:
                total_discovered += 1
                if result["discovered_domain"] != "www.trendhunter.com":
                    total_found += 1

            # Mark as processed
            with get_connection() as conn:
                conn.execute(
                    "UPDATE raw_entries SET processed = 1 WHERE id = ?",
                    (entry["id"],),
                )

            # Rate limit: Brave free plan = 1 req/sec
            time.sleep(1.1)

    logger.info(
        "Radar complete: %d processed, %d brands discovered, %d original sources found",
        total_processed, total_discovered, total_found,
    )
    return {
        "processed": total_processed,
        "discovered": total_discovered,
        "original_sources_found": total_found,
    }


if __name__ == "__main__":
    target_verticals = sys.argv[1:] if len(sys.argv) > 1 else None
    run_radar(target_verticals)
