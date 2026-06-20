#!/usr/bin/env python3
"""Recover publication dates for undated raw_entries via live-page metadata.

Fetches each article URL and extracts the publish date from JSON-LD
`datePublished`, `article:published_time`/og meta, or `<time datetime>`.
This is the publisher's own date — more accurate than guessing from text,
free (no LLM/Firecrawl), and naturally flags non-articles (no date found).

Requests are grouped by domain and issued sequentially per domain (with a
polite delay + one retry) to avoid the 403/timeout blocking that concurrent
same-domain hammering triggers; different domains run in parallel.

Usage:
    python scripts/recover_dates.py --sample 150        # measure hit rate, no writes
    python scripts/recover_dates.py --apply             # update all undated+content
    python scripts/recover_dates.py --apply --domains 8
"""
from __future__ import annotations
import argparse, re, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline.db import get_connection

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA,
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
           "Accept-Language": "en-US,en;q=0.9"}
DOMAIN_DELAY = 1.2  # seconds between requests to the same domain

_PATTERNS = [
    re.compile(r'"datePublished"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2})'),
    re.compile(r'property=["\']article:published_time["\']\s+content=["\']([0-9]{4}-[0-9]{2}-[0-9]{2})'),
    re.compile(r'content=["\']([0-9]{4}-[0-9]{2}-[0-9]{2})[^"\']*["\']\s+property=["\']article:published_time'),
    re.compile(r'name=["\'](?:publish-date|date|sailthru\.date|cXenseParse:recs:publishtime)["\']\s+content=["\']([0-9]{4}-[0-9]{2}-[0-9]{2})'),
    re.compile(r'itemprop=["\']datePublished["\'][^>]*content=["\']([0-9]{4}-[0-9]{2}-[0-9]{2})'),
    re.compile(r'<time[^>]+datetime=["\']([0-9]{4}-[0-9]{2}-[0-9]{2})'),
]


def extract_date(html: str) -> str | None:
    for pat in _PATTERNS:
        m = pat.search(html)
        if m:
            try:
                d = date.fromisoformat(m.group(1))
            except ValueError:
                continue
            if date(2000, 1, 1) <= d <= date.today():
                return d.isoformat()
    return None


def fetch_one(client: httpx.Client, url: str) -> tuple[str | None, str]:
    for attempt in range(2):
        try:
            r = client.get(url, timeout=20, follow_redirects=True)
            if r.status_code == 200:
                d = extract_date(r.text)
                return (d, "ok") if d else (None, "nodate")
            if r.status_code in (403, 429, 503) and attempt == 0:
                time.sleep(3)
                continue
            return None, f"http{r.status_code}"
        except Exception as exc:
            if attempt == 0:
                time.sleep(2)
                continue
            return None, f"err:{type(exc).__name__}"
    return None, "err"


def process_domain(domain: str, items: list[tuple[int, str]]) -> list[tuple[int, str | None, str]]:
    out = []
    with httpx.Client(headers=HEADERS) as client:
        for i, (eid, url) in enumerate(items):
            if i:
                time.sleep(DOMAIN_DELAY)
            d, status = fetch_one(client, url)
            out.append((eid, d, status))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="test N entries, no writes")
    ap.add_argument("--apply", action="store_true", help="update all undated+content")
    ap.add_argument("--domains", type=int, default=8, help="domains fetched in parallel")
    args = ap.parse_args()

    with get_connection() as c:
        q = ("SELECT id,url FROM raw_entries WHERE processed=0 AND published_date IS NULL "
             "AND length(trim(coalesce(excerpt,'')))>0 ORDER BY id")
        rows = c.execute(q + (f" LIMIT {args.sample}" if args.sample else "")).fetchall()

    by_domain: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for r in rows:
        by_domain[urlparse(r["url"]).netloc].append((r["id"], r["url"]))
    print(f"{len(rows)} undatierte Einträge mit Content über {len(by_domain)} Domains")

    results: dict[int, str] = {}
    counts = {"ok": 0, "nodate": 0, "error": 0}
    src_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # ok, nodate, error
    with ThreadPoolExecutor(max_workers=args.domains) as ex:
        futs = {ex.submit(process_domain, dom, items): dom for dom, items in by_domain.items()}
        for fut in as_completed(futs):
            dom = futs[fut]
            for eid, d, status in fut.result():
                if status == "ok":
                    counts["ok"] += 1; results[eid] = d; src_stats[dom][0] += 1
                elif status == "nodate":
                    counts["nodate"] += 1; src_stats[dom][1] += 1
                else:
                    counts["error"] += 1; src_stats[dom][2] += 1
            print(f"  {dom[:38]:<38} ok={src_stats[dom][0]} nodate={src_stats[dom][1]} err={src_stats[dom][2]}", flush=True)

    n = len(rows) or 1
    print(f"\nDatum gefunden: {counts['ok']} ({100*counts['ok']//n}%) | "
          f"kein Datum (Nicht-Artikel): {counts['nodate']} ({100*counts['nodate']//n}%) | "
          f"Fehler: {counts['error']} ({100*counts['error']//n}%)")

    if args.apply and results:
        with get_connection() as c:
            c.executemany("UPDATE raw_entries SET published_date=? WHERE id=?",
                          [(d, eid) for eid, d in results.items()])
        print(f"\n{len(results)} Einträge mit recovered Datum aktualisiert.")
    elif not args.apply:
        print("\n(Sample-Modus, keine Writes. Mit --apply anwenden.)")


if __name__ == "__main__":
    main()
