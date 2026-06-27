#!/usr/bin/env python3
"""RSS Feed Poller for Catandary Trends.

Fetches RSS/Atom feeds from configured sources and stores new entries in the database.
"""

import html
import logging
import re
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

# Browser-style UA: several quality sources (Endpoints, FDA, idw) serve
# 403/redirects to plain bot UAs. 30s timeout covers slow feeds (idw ~20s).
HTTP_CLIENT = httpx.Client(
    timeout=30,
    follow_redirects=True,
    headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36 "
                      "CatandaryTrends/1.0 (RSS Feed Reader)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    },
)

# Some publishers (e.g. Just Food) allow plain feed readers but block
# browser UAs — the inverse of bot-protected sites. Retry 403s with this.
FALLBACK_UA = "CatandaryTrends/1.0 (RSS Feed Reader)"


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
        if resp.status_code in (403, 406):
            resp = HTTP_CLIENT.get(feed_url, headers={"User-Agent": FALLBACK_UA})
        if resp.status_code >= 500:
            # transient upstream errors (idw etc.) — one retry after backoff
            time.sleep(3)
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


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return html.unescape(_TAG_RE.sub("", s or "")).strip()


def fetch_wp_categories(source_name: str, feed_url: str, categories: str) -> list[dict]:
    """Poll a curated WP source via the REST API scoped to its foresight-value
    categories (sources.yaml `wp_categories`) — so the noise the RSS firehose
    carries is never fetched. Recent window (90 days, matching the RSS cutoff),
    one page of 100 newest posts. Falls back to RSS on any error."""
    from pipeline.radar_discovery import domain_of
    domain = domain_of(feed_url)
    after = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00")
    try:
        resp = HTTP_CLIENT.get(f"https://{domain}/wp-json/wp/v2/posts", params={
            "categories": categories, "after": after, "per_page": 100,
            "orderby": "date", "order": "desc",
            "_fields": "date,link,title,excerpt,content",
        })
        if resp.status_code != 200:
            logger.warning("%s: WP-API HTTP %d — falling back to RSS", source_name, resp.status_code)
            return fetch_feed(source_name, feed_url)
        posts = resp.json()
    except Exception as e:
        logger.warning("%s: WP-API fetch failed (%s) — falling back to RSS", source_name, e)
        return fetch_feed(source_name, feed_url)
    entries = []
    for p in posts:
        url = (p.get("link") or "").strip()
        title = _strip_html(p.get("title", {}).get("rendered", ""))
        if not url or not title:
            continue
        excerpt = _strip_html(p.get("excerpt", {}).get("rendered", "")) \
            or _strip_html(p.get("content", {}).get("rendered", ""))[:2000]
        pub = (p.get("date") or "")[:19].replace("T", " ")
        entries.append({"url": url, "title": title, "excerpt": excerpt[:2000],
                        "published_date": pub or None})
    logger.info("%s: fetched %d entries (WP-API, foresight categories)", source_name, len(entries))
    return entries


def fetch_source(source_cfg: dict, source_name: str, feed_url: str) -> list[dict]:
    """Dispatch: curated WP sources (wp_categories set) → category-scoped WP-API;
    everything else → RSS. Keeps the foresight curation identical across backfill,
    frontfill and the poller."""
    cats = source_cfg.get("wp_categories")
    if cats:
        cats_str = ",".join(str(x) for x in cats) if isinstance(cats, (list, tuple)) else str(cats)
        return fetch_wp_categories(source_name, feed_url, cats_str)
    return fetch_feed(source_name, feed_url)


VALID_LEAD_TIME_TIERS = {"future", "market", "now"}


def warn_if_missing_tier(source_cfg: dict) -> None:
    """Warn if a source lacks the `lead_time_tier` field and suggest a fix.

    The lead_time_tier is used downstream by the (planned) structural-vs-hype
    score (see BACKLOG.md). Missing tiers break that scoring silently, so we
    surface them at poll time when the source is first observed.
    """
    tier = source_cfg.get("lead_time_tier")
    if tier in VALID_LEAD_TIME_TIERS:
        return

    name = source_cfg.get("name", "<unnamed>")
    stype = source_cfg.get("type", "trade_media")
    # Suggest a sensible default based on source type
    if stype == "research":
        suggested = "future"
        rationale = "research/academic → ~5-10y lead time"
    elif stype == "press_wire":
        suggested = "market"
        rationale = "press wire / corporate announcements → ~1-2y lead time"
    else:
        suggested = "market"
        rationale = (
            "trade_media default; use 'now' for consumer/lifestyle/fashion "
            "real-time culture (e.g. Hypebeast, Vogue UK) or 'future' for "
            "deep-analytical (e.g. MIT Tech Review, Carbon Brief)"
        )

    if tier is None:
        logger.warning(
            "Source '%s' has no `lead_time_tier`. Add to sources.yaml:\n"
            "        lead_time_tier: %s   # %s",
            name, suggested, rationale,
        )
    else:
        logger.warning(
            "Source '%s' has invalid lead_time_tier=%r. "
            "Must be one of %s. Suggested: %s (%s)",
            name, tier, sorted(VALID_LEAD_TIME_TIERS), suggested, rationale,
        )


def poll_vertical_sources(vertical: str, config: dict) -> dict:
    """Poll all sources for a single vertical. Returns stats."""
    stats = {"fetched": 0, "new": 0, "duplicate": 0, "errors": 0}

    all_sources = config.get("sources", []) + config.get("science", []) + config.get("radar", [])

    for source_cfg in all_sources:
        if source_cfg.get("active") is False:
            continue
        source_name = source_cfg["name"]
        feed_url = source_cfg["feed_url"]
        source_type = source_cfg.get("type", "trade_media")
        warn_if_missing_tier(source_cfg)

        source_id = upsert_source(source_name, feed_url, source_type, vertical)

        entries = fetch_source(source_cfg, source_name, feed_url)
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
            if source_cfg.get("active") is False:
                continue

            source_name = source_cfg["name"]
            feed_url = source_cfg["feed_url"]
            source_type = source_cfg.get("type", "press_wire")
            warn_if_missing_tier(source_cfg)

            source_id = upsert_source(source_name, feed_url, source_type, "CROSS")

            entries = fetch_source(source_cfg, source_name, feed_url)
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
