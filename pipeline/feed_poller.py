#!/usr/bin/env python3
"""RSS Feed Poller for Catandary Trends.

Fetches RSS/Atom feeds from configured sources and stores new entries in the database.
"""

import html
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

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

# Honest crawler identity (compliance review 2026-09-02): product token, a URL
# that explains what the bot does, and a mailbox for complaints — overridable
# via CRAWLER_USER_AGENT, default identical to pipeline.article_fetcher (tested).
# No browser spoofing any more: until 2026-09-02 the poller announced itself as
# Chrome because a few sources (Endpoints, FDA, idw) 403 plain bot UAs. A
# publisher that blocks bots is expressing a wish, and the repo principle is to
# respect it — such feeds now surface as 403 warnings (see fetch_feed) and are
# handled per source (contact the publisher or deactivate), not by disguise.
# There is no per-source `user_agent` field in sources.yaml; the value is global.
# 30s timeout covers slow feeds (idw ~20s).
DEFAULT_USER_AGENT = ("CatandaryTrendsBot/1.0 "
                      "(+https://catandary.de/trends/methodology; trends@catandary.de)")
USER_AGENT = os.getenv("CRAWLER_USER_AGENT", DEFAULT_USER_AGENT)
HTTP_CLIENT = httpx.Client(
    timeout=30,
    follow_redirects=True,
    headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    },
)

# Retry a 403/406 once with the short token: some WAF rules trip on the URL or
# the "@" in the full identity string, not on the bot itself. Still honest —
# never a browser string.
FALLBACK_UA = "CatandaryTrendsBot/1.0 (RSS Feed Reader)"


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
            if resp.status_code in (403, 406):
                # Bot block with an honest UA. By policy (compliance review
                # 2026-09-02) we do not disguise as a browser — decide per
                # source: ask the publisher, or set `active: false`.
                logger.warning("%s: HTTP %d for %s — publisher blocks non-browser "
                               "clients; no browser spoof by policy",
                               source_name, resp.status_code, FALLBACK_UA.split(" ")[0])
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
        # (see normalize_entry_url below for why entry links get validated)

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        entries = []
        for entry in feed.entries:
            url = normalize_entry_url(entry.get("link"), feed_url)
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


def normalize_entry_url(raw: str | None, feed_url: str) -> str | None:
    """Repair or reject a feed's entry link. Returns None if it cannot resolve.

    Feed links are not trustworthy and a dead backlink breaks the source
    attribution the whole free layer rests on, so entries we cannot cite are
    dropped at ingest rather than published with a broken link. Two real defects
    seen in production:

    - HOST 'undefined' (William Reed feeds): "https://www.foodnavigator.comundefined?..."
      — a JS `undefined` spliced in where the path belongs, leaving an empty
      path and a nonexistent host. Unrecoverable.
    - SITE-RELATIVE links (Harvard Business Review): "/2026/07/some-slug" with no
      host. Recoverable against the feed's own URL.

    Detection is deliberately narrow: it keys on the HOSTNAME ending in
    undefined/null, NOT on the string appearing anywhere. Three legitimate
    articles in the corpus carry "undefined" in the path as a real word
    (designboom's "undefined playground", semiengineering's "undefined state
    fault") — a substring filter would destroy those working links.
    """
    url = (raw or "").strip()
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    elif not url.lower().startswith(("http://", "https://")):
        url = urljoin(feed_url, url)          # site-relative → resolve against the feed
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    if host.endswith(("undefined", "null")) or not parsed.path.strip("/"):
        # A host-only link cites the homepage, not the article — it is not a
        # source reference, and by the next poll it points at unrelated content.
        return None
    return url


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
