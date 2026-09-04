#!/usr/bin/env python3
"""Source-compliance probe (issue #97, WP1).

Checks, per feed URL or domain, whether a source satisfies the machine-readable
usage conditions the owner set on 2026-09-03 for every source we poll:

  1. FEED       valid RSS/Atom (feedparser; entry count, newest entry date),
                conditional-GET capability (ETag / Last-Modified on the feed).
  2. ROBOTS     robots.txt verdict for our honest crawler UA (CatandaryTrendsBot,
                fallback `*`) — separately for the feed URL and one article.
  3. BOT STATUS GET of the newest article with the production UA:
                401/403/429 = `blocked` (no browser spoof, by policy).
  4. TDM        §44b Abs. 3 UrhG reservation signals via the production
                functions in pipeline/article_fetcher.py: `TDM-Reservation`
                header, `X-Robots-Tag`/`<meta robots>` noai, `<meta
                name="tdm-reservation">`, `/.well-known/tdmrep.json` (host
                cache data/tdmrep_cache.json, one lookup per host per day).
  5. LICENSE    hints only: `<link rel="license">`, creativecommons.org links,
                feed `license` element, "CC BY"/"CC0"/"Open Government
                Licence"/"Public Domain" in the page text. A structured signal
                (link/URL/feed element) yields `license` (short form); a bare
                text match yields `license_hint` only — WP3 decides `fulltext`.

Result per source: `tdm_status` + reason
    ok          feed valid, robots allow, article 200, no TDM signal
    reserved    machine-readable TDM reservation found (article or feed)
    blocked     bot blocked: feed/article 401/403/429, or robots.txt disallows
                the feed URL or the article URL
    feed_error  could not verify: feed invalid/unreachable, or the article
                request failed without a block (timeout, 5xx, 404)
    rejected    aggregator/platform domain (blocklist) — never a source
`fulltext_ok` is the article-level verdict alone (article 200 + robots allow +
no TDM): a robots rule that only covers the feed URL is a polling question for
the owner, not a reason to drop stored full text.

Etiquette: <= 1 request/s/host (thread-safe), timeout 15 s, 8 workers, at most
feed + article + tdmrep.json per source, robots.txt once per host per run.
Aggregators (trendhunter, springwise, techmeme, feedly, flipboard, news.google,
msn, yahoo, alltop, feedspot, ...) are rejected as candidates; sources already
in sources.yaml are never rejected by the blocklist (owner-curated).

    python scripts/probe_source_compliance.py https://example.com/feed example.org
    python scripts/probe_source_compliance.py --file candidates.txt --yaml
    python scripts/probe_source_compliance.py --all-active --yaml --json data/source_probe.json
    python scripts/probe_source_compliance.py --all-active --write   # patch sources.yaml protocol fields

`--file`: one URL or domain per line, optionally followed by whitespace and a
display name; `#` comments. `--yaml` prints a YAML snippet with the protocol
fields `tdm_checked`, `tdm_status`, `license` (only when detected) and
`discovered_via` (--discovered-via). `--write` patches the same three fields
into sources.yaml line-based (order + comments preserved; `fulltext: true` is
switched off when the article-level verdict is reserved/blocked).
"""
from __future__ import annotations

import argparse
import calendar
import json
import logging
import re
import sys
import threading
import time
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import feedparser
import httpx
import yaml

from pipeline import article_fetcher as af
from pipeline.config import load_sources

UA = af.UA                      # production crawler identity — never change here
FEED_FALLBACK_UA = "CatandaryTrendsBot/1.0 (RSS Feed Reader)"   # the poller's 403/406 retry token
logging.getLogger("httpx").setLevel(logging.WARNING)
TIMEOUT = 15.0
WORKERS = 8
PER_HOST_DELAY = 1.0
MAX_PAGE_CHARS = 400_000        # <head> + footer are what matters; no need to regex a 5 MB page
BLOCK_CODES = frozenset({401, 403, 429})
SOURCES_YAML = REPO / "sources.yaml"
ACCEPT_FEED = "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"

