#!/usr/bin/env python3
"""
LEGACY (2026-09-06): braucht FIRECRAWL_API_KEY — der Schluessel ist widerrufen,
der Pfad seit 2026-06 durch WP-API/OpenAlex abgeloest. Wer ihn reaktiviert, legt
bei Firecrawl einen neuen Schluessel an und traegt ihn in .env ein.

Historical signal backfill for Catandary Trends.

Discovers historical article URLs from the publishers we already follow and
inserts them into raw_entries (processed=0). The existing LLM pipeline picks
them up in the next nightly run or via `python -m pipeline.llm_processor <N>`.

Two modes:

  --mode brave  (default, Phase 1)
      Brave Search `site:<domain> freshness=py` discovers URLs from the last
      ~12 months. Excerpt = Brave snippet (~200 chars). 0 Firecrawl credits.

  --mode deep   (Phase 2, credit-aware)
      Firecrawl /map discovers all URLs on the publisher site; /scrape fetches
      article content as markdown excerpt. ~1 credit per URL scraped.
      Free plan: ~1000 credits/month. Use --vertical or --source-name to limit
      scope; check with --dry-run before running.

Usage:
    # Phase 1 — all sources, last 12 months, 0 Firecrawl credits
    python scripts/backfill_sources.py --mode brave --skip-noisy

    # Phase 2 — one vertical at a time, full history
    python scripts/backfill_sources.py --mode deep --dry-run
    python scripts/backfill_sources.py --mode deep --vertical FOOD --max-per-source 20
"""
from __future__ import annotations

import argparse
import calendar
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

# Make sure pipeline package is importable when run as a script.
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db
from pipeline.config import BRAVE_SEARCH_API_KEY, FIRECRAWL_API_KEY, load_sources
from pipeline.radar_discovery import brave_search, domain_of

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

RATE_LIMIT_SECONDS = 1.1  # Brave free tier: 1 req/s
DEEP_MAP_RATE_SECONDS = 11  # Firecrawl free tier: 6 /map per minute -> 1 per 11s

NOISY_SOURCE_NAMES = {
    "GlobeNewswire",
    "Guardian Food",
    "Guardian Culture",
    "Guardian Fashion",
    "Guardian Environment",
    "EU Parliament Press",
}

# Path segments that indicate non-article pages.
_SKIP_PATH_FRAGMENTS = (
    "/feed", "/rss", "/category/", "/tag/", "/author/", "/page/",
    "/search", "/sitemap", "/wp-content/", "/wp-json/",
    ".xml", ".css", ".js", ".pdf", ".jpg", ".png", ".gif", ".svg",
)


# ---------------------------------------------------------------------------
# Source enumeration
# ---------------------------------------------------------------------------

def iter_sources(
    config: dict,
    vertical_filter: str | None,
    source_name_filter: str | None,
    skip_noisy: bool,
) -> list[dict]:
    """Flatten sources.yaml into source dicts with injected 'vertical' key.

    Excludes: inactive, press_wire, api type sources.
    """
    result: list[dict] = []

    # Verticals block
    for vertical, groups in config.get("verticals", {}).items():
        if vertical_filter and vertical != vertical_filter:
            continue
        for sub_key in ("sources", "science"):
            for src in groups.get(sub_key, []) or []:
                if not isinstance(src, dict):
                    continue
                if src.get("active") is False:
                    continue
                if src.get("type") in ("press_wire", "api"):
                    continue
                if skip_noisy and src.get("name") in NOISY_SOURCE_NAMES:
                    continue
                if source_name_filter and src.get("name") != source_name_filter:
                    continue
                result.append({**src, "vertical": vertical})

    # Cross-industry block (only when no vertical filter)
    if not vertical_filter:
        for group_sources in config.get("cross_industry", {}).values():
            if not isinstance(group_sources, list):
                continue
            for src in group_sources:
                if not isinstance(src, dict):
                    continue
                if src.get("active") is False:
                    continue
                if src.get("type") in ("press_wire", "api"):
                    continue
                if skip_noisy and src.get("name") in NOISY_SOURCE_NAMES:
                    continue
                if source_name_filter and src.get("name") != source_name_filter:
                    continue
                result.append({**src, "vertical": "CROSS"})

    return result


