#!/usr/bin/env python3
"""Probe which sources qualify for full-text extraction (#11 broad enablement).

For each source that has ingested entries, take a recent real article URL and
check: (a) does robots.txt allow us, (b) does trafilatura extract clean text
(>= MIN_TEXT_CHARS). Reports qualified / robots-blocked / no-extract, so the
owner can decide which to flag `fulltext: true`. Read-only — changes nothing.

    python scripts/probe_fulltext.py            # all sources with entries
    python scripts/probe_fulltext.py --sample 3 # test 3 URLs/source (robuster)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from pipeline.article_fetcher import _robots_ok, UA, MIN_TEXT_CHARS
from pipeline.db import get_connection
import trafilatura


def recent_urls(sample: int) -> list[tuple[str, str, list[str]]]:
    """(source_name, source_type, [recent urls]) for sources with entries."""
    with get_connection() as conn:
        srcs = conn.execute(
            "SELECT s.id, s.name, s.source_type FROM sources s "
            "WHERE s.active = TRUE AND EXISTS "
            "(SELECT 1 FROM raw_entries r WHERE r.source_id = s.id) "
            "ORDER BY s.name").fetchall()
        out = []
        for s in srcs:
            sid = s["id"] if isinstance(s, dict) else s[0]
            name = s["name"] if isinstance(s, dict) else s[1]
            styp = s["source_type"] if isinstance(s, dict) else s[2]
            rows = conn.execute(
                "SELECT url FROM raw_entries WHERE source_id = ? AND url LIKE ? "
                "ORDER BY id DESC LIMIT ?", (sid, "http%", sample)).fetchall()
            urls = [r["url"] if isinstance(r, dict) else r[0] for r in rows]
            if urls:
                out.append((name, styp or "?", urls))
    return out


def probe_one(urls: list[str], client: httpx.Client) -> tuple[str, int]:
    """Return (verdict, best_chars). Tries each url until one extracts."""
    robots_seen = False
    for url in urls:
        if not _robots_ok(url):
            robots_seen = True
            continue
        try:
            r = client.get(url)
            if r.status_code != 200 or not r.text:
                continue
            txt = trafilatura.extract(r.text, include_comments=False,
                                      include_tables=False, favor_precision=True)
            n = len(txt) if txt else 0
            if n >= MIN_TEXT_CHARS:
                return "qualified", n
        except Exception:
            continue
    return ("robots-blocked" if robots_seen else "no-extract"), 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=2, help="urls to try per source")
    args = ap.parse_args()

    sources = recent_urls(args.sample)
    print(f"probing {len(sources)} sources (up to {args.sample} urls each)…\n")
    results = []
    with httpx.Client(timeout=20, follow_redirects=True,
                      headers={"User-Agent": UA}) as client:
        for name, styp, urls in sources:
            verdict, chars = probe_one(urls, client)
            results.append((name, styp, verdict, chars))
            print(f"  {verdict:<14} {chars:>6}  {name[:40]:<40} [{styp}]")

    q = [r for r in results if r[2] == "qualified"]
    rb = [r for r in results if r[2] == "robots-blocked"]
    ne = [r for r in results if r[2] == "no-extract"]
    print(f"\n=== SUMMARY: {len(q)} qualified · {len(rb)} robots-blocked · {len(ne)} no-extract ===")
    print("\nQUALIFIED (recommend fulltext:true), by source_type:")
    for styp in sorted(set(r[1] for r in q)):
        names = sorted(r[0] for r in q if r[1] == styp)
        print(f"  [{styp}] {', '.join(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