# Aggregators / platforms: a map for discovery (issue #97 comment 2026-09-03),
# never a source. Matched as exact host or as a parent domain of the host.
AGGREGATOR_DOMAINS = frozenset({
    "trendhunter.com", "springwise.com", "techmeme.com", "feedly.com",
    "flipboard.com", "news.google.com", "google.com", "msn.com", "yahoo.com",
    "alltop.com", "feedspot.com", "inoreader.com", "digg.com", "reddit.com",
    "news.ycombinator.com", "apple.news", "smartnews.com", "upday.com",
    "bing.com", "newsnow.co.uk", "muckrack.com", "paper.li", "scoop.it",
    "pocket.co", "getpocket.com", "newsbreak.com", "ground.news", "drudgereport.com",
    "facebook.com", "twitter.com", "x.com", "linkedin.com", "instagram.com",
    "tiktok.com", "youtube.com", "youtu.be", "t.co", "pinterest.com",
    "threads.net", "bsky.app", "mastodon.social", "wikipedia.org", "wikimedia.org",
    "archive.org", "web.archive.org", "github.com", "amazon.com",
})

FEED_FALLBACK_PATHS = ("/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml")
FEED_MIME_RE = re.compile(r"application/(?:rss|atom)\+xml", re.I)
_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.I)
_A_HREF_RE = re.compile(r"""<a\b[^>]*href\s*=\s*["']([^"']+)["']""", re.I)
_CC_URL_RE = re.compile(
    r"https?://creativecommons\.org/(licenses|publicdomain)/([a-z\-]+)/?([\d.]+)?", re.I)
_LICENSE_TEXT_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"\bCC0\b"), "CC0"),
    (re.compile(r"\bCC[\s-]BY(?:[\s-](?:NC|SA|ND))*(?:[\s-]\d\.\d)?\b"), "CC BY"),
    (re.compile(r"Open Government Licen[cs]e", re.I), "OGL"),
    (re.compile(r"\bPublic Domain\b", re.I), "Public Domain"),
    (re.compile(r"Creative Commons", re.I), "Creative Commons"),
)


# ------------------------------------------------------------------ helpers

class HostThrottle:
    """<= 1 request per PER_HOST_DELAY seconds per host, safe across threads:
    each caller reserves the next free slot under the lock, then sleeps."""

    def __init__(self, delay: float = PER_HOST_DELAY):
        self.delay = delay
        self._next: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next.get(host, 0.0))
            self._next[host] = slot + self.delay
        if slot > now:
            time.sleep(slot - now)


class RobotsCache:
    """robots.txt once per host per run; verdicts for our UA (or `*`).
    unreadable (network error) → 'unreadable' and allowed, like the fetcher."""

    def __init__(self, client: httpx.Client, throttle: HostThrottle):
        self.client, self.throttle = client, throttle
        self._parsers: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._lock = threading.Lock()
        self._host_locks: dict[str, threading.Lock] = {}
        self.requests = 0

    def _parser(self, host: str):
        with self._lock:
            if host in self._parsers:
                return self._parsers[host]
            hl = self._host_locks.setdefault(host, threading.Lock())
        with hl:                                   # one fetch per host, even under races
            with self._lock:
                if host in self._parsers:
                    return self._parsers[host]
            rp: urllib.robotparser.RobotFileParser | None
            try:
                self.throttle.wait(host)
                r = self.client.get(f"https://{host}/robots.txt")
                self.requests += 1
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except Exception:  # noqa: BLE001
                rp = None
            with self._lock:
                self._parsers[host] = rp
            return rp

    def verdict(self, url: str) -> str:
        host = urlsplit(url).netloc
        if not host:
            return "n/a"
        rp = self._parser(host)
        if rp is None:
            return "unreadable"
        try:
            return "allow" if rp.can_fetch(UA, url) else "disallow"
        except Exception:  # noqa: BLE001
            return "unreadable"


_TDMREP_LOCK = threading.Lock()
_TDMREP_HOST_LOCKS: dict[str, threading.Lock] = {}


def tdmrep_signal(url: str, client: httpx.Client) -> tuple[str | None, bool]:
    """(reservation reason from /.well-known/tdmrep.json, request_made).
    One lookup per host even under concurrency (per-host lock); the fetcher's
    host cache (data/tdmrep_cache.json, 24 h TTL) is shared with production."""
    host = urlsplit(url).netloc
    with _TDMREP_LOCK:
        hl = _TDMREP_HOST_LOCKS.setdefault(host, threading.Lock())
    with hl:
        entry = af._load_tdmrep_cache().get(host)
        cached = bool(entry and time.time() - float(entry.get("checked_at", 0)) < af.TDMREP_TTL_SECONDS)
        rules = af.tdmrep_rules(host, client)
    return af.tdm_reservation_in_tdmrep(url, rules), not cached


