"""Source quality report: real weekly frequency + freshness per feed.

Measures what verify_feeds.py cannot: how many entries a feed actually
publishes per week (from entry timestamps) and how fresh it is. Used to
(a) audit the configured source network and (b) evaluate candidate feeds
before adding them.

Usage:
    python scripts/source_quality_report.py                    # all feeds from sources.yaml
    python scripts/source_quality_report.py --candidates f.yaml  # candidate list instead
    python scripts/source_quality_report.py --json out.json    # machine-readable dump

Candidate file format (YAML):
    - name: Feed Name
      feed_url: https://...
      vertical: TECH
      type: trade_media
      lead_time_tier: market
"""

import argparse
import calendar
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feedparser
import httpx
import yaml

from pipeline.config import load_sources

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) CatandaryTrends/1.0 (RSS reader)"
STALE_DAYS = 14  # newest entry older than this -> flagged stale


def iter_configured_feeds() -> list[dict]:
    config = load_sources()
    feeds = []
    for vertical, groups in config.get("verticals", {}).items():
        for key in ("sources", "science"):
            for s in groups.get(key, []) or []:
                feeds.append({"name": s["name"], "feed_url": s["feed_url"],
                              "vertical": vertical, "type": s.get("type", "trade_media"),
                              "lead_time_tier": s.get("lead_time_tier", "")})
    for group, entries in config.get("cross_industry", {}).items():
        for s in entries or []:
            feeds.append({"name": s["name"], "feed_url": s["feed_url"],
                          "vertical": "CROSS", "type": s.get("type", "trade_media"),
                          "lead_time_tier": s.get("lead_time_tier", "")})
    return feeds


def measure_feed(feed: dict) -> dict:
    result = {**feed, "ok": False, "error": None, "entries": 0,
              "per_week": None, "newest_age_days": None, "stale": None}
    try:
        resp = httpx.get(feed["feed_url"], timeout=20, follow_redirects=True,
                         headers={"User-Agent": USER_AGENT})
        if resp.status_code != 200:
            result["error"] = f"HTTP {resp.status_code}"
            return result
        parsed = feedparser.parse(resp.text)
        if not parsed.entries:
            result["error"] = "no entries"
            return result

        now = time.time()
        timestamps = []
        for e in parsed.entries:
            t = e.get("published_parsed") or e.get("updated_parsed")
            if t:
                timestamps.append(calendar.timegm(t))
        result["ok"] = True
        result["entries"] = len(parsed.entries)
        if timestamps:
            timestamps.sort(reverse=True)
            newest = timestamps[0]
            result["newest_age_days"] = round((now - newest) / 86400, 1)
            result["stale"] = result["newest_age_days"] > STALE_DAYS
            # Weekly rate from the timestamp span. Feeds are windowed
            # (often the latest N items), so the span-based rate is the
            # honest estimate; single-timestamp feeds get None.
            oldest = timestamps[-1]
            span_days = max((newest - oldest) / 86400, 0.5)
            if len(timestamps) >= 5:
                result["per_week"] = round(len(timestamps) / span_days * 7, 1)
        return result
    except Exception as exc:
        result["error"] = str(exc)[:80]
        return result


def main():
    parser = argparse.ArgumentParser(description="Source quality report")
    parser.add_argument("--candidates", help="YAML candidate list instead of sources.yaml")
    parser.add_argument("--json", dest="json_out", help="write results as JSON")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    if args.candidates:
        with open(args.candidates, encoding="utf-8") as f:
            feeds = yaml.safe_load(f)
    else:
        feeds = iter_configured_feeds()

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(measure_feed, feed): feed for feed in feeds}
        for future in as_completed(futures):
            results.append(future.result())

    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    ok.sort(key=lambda r: -(r["per_week"] or 0))

    print(f"{'QUELLE':<34}{'VERT':<10}{'TYP':<13}{'/WOCHE':>8}{'NEUESTE':>9}  STATUS")
    print("-" * 86)
    for r in ok:
        per_week = f"{r['per_week']:.0f}" if r["per_week"] else "?"
        age = f"{r['newest_age_days']:.0f}d" if r["newest_age_days"] is not None else "?"
        flag = "STALE" if r["stale"] else ("ok" if r["stale"] is not None else "no-dates")
        print(f"{r['name'][:33]:<34}{r['vertical']:<10}{r['type']:<13}{per_week:>8}{age:>9}  {flag}")

    total_week = sum(r["per_week"] or 0 for r in ok if not r["stale"])
    fresh = [r for r in ok if r["stale"] is False]
    stale = [r for r in ok if r["stale"]]
    print("-" * 86)
    print(f"Feeds: {len(results)} | erreichbar: {len(ok)} | frisch (<= {STALE_DAYS}d): "
          f"{len(fresh)} | stale: {len(stale)} | tot: {len(failed)}")
    print(f"Projizierte Roh-Signale/Woche (frische Feeds): {total_week:.0f}")
    if failed:
        print("\nNicht erreichbar / leer:")
        for r in failed:
            print(f"  {r['name'][:40]:<42}{r['error']}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
        print(f"\nJSON: {args.json_out}")


if __name__ == "__main__":
    main()