# ---------------------------------------------------------------------------
# Date-window slicing (for historical depth beyond Brave's `py` = 12 months)
# ---------------------------------------------------------------------------

def _shift_months(d: date, months: int) -> date:
    """Return d shifted back by `months` (clamped to a valid day-of-month)."""
    total = d.month - 1 - months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_date_windows(months_back: int, today: date,
                       window_months: int = 6) -> list[str]:
    """Slice [today - months_back, today] into Brave freshness ranges.

    Brave's `freshness` only offers presets up to `py` (past year). To reach
    further back we pass explicit `YYYY-MM-DDtoYYYY-MM-DD` ranges, one per
    window, newest first. Each window is queried separately so historical
    articles actually surface (a single wide query only returns the top ~20
    by relevance, skewed to recent).
    """
    floor = _shift_months(today, months_back)
    windows: list[str] = []
    cur_end = today
    while cur_end > floor:
        cur_start = max(_shift_months(cur_end, window_months), floor)
        windows.append(f"{cur_start.isoformat()}to{cur_end.isoformat()}")
        cur_end = cur_start - timedelta(days=1)
    return windows


# ---------------------------------------------------------------------------
# URL filtering
# ---------------------------------------------------------------------------

def _parse_page_age(page_age: str) -> str | None:
    """Normalize Brave's `page_age` (ISO 8601) to a 'YYYY-MM-DD HH:MM:SS' string.

    Brave returns e.g. '2024-06-06T12:00:00' or '2024-06-06'. Anything we can't
    parse becomes None so the row stays honestly undated rather than mis-dated.
    """
    page_age = (page_age or "").strip()
    if not page_age:
        return None
    iso = page_age.replace("Z", "").replace("T", " ")
    head = iso[:19] if len(iso) >= 19 else iso[:10]
    try:
        if len(head) >= 19:
            date.fromisoformat(head[:10])  # validate date part
            return head
        date.fromisoformat(head[:10])
        return head[:10]
    except ValueError:
        return None


_URL_DATE_RE = re.compile(r"/(20\d{2})[/-](\d{1,2})(?:[/-](\d{1,2}))?")


def _date_from_url(url: str) -> str | None:
    """Extract a publication date from a /YYYY/MM[/DD]/ style URL path.

    Most news publishers date-stamp article URLs (e.g. /Article/2023/11/09/...).
    Returns 'YYYY-MM-DD' if a plausible past date is found, else None — so the
    deep backfill positions historical articles correctly in the timeline
    instead of dating them to ingestion day.
    """
    m = _URL_DATE_RE.search(urlparse(url).path)
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    try:
        dt = date(year, month, day)
    except ValueError:
        return None
    if dt > date.today():
        return None
    return dt.isoformat()