def _host(url: str) -> str:
    return (urlsplit(url).netloc or "").lower()


def _strip_www(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def is_aggregator(url_or_host: str) -> str | None:
    """The matching blocklist domain, or None."""
    host = _host(url_or_host) if "://" in url_or_host else url_or_host.split("/")[0].lower()
    host = host.split(":")[0]
    parts = host.split(".")
    for i in range(len(parts) - 1):
        cand = ".".join(parts[i:])
        if cand in AGGREGATOR_DOMAINS:
            return cand
    return None


def looks_like_domain(s: str) -> bool:
    """`example.com`, `https://example.com`, `https://example.com/` → domain input
    (needs feed autodiscovery); anything with a path is treated as a feed URL."""
    s = s.strip()
    if "://" not in s:
        return "/" not in s.rstrip("/")
    p = urlsplit(s)
    return p.path in ("", "/") and not p.query


def _newest_entry(entries) -> tuple[dict | None, str | None]:
    best, best_ts = None, None
    for e in entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        ts = calendar.timegm(t) if t else None
        if best is None or (ts is not None and (best_ts is None or ts > best_ts)):
            best, best_ts = e, ts
    date = datetime.fromtimestamp(best_ts, tz=timezone.utc).strftime("%Y-%m-%d") if best_ts else None
    return best, date


def _entry_link(entry) -> str | None:
    link = entry.get("link")
    if link:
        return link
    for l in entry.get("links") or []:
        if l.get("rel") in (None, "alternate") and l.get("href"):
            return l["href"]
    return None


def parse_feed_response(resp: httpx.Response) -> dict:
    """Feed facts from an HTTP response: validity, entries, newest, article,
    conditional-GET capability, feed-level license and TDM header."""
    out = {"feed_http": resp.status_code, "feed_ok": False, "feed_entries": 0,
           "feed_newest": None, "feed_error": None, "article_url": None,
           "conditional_get": "none", "feed_license": None, "feed_tdm": None}
    caps = [k for k, h in (("etag", "etag"), ("last-modified", "last-modified")) if resp.headers.get(h)]
    out["conditional_get"] = "+".join(caps) or "none"
    out["feed_tdm"] = af.tdm_reservation_in_headers(resp.headers)
    if resp.status_code != 200:
        out["feed_error"] = f"feed HTTP {resp.status_code}"
        return out
    parsed = feedparser.parse(resp.content)
    if not parsed.entries:
        exc = getattr(parsed, "bozo_exception", None)
        out["feed_error"] = f"no entries ({type(exc).__name__})" if parsed.bozo and exc else "no entries"
        return out
    out["feed_ok"] = True
    out["feed_entries"] = len(parsed.entries)
    newest, date = _newest_entry(parsed.entries)
    out["feed_newest"] = date
    out["article_url"] = _entry_link(newest) if newest else None
    lic = parsed.feed.get("license") or (newest.get("license") if newest else None)
    if lic:
        out["feed_license"] = str(lic)
    return out


def license_from_html(page: str) -> tuple[str | None, str | None]:
    """(license short form from a structured signal, evidence/hint).
    Structured = <link rel="license"> or a creativecommons.org link; a bare
    text mention only yields the hint."""
    if not page:
        return None, None
    head = page[:MAX_PAGE_CHARS]
    for m in _LINK_TAG_RE.finditer(head):
        tag = m.group(0)
        if re.search(r"""rel\s*=\s*["']?license["']?""", tag, re.I):
            href = re.search(r"""href\s*=\s*["']([^"']+)["']""", tag, re.I)
            if href:
                url = href.group(1)
                return _cc_short(url) or _short_from_text(url) or "license-link", f"link rel=license {url}"
    for m in _A_HREF_RE.finditer(head):
        short = _cc_short(m.group(1))
        if short:
            return short, f"a href {m.group(1)}"
    text = re.sub(r"<[^>]+>", " ", head)
    for pat, short in _LICENSE_TEXT_PATTERNS:
        m = pat.search(text)
        if m:
            return None, f"text: {m.group(0).strip()}"
    return None, None


def _cc_short(url: str) -> str | None:
    m = _CC_URL_RE.search(url or "")
    if not m:
        return None
    kind, code, version = m.group(1).lower(), m.group(2).lower(), m.group(3)
    if kind == "publicdomain":
        base = "CC0" if code.startswith("zero") else "Public Domain Mark"
    else:
        base = "CC " + code.upper()
    return f"{base} {version}" if version else base


def _short_from_text(s: str) -> str | None:
    for pat, short in _LICENSE_TEXT_PATTERNS:
        if short != "Creative Commons" and pat.search(s or ""):
            return short
    return None


# ----------------------------------------------------------- feed discovery

def discover_feed(domain_or_url: str, client: httpx.Client, throttle: HostThrottle,
                  robots: RobotsCache | None = None) -> tuple[str | None, httpx.Response | None, list[str]]:
    """Feed URL for a domain: <link rel="alternate" type="application/rss+xml|atom+xml">
    on the homepage, then the usual fallback paths. Returns (feed_url, feed
    response, tried URLs). Stops at the first URL feedparser accepts."""
    base = domain_or_url.strip()
    if "://" not in base:
        base = "https://" + base
    base = base.rstrip("/") + "/"
    tried: list[str] = []
    candidates: list[str] = []
    try:
        if robots is None or robots.verdict(base) != "disallow":
            throttle.wait(_host(base))
            tried.append(base)
            r = client.get(base)
            if r.status_code == 200 and "html" in (r.headers.get("content-type") or ""):
                for m in _LINK_TAG_RE.finditer(r.text[:MAX_PAGE_CHARS]):
                    tag = m.group(0)
                    if not re.search(r"""rel\s*=\s*["']?alternate["']?""", tag, re.I):
                        continue
                    if not FEED_MIME_RE.search(tag):
                        continue
                    href = re.search(r"""href\s*=\s*["']([^"']+)["']""", tag, re.I)
                    if href:
                        candidates.append(urljoin(str(r.url), href.group(1)))
    except Exception:  # noqa: BLE001
        pass
    candidates += [urljoin(base, p) for p in FEED_FALLBACK_PATHS]
    seen: set[str] = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            throttle.wait(_host(url))
            tried.append(url)
            r = client.get(url, headers={"Accept": ACCEPT_FEED})
        except Exception:  # noqa: BLE001
            continue
        if r.status_code == 200 and feedparser.parse(r.content).entries:
            return str(url), r, tried
    return None, None, tried


# ------------------------------------------------------------------- probe

def classify(r: dict) -> tuple[str, str]:
    """Pure status decision from the collected facts → (tdm_status, reason)."""
    if r.get("rejected"):
        return "rejected", f"aggregator/platform domain ({r['rejected']}) — never a source"
    if r.get("feed_tdm"):
        return "reserved", f"feed {r['feed_tdm']}"
    if r.get("feed_http") in BLOCK_CODES:
        return "blocked", f"feed HTTP {r['feed_http']} for the bot UA"
    if not r.get("feed_ok"):
        return "feed_error", r.get("feed_error") or "feed invalid"
    if r.get("tdm_signal"):
        return "reserved", r["tdm_signal"]
    if r.get("robots_feed") == "disallow":
        return "blocked", "robots.txt disallows the feed URL"
    if r.get("robots_article") == "disallow":
        return "blocked", "robots.txt disallows the article URL"
    code = r.get("article_http")
    if code in BLOCK_CODES:
        return "blocked", f"article HTTP {code} for the bot UA"
    if not r.get("article_url"):
        return "feed_error", "feed entries carry no link"
    if code != 200:
        return "feed_error", (f"article HTTP {code} (unverified)" if code
                              else f"article unreachable ({r.get('article_error') or 'error'})")
    return "ok", "feed valid, robots allow, article 200, no TDM signal"


def fulltext_ok(r: dict) -> bool:
    """Article-level verdict: may full text of this source be stored?"""
    return (r.get("article_http") == 200 and r.get("robots_article") != "disallow"
            and not r.get("tdm_signal") and not r.get("feed_tdm"))


def probe_one(entry: dict, client: httpx.Client, throttle: HostThrottle,
              robots: RobotsCache) -> dict:
    """One source: feed → robots → article → TDM → license. `entry` needs
    `input` (feed URL or domain) and may carry name/feed_url/from_config/…"""
    r = {"name": entry.get("name"), "input": entry.get("input") or entry.get("feed_url"),
         "feed_url": entry.get("feed_url"), "vertical": entry.get("vertical"),
         "from_config": bool(entry.get("from_config")), "fulltext": entry.get("fulltext"),
         "prev_status": entry.get("prev_status"), "discovered_via": entry.get("discovered_via"),
         "rejected": None, "feed_http": None, "feed_ok": False, "feed_entries": 0,
         "feed_newest": None, "feed_error": None, "conditional_get": "none",
         "feed_license": None, "feed_tdm": None, "robots_feed": "n/a",
         "article_url": None, "article_final_url": None, "article_http": None,
         "article_error": None, "robots_article": "n/a", "tdm_signal": None,
         "license": None, "license_hint": None, "feed_ua_fallback": False,
         "requests": 0, "tried": []}
    target = r["input"] or ""
    if not r["from_config"]:
        r["rejected"] = is_aggregator(target)
        if r["rejected"]:
            r["tdm_status"], r["reason"] = classify(r)
            r["fulltext_ok"] = False
            return r
    try:
        if not r["feed_url"] and looks_like_domain(target):
            feed_url, resp, tried = discover_feed(target, client, throttle, robots)
            r["tried"] = tried
            r["requests"] += len(tried)
            if not feed_url:
                r["feed_error"] = f"no feed found ({len(tried)} URLs tried)"
                r["tdm_status"], r["reason"] = classify(r)
                r["fulltext_ok"] = False
                return r
            r["feed_url"] = feed_url
        else:
            r["feed_url"] = r["feed_url"] or (target if "://" in target else "https://" + target)
            resp = None
        if not r["name"]:
            r["name"] = _strip_www(_host(r["feed_url"]))
        # 1. feed (mirrors pipeline.feed_poller: one retry with the short UA
        #    token on 403/406 — some WAF rules trip on the URL/@ in the identity)
        if resp is None:
            try:
                throttle.wait(_host(r["feed_url"]))
                r["requests"] += 1
                resp = client.get(r["feed_url"], headers={"Accept": ACCEPT_FEED})
                if resp.status_code in (403, 406):
                    throttle.wait(_host(r["feed_url"]))
                    r["requests"] += 1
                    retry = client.get(r["feed_url"], headers={"Accept": ACCEPT_FEED,
                                                               "User-Agent": FEED_FALLBACK_UA})
                    if retry.status_code == 200:
                        resp = retry
                        r["feed_ua_fallback"] = True
            except Exception as e:  # noqa: BLE001
                r["feed_error"] = f"feed unreachable ({type(e).__name__})"
                resp = None
        if resp is not None:
            r.update(parse_feed_response(resp))
        r["robots_feed"] = robots.verdict(r["feed_url"])
        if not r["feed_ok"] or not r["article_url"]:
            r["tdm_status"], r["reason"] = classify(r)
            r["fulltext_ok"] = False
            return r
        # 2.+4. article: robots, tdmrep.json, GET, headers, meta, license
        url = r["article_url"]
        r["robots_article"] = robots.verdict(url)
        signal, made = tdmrep_signal(url, client)
        r["requests"] += int(made)
        r["tdm_signal"] = signal
        if r["robots_article"] != "disallow" and not signal:
            try:
                throttle.wait(_host(url))
                r["requests"] += 1
                a = client.get(url)
                r["article_http"] = a.status_code
                r["article_final_url"] = str(a.url)
                r["tdm_signal"] = af.tdm_reservation_in_headers(a.headers)
                ctype = a.headers.get("content-type") or ""
                if a.status_code == 200 and "html" in ctype:
                    page = a.text[:MAX_PAGE_CHARS]
                    r["tdm_signal"] = r["tdm_signal"] or af.tdm_reservation_in_html(page)
                    r["license"], r["license_hint"] = license_from_html(page)
            except Exception as e:  # noqa: BLE001
                r["article_error"] = type(e).__name__
        if r["feed_license"] and not r["license"]:
            r["license"] = _cc_short(r["feed_license"]) or _short_from_text(r["feed_license"]) or "feed-license"
            r["license_hint"] = r["license_hint"] or f"feed license: {r['feed_license']}"
    except Exception as e:  # noqa: BLE001 — never lose a row to one bad host
        r["feed_error"] = r["feed_error"] or f"probe error ({type(e).__name__})"
    r["tdm_status"], r["reason"] = classify(r)
    r["fulltext_ok"] = fulltext_ok(r)
    return r


def make_client(timeout: float = TIMEOUT) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True,
                        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})


