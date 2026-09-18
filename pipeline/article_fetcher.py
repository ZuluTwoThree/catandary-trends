#!/usr/bin/env python3
"""Full-text article fetcher (Epic W3.1 / issue #11).

The pipeline classifies + generates from the RSS excerpt alone (~70 words), so
the model inflates a teaser into 150-250 words — the root cause of the ~1/3
fabrication rate the grounding gate catches. This enriches `raw_entries.raw_content`
with the real article text so downstream stages work from substance, not a stub.

Legal guardrails (repo principle: legal primary sources only; legal basis for the
copy itself is text and data mining, §44b UrhG — which is only available while no
machine-readable reservation exists and the copy is deleted once no longer needed):
  - OPT-IN per source: only sources flagged `fulltext: true` in sources.yaml are
    fetched. Default off. 160 of 238 RSS sources are opted in (commit eb0931c,
    owner-approved after a robots + extractability probe; HBR, MIT Technology
    Review, Project Syndicate, Nature and paywalled/blocked feeds stay out).
  - robots.txt is honoured (per-host cache; RFC 9309 matching — wildcards,
    `$`, longest rule wins, exact product token — since 2026-09-04, #97).
  - TDM reservation is honoured (TDM_RESPECT=1, default on): a rights holder's
    machine-readable opt-out (TDMRep header/meta, /.well-known/tdmrep.json,
    `noai`/`noimageai` robots directives) means the full text is NOT stored —
    the entry keeps only the feed's own title + teaser, like a non-opt-in source.
    /.well-known/tdmrep.json is looked up at most once per host per day
    (data/tdmrep_cache.json).
  - <= 1 request/second/host, honest User-Agent with contact (CRAWLER_USER_AGENT).
  - No retroactive mass backfill — only unprocessed entries without raw_content.
  - Retention: scripts/purge_raw_content.py NULLs stored full text once the
    entry is processed and older than the judge window (default 90 days).

    python -m pipeline.article_fetcher            # fetch a batch (default 100)
    python -m pipeline.article_fetcher --limit 500
    python -m pipeline.article_fetcher --url https://…   # one-off test
"""
from __future__ import annotations

import argparse
import fnmatch
import html as html_lib
import json
import logging
import os
import re
import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlsplit

from collections import Counter

import httpx
from concurrent.futures import ThreadPoolExecutor
import trafilatura

from pipeline.config import DATA_DIR, load_sources
from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("article_fetcher")

# Honest crawler identity (compliance review 2026-09-02; V2 since 2026-09-11,
# Owner): product token + a URL that explains what the bot does and how to
# reach us. The mailbox moved OFF the UA line and onto that page — a publisher
# can still steer the bot (robots.txt token) and still reach us, but the
# address no longer travels in every request log. The same value is used by
# pipeline.feed_poller — keep the defaults identical (tested).
DEFAULT_USER_AGENT = ("CatandaryTrendsBot/1.0 "
                      "(+https://catandary.de/trends/methodology)")
UA = os.getenv("CRAWLER_USER_AGENT", DEFAULT_USER_AGENT)
MIN_TEXT_CHARS = 400          # below this the extraction is not worth keeping
MAX_TEXT_CHARS = 12_000       # cap what we store (stages slice the first ~1.5k anyway)
PDF_MAX_PAGES = 60            # a Grundschutz building block is ~10 pages; a whole compendium is not wanted
PER_HOST_DELAY = 1.0          # seconds between requests to the same host
# Hosts, die die Regelrate nicht vertragen, bekommen ihre eigene. Project
# Syndicate antwortete im Nachhollauf vom 2026-09-17 auf 37 von 52 Anfragen mit
# 429 bei 1/s. Gemessen am selben Tag: bei 1,5 s kamen 9 durch, dann 429; bei
# 3 s direkt danach 20 von 20 mit 429; nach 10 min Pause mit 10 s Abstand 30
# von 30 mit 429. Das ist ein Kontingent je Zeitfenster mit langer Strafzeit,
# kein Intervall — der Abstand ist nicht der Hebel. Der Nachtlauf holt dort
# 5-10 Artikel und bleibt unter jedem Kontingent; 2 s halten den Host nur von
# Bursts fern (Owner 2026-09-17: 10 s zu langsam).
HOST_DELAYS: dict[str, float] = {
    "www.project-syndicate.org": 2.0,
}


def host_delay(host: str) -> float:
    """Seconds to keep between two requests to `host`."""
    return HOST_DELAYS.get(host, PER_HOST_DELAY)
