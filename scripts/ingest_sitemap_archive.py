#!/usr/bin/env python3
"""Archiv einer erlaubten Quelle über ihre Sitemaps einlesen — der Rückweg in die Zeit vor dem Feed.

    .venv/bin/python scripts/ingest_sitemap_archive.py sciencealert.com --dry-run
    .venv/bin/python scripts/ingest_sitemap_archive.py sciencealert.com \\
        --source "ScienceAlert Health" --since 2014-01 --until 2020-01 --apply
    .venv/bin/python scripts/ingest_sitemap_archive.py --check-blocked

Warum es das gibt (Owner 2026-09-16): ein RSS-Feed zeigt die letzten zehn
Einträge. Alles davor sieht der Korpus nie — und genau dort liegt die Frühphase
eines Trends. Die frühe Meldung über künstliche Milch von 2014 stand in unserem
Bestand nur deshalb, weil eine andere Quelle sie zufällig mitgenommen hatte.
Eine Sitemap listet dagegen das ganze Archiv, und robots.txt nennt sie in aller
Regel selbst.

Was das Werkzeug NICHT tut:

* Es fasst nichts an, was robots.txt sperrt. Geprüft wird die Sitemap-URL, und
  jede Artikel-URL einzeln, mit demselben RFC-9309-Matcher wie der Fetcher.
  Die WordPress-Schnittstelle `/wp-json/` ist bei vielen Häusern gesperrt,
  während die Sitemap erlaubt ist — das ist der ganze Punkt.
* Es holt keine Volltexte. Es legt `raw_entries` an (URL, Titel, Datum); den
  Text holt später `article_fetcher`, der jeden Artikel erneut auf robots und
  TDM-Vorbehalt prüft. Ein Archivlauf umgeht also keine einzige Schranke.
* Es löscht nichts. Bestehende Einträge bleiben, doppelte URLs werden
  übersprungen (`insert_raw_entry` gibt None zurück).

Drossel: eine Anfrage pro Sekunde gegen denselben Host, wie im Fetcher.
"""
from __future__ import annotations

import argparse
import gzip
import logging
import os
import re
import sys
import time
import urllib.robotparser
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import db as db_mod
from pipeline.article_fetcher import UA, robots_allows
from pipeline.config import load_sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("sitemap_archive")

DELAY = float(os.getenv("SITEMAP_DELAY", "1.0"))
TIMEOUT = 25
MAX_SITEMAPS = int(os.getenv("SITEMAP_MAX", "2000"))
LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
LASTMOD = re.compile(r"<lastmod>\s*([0-9]{4}-[0-9]{2}(?:-[0-9]{2})?)", re.I)
URL_BLOCK = re.compile(r"<url>(.*?)</url>", re.I | re.S)


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=TIMEOUT, follow_redirects=True)


def robots_for(host: str, client: httpx.Client) -> urllib.robotparser.RobotFileParser | None:
    """Parsed robots.txt, or None when it cannot be read (then: treat as allowed,
    same rule as the fetcher)."""
    try:
        r = client.get(f"https://{host}/robots.txt")
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        return rp
    except Exception:
        return None


def sitemaps_from_robots(host: str, client: httpx.Client) -> list[str]:
    """The Sitemap: lines of robots.txt — an explicit invitation, and the only
    place a site names its archive without us guessing."""
    try:
        r = client.get(f"https://{host}/robots.txt")
        if r.status_code != 200:
            return []
        return [ln.split(":", 1)[1].strip() for ln in r.text.splitlines()
                if ln.lower().startswith("sitemap:")]
    except Exception:
        return []


def fetch_xml(url: str, client: httpx.Client) -> str:
    r = client.get(url)
    r.raise_for_status()
    body = r.content
    if url.endswith(".gz") or body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body.decode("utf-8", "replace")


