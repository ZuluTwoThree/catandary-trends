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


def probe_wp(client, base: str) -> int | None:
    """Total post count if the WP REST API is live, else None."""
    try:
        r = client.get(f"{base}/wp-json/wp/v2/posts", params={"per_page": 1, "_fields": "id"},
                       timeout=12, follow_redirects=True)
        if r.status_code == 200 and isinstance(r.json(), list):
            return int(r.headers.get("X-WP-Total", "0"))
    except Exception:
        return None
    return None


def yaml_wp_targets(skip_capped: bool) -> list[dict]:
    """Trade/press sources from sources.yaml with their per-source WP strategy
    (wp_categories scoping, ingest_cap). The deep backfill skips `ingest_cap`
    sources — those are the flagged entertainment/low-yield giants (Variety,
    Hollywood Reporter, WWD, Robb Report …) that add little foresight and are
    already GPU-expensive to filter; and keeps each clean source's category
    scoping. One entry per domain."""
    cfg = load_sources()
    seen: set[str] = set()
    out: list[dict] = []
    for vert, groups in cfg.get("verticals", {}).items():
        for key in ("sources", "science"):
            for s in groups.get(key, []) or []:
                if not isinstance(s, dict):
                    continue
                if s.get("type") not in (None, "trade_media", "press_wire"):
                    continue
                d = domain_of(s.get("feed_url", ""))
                if not d or d in seen:
                    continue
                if skip_capped and s.get("ingest_cap"):
                    continue  # flagged entertainment/low-yield giant — skip the deep pull
                seen.add(d)
                out.append({
                    "base": f"https://{d}", "name": s.get("name") or d,
                    "feed_url": s.get("feed_url", ""), "type": s.get("type", "trade_media"),
                    "vertical": vert, "cap": s.get("ingest_cap"),
                    "categories": _csv_ids(s.get("wp_categories")),
                    "categories_exclude": _csv_ids(s.get("wp_categories_exclude")),
                })
    return out


def _csv_ids(v):
    if v is None:
        return None
    return ",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)


def ingest_one(client, base: str, source_name: str, feed_url: str, source_type: str,
               vertical: str, after: str, before: str, cap, categories,
               categories_exclude, dry_run: bool) -> dict:
    """Ingest one WordPress site's archive over [after, before). Batched inserts."""
    source_id = -1 if dry_run else db.upsert_source(
        name=source_name, feed_url=feed_url or base, source_type=source_type, vertical=vertical)
    stats = {"fetched": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    buf: list[tuple] = []
    for a, b in month_chunks(after, before):
        posts = fetch_month(client, base, a, b, cap=cap,
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
            if dry_run:
                stats["inserted"] += 1
                continue
            buf.append((source_id, url, title, excerpt[:2000], pub or None))
            if len(buf) >= 2000:
                ins = db.insert_raw_entries_market_batch(buf)
                stats["inserted"] += ins
                stats["duplicates"] += len(buf) - ins
                buf.clear()
    if buf and not dry_run:
        ins = db.insert_raw_entries_market_batch(buf)
        stats["inserted"] += ins
        stats["duplicates"] += len(buf) - ins
    print(f"  {source_name}: fetched {stats['fetched']} | inserted {stats['inserted']} | "
          f"{stats['duplicates']} dup | {stats['skipped']} skip")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-name", help="single-source mode (from sources.yaml)")
    ap.add_argument("--all", action="store_true", help="deep-sweep WP-capable trade sources (sources.yaml)")
    ap.add_argument("--include-capped", action="store_true",
                    help="--all: also include the ingest_cap'd entertainment giants (default: skip)")
    ap.add_argument("--probe", action="store_true", help="only list WP-capable sources + archive sizes")
    ap.add_argument("--base-url", help="override; else derived from sources.yaml feed_url")
    ap.add_argument("--after", help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--before", help="YYYY-MM-DD (exclusive)")
    ap.add_argument("--max-per-month", type=int, help="cap posts/month (overrides sources.yaml ingest_cap)")
    ap.add_argument("--categories", help="comma-sep WP category IDs to INCLUDE (overrides sources.yaml wp_categories)")
    ap.add_argument("--categories-exclude", help="comma-sep WP category IDs to EXCLUDE (overrides wp_categories_exclude)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    def _csv(v):
        if v is None:
            return None
        return ",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)

    with httpx.Client(headers=HEADERS) as client:
        # --probe: list which trade sources expose the WP API + archive sizes
        if args.probe:
            wp = []
            for tgt in yaml_wp_targets(skip_capped=not args.include_capped):
                total = probe_wp(client, tgt["base"])
                if total:
                    wp.append(tgt)
                    print(f"  {tgt['base'][8:]:34s} {tgt['vertical']:9s} ~{total:>7} posts  ({tgt['name'][:26]})")
            print(f"\n{len(wp)} WordPress-capable trade sources"
                  f"{' (incl. capped)' if args.include_capped else ' (entertainment giants skipped)'}.")
            return

        # --all: deep-sweep, respecting each source's sources.yaml strategy
        if args.all:
            if not (args.after and args.before):
                ap.error("--all needs --after and --before")
            tgts = yaml_wp_targets(skip_capped=not args.include_capped)
            print(f"[wp-all] {len(tgts)} candidate domains | {args.after}..{args.before} | "
                  f"{'incl. capped' if args.include_capped else 'entertainment giants skipped'}")
            grand = 0
            for tgt in tgts:
                if probe_wp(client, tgt["base"]) is None:
                    continue
                # deep backfill: no cap for the clean sources, but keep their
                # category scoping (the existing relevance strategy)
                st = ingest_one(client, tgt["base"], tgt["name"], tgt["feed_url"], tgt["type"],
                                tgt["vertical"], args.after, args.before, args.max_per_month,
                                tgt["categories"], tgt["categories_exclude"], args.dry_run)
                grand += st["inserted"]
            print(f"\n[wp-all] DONE: {grand} inserted across WordPress archives")
            return

        # single-source mode (sources.yaml, with optional category scoping)
        if not (args.source_name and args.after and args.before):
            ap.error("need --probe, --all, or --source-name with --after/--before")
        src = find_source(args.source_name)
        if not src and not args.base_url:
            print(f"Quelle '{args.source_name}' nicht in sources.yaml und kein --base-url"); sys.exit(1)
        base = args.base_url or f"https://{domain_of(src['feed_url'])}"
        vertical = src["vertical"] if src else "FOOD"
        cap = args.max_per_month or (src or {}).get("ingest_cap")
        categories = args.categories or _csv((src or {}).get("wp_categories"))
        categories_exclude = args.categories_exclude or _csv((src or {}).get("wp_categories_exclude"))
        print(f"[wp] {args.source_name} @ {base} | {args.after} .. {args.before}"
              f"{f' | cap={cap}/month' if cap else ''}")
        ingest_one(client, base, args.source_name, (src or {}).get("feed_url", base),
                   (src or {}).get("type", "trade_media"), vertical, args.after, args.before,
                   cap, categories, categories_exclude, args.dry_run)


if __name__ == "__main__":
    main()