FETCH_WORKERS = int(os.getenv("FETCH_WORKERS", "8"))   # fetch_batch threads (hosts in parallel, never a host)

# --- TDM reservation (§44b Abs. 3 UrhG; TDMRep, W3C Community Group) ---------
# A rights holder who reserves text and data mining in machine-readable form
# takes the §44b exception away — so no full-text copy may be stored. Checked
# signals, most specific first:
#   (a) HTTP header  `TDM-Reservation: 1`
#   (b) HTTP header  `X-Robots-Tag` carrying `noai` / `noimageai`
#   (c) <meta name="tdm-reservation" content="1">
#   (d) <meta name="robots" content="… noai …"> (conservative: not a TDM
#       standard, but an explicit opt-out from AI use — treated as a reservation)
#   (e) /.well-known/tdmrep.json per host (location patterns, cached one day)
# TDM_RESPECT=0 switches the check off (for tests / a deliberate owner decision).
TDM_RESPECT = os.getenv("TDM_RESPECT", "1") == "1"
TDMREP_CACHE_PATH = Path(os.getenv("TDMREP_CACHE_PATH", str(DATA_DIR / "tdmrep_cache.json")))
TDMREP_TTL_SECONDS = 24 * 3600      # max. one /.well-known/tdmrep.json request per host per day
NOAI_TOKENS = frozenset({"noai", "noimageai"})
_HEAD_SCAN_CHARS = 200_000          # <meta> lives in <head>; no need to regex a 2 MB page

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}
_tdmrep_cache: dict[str, dict] | None = None


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


def _rule_regex(pattern: str) -> re.Pattern:
    """robots.txt path pattern → regex: `*` = any run, trailing `$` = end anchor,
    otherwise prefix match (RFC 9309 §2.2.3)."""
    pattern = unquote(pattern or "")
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    # `?` MUSS in der safe-Liste stehen. Ohne es kodiert quote() das Fragezeichen
    # der Regel zu %3F, waehrend robots_allows den Query der URL roh anhaengt —
    # die beiden konnten sich nie treffen, und damit war JEDE query-basierte
    # Regel wirkungslos: `Disallow: /*?utm_source=`, `/?rest_route=`, `/*?s=`.
    # Gefunden am 2026-09-16 bei der Quellenpruefung von sciencealert.com, wo
    # unser Pruefer die per robots gesperrte WordPress-Schnittstelle als erlaubt
    # meldete.
    parts = [re.escape(quote(p, safe="/:@!$&'()*+,;=~?")) for p in pattern.split("*")]
    return re.compile("^" + ".*".join(parts) + ("$" if anchored else ""))


def robots_allows(rp: urllib.robotparser.RobotFileParser, ua: str, url: str) -> bool:
    """RFC 9309 verdict on a parsed robots.txt: the group whose user-agent line
    equals our product token (else `*`), wildcard-aware rules, the longest
    matching rule wins, a tie goes to Allow. urllib's own can_fetch() reads
    `*` literally (Condé Nast's `Disallow: /*` or idw's `Disallow:
    /*pressreleasesrss` would silently pass) and picks groups by substring
    (`User-agent: bot` would apply to us). Found by the #97 probe 2026-09-04."""
    token = ua.split("/")[0].strip().lower()
    entry = next((e for e in rp.entries
                  if any(a.strip().lower() == token for a in e.useragents)), None) or rp.default_entry
    if entry is None:
        return True
    parts = urlsplit(url)
    path = quote(unquote(parts.path or "/"), safe="/:@!$&'()*+,;=~")
    if parts.query:
        path += "?" + parts.query
    best_len, best_allow = -1, True
    for rule in entry.rulelines:
        raw = unquote(rule.path)
        if not raw:                              # `Disallow:` (empty) = allow everything
            continue
        if _rule_regex(raw).match(path):
            n = len(raw)
            if n > best_len or (n == best_len and rule.allowance):
                best_len, best_allow = n, bool(rule.allowance)
    return best_allow


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
        return robots_allows(rp, UA, url)
    except Exception:
        return True


# Ein Schloss je Host: die Bremse muss auch dann halten, wenn mehrere Threads
# fetchen (scripts/refetch_fulltext.py, 2026-09-10). Vorher war das ein
# ungeschuetztes read-modify-write — zwei Threads lasen denselben Zeitstempel und
# schlugen gleichzeitig auf demselben Server auf. Die Sperre serialisiert je
# Host (also weiterhin hoechstens 1 Anfrage/s/Host) und laesst verschiedene
# Hosts parallel laufen.
_throttle_registry_lock = threading.Lock()
_host_locks: dict[str, threading.Lock] = {}