def walk_sitemaps(roots: list[str], rp, ua_token: str, client: httpx.Client,
                  progress=None) -> tuple[list[tuple[str, str | None]], list[str]]:
    """(URLs with their lastmod, skipped sitemaps). Follows sitemap indexes."""
    seen: set[str] = set()
    queue = list(roots)
    urls: list[tuple[str, str | None]] = []
    skipped: list[str] = []
    while queue and len(seen) < MAX_SITEMAPS:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        if rp is not None and not robots_allows(rp, ua_token, sm):
            skipped.append(sm)
            continue
        try:
            xml = fetch_xml(sm, client)
        except Exception as exc:
            logger.warning("  %s: %s", sm, exc.__class__.__name__)
            skipped.append(sm)
            continue
        time.sleep(DELAY)
        if "<sitemapindex" in xml[:4000].lower():
            queue.extend(LOC.findall(xml))
        else:
            for block in URL_BLOCK.findall(xml):
                loc = LOC.search(block)
                if not loc:
                    continue
                lm = LASTMOD.search(block)
                urls.append((loc.group(1), lm.group(1) if lm else None))
        if progress:
            progress(len(seen), len(queue), len(urls))
    return urls, skipped


def in_window(lastmod: str | None, since: str | None, until: str | None) -> bool:
    """A URL without lastmod cannot be placed in time — it is kept, because
    dropping it would silently lose the oldest pages of many sitemaps."""
    if lastmod is None:
        return True
    m = lastmod[:7]
    if since and m < since:
        return False
    if until and m >= until:
        return False
    return True


def title_from_url(url: str) -> str:
    """Placeholder title from the slug. The real title arrives with the text —
    article_fetcher overwrites nothing, so it stays readable either way."""
    slug = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    slug = re.sub(r"\.(html?|php|aspx)$", "", slug)
    return re.sub(r"[-_]+", " ", slug).strip().capitalize() or url


def pick_source(name: str | None, host: str) -> tuple[int, str] | None:
    """The source row an archive run writes into. Never creates one: an archive
    belongs to a source the owner has already vetted."""
    cfg = load_sources()
    cands = []
    for vert, block in (cfg.get("verticals") or {}).items():
        for s in (block.get("sources") or []):
            if s.get("active") is False:
                continue
            if name and s.get("name") == name:
                cands = [(s, vert)]
                break
            if not name and host in (s.get("feed_url") or ""):
                cands.append((s, vert))
    if not cands:
        return None
    s, vert = cands[0]
    sid = db_mod.upsert_source(s["name"], s["feed_url"], s.get("type", "trade_media"), vert)
    return sid, s["name"]


