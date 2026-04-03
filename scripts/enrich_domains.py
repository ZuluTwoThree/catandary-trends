#!/usr/bin/env python3
"""Enrich TH-discovered domains: classify, check RSS feeds, find similar sites.

Step 1: Classify 281 domains via LLM (trade_media, brand, academic, press_wire, other)
Step 2: Check RSS feeds for trade_media domains (HTTP only, no Brave queries)
Step 3: Find similar sites via Brave Search for top domains (~60-80 queries)
Step 4: Check RSS feeds for newly discovered similar sites
"""

import json
import os
import re
import sys
import time
from urllib.parse import urlparse

import feedparser
import httpx
from dotenv import load_dotenv

load_dotenv()

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
OLLAMA_HOST = "http://127.0.0.1:11434"

brave_queries_used = 0

# Known domain patterns for rule-based pre-classification
ACADEMIC_PATTERNS = {
    "ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov",
    "sciencedirect.com", "tandfonline.com", "mdpi.com", "springer.com",
    "wiley.com", "nature.com", "journals.sagepub.com", "pubs.acs.org",
    "arxiv.org", "researchgate.net", "academia.edu", "jstor.org",
    "ieee.org", "acm.org", "elsevier.com",
}

PRESS_WIRE_PATTERNS = {
    "prnewswire.com", "businesswire.com", "globenewswire.com", "openpr.com",
    "prweb.com", "newswire.com",
}

SOCIAL_PATTERNS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com",
    "youtube.com", "reddit.com", "pinterest.com", "tiktok.com", "medium.com",
    "substack.com",
}

GOV_NGO_PATTERNS = {
    "unesco.org", "weforum.org", "oecd.org", "who.int", "un.org",
    "europa.eu", "worldbank.org",
}

ECOMMERCE_PATTERNS = {
    "amazon.com", "ebay.com", "etsy.com", "shopify.com", "alibaba.com",
}

# Common RSS feed paths to check
RSS_PATHS = [
    "/feed/", "/feed", "/rss/", "/rss", "/feeds/rss/",
    "/atom.xml", "/rss.xml", "/feed.xml", "/index.xml",
    "/feeds/posts/default", "/.rss/full/",
]


def brave_search(query: str, count: int = 5) -> list[dict]:
    global brave_queries_used
    if not BRAVE_API_KEY:
        return []
    try:
        resp = httpx.get(
            BRAVE_URL,
            params={"q": query, "count": count},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": BRAVE_API_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        brave_queries_used += 1
        return resp.json().get("web", {}).get("results", [])
    except Exception as e:
        print(f"  SEARCH ERROR: {e}")
        return []


def ollama_classify(domains_batch: list[dict]) -> list[dict]:
    """Classify a batch of domains using Qwen3 8B."""
    domain_list = "\n".join(
        f"- {d['domain']} ({d['count']}x, verticals: {', '.join(d['verticals'])})"
        for d in domains_batch
    )

    prompt = f"""Classify each domain into exactly one category. Return ONLY a JSON array.

Categories:
- "trade_media" = news sites, industry magazines, trade publications, blogs about specific industries
- "brand" = company/product websites (their own site, not reporting about others)
- "academic" = journals, research papers, university sites
- "press_wire" = press release distributors
- "gov_ngo" = government, international organizations, NGOs
- "marketplace" = e-commerce, review sites, comparison sites
- "other" = anything else

Domains:
{domain_list}

Return JSON array like: [{{"domain": "example.com", "type": "trade_media"}}]
Only return the JSON, nothing else. /no_think"""

    try:
        resp = httpx.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": "qwen3:8b",
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=120,
        )
        text = resp.json().get("response", "")
        # Extract JSON from response
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"  LLM ERROR: {e}")
    return []