def _throttle(host: str) -> None:
    with _throttle_registry_lock:
        lock = _host_locks.setdefault(host, threading.Lock())
    with lock:
        last = _last_hit.get(host, 0.0)
        wait = host_delay(host) - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        _last_hit[host] = time.time()


# --- TDM reservation: header + meta ------------------------------------------

_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")


def _meta_tags(page: str) -> list[dict[str, str]]:
    """Attribute dicts of every <meta> tag in the first _HEAD_SCAN_CHARS."""
    out: list[dict[str, str]] = []
    for m in _META_TAG_RE.finditer(page[:_HEAD_SCAN_CHARS]):
        attrs: dict[str, str] = {}
        for a in _ATTR_RE.finditer(m.group(0)):
            val = a.group(2) if a.group(2) is not None else (a.group(3) or a.group(4) or "")
            attrs[a.group(1).lower()] = html_lib.unescape(val)
        out.append(attrs)
    return out


def _directive_tokens(value: str) -> set[str]:
    return {t.strip().lower() for t in re.split(r"[,\s]+", value or "") if t.strip()}


def tdm_reservation_in_headers(headers) -> str | None:
    """Reservation reason from HTTP response headers, or None."""
    h = headers if isinstance(headers, httpx.Headers) else httpx.Headers(headers or {})
    v = h.get("tdm-reservation")
    if v is not None and v.strip() == "1":
        return "header tdm-reservation: 1"
    xr = h.get("x-robots-tag")
    if xr and (_directive_tokens(xr) & NOAI_TOKENS):
        return f"header x-robots-tag: {xr.strip()}"
    return None


def tdm_reservation_in_html(page: str) -> str | None:
    """Reservation reason from <meta> tags, or None."""
    if not page:
        return None
    for attrs in _meta_tags(page):
        name = (attrs.get("name") or attrs.get("property") or "").strip().lower()
        content = attrs.get("content", "")
        if name == "tdm-reservation" and content.strip() == "1":
            return "meta tdm-reservation: 1"
        if name == "robots" and (_directive_tokens(content) & NOAI_TOKENS):
            return f"meta robots: {content.strip()}"
    return None


# --- TDM reservation: /.well-known/tdmrep.json --------------------------------

def _load_tdmrep_cache() -> dict[str, dict]:
    global _tdmrep_cache
    if _tdmrep_cache is None:
        try:
            data = json.loads(TDMREP_CACHE_PATH.read_text(encoding="utf-8"))
            _tdmrep_cache = data if isinstance(data, dict) else {}
        except Exception:
            _tdmrep_cache = {}
    return _tdmrep_cache


def _save_tdmrep_cache() -> None:
    if _tdmrep_cache is None:
        return
    try:
        TDMREP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = TDMREP_CACHE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_tdmrep_cache, sort_keys=True), encoding="utf-8")
        os.replace(tmp, TDMREP_CACHE_PATH)
    except Exception as e:  # noqa: BLE001
        logger.debug("tdmrep cache not written: %r", e)


def tdmrep_rules(host: str, client: httpx.Client | None = None,
                 now: float | None = None) -> list[dict] | None:
    """Rules from https://<host>/.well-known/tdmrep.json, or None if the host
    publishes none. Cached per host for TDMREP_TTL_SECONDS (also the negative
    result) so a host is asked at most once a day."""
    cache = _load_tdmrep_cache()
    now = time.time() if now is None else now
    entry = cache.get(host)
    if entry and now - float(entry.get("checked_at", 0)) < TDMREP_TTL_SECONDS:
        return entry.get("rules")
    rules: list[dict] | None = None
    try:
        _throttle(host)
        getter = client.get if client is not None else httpx.get
        r = getter(f"https://{host}/.well-known/tdmrep.json", timeout=8,
                   follow_redirects=True, headers={"User-Agent": UA})
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                rules = [d for d in data if isinstance(d, dict)]
    except Exception as e:  # noqa: BLE001
        logger.debug("tdmrep.json lookup failed for %s: %r", host, e)
        rules = None
    cache[host] = {"checked_at": now, "rules": rules}
    _save_tdmrep_cache()
    return rules


