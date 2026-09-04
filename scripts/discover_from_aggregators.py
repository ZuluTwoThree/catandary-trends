#!/usr/bin/env python3
"""Aggregators as a discovery map (issue #97, owner comment 2026-09-03 + ToS
clarification): count the outbound domains of API-/feed-based indices, run
feed autodiscovery per domain and hand the candidates to the compliance
probe. Aggregator CONTENT is never ingested — only link domains are counted.

Scriptable indices (allowlist from the ToS clarification; everything else —
Techmeme, Feedspot, Feedly, Google News, Trendhunter/Springwise, presseportal —
is manual reading only and NOT implemented here on purpose):

  hn          Hacker News Firebase API (top + best stories → story URL hosts).
              Public API without ToS restriction; polled with a small delay.
  wikipedia   Wikipedia list pages via the MediaWiki API (CC BY-SA): the
              articles a list links to → their Wikidata item → official
              website (P856). Default lists cover trade/science/food/fashion/
              computer/environmental magazines (en) + deutschsprachige
              Zeitschriften (de); override with --wiki-page lang:Title.
  idw         idw-online.de press-release RSS (allowlisted by the owner) →
              the newest N idw news pages (robots.txt allows them) → the
              institution's website link. Note: idw's robots.txt disallows
              the RSS path for `*`; the tool reports that and proceeds on
              the owner's explicit allowlisting.
  reddit      only with REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET (registered app,
              official Data API, client_credentials, link domains of a few
              subreddits' monthly top). Skipped with a hint otherwise —
              registrations are announced first (sources@catandary.de).

Filters: domains of active sources.yaml feeds and the aggregator/platform
blocklist of probe_source_compliance are dropped. Output: domain candidates
with frequency, index origin, example, autodiscovered feed URL (`<link
rel="alternate" type="application/rss+xml|atom+xml">`, fallbacks /feed, /rss,
/feed.xml, /rss.xml, /atom.xml). `--probe` runs the compliance probe on the
candidates with a feed and prints the YAML snippet with `discovered_via`.

Etiquette: 1 request/s/host for websites (Wikipedia/Wikidata, idw pages,
homepages), 0.2 s between HN API item calls, honest UA, robots.txt honoured
for every page fetch. Nothing from an index is stored — only domains.

    python scripts/discover_from_aggregators.py                     # all indices, table
    python scripts/discover_from_aggregators.py --index hn,idw --top 30 --probe --yaml
    python scripts/discover_from_aggregators.py --index wikipedia --wiki-page "en:List of fashion magazines"
    python scripts/discover_from_aggregators.py --json data/discover.json --no-feeds
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import feedparser
import httpx

import probe_source_compliance as psc

UA = psc.UA
INDEXES = ("hn", "wikipedia", "idw", "reddit")
HN_API = "https://hacker-news.firebaseio.com/v0"
HN_LISTS = ("topstories", "beststories")
HN_DELAY = 0.2
WIKI_DEFAULT_PAGES: tuple[tuple[str, str], ...] = (
    ("en", "List of trade magazines"),
    ("en", "List of science magazines"),
    ("en", "List of food and drink magazines"),
    ("en", "List of fashion magazines"),
    ("en", "List of computer magazines"),
    ("en", "List of environmental periodicals"),
    ("de", "Liste deutschsprachiger Zeitschriften"),
)
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
IDW_FEED = "https://idw-online.de/pages/de/pressreleasesrss"
IDW_INSTITUTION_RE = re.compile(r'class="[^"]*InstitutionLogo"[^>]*>\s*<a\s+href="([^"]+)"', re.I)
REDDIT_DEFAULT_SUBS = ("technology", "Futurology", "science", "sustainability",
                       "foodscience", "fashion", "Design", "business")
REDDIT_UA = os.getenv("REDDIT_USER_AGENT",
                      "linux:catandary-trends-source-discovery:1.0 (contact sources@catandary.de)")
# Hosts shared by many unrelated publishers: filter only on an exact host match.
MULTI_TENANT = frozenset({"feedburner.com", "medium.com", "substack.com", "wordpress.com",
                          "blogspot.com", "github.io", "tumblr.com", "ghost.io", "beehiiv.com"})
# Second-level labels under which the registrable domain has three labels (bbc.co.uk).
_SLD = frozenset({"co", "com", "org", "net", "ac", "gov", "edu", "or", "ne"})
_IGNORE_HOSTS = frozenset({"self", "redd.it", "i.redd.it", "v.redd.it", "reddit.com", "imgur.com"})


# ---------------------------------------------------------------- helpers

def host_of(url: str) -> str | None:
    try:
        h = (urlsplit(url).netloc or "").lower().split("@")[-1].split(":")[0]
    except ValueError:
        return None
    if not h or "." not in h:
        return None
    return h[4:] if h.startswith("www.") else h


def registered_domain(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in _SLD and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _get_json(client: httpx.Client, url: str, throttle: psc.HostThrottle, **kw):
    throttle.wait(host_of(url) or url)
    r = client.get(url, **kw)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- indices

def collect_hn(client: httpx.Client, limit: int = 150, lists=HN_LISTS,
               throttle: psc.HostThrottle | None = None, log=print) -> list[dict]:
    """[{host, index:'hn', example, title}] for the story URLs of HN top/best."""
    throttle = throttle or psc.HostThrottle(HN_DELAY)
    ids: list[int] = []
    for name in lists:
        try:
            data = _get_json(client, f"{HN_API}/{name}.json", throttle)
        except Exception as e:  # noqa: BLE001
            log(f"hn: {name} failed ({type(e).__name__})")
            continue
        ids += [i for i in data[:limit] if isinstance(i, int)]
    seen, hits = set(), []
    for i in ids:
        if i in seen:
            continue
        seen.add(i)
        try:
            item = _get_json(client, f"{HN_API}/item/{i}.json", throttle) or {}
        except Exception:  # noqa: BLE001
            continue
        if item.get("type") != "story" or not item.get("url"):
            continue
        h = host_of(item["url"])
        if h:
            hits.append({"host": h, "index": "hn", "example": item["url"], "title": item.get("title", "")})
    log(f"hn: {len(seen)} stories → {len(hits)} link hosts")
    return hits


def _wiki_api(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def wiki_linked_items(client: httpx.Client, lang: str, title: str,
                      throttle: psc.HostThrottle) -> list[tuple[str, str]]:
    """[(article title, Wikidata Q-id)] for the main-namespace articles a
    list page links to (generator=links, follows API continuation)."""
    out: list[tuple[str, str]] = []
    params = {"action": "query", "generator": "links", "titles": title, "gplnamespace": 0,
              "gpllimit": 500, "prop": "pageprops", "ppprop": "wikibase_item",
              "format": "json", "formatversion": 2}
    while True:
        data = _get_json(client, _wiki_api(lang), throttle, params=params)
        for p in (data.get("query") or {}).get("pages") or []:
            q = (p.get("pageprops") or {}).get("wikibase_item")
            if q:
                out.append((p.get("title", ""), q))
        cont = data.get("continue")
        if not cont:
            break
        params = {**params, **cont}
    return out


def wikidata_websites(client: httpx.Client, qids: list[str],
                      throttle: psc.HostThrottle) -> dict[str, str]:
    """{Q-id: official website (P856)} in batches of 50."""
    out: dict[str, str] = {}
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        try:
            data = _get_json(client, WIKIDATA_API, throttle,
                             params={"action": "wbgetentities", "ids": "|".join(batch),
                                     "props": "claims", "format": "json"})
        except Exception:  # noqa: BLE001
            continue
        for q, ent in (data.get("entities") or {}).items():
            for claim in (ent.get("claims") or {}).get("P856") or []:
                val = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if isinstance(val, str) and val.startswith("http"):
                    out[q] = val
                    break
    return out


def collect_wikipedia(client: httpx.Client, pages=WIKI_DEFAULT_PAGES,
                      throttle: psc.HostThrottle | None = None, log=print) -> list[dict]:
    throttle = throttle or psc.HostThrottle(psc.PER_HOST_DELAY)
    hits: list[dict] = []
    for lang, title in pages:
        try:
            items = wiki_linked_items(client, lang, title, throttle)
        except Exception as e:  # noqa: BLE001
            log(f"wikipedia: {lang}:{title} failed ({type(e).__name__})")
            continue
        sites = wikidata_websites(client, [q for _, q in items], throttle)
        n = 0
        for name, q in items:
            url = sites.get(q)
            h = host_of(url) if url else None
            if h:
                n += 1
                hits.append({"host": h, "index": f"wikipedia:{lang}:{title}", "example": url, "title": name})
        log(f"wikipedia: {lang}:{title} → {len(items)} articles, {n} with website")
    return hits


def collect_idw(client: httpx.Client, limit: int = 40, feed_url: str = IDW_FEED,
                throttle: psc.HostThrottle | None = None, robots: psc.RobotsCache | None = None,
                log=print) -> list[dict]:
    """Institution websites behind the newest idw press releases."""
    throttle = throttle or psc.HostThrottle(psc.PER_HOST_DELAY)
    robots = robots or psc.RobotsCache(client, throttle)
    if robots.verdict(feed_url) == "disallow":
        log("idw: robots.txt disallows the RSS path for `*` — proceeding on the owner's "
            "explicit allowlisting of idw-RSS (#97, 2026-09-03); flagged for the record")
    try:
        throttle.wait(host_of(feed_url) or "")
        r = client.get(feed_url, headers={"Accept": psc.ACCEPT_FEED})
        entries = feedparser.parse(r.content).entries if r.status_code == 200 else []
    except Exception as e:  # noqa: BLE001
        log(f"idw: feed failed ({type(e).__name__})")
        return []
    hits: list[dict] = []
    for e in entries[:limit]:
        link = e.get("link")
        if not link or robots.verdict(link) == "disallow":
            continue
        try:
            throttle.wait(host_of(link) or "")
            page = client.get(link)
        except Exception:  # noqa: BLE001
            continue
        if page.status_code != 200:
            continue
        m = IDW_INSTITUTION_RE.search(page.text[:psc.MAX_PAGE_CHARS])
        if not m:
            continue
        h = host_of(m.group(1))
        if h:
            hits.append({"host": h, "index": "idw", "example": m.group(1), "title": e.get("title", "")})
    log(f"idw: {min(len(entries), limit)} releases → {len(hits)} institution hosts")
    return hits


def reddit_credentials() -> tuple[str, str] | None:
    cid, sec = os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET")
    return (cid, sec) if cid and sec else None


def collect_reddit(client: httpx.Client, subs=REDDIT_DEFAULT_SUBS, limit: int = 100,
                   throttle: psc.HostThrottle | None = None, log=print) -> list[dict] | None:
    """Link domains of the monthly top posts of a few subreddits via the
    official Data API (client_credentials). None = skipped (no credentials)."""
    creds = reddit_credentials()
    if not creds:
        log("reddit: skipped — set REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET (registered app; "
            "registrations are announced first, contact sources@catandary.de)")
        return None
    throttle = throttle or psc.HostThrottle(psc.PER_HOST_DELAY)
    auth = base64.b64encode(f"{creds[0]}:{creds[1]}".encode()).decode()
    try:
        throttle.wait("www.reddit.com")
        tok = client.post("https://www.reddit.com/api/v1/access_token",
                          data={"grant_type": "client_credentials"},
                          headers={"Authorization": f"Basic {auth}", "User-Agent": REDDIT_UA})
        tok.raise_for_status()
        token = tok.json()["access_token"]
    except Exception as e:  # noqa: BLE001
        log(f"reddit: auth failed ({type(e).__name__})")
        return []
    hits: list[dict] = []
    for sub in subs:
        try:
            data = _get_json(client, f"https://oauth.reddit.com/r/{sub}/top", throttle,
                             params={"t": "month", "limit": limit},
                             headers={"Authorization": f"Bearer {token}", "User-Agent": REDDIT_UA})
        except Exception as e:  # noqa: BLE001
            log(f"reddit: r/{sub} failed ({type(e).__name__})")
            continue
        for child in (data.get("data") or {}).get("children") or []:
            d = child.get("data") or {}
            dom = (d.get("domain") or "").lower()
            if not dom or dom.startswith("self.") or dom in _IGNORE_HOSTS:
                continue
            h = host_of(d.get("url") or f"https://{dom}/") or dom
            hits.append({"host": h, "index": f"reddit:r/{sub}", "example": d.get("url", ""),
                         "title": d.get("title", "")})
    log(f"reddit: {len(subs)} subreddits → {len(hits)} link hosts")
    return hits


# ------------------------------------------------------------ aggregation

def aggregate(hits: list[dict]) -> list[dict]:
    """Group hits by host → candidates sorted by count desc, then host."""
    by_host: dict[str, dict] = {}
    for h in hits:
        c = by_host.setdefault(h["host"], {"host": h["host"], "count": 0, "indices": defaultdict(int),
                                           "example": h.get("example"), "title": h.get("title")})
        c["count"] += 1
        c["indices"][h["index"].split(":")[0]] += 1
        c.setdefault("via", []).append(h["index"])
    out = []
    for c in by_host.values():
        c["indices"] = dict(c["indices"])
        c["via"] = sorted(set(c["via"]))
        out.append(c)
    out.sort(key=lambda c: (-c["count"], c["host"]))
    return out


def filter_candidates(cands: list[dict], active_hosts: set[str]) -> tuple[list[dict], dict[str, str]]:
    """Drop active sources (by registrable domain; multi-tenant hosts by exact
    host) and aggregator/platform domains. Returns (kept, {host: reason})."""
    active_reg = {registered_domain(h) for h in active_hosts if registered_domain(h) not in MULTI_TENANT}
    active_exact = set(active_hosts)
    kept, dropped = [], {}
    for c in cands:
        h = c["host"]
        agg = psc.is_aggregator(h)
        if agg:
            dropped[h] = f"aggregator/platform ({agg})"
        elif h in active_exact:
            dropped[h] = "active source"
        elif registered_domain(h) not in MULTI_TENANT and registered_domain(h) in active_reg:
            dropped[h] = f"active source domain ({registered_domain(h)})"
        else:
            kept.append(c)
    return kept, dropped


def autodiscover_feeds(cands: list[dict], client: httpx.Client, throttle: psc.HostThrottle,
                       robots: psc.RobotsCache, workers: int = 4) -> None:
    """Fill `feed_url` (or None) + `tried` for each candidate, in place."""
    def one(c: dict) -> None:
        feed_url, _resp, tried = psc.discover_feed(c["host"], client, throttle, robots)
        c["feed_url"], c["tried"] = feed_url, len(tried)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(one, cands))


def format_table(cands: list[dict]) -> str:
    head = f"{'host':<36} {'n':>3} {'indices':<22} {'feed':<52} example"
    rows = [head, "-" * len(head)]
    for c in cands:
        idx = ",".join(f"{k}:{v}" for k, v in sorted(c["indices"].items()))
        feed = c.get("feed_url") if "feed_url" in c else "(not tried)"
        rows.append(f"{c['host'][:36]:<36} {c['count']:>3} {idx[:22]:<22} "
                    f"{(feed or '— no feed')[:52]:<52} {(c.get('title') or c.get('example') or '')[:40]}")
    return "\n".join(rows)


def run(indexes, client: httpx.Client, *, hn_limit=150, wiki_pages=WIKI_DEFAULT_PAGES,
        idw_limit=40, subs=REDDIT_DEFAULT_SUBS, top=40, min_count=1, feeds=True,
        active_hosts: set[str] | None = None, delay: float | None = None, log=print) -> dict:
    """Collect → aggregate → filter → autodiscover. Returns the full picture."""
    throttle = psc.HostThrottle(psc.PER_HOST_DELAY if delay is None else delay)
    robots = psc.RobotsCache(client, throttle)
    hits: list[dict] = []
    skipped: list[str] = []
    if "hn" in indexes:
        hits += collect_hn(client, hn_limit, throttle=psc.HostThrottle(HN_DELAY), log=log)
    if "wikipedia" in indexes:
        hits += collect_wikipedia(client, wiki_pages, throttle=throttle, log=log)
    if "idw" in indexes:
        hits += collect_idw(client, idw_limit, throttle=throttle, robots=robots, log=log)
    if "reddit" in indexes:
        rh = collect_reddit(client, subs, throttle=throttle, log=log)
        if rh is None:
            skipped.append("reddit (no credentials)")
        else:
            hits += rh
    cands = [c for c in aggregate(hits) if c["count"] >= min_count]
    active = psc.active_feed_hosts() if active_hosts is None else active_hosts
    kept, dropped = filter_candidates(cands, active)
    shortlist = kept[:top]
    if feeds:
        autodiscover_feeds(shortlist, client, throttle, robots)
    return {"hits": len(hits), "candidates": kept, "shortlist": shortlist,
            "dropped": dropped, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Aggregator indices → source candidates (#97 WP2 helper)")
    ap.add_argument("--index", default="hn,wikipedia,idw,reddit",
                    help=f"comma list of {','.join(INDEXES)} (default: all)")
    ap.add_argument("--hn-limit", type=int, default=150, help="stories per HN list (top/best)")
    ap.add_argument("--wiki-page", action="append", metavar="lang:Title",
                    help="Wikipedia list page (repeatable; replaces the defaults)")
    ap.add_argument("--idw-limit", type=int, default=40, help="newest idw releases to inspect")
    ap.add_argument("--subreddit", action="append", help="subreddit (repeatable; replaces the defaults)")
    ap.add_argument("--top", type=int, default=40, help="candidates to autodiscover/probe")
    ap.add_argument("--min-count", type=int, default=1)
    ap.add_argument("--no-feeds", action="store_true", help="skip feed autodiscovery")
    ap.add_argument("--probe", action="store_true", help="run probe_source_compliance on candidates with a feed")
    ap.add_argument("--yaml", action="store_true", help="with --probe: print the YAML snippet")
    ap.add_argument("--json", help="write candidates (+ probe results) to this path")
    args = ap.parse_args(argv)

    indexes = [i.strip() for i in args.index.split(",") if i.strip()]
    bad = [i for i in indexes if i not in INDEXES]
    if bad:
        ap.error(f"unknown index {bad}; choose from {INDEXES}")
    wiki_pages = WIKI_DEFAULT_PAGES
    if args.wiki_page:
        wiki_pages = tuple(tuple(p.split(":", 1)) if ":" in p else ("en", p) for p in args.wiki_page)
    subs = tuple(args.subreddit) if args.subreddit else REDDIT_DEFAULT_SUBS

    def log(msg: str) -> None:
        print(msg, file=sys.stderr, flush=True)

    t0 = time.time()
    with httpx.Client(timeout=psc.TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": UA, "Accept": "text/html,application/json,*/*;q=0.8"}) as client:
        out = run(indexes, client, hn_limit=args.hn_limit, wiki_pages=wiki_pages, idw_limit=args.idw_limit,
                  subs=subs, top=args.top, min_count=args.min_count, feeds=not args.no_feeds, log=log)
        print(format_table(out["shortlist"]))
        print(f"\n{out['hits']} hits → {len(out['candidates'])} candidate hosts "
              f"({len(out['dropped'])} dropped: active sources/aggregators), shortlist {len(out['shortlist'])}, "
              f"{time.time() - t0:.0f}s" + (f"; skipped: {', '.join(out['skipped'])}" if out["skipped"] else ""))
        probe_results = None
        if args.probe:
            entries = [{"input": c["feed_url"], "feed_url": c["feed_url"], "name": c["host"],
                        "discovered_via": "+".join(sorted(c["indices"]))}
                       for c in out["shortlist"] if c.get("feed_url")]
            if entries:
                probe_results = psc.probe_sources(entries, client=client)
                print()
                print(psc.format_table(probe_results))
                counts = psc.summarize(probe_results)
                print("\nprobe: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
                if args.yaml:
                    print()
                    print(psc.format_yaml(probe_results, datetime.now(timezone.utc).strftime("%Y-%m-%d")))
            else:
                print("\nprobe: no candidate with a feed")
    if args.json:
        Path(args.json).write_text(json.dumps({**out, "probe": probe_results}, indent=1,
                                              ensure_ascii=False, default=str), encoding="utf-8")
        print(f"JSON: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