def probe_sources(entries: list[dict], client: httpx.Client | None = None,
                  workers: int = WORKERS, delay: float = PER_HOST_DELAY,
                  progress=None) -> list[dict]:
    """Probe many sources concurrently; results in input order. Duplicate
    feed URLs are probed once and the result is copied."""
    own = client is None
    client = client or make_client()
    throttle = HostThrottle(delay)
    robots = RobotsCache(client, throttle)
    af._load_tdmrep_cache()                      # initialise the shared cache before the threads
    uniq: dict[str, dict] = {}
    order: list[str] = []
    for e in entries:
        key = (e.get("feed_url") or e.get("input") or "").strip()
        if key not in uniq:
            uniq[key] = e
            order.append(key)
    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futures = {k: ex.submit(probe_one, uniq[k], client, throttle, robots) for k in order}
            done = 0
            results_by_key: dict[str, dict] = {}
            for k in order:
                results_by_key[k] = futures[k].result()
                done += 1
                if progress:
                    progress(done, len(order), results_by_key[k])
    finally:
        if own:
            client.close()
    out = []
    for e in entries:
        key = (e.get("feed_url") or e.get("input") or "").strip()
        res = dict(results_by_key[key])
        res["name"] = e.get("name") or res["name"]
        res["vertical"] = e.get("vertical")
        res["fulltext"] = e.get("fulltext")
        res["prev_status"] = e.get("prev_status")
        out.append(res)
    return out