def _location_matches(pattern: str, path: str) -> bool:
    pattern = (pattern or "").strip()
    if not pattern:
        return False
    if not pattern.startswith("/"):
        pattern = "/" + pattern
    if pattern in ("/", "/*"):
        return True
    if fnmatch.fnmatchcase(path, pattern):
        return True
    # A bare directory ("/news") covers everything beneath it.
    return "*" not in pattern and (path == pattern or path.startswith(pattern.rstrip("/") + "/"))


def tdm_reservation_in_tdmrep(url: str, rules: list[dict] | None) -> str | None:
    """Reservation reason from tdmrep.json rules for this URL, or None.
    The first rule whose `location` matches the path decides (publishers list
    the specific paths before the generic ones)."""
    if not rules:
        return None
    path = urlparse(url).path or "/"
    for rule in rules:
        if _location_matches(str(rule.get("location", "")), path):
            flag = str(rule.get("tdm-reservation", "")).strip().lower()
            if flag in ("1", "true"):
                return f"tdmrep.json location={rule.get('location')!r}"
            return None
    return None


# --- fetch --------------------------------------------------------------------

@dataclass
class FetchResult:
    """Outcome of one full-text fetch. `reason` explains an empty `text`:
    robots | tdm:<signal> | http <status> | too_short | error <type>."""
    text: str | None
    reason: str | None = None

    @property
    def tdm_reserved(self) -> bool:
        return bool(self.reason and self.reason.startswith("tdm:"))


def _looks_like_pdf(content_type: str, final_url: str, head: bytes) -> bool:
    ctype = (content_type or "").lower()
    if "application/pdf" in ctype or "application/x-pdf" in ctype:
        return True
    if head[:5] == b"%PDF-":
        return True
    return urlparse(final_url).path.lower().endswith(".pdf")


def pdf_text(data: bytes, max_pages: int = PDF_MAX_PAGES) -> str:
    """Text of a PDF (first `max_pages` pages), or "" when it cannot be read.

    Until 2026-09-18 every PDF went through trafilatura like HTML and came
    back "too_short": the dossier's primary-first pass found the BSI
    IT-Grundschutz block SYS.1.5 Virtualisierung four times and could read it
    zero times — the one regulatory baseline the question asked for, dropped
    because it is published as a PDF. Encrypted files with an empty user
    password are opened; anything else is skipped, never guessed."""
    try:
        from pypdf import PdfReader
    except ImportError:                                            # pragma: no cover
        logger.warning("pypdf is not installed — PDF full text skipped")
        return ""
    try:
        import io
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:                                      # noqa: BLE001
                return ""
        parts: list[str] = []
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            parts.append(page.extract_text() or "")
    except Exception as e:                                         # noqa: BLE001
        logger.debug("pdf extraction failed: %r", e)
        return ""
    text = "\n".join(parts)
    text = re.sub(r"(?<=\w)-\n(?=[a-zäöüß])", "", text)     # hy-\nphenation
    text = re.sub(r"[ \t\f\r]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_fulltext_result(url: str, client: httpx.Client | None = None,
                          open_licence: str | None = None) -> FetchResult:
    """Fetch + extract clean article text, with the reason when nothing is kept.

    `open_licence`: the caller has verified that THIS article carries an open
    licence (CC BY / CC0 / public domain — see pipeline/open_license.py). A
    licence is a permission; the TDM reservation from §44b Abs. 3 only bars the
    statutory exception, which a licensed use does not need. The host-level
    reservation is therefore not applied — robots.txt still is, because that is
    the site's access policy, not a copyright reservation (#97, 2026-09-09).

    Redirects are re-checked (fixed 2026-09-09): robots and the TDM signals were
    evaluated only against the REQUESTED url. A DOI link
    (`doi.org/10.1038/…` -> `nature.com/articles/…`) therefore slipped past
    nature.com's site-wide `tdmrep.json` and 12.000 characters were stored.
    """
    if not _robots_ok(url):
        logger.info("robots.txt disallows %s", url)
        return FetchResult(None, "robots")
    host = urlparse(url).netloc
    respect_tdm = TDM_RESPECT and not open_licence
    own = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=True,
                                    headers={"User-Agent": UA})
    try:
        if respect_tdm:
            why = tdm_reservation_in_tdmrep(url, tdmrep_rules(host, client))
            if why:
                logger.info("TDM reservation (%s) — full text not stored, feed teaser only: %s", why, url)
                return FetchResult(None, f"tdm:{why}")
        _throttle(host)
        r = client.get(url)
        if r.status_code != 200 or not r.text:
            return FetchResult(None, f"http {r.status_code}")
        final = str(r.url)
        if final != url:
            if not _robots_ok(final):
                logger.info("robots.txt disallows the redirect target %s (from %s)", final, url)
                return FetchResult(None, "robots")
            if respect_tdm:
                why = tdm_reservation_in_tdmrep(final, tdmrep_rules(urlparse(final).netloc, client))
                if why:
                    logger.info("TDM reservation (%s) on the redirect target %s (from %s)", why, final, url)
                    return FetchResult(None, f"tdm:{why}")
        is_pdf = _looks_like_pdf(r.headers.get("content-type", ""), final, r.content[:8])
        if respect_tdm:
            why = tdm_reservation_in_headers(r.headers) or (
                None if is_pdf else tdm_reservation_in_html(r.text))
            if why:
                logger.info("TDM reservation (%s) — full text not stored, feed teaser only: %s", why, url)
                return FetchResult(None, f"tdm:{why}")
        if open_licence:
            logger.info("open licence %s — host TDM reservation not applied: %s", open_licence, url)
        if is_pdf:
            text = pdf_text(r.content)
        else:
            text = trafilatura.extract(
                r.text, include_comments=False, include_tables=False,
                no_fallback=False, favor_precision=True)
        if not text or len(text) < MIN_TEXT_CHARS:
            return FetchResult(None, "too_short")
        return FetchResult(text[:MAX_TEXT_CHARS])
    except Exception as e:  # noqa: BLE001
        logger.debug("fetch failed %s: %r", url, e)
        return FetchResult(None, f"error {type(e).__name__}")
    finally:
        if own:
            client.close()


