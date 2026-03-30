#!/usr/bin/env python3
"""Verify RSS feed URLs and report results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import feedparser
import httpx
from pipeline.config import load_sources


def verify_feed(name: str, url: str, vertical: str) -> dict:
    """Verify a single feed URL."""
    result = {"name": name, "url": url, "vertical": vertical, "ok": False, "entries": 0, "error": None}
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True, headers={
            "User-Agent": "CatandaryTrends/1.0 (RSS Feed Reader)"
        })
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result

        feed = feedparser.parse(resp.text)
        if feed.bozo and not feed.entries:
            result["error"] = f"Parse error: {feed.bozo_exception}"
            return result

        result["ok"] = True
        result["entries"] = len(feed.entries)
        if feed.entries:
            result["sample_title"] = feed.entries[0].get("title", "")[:80]
    except Exception as e:
        result["error"] = str(e)[:100]
    return result


def main():
    sources = load_sources()
    results = []

    # Vertical sources
    for vertical, config in sources.get("verticals", {}).items():
        for source in config.get("sources", []):
            print(f"  Checking {source['name']} ({vertical})...", end=" ", flush=True)
            r = verify_feed(source["name"], source["feed_url"], vertical)
            status = f"OK ({r['entries']} entries)" if r["ok"] else f"FAIL: {r['error']}"
            print(status)
            results.append(r)

        for source in config.get("radar", []):
            print(f"  Checking {source['name']} (radar)...", end=" ", flush=True)
            r = verify_feed(source["name"], source["feed_url"], f"{vertical}_radar")
            status = f"OK ({r['entries']} entries)" if r["ok"] else f"FAIL: {r['error']}"
            print(status)
            results.append(r)

    # Cross-industry
    for category, feeds in sources.get("cross_industry", {}).items():
        for source in feeds:
            print(f"  Checking {source['name']} (cross)...", end=" ", flush=True)
            r = verify_feed(source["name"], source["feed_url"], "CROSS")
            status = f"OK ({r['entries']} entries)" if r["ok"] else f"FAIL: {r['error']}"
            print(status)
            results.append(r)

    # Summary
    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    print(f"\n{'='*60}")
    print(f"Results: {len(ok)}/{len(results)} feeds working")
    if fail:
        print(f"\nFailed feeds:")
        for r in fail:
            print(f"  - {r['name']} ({r['vertical']}): {r['error']}")

    return results


if __name__ == "__main__":
    main()