# ----------------------------------------------------------- sources.yaml

def iter_active_sources(cfg: dict | None = None) -> list[dict]:
    """Every pollable source in sources.yaml (verticals sources/science +
    cross_industry groups) that is not `active: false`, as probe entries."""
    cfg = cfg or load_sources()
    out: list[dict] = []

    def put(s: dict, vertical: str) -> None:
        if s.get("active") is False or not s.get("feed_url"):
            return
        out.append({"name": s["name"], "feed_url": s["feed_url"], "input": s["feed_url"],
                    "vertical": vertical, "from_config": True,
                    "fulltext": bool(s.get("fulltext")),
                    "prev_status": s.get("tdm_status"),
                    "prev_checked": str(s.get("tdm_checked") or "") or None,
                    "license": s.get("license")})

    for v, groups in (cfg.get("verticals") or {}).items():
        for key in ("sources", "science"):
            for s in groups.get(key) or []:
                put(s, v)
    for _g, entries in (cfg.get("cross_industry") or {}).items():
        for s in entries or []:
            put(s, "CROSS")
    return out


def active_feed_hosts(cfg: dict | None = None) -> set[str]:
    """Feed hosts (without www.) of all active sources — discovery filter."""
    return {_strip_www(_host(e["feed_url"])) for e in iter_active_sources(cfg)}