def fetch_fulltext(url: str, client: httpx.Client | None = None) -> str | None:
    """Fetch + extract clean article text, or None (robots/TDM/blocked/too short)."""
    return fetch_fulltext_result(url, client=client).text


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
    filled = reserved = 0
    reasons: Counter = Counter()
    items = [(r["id"] if isinstance(r, dict) else r[0], r["url"] if isinstance(r, dict) else r[1])
             for r in rows]
    # Parallel wie scripts/refetch_fulltext.py (2026-09-11, Option A: 480 statt
    # 165 Volltext-Quellen). Die Hoeflichkeit bleibt: fetch_fulltext_result
    # drosselt JE HOST auf eine Anfrage pro Sekunde (per-host lock in _throttle);
    # die Threads verteilen sich nur ueber verschiedene Hosts. Sequenziell
    # haetten ~1.400 Abrufe je Nacht den Cycle um eine Dreiviertelstunde
    # verlaengert.
    with httpx.Client(timeout=20, follow_redirects=True,
                      headers={"User-Agent": UA}) as client:
        def work(item):
            rid, url = item
            return rid, fetch_fulltext_result(url, client=client)
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            for rid, res in pool.map(work, items):
                if res.tdm_reserved:
                    reserved += 1
                    continue
                if res.text:
                    with get_connection() as conn:
                        conn.execute("UPDATE raw_entries SET raw_content = ? WHERE id = ?",
                                     (res.text, rid))
                    filled += 1
                elif res.reason:
                    # Den ganzen Grund behalten, nicht nur das erste Wort. Bis
                    # 2026-09-16 landete jedes "http 403", "http 429", "http 503"
                    # im selben Eimer "http" — und genau deshalb war zwei Wochen
                    # lang nicht sichtbar, dass wir kein Sperr-, sondern ein
                    # Abholproblem haben (24 von 25 schwachen Quellen antworten
                    # mit 200). Ohne den Code kann niemand eine Drosselung von
                    # einer Bot-Sperre unterscheiden.
                    reasons[res.reason.strip()] += 1
    logger.info("enriched %d/%d entries with full text (%d TDM-reserved, kept teaser only; "
                "misses: %s)", filled, len(rows), reserved,
                ", ".join(f"{k} {v}" for k, v in reasons.most_common(8)) or "none")
    return filled


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch full article text (#11)")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--url", help="fetch one URL and print the text (test)")
    args = ap.parse_args()
    if args.url:
        res = fetch_fulltext_result(args.url)
        print(f"--- {len(res.text) if res.text else 0} chars"
              f"{' — ' + res.reason if res.reason else ''} ---")
        print((res.text or "(nothing extracted)")[:2000])
        return 0
    fetch_batch(args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
