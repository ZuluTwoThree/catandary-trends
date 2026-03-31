#!/usr/bin/env python3
"""RSS Feed Poller for Catandary Trends.

Fetches RSS/Atom feeds from configured sources and stores new entries in the database.
"""

import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import httpx

from pipeline.config import load_sources, LOG_LEVEL
from pipeline.db import (
    init_db, insert_raw_entry, update_source_last_fetched, upsert_source,
)

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

HTTP_CLIENT = httpx.Client(
    timeout=20,
    follow_redirects=True,
    headers={"User-Agent": "CatandaryTrends/1.0 (RSS Feed Reader)"},
)


def parse_published_date(entry: dict) -> str | None:
    """Extract and normalize published date from a feed entry."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            try:
                return datetime(*parsed[:6]).isoformat()
            except Exception:
                continue
    return None


def get_entry_excerpt(entry: dict) -> str:
    """Extract a clean excerpt/summary from a feed entry."""
    # Prefer summary, fall back to content snippet
    if entry.get("summary"):
        return entry["summary"][:2000]
    if entry.get("content"):
        return entry["content"][0].get("value", "")[:2000]
    return ""


def fetch_feed(source_name: str, feed_url: str) -> list[dict]:
    """Fetch and parse a single RSS/Atom feed."""
    try:
        resp = HTTP_CLIENT.get(feed_url)
        if resp.status_code != 200:
            logger.warning("%s: HTTP %d", source_name, resp.status_code)
            return []

        feed = feedparser.parse(resp.text)
        if feed.bozo and not feed.entries:
            logger.warning("%s: parse error: %s", source_name, feed.bozo_exception)
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        entries = []
        for entry in feed.entries:
            url = entry.get("link")
            title = entry.get("title", "").strip()
            if not url or not title:
                continue
            pub_date = parse_published_date(entry)
            # Skip entries older than 90 days
            if pub_date:
                try:
                    entry_dt = datetime.fromisoformat(pub_date).replace(tzinfo=timezone.utc)
                    if entry_dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            entries.append({
                "url": url,
                "title": title,
                "excerpt": get_entry_excerpt(entry),
                "published_date": pub_date,
            })

        logger.info("%s: fetched %d entries", source_name, len(entries))
        return entries

    except Exception as e:
        logger.error("%s: fetch failed: %s", source_name, e)
        return []


def poll_vertical_sources(vertical: str, config: dict) -> dict:
    """Poll all sources for a single vertical. Returns stats."""
    stats = {"fetched": 0, "new": 0, "duplicate": 0, "errors": 0}

    all_sources = config.get("sources", []) + config.get("radar", [])

    for source_cfg in all_sources:
        source_name = source_cfg["name"]
        feed_url = source_cfg["feed_url"]
        source_type = source_cfg.get("type", "trade_media")

        source_id = upsert_source(source_name, feed_url, source_type, vertical)

        entries = fetch_feed(source_name, feed_url)
        stats["fetched"] += len(entries)

        for entry in entries:
            entry_id = insert_raw_entry(
                source_id=source_id,
                url=entry["url"],
                title=entry["title"],
                excerpt=entry["excerpt"],
                published_date=entry["published_date"],
            )
            if entry_id:
                stats["new"] += 1
            else:
                stats["duplicate"] += 1

        update_source_last_fetched(source_id)

    return stats


def poll_cross_industry(config: dict) -> dict:
    """Poll cross-industry sources (press wires, APIs)."""
    stats = {"fetched": 0, "new": 0, "duplicate": 0, "errors": 0}

    for category_sources in config.values():
        for source_cfg in category_sources:
            if source_cfg.get("type") == "api":
                continue  # API sources handled separately

            source_name = source_cfg["name"]
            feed_url = source_cfg["feed_url"]
            source_type = source_cfg.get("type", "press_wire")

            source_id = upsert_source(source_name, feed_url, source_type, "CROSS")

            entries = fetch_feed(source_name, feed_url)
            stats["fetched"] += len(entries)

            for entry in entries:
                entry_id = insert_raw_entry(
                    source_id=source_id,
                    url=entry["url"],
                    title=entry["title"],
                    excerpt=entry["excerpt"],
                    published_date=entry["published_date"],
                )
                if entry_id:
                    stats["new"] += 1
                else:
                    stats["duplicate"] += 1

            update_source_last_fetched(source_id)

    return stats


def run_poll(verticals: list[str] | None = None):
    """Run a full poll cycle.

    Args:
        verticals: Optional list of vertical codes to poll. If None, polls all.
    """
    start = time.time()
    init_db()

    sources_config = load_sources()
    total_stats = {"fetched": 0, "new": 0, "duplicate": 0, "errors": 0}

    # Poll vertical sources
    for vertical, config in sources_config.get("verticals", {}).items():
        if verticals and vertical not in verticals:
            continue
        logger.info("Polling vertical: %s", vertical)
        stats = poll_vertical_sources(vertical, config)
        for k in total_stats:
            total_stats[k] += stats[k]

    # Poll cross-industry sources
    if not verticals or "CROSS" in verticals:
        logger.info("Polling cross-industry sources")
        cross_config = sources_config.get("cross_industry", {})
        if cross_config:
            stats = poll_cross_industry(cross_config)
            for k in total_stats:
                total_stats[k] += stats[k]

    elapsed = time.time() - start
    logger.info(
        "Poll complete in %.1fs: %d fetched, %d new, %d duplicates",
        elapsed, total_stats["fetched"], total_stats["new"], total_stats["duplicate"],
    )
    return total_stats


if __name__ == "__main__":
    # Optional: pass vertical codes as arguments
    target_verticals = sys.argv[1:] if len(sys.argv) > 1 else None
    run_poll(target_verticals)
