#!/usr/bin/env python3
"""Full-text article fetcher (Epic W3.1 / issue #11).

The pipeline classifies + generates from the RSS excerpt alone (~70 words), so
the model inflates a teaser into 150-250 words — the root cause of the ~1/3
fabrication rate the grounding gate catches. This enriches `raw_entries.raw_content`
with the real article text so downstream stages work from substance, not a stub.

Legal guardrails (repo principle: legal primary sources only):
  - OPT-IN per source: only sources flagged `fulltext: true` in sources.yaml are
    fetched. Default off. Start set: the press wires + The Conversation.
  - robots.txt is honoured (per-host cache).
  - <= 1 request/second/host, descriptive User-Agent.
  - No retroactive mass backfill — only unprocessed entries without raw_content.

    python -m pipeline.article_fetcher            # fetch a batch (default 100)
    python -m pipeline.article_fetcher --limit 500
    python -m pipeline.article_fetcher --url https://…   # one-off test
"""
from __future__ import annotations

import argparse
import logging
import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx
import trafilatura

from pipeline.config import load_sources
from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("article_fetcher")

UA = "CatandaryTrends/1.0 (+https://catandary.de; trends@catandary.de)"
MIN_TEXT_CHARS = 400          # below this the extraction is not worth keeping
MAX_TEXT_CHARS = 12_000       # cap what we store (stages slice the first ~1.5k anyway)
PER_HOST_DELAY = 1.0          # seconds between requests to the same host

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}


def fulltext_source_names() -> set[str]:
    """Source names flagged `fulltext: true` in sources.yaml (verticals + cross)."""
    cfg = load_sources()
    names: set[str] = set()
    for _v, groups in (cfg.get("verticals") or {}).items():
        for key in ("sources", "science"):
            for s in groups.get(key) or []:
                if s.get("fulltext"):
                    names.add(s["name"])
    for _g, entries in (cfg.get("cross_industry") or {}).items():
        for s in entries or []:
            if s.get("fulltext"):
                names.add(s["name"])
    return names


def _robots_ok(url: str) -> bool:
    host = urlparse(url).netloc
    if host not in _robots:
        # Fetch robots.txt via httpx with a timeout — urllib's rp.read() has no
        # timeout and hangs on slow hosts.
        try:
            r = httpx.get(f"https://{host}/robots.txt", timeout=8,
                          follow_redirects=True, headers={"User-Agent": UA})
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            _robots[host] = rp
        except Exception:
            _robots[host] = None  # unreadable robots → treat as allowed
    rp = _robots[host]
    if rp is None:
        return True
    try:
        return rp.can_fetch(UA, url)
    except Exception:
        return True


def _throttle(host: str) -> None:
    last = _last_hit.get(host, 0.0)
    wait = PER_HOST_DELAY - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()


def fetch_fulltext(url: str, client: httpx.Client | None = None) -> str | None:
    """Fetch + extract clean article text, or None (robots/blocked/too short)."""
    if not _robots_ok(url):
        logger.info("robots.txt disallows %s", url)
        return None
    host = urlparse(url).netloc
    _throttle(host)
    own = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True,
                                    headers={"User-Agent": UA})
    try:
        r = client.get(url)
        if r.status_code != 200 or not r.text:
            return None
        text = trafilatura.extract(
            r.text, include_comments=False, include_tables=False,
            no_fallback=False, favor_precision=True)
        if not text or len(text) < MIN_TEXT_CHARS:
            return None
        return text[:MAX_TEXT_CHARS]
    except Exception as e:  # noqa: BLE001
        logger.debug("fetch failed %s: %r", url, e)
        return None
    finally:
        if own:
            client.close()


def fetch_batch(limit: int = 100) -> int:
    """Fill raw_content for unprocessed, opt-in-source entries that lack it."""
    names = fulltext_source_names()
    if not names:
        logger.warning("no sources flagged fulltext:true — nothing to do")
        return 0
    ph = ",".join("?" * len(names))
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT re.id, re.url FROM raw_entries re JOIN sources s ON re.source_id = s.id "
            f"WHERE s.name IN ({ph}) AND re.processed = FALSE "
            "AND (re.raw_content IS NULL OR re.raw_content = '') "
            "ORDER BY re.id DESC LIMIT ?", (*names, limit)).fetchall()
    logger.info("%d entries to enrich from %d opt-in sources", len(rows), len(names))
    filled = 0
    with httpx.Client(timeout=20, follow_redirects=True,
                      headers={"User-Agent": UA}) as client:
        for r in rows:
            rid = r["id"] if isinstance(r, dict) else r[0]
            url = r["url"] if isinstance(r, dict) else r[1]
            text = fetch_fulltext(url, client=client)
            if text:
                with get_connection() as conn:
                    conn.execute("UPDATE raw_entries SET raw_content = ? WHERE id = ?",
                                 (text, rid))
                filled += 1
    logger.info("enriched %d/%d entries with full text", filled, len(rows))
    return filled


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch full article text (#11)")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--url", help="fetch one URL and print the text (test)")
    args = ap.parse_args()
    if args.url:
        text = fetch_fulltext(args.url)
        print(f"--- {len(text) if text else 0} chars ---")
        print((text or "(nothing extracted)")[:2000])
        return 0
    fetch_batch(args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