def is_article_url(url: str, domain: str) -> bool:
    """Return True if the URL looks like a publisher article (not a page/feed/asset)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if domain not in parsed.netloc.lower():
        return False
    path = parsed.path.lower()
    for fragment in _SKIP_PATH_FRAGMENTS:
        if fragment in path:
            return False
    segments = [s for s in path.split("/") if s]
    return len(segments) >= 1


# ---------------------------------------------------------------------------
# Mode 1: Brave Search
# ---------------------------------------------------------------------------

def backfill_brave(
    source: dict,
    source_id: int,
    max_per_source: int,
    dry_run: bool,
    freshness_windows: list[str] | None = None,
) -> dict:
    """Brave Search `site:<domain>` → insert raw_entries. 0 Firecrawl credits.

    Without `freshness_windows` a single `py` (past-year) query runs. With
    windows (from build_date_windows) one query per window runs, newest first,
    accumulating up to `max_per_source` unique article URLs across all windows.
    """
    domain = domain_of(source["feed_url"])
    query = f"site:{domain}"
    windows = freshness_windows or ["py"]

    stats: dict = {"results": 0, "queries": 0, "inserted": 0,
                   "duplicates": 0, "errors": 0}
    seen: set[str] = set()

    for fr in windows:
        if len(seen) >= max_per_source:
            break
        remaining = max_per_source - len(seen)
        results = brave_search(query, count=min(remaining, 20), freshness=fr)
        stats["queries"] += 1
        stats["results"] += len(results)
        time.sleep(RATE_LIMIT_SECONDS)

        for r in results:
            url = (r.get("url") or "").strip()
            title = (r.get("title") or "").strip()
            excerpt = (r.get("description") or "").strip()[:2000]
            published_date = _parse_page_age(r.get("page_age", ""))

            if not url or not title:
                continue
            if not is_article_url(url, domain):
                continue
            if url in seen:
                continue
            seen.add(url)
            if published_date is not None:
                stats["dated"] = stats.get("dated", 0) + 1

            if dry_run:
                stats["inserted"] += 1
            else:
                try:
                    entry_id = db.insert_raw_entry(source_id, url, title, excerpt, published_date)
                    if entry_id is None:
                        stats["duplicates"] += 1
                    else:
                        stats["inserted"] += 1
                except Exception as exc:
                    logger.debug("insert failed for %s: %s", url[:80], exc)
                    stats["errors"] += 1

            if len(seen) >= max_per_source:
                break

    return stats


# ---------------------------------------------------------------------------
# Mode 2: Firecrawl Deep
# ---------------------------------------------------------------------------

def _title_from_url(url: str) -> str:
    """Derive a fallback title from the URL path slug."""
    segments = [s for s in urlparse(url).path.split("/") if s]
    if not segments:
        return url
    return segments[-1].replace("-", " ").replace("_", " ")


def _extract_link(item) -> tuple[str, str, str]:
    """Extract (url, title, description) from a LinkResult, dict, or plain string."""
    if hasattr(item, "url"):
        url = item.url or ""
        title = getattr(item, "title", "") or ""
        desc = getattr(item, "description", "") or ""
    elif isinstance(item, dict):
        url = item.get("url", "")
        title = item.get("title", "")
        desc = item.get("description", "")
    else:
        url = str(item)
        title = ""
        desc = ""
    return url.strip(), title.strip(), desc.strip()


def backfill_deep(
    source: dict,
    source_id: int,
    max_per_source: int,
    workers: int,
    dry_run: bool,
) -> dict:
    """Firecrawl /map URL discovery + optional /scrape → insert raw_entries.

    If a LinkResult already carries a description, it is used as the excerpt
    directly (no scrape call, no credit cost beyond the map). Only items with
    an empty description are scraped for content.
    """
    try:
        from firecrawl import FirecrawlApp
    except ImportError:
        logger.error("firecrawl-py not installed: pip install firecrawl-py")
        return {"urls_found": 0, "inserted": 0, "duplicates": 0, "errors": 1, "credits_used": 0}

    if not FIRECRAWL_API_KEY:
        logger.error("FIRECRAWL_API_KEY not set in .env")
        return {"urls_found": 0, "inserted": 0, "duplicates": 0, "errors": 1, "credits_used": 0}

    app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    domain = domain_of(source["feed_url"])
    stats: dict = {"urls_found": 0, "inserted": 0, "duplicates": 0, "errors": 0, "credits_used": 0}

    # URL discovery via Firecrawl /map
    try:
        map_result = app.map_url(f"https://{domain}")
        # MapData object has .links; dict has "links" key; list is direct
        if hasattr(map_result, "links"):
            raw_items = map_result.links or []
        elif isinstance(map_result, dict):
            raw_items = map_result.get("links", [])
        elif isinstance(map_result, list):
            raw_items = map_result
        else:
            raw_items = []
    except Exception as exc:
        logger.error("firecrawl map failed for %s: %s", domain, exc)
        stats["errors"] += 1
        return stats

    stats["urls_found"] = len(raw_items)

    # Extract and filter
    candidates: list[tuple[str, str, str]] = []  # (url, title, excerpt)
    for item in raw_items:
        url, title, desc = _extract_link(item)
        if not url or not is_article_url(url, domain):
            continue
        if not title:
            title = _title_from_url(url)
        candidates.append((url, title, desc[:2000]))
        if len(candidates) >= max_per_source:
            break

    if dry_run:
        # Estimate: 1 scrape credit only for items without description
        needs_scrape = sum(1 for _, _, d in candidates if not d)
        stats["inserted"] = len(candidates)
        stats["credits_used"] = needs_scrape
        return stats

    # Items with description: insert directly (no scrape needed)
    to_scrape: list[tuple[str, str]] = []  # (url, title) needing content fetch
    for url, title, excerpt in candidates:
        if excerpt:
            try:
                entry_id = db.insert_raw_entry(source_id, url, title, excerpt, _date_from_url(url))
                if entry_id is None:
                    stats["duplicates"] += 1
                else:
                    stats["inserted"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.debug("insert failed for %s: %s", url[:80], exc)
        else:
            to_scrape.append((url, title))

    # Items without description: scrape for content (429-aware retry)
    def _scrape_and_insert(url: str, title: str) -> str:
        for attempt in range(3):
            try:
                result = app.scrape_url(url, params={"formats": ["markdown"]})
                if isinstance(result, dict):
                    md = result.get("markdown", "")
                else:
                    md = getattr(result, "markdown", "") or ""
                return (md or "")[:2000]
            except Exception as exc:
                msg = str(exc).lower()
                if ("rate limit" in msg or "429" in msg) and attempt < 2:
                    time.sleep(6 * (attempt + 1))
                    continue
                logger.debug("firecrawl scrape failed for %s: %s", url[:80], exc)
                return ""
        return ""

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_scrape_and_insert, url, title): (url, title)
                   for url, title in to_scrape}
        for future in as_completed(futures):
            url, title = futures[future]
            stats["credits_used"] += 1
            try:
                excerpt = future.result()
                entry_id = db.insert_raw_entry(source_id, url, title, excerpt, _date_from_url(url))
                if entry_id is None:
                    stats["duplicates"] += 1
                else:
                    stats["inserted"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.debug("error inserting %s: %s", url[:80], exc)

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Historical signal backfill via Brave Search or Firecrawl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--mode", choices=["brave", "deep"], default="brave",
                    help="brave: Brave Search + snippet (default); deep: Firecrawl map+scrape")
    ap.add_argument("--vertical", metavar="V",
                    help="Filter by vertical (FOOD, TECH, HEALTH, ECO, DESIGN, FASHION, BIZ, LIFESTYLE)")
    ap.add_argument("--source-name", metavar="NAME", help="Process a single source by name")
    ap.add_argument("--max-per-source", type=int, default=None,
                    help="Max URLs per source (default: 50 brave / 120 brave+months-back / 20 deep)")
    ap.add_argument("--months-back", type=int, default=None, metavar="N",
                    help="brave mode: reach N months back via 6-month date windows "
                         "(default off = single past-year query)")
    ap.add_argument("--window-months", type=int, default=6, metavar="M",
                    help="brave mode: size of each date window in months (default: 6)")
    ap.add_argument("--skip-noisy", action="store_true",
                    help="Skip known low-pass-rate feeds (Guardian sections, GlobeNewswire, ...)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Count without inserting. In deep mode: no Firecrawl API calls.")
    ap.add_argument("--workers", type=int, default=3,
                    help="Parallel workers for Firecrawl scrapes in deep mode (default: 3)")
    args = ap.parse_args()

    # Date windows for historical depth (brave only).
    freshness_windows: list[str] | None = None
    if args.mode == "brave" and args.months_back:
        freshness_windows = build_date_windows(
            args.months_back, date.today(), window_months=args.window_months)

    if args.max_per_source:
        max_per_source = args.max_per_source
    elif args.mode == "deep":
        max_per_source = 20
    elif freshness_windows:
        max_per_source = 120
    else:
        max_per_source = 50

    config = load_sources()
    sources = iter_sources(config, args.vertical, args.source_name, args.skip_noisy)

    if not sources:
        print("No sources matched the filter criteria.")
        sys.exit(0)

    print(f"[backfill] mode={args.mode} | {len(sources)} sources | "
          f"max_per_source={max_per_source} | dry_run={args.dry_run}")
    if freshness_windows:
        print(f"[brave] {args.months_back} months back via {len(freshness_windows)} "
              f"date windows ({args.window_months}-mo each): "
              f"{freshness_windows[-1].split('to')[0]} … {freshness_windows[0].split('to')[1]}")
        print(f"[brave] up to ~{len(sources) * len(freshness_windows)} Brave queries "
              f"(rate-limited at {RATE_LIMIT_SECONDS}s → "
              f"~{len(sources) * len(freshness_windows) * RATE_LIMIT_SECONDS / 60:.0f} min)")

    if args.mode == "deep":
        est = len(sources) * max_per_source
        print(f"[deep] ~{est} Firecrawl credits estimated (budget: ~1000/month). "
              f"Use --max-per-source to reduce.")

    if args.mode == "brave" and not BRAVE_SEARCH_API_KEY:
        print("ERROR: BRAVE_SEARCH_API_KEY not set in .env")
        sys.exit(1)
    if args.mode == "deep" and not FIRECRAWL_API_KEY:
        print("ERROR: FIRECRAWL_API_KEY not set in .env")
        sys.exit(1)

    totals: dict = {"inserted": 0, "duplicates": 0, "errors": 0, "credits_used": 0}
    no_results = 0

    for src in sources:
        vertical = src["vertical"]
        name = src.get("name", "?")
        domain = domain_of(src.get("feed_url", ""))

        if args.dry_run:
            source_id = -1
        else:
            source_id = db.upsert_source(
                name=src["name"],
                feed_url=src["feed_url"],
                source_type=src.get("type", "trade_media"),
                vertical=vertical,
            )

        if args.mode == "brave":
            stats = backfill_brave(src, source_id, max_per_source, args.dry_run,
                                   freshness_windows)
            print(f"  [{vertical}] {name} ({domain}): "
                  f"{stats['results']} results / {stats['queries']} queries → "
                  f"{stats['inserted']} inserted, {stats['duplicates']} dup, "
                  f"{stats['errors']} err")
            for k in ("inserted", "duplicates", "errors"):
                totals[k] += stats[k]
            totals["queries"] = totals.get("queries", 0) + stats["queries"]
            if stats["results"] == 0:
                no_results += 1
        else:
            stats = backfill_deep(src, source_id, max_per_source, args.workers, args.dry_run)
            print(f"  [{vertical}] {name} ({domain}): "
                  f"{stats['urls_found']} URLs found → "
                  f"{stats['inserted']} inserted, {stats['duplicates']} dup, "
                  f"{stats['credits_used']} credits")
            for k in ("inserted", "duplicates", "errors", "credits_used"):
                totals[k] += stats[k]
            # Firecrawl free tier: 6 /map per minute. Space calls to avoid 429s.
            time.sleep(DEEP_MAP_RATE_SECONDS)

    print()
    dry_tag = "[dry-run] Would insert" if args.dry_run else "Inserted"
    print(f"Backfill complete: {len(sources)} sources | "
          f"{dry_tag} {totals['inserted']} | "
          f"{totals['duplicates']} duplicates | "
          f"{totals['errors']} errors")
    if args.mode == "deep":
        print(f"  Firecrawl credits used: ~{totals['credits_used']}")
    if args.mode == "brave":
        print(f"  Brave queries issued: {totals.get('queries', 0)}")
    if no_results and args.mode == "brave":
        print(f"  {no_results} sources returned 0 Brave results")
    if not args.dry_run and totals["inserted"] > 0:
        print(f"\nNext step:")
        print(f"  python -m pipeline.llm_processor {totals['inserted']}")
        print(f"  or: nächster Nachtlauf draint Backlog automatisch (scheduled_cycle.sh Run 2)")


if __name__ == "__main__":
    main()
