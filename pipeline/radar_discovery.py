#!/usr/bin/env python3
"""Trendhunter Radar Discovery Pipeline.

Processes Trendhunter RSS feed entries to discover original brand sources:
1. Extract brand name from RSS title via LLM
2. Log discovery with domain info
3. Track domain frequency for potential RSS source addition
"""

import logging
import sys
from urllib.parse import urlparse

from pipeline.config import LOG_LEVEL, MODEL_FILTER, load_sources
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

    # Extract domain from the Trendhunter link (the entry URL points to TH)
    # The actual original source domain would need web search in production.
    # For now, we log the brand discovery for later manual/automated source finding.
    domain = urlparse(url).netloc

    discovery = {
        "radar_source": "trendhunter",
        "radar_vertical": vertical,
        "original_title": title,
        "extracted_brand": brand,
        "discovered_url": url,
        "discovered_domain": domain,
    }

    discovery_id = insert_source_discovery(discovery)
    count = get_discovery_count(domain)

    logger.info(
        "Discovered brand '%s' from '%s' (domain: %s, seen %d times)",
        brand, title[:60], domain, count,
    )

    if count >= 3:
        logger.info(
            "Domain %s seen %d times – candidate for direct RSS source",
            domain, count,
        )

    return discovery


def run_radar(verticals: list[str] | None = None):
    """Run the radar discovery pipeline."""
    init_db()
    sources_config = load_sources()

    total_discovered = 0
    total_processed = 0

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

            # Mark as processed (radar entries go through discovery, not the LLM pipeline)
            with get_connection() as conn:
                conn.execute(
                    "UPDATE raw_entries SET processed = 1 WHERE id = ?",
                    (entry["id"],),
                )

    logger.info(
        "Radar complete: %d processed, %d brands discovered",
        total_processed, total_discovered,
    )
    return {"processed": total_processed, "discovered": total_discovered}


if __name__ == "__main__":
    target_verticals = sys.argv[1:] if len(sys.argv) > 1 else None
    run_radar(target_verticals)
