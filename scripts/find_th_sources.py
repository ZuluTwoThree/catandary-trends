#!/usr/bin/env python3
"""Analyze existing Trendhunter-sourced trends to find original primary sources.

For each TH trend, extracts brand/keywords from the title and searches
Brave Search for the original source. Outputs domain frequency analysis
to identify candidates for direct RSS polling.
"""

import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
DB_PATH = "data/catandary.db"
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

SKIP_DOMAINS = {
    "trendhunter.com", "www.trendhunter.com",
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "linkedin.com", "youtube.com", "reddit.com", "pinterest.com",
    "tiktok.com", "wikipedia.org", "en.wikipedia.org", "amazon.com",
    "ebay.com", "etsy.com",
}


def brave_search(query: str, count: int = 5) -> list[dict]:
    try:
        resp = httpx.get(
            BRAVE_URL,
            params={"q": query, "count": count},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("web", {}).get("results", [])
    except Exception as e:
        print(f"  SEARCH ERROR: {e}")
        return []


def find_source(title: str, th_url: str) -> dict | None:
    """Search for original source based on trend title."""
    # Extract likely brand/product from TH URL slug
    slug = th_url.rstrip("/").split("/")[-1]
    slug_words = slug.replace("-", " ")

    query = f"{title}"
    results = brave_search(query)

    for r in results:
        domain = urlparse(r["url"]).netloc.replace("www.", "")
        if domain not in SKIP_DOMAINS:
            return {
                "url": r["url"],
                "domain": domain,
                "title": r.get("title", ""),
            }

    # Fallback: search with slug keywords
    if slug_words:
        results = brave_search(slug_words)
        for r in results:
            domain = urlparse(r["url"]).netloc.replace("www.", "")
            if domain not in SKIP_DOMAINS:
                return {
                    "url": r["url"],
                    "domain": domain,
                    "title": r.get("title", ""),
                }

    return None


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT t.id, t.title_en, t.source_url, t.primary_vertical
        FROM trends t
        JOIN raw_entries r ON t.raw_entry_id = r.id
        JOIN sources s ON r.source_id = s.id
        WHERE s.source_type = 'radar'
        ORDER BY t.primary_vertical, t.id
    """)
    rows = c.fetchall()
    total = len(rows)
    print(f"Found {total} TH-sourced trends to analyze\n")

    domain_counts = defaultdict(lambda: {"count": 0, "verticals": set(), "examples": []})
    found = 0
    missed = 0

    for i, row in enumerate(rows):
        tid = row["id"]
        title = row["title_en"]
        url = row["source_url"]
        vert = row["primary_vertical"]

        print(f"[{i+1}/{total}] {vert:8} {title[:65]}", end=" ", flush=True)

        result = find_source(title, url)

        if result:
            found += 1
            d = result["domain"]
            domain_counts[d]["count"] += 1
            domain_counts[d]["verticals"].add(vert)
            if len(domain_counts[d]["examples"]) < 3:
                domain_counts[d]["examples"].append(title[:60])
            print(f"-> {d}")
        else:
            missed += 1
            print("-> MISS")

        time.sleep(1.1)

    print(f"\n{'='*70}")
    print(f"RESULTS: {found} found, {missed} missed ({found/total*100:.0f}% hit rate)")
    print(f"{'='*70}\n")

    # Sort by frequency
    sorted_domains = sorted(domain_counts.items(), key=lambda x: -x[1]["count"])

    print(f"{'Domain':<40} {'Count':>5}  {'Verticals':<30}  Examples")
    print("-" * 120)
    for domain, info in sorted_domains:
        verts = ", ".join(sorted(info["verticals"]))
        example = info["examples"][0][:50] if info["examples"] else ""
        print(f"{domain:<40} {info['count']:>5}  {verts:<30}  {example}")

    # RSS candidates (3+ hits)
    print(f"\n{'='*70}")
    print("RSS CANDIDATES (3+ hits):")
    print(f"{'='*70}")
    candidates = [(d, i) for d, i in sorted_domains if i["count"] >= 3]
    for domain, info in candidates:
        verts = ", ".join(sorted(info["verticals"]))
        print(f"\n{domain} ({info['count']}x, {verts})")
        for ex in info["examples"]:
            print(f"  - {ex}")

    # Save full results to JSON
    output = {
        "total": total,
        "found": found,
        "missed": missed,
        "hit_rate": f"{found/total*100:.0f}%",
        "domains": {
            d: {"count": i["count"], "verticals": sorted(i["verticals"]), "examples": i["examples"]}
            for d, i in sorted_domains
        },
        "rss_candidates": [
            {"domain": d, "count": i["count"], "verticals": sorted(i["verticals"])}
            for d, i in candidates
        ],
    }
    with open("data/th_source_analysis.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull results saved to data/th_source_analysis.json")

    conn.close()


if __name__ == "__main__":
    main()