_ITEM_RE = re.compile(r"^(\s*)- name:\s*(.*?)\s*$")
_FIELD_RE = re.compile(r"^(\s*)([A-Za-z_][\w-]*):(.*)$")


def _field_value(line: str) -> str:
    m = _FIELD_RE.match(line)
    if not m:
        return ""
    val = m.group(3).strip()
    if " #" in val:
        val = val.split(" #", 1)[0].rstrip()
    return val.strip("'\"")


def _split_items(lines: list[str]) -> list[dict]:
    """List items that start with `- name:`: {start, last, indent, fields{key: line index}}.
    An item ends at the next non-blank line indented <= its own dash."""
    items: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        m = _ITEM_RE.match(lines[i])
        if not m:
            i += 1
            continue
        indent = len(m.group(1))
        field_indent = indent + 2
        fields = {"name": i}
        last = i
        j = i + 1
        while j < n:
            line = lines[j]
            stripped = line.strip()
            if not stripped:
                j += 1
                continue
            cur = len(line) - len(line.lstrip(" "))
            if cur <= indent:
                break
            if not stripped.startswith("#"):
                fm = _FIELD_RE.match(line)
                if fm and cur == field_indent:
                    fields[fm.group(2)] = j
            last = j
            j += 1
        items.append({"start": i, "last": last, "indent": indent, "fields": fields})
        i = j
    return items


def _fmt_field(indent: int, key: str, value: str, comment: str | None = None) -> str:
    line = f"{' ' * indent}{key}: {value}"
    return f"{line}   # {comment}" if comment else line