def check_rss_feed(domain: str) -> dict | None:
    """Try to find an RSS feed for a domain. Returns {url, title, entry_count} or None."""
    base_urls = [f"https://www.{domain}", f"https://{domain}"]

    # First try: check HTML for <link rel="alternate" type="application/rss+xml">
    for base in base_urls:
        try:
            resp = httpx.get(
                base,
                timeout=10,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; CatandaryTrends/1.0)"},
            )
            if resp.status_code == 200:
                # Look for RSS link in HTML
                rss_links = re.findall(
                    r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+href=["\']([^"\']+)["\']',
                    resp.text[:5000],
                )
                if not rss_links:
                    rss_links = re.findall(
                        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\']',
                        resp.text[:5000],
                    )
                for link in rss_links:
                    if link.startswith("/"):
                        link = base.rstrip("/") + link
                    feed = feedparser.parse(link)
                    if feed.entries:
                        return {
                            "url": link,
                            "title": feed.feed.get("title", ""),
                            "entry_count": len(feed.entries),
                        }
                break  # Got a response, don't try alternate base URL
        except Exception:
            continue

    # Second try: brute-force common RSS paths
    for base in base_urls:
        for path in RSS_PATHS:
            url = base.rstrip("/") + path
            try:
                feed = feedparser.parse(url)
                if feed.entries and len(feed.entries) >= 3:
                    return {
                        "url": url,
                        "title": feed.feed.get("title", ""),
                        "entry_count": len(feed.entries),
                    }
            except Exception:
                continue
        break  # Only try one base URL for brute force

    return None


def find_similar_sites(domain: str, vertical: str) -> list[dict]:
    """Use Brave Search to find sites similar to a domain."""
    results = []

    query = f"sites similar to {domain} {vertical} news"
    search_results = brave_search(query, count=10)
    time.sleep(1.1)

    seen = set()
    for r in search_results:
        d = urlparse(r["url"]).netloc.replace("www.", "")
        if d not in seen and d != domain:
            seen.add(d)
            results.append({
                "domain": d,
                "url": r["url"],
                "title": r.get("title", ""),
                "source": f"similar to {domain}",
            })

    return results


def main():
    # Load domain data from TH analysis
    with open("data/th_source_analysis.json") as f:
        data = json.load(f)

    domains = data["domains"]
    print(f"Loaded {len(domains)} domains from TH analysis\n")

    # ====== STEP 1: Pre-classify by pattern matching ======
    print("=" * 70)
    print("STEP 1: Classifying domains")
    print("=" * 70)

    classified = {}
    llm_batch = []

    for domain, info in domains.items():
        clean = domain.replace("www.", "")

        if any(p in clean for p in ACADEMIC_PATTERNS):
            classified[domain] = {"type": "academic", **info}
        elif any(p in clean for p in PRESS_WIRE_PATTERNS):
            classified[domain] = {"type": "press_wire", **info}
        elif any(p in clean for p in SOCIAL_PATTERNS):
            classified[domain] = {"type": "social", **info}
        elif any(p in clean for p in GOV_NGO_PATTERNS):
            classified[domain] = {"type": "gov_ngo", **info}
        elif any(p in clean for p in ECOMMERCE_PATTERNS):
            classified[domain] = {"type": "marketplace", **info}
        else:
            llm_batch.append({"domain": domain, **info})

    print(f"  Pre-classified by pattern: {len(classified)}")
    print(f"  Need LLM classification: {len(llm_batch)}")

    # Classify remaining via LLM in batches of 30
    batch_size = 30
    for i in range(0, len(llm_batch), batch_size):
        batch = llm_batch[i:i + batch_size]
        print(f"  LLM batch {i // batch_size + 1}/{(len(llm_batch) + batch_size - 1) // batch_size}...", end=" ", flush=True)
        results = ollama_classify(batch)

        result_map = {r["domain"]: r["type"] for r in results}
        for item in batch:
            dtype = result_map.get(item["domain"], "other")
            classified[item["domain"]] = {"type": dtype, **{k: v for k, v in item.items() if k != "domain"}}

        classified_count = sum(1 for r in results if r.get("type"))
        print(f"{classified_count}/{len(batch)} classified")

    # Summary
    type_counts = {}
    for info in classified.values():
        t = info["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"\nClassification results:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:<15} {c:>4}")

    # ====== STEP 2: Check RSS for trade_media domains ======
    trade_media = {d: info for d, info in classified.items() if info["type"] == "trade_media"}
    print(f"\n{'=' * 70}")
    print(f"STEP 2: Checking RSS feeds for {len(trade_media)} trade media domains")
    print("=" * 70)

    rss_found = {}
    rss_missing = []

    for i, (domain, info) in enumerate(sorted(trade_media.items(), key=lambda x: -x[1]["count"])):
        print(f"  [{i+1}/{len(trade_media)}] {domain:<40}", end=" ", flush=True)
        rss = check_rss_feed(domain)
        if rss:
            rss_found[domain] = {**info, "rss": rss}
            print(f"RSS OK ({rss['entry_count']} entries) — {rss['url'][:60]}")
        else:
            rss_missing.append(domain)
            print("no RSS")

    print(f"\n  RSS found: {len(rss_found)}")
    print(f"  No RSS: {len(rss_missing)}")

    # ====== STEP 3: Find similar sites for top domains ======
    # Pick top domains: those with RSS and 2+ TH hits, or high-value verticals
    top_domains = sorted(rss_found.items(), key=lambda x: -x[1]["count"])[:20]

    print(f"\n{'=' * 70}")
    print(f"STEP 3: Finding similar sites for top {len(top_domains)} domains (~{len(top_domains)} Brave queries)")
    print("=" * 70)

    similar_all = {}
    for domain, info in top_domains:
        primary_vert = info["verticals"][0] if info["verticals"] else ""
        print(f"  {domain} ({info['count']}x, {primary_vert})...", end=" ", flush=True)
        similar = find_similar_sites(domain, primary_vert)
        similar_all[domain] = similar
        print(f"{len(similar)} found")

    # Deduplicate and count similar domains
    similar_counts = {}
    for source_domain, similars in similar_all.items():
        for s in similars:
            d = s["domain"]
            if d not in classified and d not in similar_counts:
                similar_counts[d] = {"sources": [], "titles": []}
            if d not in classified:
                similar_counts[d]["sources"].append(source_domain)
                if s["title"]:
                    similar_counts[d]["titles"].append(s["title"][:60])

    # Filter: only new domains not already in our system
    new_similar = {d: info for d, info in similar_counts.items() if len(info["sources"]) >= 1}
    print(f"\n  New domains discovered: {len(new_similar)}")

    # ====== STEP 4: Check RSS for promising new domains ======
    # Only check the most promising ones (found via multiple top domains)
    multi_source = sorted(new_similar.items(), key=lambda x: -len(x[1]["sources"]))[:40]

    print(f"\n{'=' * 70}")
    print(f"STEP 4: Checking RSS for {len(multi_source)} promising new domains")
    print("=" * 70)

    new_rss_found = {}
    for i, (domain, info) in enumerate(multi_source):
        print(f"  [{i+1}/{len(multi_source)}] {domain:<40}", end=" ", flush=True)
        rss = check_rss_feed(domain)
        if rss:
            new_rss_found[domain] = {"rss": rss, "discovered_via": info["sources"]}
            print(f"RSS OK ({rss['entry_count']} entries)")
        else:
            print("no RSS")

    # ====== FINAL REPORT ======
    print(f"\n{'=' * 70}")
    print("FINAL REPORT")
    print("=" * 70)

    print(f"\nBrave queries used this run: {brave_queries_used}")

    print(f"\n--- Existing TH domains with RSS ({len(rss_found)}) ---")
    for domain, info in sorted(rss_found.items(), key=lambda x: -x[1]["count"]):
        verts = ", ".join(info["verticals"])
        print(f"  {domain:<40} {info['count']:>2}x  {verts:<20}  {info['rss']['url'][:55]}")

    if new_rss_found:
        print(f"\n--- Newly discovered domains with RSS ({len(new_rss_found)}) ---")
        for domain, info in new_rss_found.items():
            via = ", ".join(info["discovered_via"][:3])
            print(f"  {domain:<40} via {via:<30}  {info['rss']['url'][:50]}")

    # Save everything
    output = {
        "brave_queries_used": brave_queries_used,
        "classification": {d: {**info, "verticals": info.get("verticals", [])} for d, info in classified.items()},
        "trade_media_with_rss": {
            d: {**info, "rss_url": info["rss"]["url"], "rss_entries": info["rss"]["entry_count"]}
            for d, info in rss_found.items()
        },
        "trade_media_no_rss": rss_missing,
        "new_domains_with_rss": {
            d: {**info, "rss_url": info["rss"]["url"], "rss_entries": info["rss"]["entry_count"]}
            for d, info in new_rss_found.items()
        },
    }

    # Convert sets to lists for JSON serialization
    def make_serializable(obj):
        if isinstance(obj, set):
            return sorted(obj)
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [make_serializable(i) for i in obj]
        return obj

    with open("data/domain_enrichment.json", "w") as f:
        json.dump(make_serializable(output), f, indent=2)
    print(f"\nFull results saved to data/domain_enrichment.json")


if __name__ == "__main__":
    main()
