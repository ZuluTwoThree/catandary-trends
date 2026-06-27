#!/usr/bin/env python3
"""Ingest historical posts from a WordPress site's REST API into raw_entries.

Many trade-media sites run WordPress and expose /wp-json/wp/v2/posts — a free,
paginated JSON feed carrying date, title, excerpt and full content. This gives
dated historical signals with zero scraping/LLM/Firecrawl cost, far cheaper
than the Firecrawl deep crawl.

The date range is chunked per-month so we never hit WordPress' deep-pagination
ceiling, and each post is inserted with its real publication date.

Usage:
    python scripts/ingest_wordpress.py --source-name vegconomist \
        --after 2018-01-01 --before 2023-01-01 --dry-run
    python scripts/ingest_wordpress.py --source-name vegconomist \
        --after 2018-01-01 --before 2023-01-01
"""
from __future__ import annotations
import argparse, html, re, sys, time
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline import db
from pipeline.config import load_sources
from pipeline.radar_discovery import domain_of

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CatandaryBot/1.0; +https://catandary.de)"}
_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s: str) -> str:
    return html.unescape(_TAG_RE.sub("", s or "")).strip()


def find_source(name: str) -> dict | None:
    cfg = load_sources()
    for vert, groups in cfg.get("verticals", {}).items():
        for key in ("sources", "science"):
            for s in groups.get(key, []) or []:
                if isinstance(s, dict) and s.get("name") == name:
                    return {**s, "vertical": vert}
    return None


def month_chunks(after: str, before: str):
    """Yield (start, end) ISO datetimes per calendar month in [after, before)."""
    y, m = int(after[:4]), int(after[5:7])
    end = date.fromisoformat(before)
    while date(y, m, 1) < end:
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        start = date(y, m, 1)
        stop = min(date(ny, nm, 1), end)
        yield f"{start.isoformat()}T00:00:00", f"{stop.isoformat()}T00:00:00"
        y, m = ny, nm


def fetch_month(client, base, after, before, cap=None, categories=None, categories_exclude=None):
    """Fetch a month's posts. `cap` limits posts/month (for noisy high-volume
    sources) — stops paginating once `cap` is reached (oldest-first).
    `categories` / `categories_exclude` are comma-separated WP category IDs for
    server-side topic scoping (e.g. keep Foodtech, drop Delivery & Commerce) so
    noise is never even fetched."""
    posts, page = [], 1
    per_page = min(100, cap) if cap else 100
    cat_params = {}
    if categories:
        cat_params["categories"] = categories
    if categories_exclude:
        cat_params["categories_exclude"] = categories_exclude
    while True:
        try:
            r = client.get(f"{base}/wp-json/wp/v2/posts", params={
                "after": after, "before": before, "per_page": per_page, "page": page,
                "_fields": "date,link,title,excerpt,content", "orderby": "date", "order": "asc",
                **cat_params,
            }, timeout=30, follow_redirects=True)
        except Exception as exc:
            print(f"    fetch error {after[:7]} p{page}: {type(exc).__name__}")
            break
        if r.status_code == 400:  # page beyond range
            break
        if r.status_code != 200:
            print(f"    HTTP {r.status_code} {after[:7]} p{page}")
            break
        batch = r.json()
        if not batch:
            break
        posts.extend(batch)
        if cap and len(posts) >= cap:
            return posts[:cap]
        if page >= int(r.headers.get("X-WP-TotalPages", 1)):
            break
        page += 1
        time.sleep(0.3)
    return posts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-name", required=True)
    ap.add_argument("--base-url", help="override; else derived from sources.yaml feed_url")
    ap.add_argument("--after", required=True, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--before", required=True, help="YYYY-MM-DD (exclusive)")
    ap.add_argument("--max-per-month", type=int, help="cap posts/month (overrides sources.yaml ingest_cap)")
    ap.add_argument("--categories", help="comma-sep WP category IDs to INCLUDE (overrides sources.yaml wp_categories)")
    ap.add_argument("--categories-exclude", help="comma-sep WP category IDs to EXCLUDE (overrides wp_categories_exclude)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    def _csv(v):
        if v is None:
            return None
        return ",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)

    src = find_source(args.source_name)
    if not src and not args.base_url:
        print(f"Quelle '{args.source_name}' nicht in sources.yaml und kein --base-url"); sys.exit(1)
    base = args.base_url or f"https://{domain_of(src['feed_url'])}"
    vertical = src["vertical"] if src else "FOOD"
    cap = args.max_per_month or (src or {}).get("ingest_cap")  # per-source cap for noisy giants
    categories = args.categories or _csv((src or {}).get("wp_categories"))
    categories_exclude = args.categories_exclude or _csv((src or {}).get("wp_categories_exclude"))
    catinfo = (f" | cats={categories}" if categories else "") + \
              (f" | cats_excl={categories_exclude}" if categories_exclude else "")
    print(f"[wp] {args.source_name} @ {base} | {args.after} .. {args.before} | "
          f"dry_run={args.dry_run}{f' | cap={cap}/month' if cap else ''}{catinfo}")

    source_id = -1 if args.dry_run else db.upsert_source(
        name=args.source_name, feed_url=(src or {}).get("feed_url", base),
        source_type=(src or {}).get("type", "trade_media"), vertical=vertical)

    stats = {"fetched": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    with httpx.Client(headers=HEADERS) as client:
        for after, before in month_chunks(args.after, args.before):
            posts = fetch_month(client, base, after, before, cap=cap,
                                categories=categories, categories_exclude=categories_exclude)
            stats["fetched"] += len(posts)
            for p in posts:
                url = (p.get("link") or "").strip()
                title = strip_html(p.get("title", {}).get("rendered", ""))
                excerpt = strip_html(p.get("excerpt", {}).get("rendered", ""))
                if not excerpt:
                    excerpt = strip_html(p.get("content", {}).get("rendered", ""))[:2000]
                pub = (p.get("date") or "")[:19].replace("T", " ")
                if not url or not title:
                    stats["skipped"] += 1
                    continue
                if args.dry_run:
                    stats["inserted"] += 1
                    continue
                eid = db.insert_raw_entry(source_id, url, title, excerpt[:2000], pub or None)
                stats["duplicates" if eid is None else "inserted"] += 1
            tag = "[dry] " if args.dry_run else ""
            print(f"  {tag}{after[:7]}: {len(posts)} posts")

    print(f"\n{args.source_name}: fetched {stats['fetched']} | "
          f"{'würde einfügen' if args.dry_run else 'eingefügt'} {stats['inserted']} | "
          f"{stats['duplicates']} dup | {stats['skipped']} skip")
    if not args.dry_run and stats["inserted"]:
        print(f"  -> {stats['inserted']} neue datierte raw_entries (processed=0)")


if __name__ == "__main__":
    main()