def write_protocol_fields(yaml_path: Path | str, results: list[dict], today: str,
                          dry_run: bool = False) -> dict:
    """Patch tdm_checked / tdm_status / license (+ fulltext off) into
    sources.yaml, line-based: order and comments of the file are preserved,
    items are matched by feed_url. Returns a summary; raises if the patched
    file would not parse or would lose an item."""
    path = Path(yaml_path)
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    by_url: dict[str, dict] = {}
    for r in results:
        if r.get("feed_url") and r.get("tdm_status") not in (None, "rejected"):
            by_url[r["feed_url"].strip()] = r
    before = yaml.safe_load(text)
    summary = {"updated": 0, "fulltext_off": [], "missing": sorted(
        set(by_url) - {_field_value(lines[it["fields"]["feed_url"]])
                       for it in _split_items(lines) if "feed_url" in it["fields"]})}
    items = _split_items(lines)
    for it in reversed(items):                  # bottom-up: indices stay valid
        f = it["fields"]
        if "feed_url" not in f:
            continue
        r = by_url.get(_field_value(lines[f["feed_url"]]))
        if r is None:
            continue
        fi = it["indent"] + 2
        status = r["tdm_status"]
        reason = None if status == "ok" else r.get("reason")
        new_fields = [("tdm_checked", f'"{today}"', None), ("tdm_status", status, reason)]
        if r.get("license"):
            new_fields.append(("license", r["license"], None))
        inserts: list[str] = []
        for key, value, comment in new_fields:
            line = _fmt_field(fi, key, value, comment)
            if key in f:
                lines[f[key]] = line
            else:
                inserts.append(line)
        if inserts:
            lines[it["last"] + 1:it["last"] + 1] = inserts
        if ("fulltext" in f and status in ("reserved", "blocked") and not r.get("fulltext_ok")
                and _field_value(lines[f["fulltext"]]).lower() == "true"):
            lines[f["fulltext"]] = _fmt_field(fi, "fulltext", "false",
                                              f"{r.get('reason')} — Prüfung {today}, Volltext automatisch aus (#97)")
            summary["fulltext_off"].append(r.get("name") or r["feed_url"])
        summary["updated"] += 1
    new_text = "\n".join(lines)
    after = yaml.safe_load(new_text)
    if _item_keys(before) != _item_keys(after):
        raise RuntimeError("sources.yaml patch would change the set of sources — not written")
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    summary["text"] = new_text
    return summary


def _item_keys(cfg: dict) -> list[tuple[str, str]]:
    keys = []
    for _v, groups in (cfg.get("verticals") or {}).items():
        for key in ("sources", "science", "radar"):
            for s in groups.get(key) or []:
                if isinstance(s, dict):
                    keys.append((s.get("name"), s.get("feed_url")))
    for _g, entries in (cfg.get("cross_industry") or {}).items():
        for s in entries or []:
            keys.append((s.get("name"), s.get("feed_url")))
    for s in cfg.get("funding_apis") or []:
        keys.append((s.get("name"), s.get("feed_url")))
    return keys


# ------------------------------------------------------------------ output

def format_table(results: list[dict]) -> str:
    cols = [("name", 28), ("status", 10), ("feed", 16), ("robots", 12), ("http", 5),
            ("tdm", 26), ("license", 14), ("cond", 9), ("reason", 48)]
    head = " ".join(f"{c:<{w}}" for c, w in cols)
    rows = [head, "-" * len(head)]
    for r in results:
        feed = (f"{r['feed_entries']}e {r['feed_newest'] or '?'}" if r.get("feed_ok")
                else (f"HTTP {r['feed_http']}" if r.get("feed_http") else "—"))
        robots = f"{_abbr(r.get('robots_feed'))}/{_abbr(r.get('robots_article'))}"
        vals = [(r.get("name") or "")[:28], r.get("tdm_status", ""), feed, robots,
                str(r.get("article_http") or ""), (r.get("tdm_signal") or r.get("feed_tdm") or "")[:26],
                (r.get("license") or ("hint" if r.get("license_hint") else ""))[:14],
                r.get("conditional_get", ""), (r.get("reason") or "")[:48]]
        rows.append(" ".join(f"{str(v):<{w}}" for v, (_, w) in zip(vals, cols)))
    return "\n".join(rows)


