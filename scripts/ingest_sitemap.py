#!/usr/bin/env python3
"""Ingest historical articles from a publisher's XML sitemap (fallback path).

For sources that are neither WordPress nor academic. Discovers article URLs and
`lastmod` dates from /sitemap.xml (or a sitemap index), filters to the date
range, and fetches each page's og:title/og:description for a usable excerpt
(rate-limited per domain). Lower-priority / lower-yield than WP-API + OpenAlex.

Usage:
    python scripts/ingest_sitemap.py --source-name "Carbon Brief" \
        --after 2018-01-01 --before 2023-01-01 --dry-run
"""
from __future__ import annotations
import argparse
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline import db
from pipeline.config import load_sources
from pipeline.radar_discovery import domain_of

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xml,*/*"}
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_URL_BLOCK = re.compile(r"<url>(.*?)</url>", re.I | re.S)
_LASTMOD = re.compile(r"<lastmod>\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", re.I)
_OG = lambda prop: re.compile(  # noqa: E731
    rf'property=["\']og:{prop}["\']\s+content=["\']([^"\']*)', re.I)


def find_source_entry(name: str) -> dict | None:
    cfg = load_sources()
    for vert, groups in cfg.get("verticals", {}).items():
        for key in ("sources", "science"):
            for s in groups.get(key, []) or []:
                if isinstance(s, dict) and s.get("name") == name:
                    return {**s, "vertical": vert}
    for grp in cfg.get("cross_industry", {}).values():
        if isinstance(grp, list):
            for s in grp:
                if isinstance(s, dict) and s.get("name") == name:
                    return {**s, "vertical": "CROSS"}
    return None


def fetch(client, url):
    try:
        r = client.get(url, timeout=25, follow_redirects=True)
        return r.text if r.status_code == 200 else ""
    except Exception:
        return ""


def discover(client, domain, after, before) -> list[tuple[str, str]]:
    """Return [(url, lastmod)] in [after, before) from the sitemap tree."""
    seen, out = set(), []
    queue = [f"https://{domain}/sitemap.xml", f"https://{domain}/sitemap_index.xml"]
    visited = set()
    while queue:
        sm = queue.pop()
        if sm in visited:
            continue
        visited.add(sm)
        xml = fetch(client, sm)
        if not xml:
            continue
        if "<sitemapindex" in xml.lower():
            queue.extend(loc for loc in _LOC.findall(xml) if loc not in visited)
            continue
        for block in _URL_BLOCK.findall(xml):
            loc = _LOC.search(block)
            lm = _LASTMOD.search(block)
            if not loc:
                continue
            url, date = loc.group(1).strip(), (lm.group(1) if lm else None)
            if url in seen:
                continue
            if date and not (after <= date < before):
                continue
            seen.add(url)
            out.append((url, date))
        if len(visited) > 60:  # bound the crawl
            break
    return out


def og_meta(client, url):
    html = fetch(client, url)
    if not html:
        return "", ""
    t = _OG("title").search(html)
    d = _OG("description").search(html)
    return (t.group(1) if t else "").strip(), (d.group(1) if d else "").strip()


def ingest(name, after, before, dry_run, max_fetch=300) -> dict:
    src = find_source_entry(name)
    if not src:
        logger.error("source '%s' not in sources.yaml", name)
        return {}
    domain = domain_of(src.get("feed_url", ""))
    vertical = src["vertical"]
    stats = {"urls": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    with httpx.Client(headers=HEADERS) as client:
        urls = discover(client, domain, after, before)
        stats["urls"] = len(urls)
        logger.info("[sitemap] %s (%s): %d URLs in range", name, domain, len(urls))
        if dry_run:
            print(f"{name}: {len(urls)} sitemap URLs in range (dry-run, no fetch)")
            return stats
        source_id = db.upsert_source(name=name, feed_url=src["feed_url"],
                                     source_type=src.get("type", "trade_media"), vertical=vertical)
        for i, (url, date) in enumerate(urls[:max_fetch]):
            title, excerpt = og_meta(client, url)
            time.sleep(0.8)
            if not title:
                stats["skipped"] += 1
                continue
            eid = db.insert_raw_entry(source_id, url, title, excerpt[:2000], date)
            stats["duplicates" if eid is None else "inserted"] += 1
    print(f"{name}: {stats['urls']} URLs | inserted {stats['inserted']} | "
          f"{stats['duplicates']} dup | {stats['skipped']} skip")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-name", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--before", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-fetch", type=int, default=300)
    args = ap.parse_args()
    ingest(args.source_name, args.after, args.before, args.dry_run, args.max_fetch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