def check_blocked() -> int:
    """Which sources that we cannot poll would be reachable through sitemaps?

    A robots rule often hits only the feed path while the sitemap and the
    articles are allowed — for those, the archive route is not a workaround but
    the site's own front door. Prints candidates, changes nothing."""
    cfg = load_sources()
    rows = []
    for vert, block in (cfg.get("verticals") or {}).items():
        for s in (block.get("sources") or []):
            if s.get("tdm_status") in ("blocked", "feed_error") and s.get("active") is not False:
                rows.append((vert, s))
    if not rows:
        print("keine gesperrten Quellen in sources.yaml")
        return 0
    print(f"{len(rows)} Quellen mit tdm_status blocked/feed_error — pruefe den Sitemap-Weg\n")
    ok = 0
    with _client() as client:
        for vert, s in rows:
            host = urlsplit(s["feed_url"]).netloc
            rp = robots_for(host, client)
            sms = sitemaps_from_robots(host, client)
            feed_ok = rp is None or robots_allows(rp, "CatandaryTrendsBot", s["feed_url"])
            sm_ok = bool(sms) and (rp is None or robots_allows(rp, "CatandaryTrendsBot", sms[0]))
            verdict = "SITEMAP MOEGLICH" if (sm_ok and not feed_ok) else (
                "sitemap erlaubt" if sm_ok else "keine/gesperrte sitemap")
            if sm_ok and not feed_ok:
                ok += 1
            print(f"  {verdict:<18} {s['name'][:34]:<34} {host}")
            if sms:
                print(f"                     {sms[0][:78]}")
            time.sleep(DELAY)
    print(f"\n{ok} Quellen, bei denen robots den Feed sperrt, die Sitemap aber erlaubt.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Archiv einer Quelle ueber ihre Sitemaps einlesen")
    ap.add_argument("host", nargs="?", help="Host oder Sitemap-URL")
    ap.add_argument("--source", default=None, help="Name der Quelle in sources.yaml")
    ap.add_argument("--since", default=None, help="fruehester Monat YYYY-MM")
    ap.add_argument("--until", default=None, help="exklusiver Endmonat YYYY-MM")
    ap.add_argument("--limit", type=int, default=0, help="hoechstens so viele Eintraege schreiben")
    ap.add_argument("--apply", action="store_true", help="schreiben (sonst Dry-Run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="ausdruecklich nur rechnen — Vorgabe, nur zur Deutlichkeit "
                         "(wie purge_raw_content, resolve_open_licence, publish_static_site)")
    ap.add_argument("--check-blocked", action="store_true",
                    help="nur pruefen, welche gesperrten Quellen ueber Sitemaps erreichbar waeren")
    args = ap.parse_args()

    if args.check_blocked:
        return check_blocked()
    if not args.host:
        ap.error("host fehlt (oder --check-blocked)")

    host = urlsplit(args.host).netloc or args.host
    roots = [args.host] if args.host.startswith("http") else []
    t0 = time.time()
    with _client() as client:
        rp = robots_for(host, client)
        if not roots:
            roots = sitemaps_from_robots(host, client)
            if not roots:
                roots = [f"https://{host}/sitemap_index.xml", f"https://{host}/sitemap.xml"]
                logger.info("robots.txt nennt keine Sitemap — versuche die ueblichen Pfade")
        logger.info("Wurzel-Sitemaps: %s", ", ".join(roots))
        urls, skipped = walk_sitemaps(
            roots, rp, "CatandaryTrendsBot", client,
            progress=lambda done, left, n: logger.info("  %d Sitemaps gelesen, %d offen, %d URLs",
                                                       done, left, n) if done % 25 == 0 else None)
    logger.info("%d URLs eingesammelt, %d Sitemaps uebersprungen, %.0fs",
                len(urls), len(skipped), time.time() - t0)

    in_win = [(u, lm) for u, lm in urls if in_window(lm, args.since, args.until)]
    with _client() as client:
        rp = robots_for(host, client)
        allowed = [(u, lm) for u, lm in in_win
                   if rp is None or robots_allows(rp, "CatandaryTrendsBot", u)]
    blocked_n = len(in_win) - len(allowed)
    known = db_mod.known_entry_urls([u for u, _ in allowed])
    fresh = [(u, lm) for u, lm in allowed if u not in known]

    dated = [(u, lm) for u, lm in in_win if lm]
    undated = len(in_win) - len(dated)
    print(f"\n  URLs in den Sitemaps      {len(urls):>7}")
    print(f"  davon im Zeitfenster      {len(in_win):>7}"
          + (f"   ({args.since or 'Anfang'} .. {args.until or 'heute'})" if args.since or args.until else ""))
    # Getrennt ausweisen: undatierte URLs bleiben absichtlich drin (die aeltesten
    # Seiten tragen oft kein lastmod), aber sie sind KEIN Beleg fuer das Fenster.
    print(f"     davon mit Datum        {len(dated):>7}")
    print(f"     ohne lastmod           {undated:>7}   (bleiben drin, Datum unbekannt)")
    print(f"  davon robots-erlaubt      {len(allowed):>7}" + (f"   ({blocked_n} gesperrt)" if blocked_n else ""))
    print(f"  davon schon im Bestand    {len(allowed) - len(fresh):>7}")
    print(f"  NEU                       {len(fresh):>7}")
    if args.limit:
        fresh = fresh[:args.limit]
        print(f"  auf --limit gekuerzt      {len(fresh):>7}")

    if not args.apply:
        print("\n  Dry-Run — nichts geschrieben. Mit --apply ausfuehren.")
        # Stichprobe aus den DATIERTEN, sonst zeigt sie die undatierten zuerst
        # und damit heutige Artikel statt der Jahrgaenge, die man sehen wollte.
        sample = [x for x in fresh if x[1]][:5] or fresh[:5]
        for u, lm in sample:
            print(f"    {lm or 'ohne Datum':<12} {u}")
        return 0

    picked = pick_source(args.source, host)
    if not picked:
        print(f"\n  Keine passende Quelle in sources.yaml fuer {host}"
              f"{' / ' + args.source if args.source else ''}. "
              f"Ein Archiv gehoert zu einer geprueften Quelle — erst eintragen.", file=sys.stderr)
        return 2
    sid, sname = picked
    written = 0
    for u, lm in fresh:
        pub = f"{lm}-01" if lm and len(lm) == 7 else lm
        if db_mod.insert_raw_entry(sid, u, title_from_url(u), "", pub):
            written += 1
    print(f"\n  {written} Eintraege unter '{sname}' angelegt (id {sid}). "
          f"Den Text holt der Fetcher, der jeden Artikel erneut prueft.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