def _abbr(v: str | None) -> str:
    return {"allow": "allow", "disallow": "DENY", "unreadable": "unr", "n/a": "-"}.get(v or "n/a", v or "-")


def summarize(results: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.get("tdm_status", "?")] = counts.get(r.get("tdm_status", "?"), 0) + 1
    return counts


def _yaml_str(s: str) -> str:
    return yaml.safe_dump(s, default_style=None, allow_unicode=True).strip().removesuffix("\n...").strip()


def format_yaml(results: list[dict], today: str, discovered_via: str | None = None) -> str:
    """YAML snippet: protocol fields per source, ready to paste into
    sources.yaml (config sources) or to seed a new entry (candidates)."""
    out = [f"# probe_source_compliance {today} — tdm_status: ok|reserved|blocked|feed_error (#97)"]
    for r in results:
        via = r.get("discovered_via") or discovered_via
        if r.get("tdm_status") == "rejected":
            out.append(f"# REJECTED {r.get('name') or r.get('input')}: {r.get('reason')}")
            continue
        out.append(f"- name: {_yaml_str(r.get('name') or '')}")
        out.append(f"  feed_url: {r.get('feed_url') or r.get('input')}")
        if not r.get("from_config"):
            out.append("  type: trade_media          # TODO WP3: verify type + vertical")
            out.append("  lead_time_tier: market     # TODO WP3")
        out.append(f'  tdm_checked: "{today}"')
        status = r.get("tdm_status")
        out.append(_fmt_field(2, "tdm_status", status, None if status == "ok" else r.get("reason")))
        if r.get("license"):
            out.append(_fmt_field(2, "license", r["license"], r.get("license_hint")))
        elif r.get("license_hint"):
            out.append(f"  # license hint (unstructured): {r['license_hint']}")
        if via:
            out.append(f"  discovered_via: {_yaml_str(via)}")
    return "\n".join(out)


def read_input_file(path: Path | str) -> list[dict]:
    entries = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        entries.append({"input": parts[0], "name": parts[1].strip() if len(parts) > 1 else None})
    return entries


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source compliance probe (#97 WP1)")
    ap.add_argument("targets", nargs="*", help="feed URLs or domains")
    ap.add_argument("--file", help="file with one URL/domain per line (+ optional name)")
    ap.add_argument("--all-active", action="store_true", help="every active source in sources.yaml")
    ap.add_argument("--yaml", action="store_true", help="print YAML snippet with protocol fields")
    ap.add_argument("--json", help="write full results as JSON to this path")
    ap.add_argument("--write", action="store_true",
                    help="patch tdm_checked/tdm_status/license into sources.yaml (config sources only)")
    ap.add_argument("--discovered-via", help="value for discovered_via in the YAML snippet")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--timeout", type=float, default=TIMEOUT)
    ap.add_argument("--delay", type=float, default=PER_HOST_DELAY, help="seconds between requests per host")
    ap.add_argument("--quiet", action="store_true", help="no progress on stderr")
    args = ap.parse_args(argv)

    entries: list[dict] = []
    if args.all_active:
        entries += iter_active_sources()
    if args.file:
        entries += read_input_file(args.file)
    entries += [{"input": t, "name": None} for t in args.targets]
    for e in entries:
        if args.discovered_via and not e.get("discovered_via"):
            e["discovered_via"] = args.discovered_via
    if not entries:
        ap.error("nothing to probe: give URLs/domains, --file or --all-active")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    t0 = time.time()

    def progress(done: int, total: int, r: dict) -> None:
        if not args.quiet:
            print(f"[{done}/{total}] {r.get('tdm_status'):<10} {r.get('name') or r.get('input')}",
                  file=sys.stderr, flush=True)

    results = probe_sources(entries, client=make_client(args.timeout), workers=args.workers,
                            delay=args.delay, progress=progress)
    print(format_table(results))
    counts = summarize(results)
    print(f"\n{len(results)} sources, {sum(r['requests'] for r in results)} requests, "
          f"{time.time() - t0:.0f}s — " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"JSON: {args.json}")
    if args.yaml:
        print()
        print(format_yaml(results, today, args.discovered_via))
    if args.write:
        s = write_protocol_fields(SOURCES_YAML, [r for r in results if r.get("from_config")], today)
        print(f"sources.yaml: {s['updated']} items updated, fulltext off: {len(s['fulltext_off'])} "
              f"{s['fulltext_off'] or ''}, not found: {len(s['missing'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
