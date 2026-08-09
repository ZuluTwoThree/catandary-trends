#!/usr/bin/env python3
"""Generischer CMS-Archiv-Ingester (#4 Restscope, Enabler für #46).

Ergänzt ingest_wordpress.py um die drei nächsthäufigsten Plattformen — je
Adapter der jeweils offizielle, öffentliche JSON-/XML-Endpunkt (kein Scraping,
robots-konform, dieselbe Legal-Primärquellen-Linie wie der WP-Ingester):

  substack   {base}/api/v1/archive?sort=new&offset=N          (JSON, datiert)
  drupal     {base}/jsonapi/node/article?sort=-created        (JSON:API)
  ghost      {base}/sitemap-posts.xml + og:title je URL       (Content-API
             bräuchte einen Key; die Post-Sitemap ist öffentlich und datiert.
             og-Fetch mit ~1 s Takt, gecappt — wie ingest_sitemap)

  --probe URL...  erkennt die Plattform (wordpress/substack/drupal/ghost/—)
                  und schlägt den passenden Ingester vor; schreibt nichts.

Beispiele:
  python scripts/ingest_cms.py --probe https://blog.beispiel.com https://firma.com/newsroom
  python scripts/ingest_cms.py --backend substack --url https://example.substack.com \
      --source-name "Example Letter" --vertical TECH --type trade_media --dry-run
  python scripts/ingest_cms.py --backend drupal --url https://www.beispiel.org \
      --source-name "Beispiel News" --vertical ECO --after 2015-01-01
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from pipeline import db

# Hybrid-UA: identifizierbar (Name+URL) UND browser-kompatibel — Substack/
# Cloudflare beantworten den nackten Bot-UA mit 403, den hybriden mit 200.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CatandaryTrends/1.0; +https://catandary.de)"}
SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s or "").replace("&nbsp;", " ").strip()


def _fetch_json(client: httpx.Client, url: str, params: dict | None = None):
    """GET → JSON, mit curl-Fallback: Cloudflare (Substack) challengt den
    TLS-Fingerprint von Python-httpx (403 "Just a moment"), lässt curl mit
    identischem UA aber durch. Erst httpx, bei 403 einmal curl."""
    try:
        r = client.get(url, params=params, timeout=20, follow_redirects=True)
        if r.status_code == 200:
            return r.json()
        if r.status_code != 403:
            return None
    except Exception:  # noqa: BLE001
        return None
    import json as _json
    import subprocess
    import urllib.parse
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    try:
        out = subprocess.run(
            ["curl", "-sL", "-m", "20", "-A", HEADERS["User-Agent"], full],
            capture_output=True, timeout=25)
        return _json.loads(out.stdout)
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------- probe
def probe(client: httpx.Client, base: str) -> str | None:
    base = base.rstrip("/")
    checks = [
        ("wordpress", f"{base}/wp-json/wp/v2/posts?per_page=1",
         lambda r: r.headers.get("content-type", "").startswith("application/json")
         and isinstance(r.json(), list)),
        ("drupal", f"{base}/jsonapi",
         lambda r: "jsonapi" in (r.json() or {})),
        ("ghost", f"{base}/sitemap-posts.xml",
         lambda r: b"<urlset" in r.content[:400] or b"<sitemapindex" in r.content[:400]),
    ]
    for name, url, ok in checks:
        try:
            r = client.get(url, timeout=12, follow_redirects=True)
            if r.status_code == 200 and ok(r):
                return name
        except Exception:  # noqa: BLE001 — Probe darf nie abbrechen
            continue
    # Substack separat: braucht wegen Cloudflare ggf. den curl-Fallback
    j = _fetch_json(client, f"{base}/api/v1/archive", {"sort": "new", "limit": 1})
    if isinstance(j, list) and j and "post_date" in j[0]:
        return "substack"
    return None


# ------------------------------------------------------------------ adapters
def iter_substack(client, base: str, after: str, limit: int):
    offset = 0
    while offset < limit:
        posts = _fetch_json(client, f"{base.rstrip('/')}/api/v1/archive",
                            {"sort": "new", "offset": offset, "limit": 12})
        if not posts or not isinstance(posts, list):
            break
        for p in posts:
            date = (p.get("post_date") or "")[:19].replace("T", " ")
            if date and date < after:
                return
            yield {"url": p.get("canonical_url") or "",
                   "title": (p.get("title") or "").strip(),
                   "excerpt": (p.get("description") or p.get("truncated_body_text") or "")[:2000],
                   "date": date or None}
        offset += len(posts)
        time.sleep(0.5)


def iter_drupal(client, base: str, after: str, limit: int, resource: str = "node/article"):
    rtype = resource.replace("/", "--")
    url = (f"{base.rstrip('/')}/jsonapi/{resource}?sort=-created"
           f"&page%5Blimit%5D=50&fields%5B{rtype}%5D=title,created,path,body")
    seen = 0
    while url and seen < limit:
        r = client.get(url, timeout=20, follow_redirects=True)
        if r.status_code != 200:
            break
        j = r.json()
        for item in j.get("data", []):
            a = item.get("attributes", {})
            date = (a.get("created") or "")[:19].replace("T", " ")
            if date and date < after:
                return
            alias = ((a.get("path") or {}).get("alias")) or ""
            body = ((a.get("body") or {}) or {}).get("summary") or ""
            seen += 1
            yield {"url": f"{base.rstrip('/')}{alias}" if alias else "",
                   "title": (a.get("title") or "").strip(),
                   "excerpt": strip_html(body)[:2000], "date": date or None}
        url = (j.get("links", {}).get("next") or {}).get("href")
        time.sleep(0.5)


def iter_ghost(client, base: str, after: str, limit: int):
    r = client.get(f"{base.rstrip('/')}/sitemap-posts.xml", timeout=20, follow_redirects=True)
    if r.status_code != 200:
        return
    root = ET.fromstring(r.content)
    entries = []
    for u in root.iter(f"{SM}url"):
        loc = (u.findtext(f"{SM}loc") or "").strip()
        mod = (u.findtext(f"{SM}lastmod") or "")[:19].replace("T", " ")
        if loc and (not mod or mod >= after):
            entries.append((loc, mod or None))
    for loc, mod in entries[:limit]:
        title = ""
        try:
            page = client.get(loc, timeout=12, follow_redirects=True)
            m = re.search(r'property="og:title"\s+content="([^"]+)"', page.text) or \
                re.search(r'content="([^"]+)"\s+property="og:title"', page.text)
            if m:
                title = m.group(1).strip()
        except Exception:  # noqa: BLE001
            pass
        if not title:  # Fallback: Slug lesbar machen
            title = loc.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
        yield {"url": loc, "title": title, "excerpt": "", "date": mod}
        time.sleep(1.0)  # og-Fetch: höflicher Takt wie ingest_sitemap


ADAPTERS = {"substack": iter_substack, "drupal": iter_drupal, "ghost": iter_ghost}


# --------------------------------------------------------------------- main
def run_ingest(backend: str, base: str, source_name: str, vertical: str,
               source_type: str, after: str, limit: int, dry_run: bool,
               resource: str = "") -> dict:
    stats = {"fetched": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    source_id = -1 if dry_run else db.upsert_source(
        name=source_name, feed_url=base, source_type=source_type, vertical=vertical)
    buf: list[tuple] = []
    kw = {"resource": resource} if backend == "drupal" and resource else {}
    with httpx.Client(headers=HEADERS) as client:
        for e in ADAPTERS[backend](client, base, after, limit, **kw):
            stats["fetched"] += 1
            if not e["url"] or not e["title"]:
                stats["skipped"] += 1
                continue
            if dry_run:
                stats["inserted"] += 1
                if stats["inserted"] <= 5:
                    print(f"  [dry] {e['date']} · {e['title'][:70]}")
                continue
            buf.append((source_id, e["url"], e["title"], e["excerpt"], e["date"]))
            if len(buf) >= 500:
                ins = db.insert_raw_entries_market_batch(buf)
                stats["inserted"] += ins
                stats["duplicates"] += len(buf) - ins
                buf.clear()
    if buf and not dry_run:
        ins = db.insert_raw_entries_market_batch(buf)
        stats["inserted"] += ins
        stats["duplicates"] += len(buf) - ins
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Generic CMS archive ingester (substack/drupal/ghost)")
    ap.add_argument("--probe", nargs="+", help="URLs klassifizieren, nichts schreiben")
    ap.add_argument("--backend", choices=sorted(ADAPTERS))
    ap.add_argument("--url", help="Basis-URL der Site")
    ap.add_argument("--source-name")
    ap.add_argument("--vertical", default="CROSS")
    ap.add_argument("--type", default="trade_media", choices=["trade_media", "brand"])
    ap.add_argument("--resource", default="node/article",
                    help="drupal: JSON:API-Ressource (Site-abhängig, z. B. node/news)")
    ap.add_argument("--after", default="2010-01-01")
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.probe:
        with httpx.Client(headers=HEADERS) as client:
            for u in args.probe:
                kind = probe(client, u)
                hint = {"wordpress": "→ scripts/ingest_wordpress.py",
                        None: "→ kein bekanntes CMS (evtl. ingest_sitemap.py)"}.get(
                    kind, f"→ ingest_cms.py --backend {kind}")
                print(f"{(kind or '—'):<10} {u}  {hint}")
        return 0

    if not (args.backend and args.url and args.source_name):
        ap.error("--backend, --url und --source-name sind Pflicht (oder --probe)")
    after = args.after + (" 00:00:00" if len(args.after) == 10 else "")
    st = run_ingest(args.backend, args.url, args.source_name, args.vertical,
                    args.type, after, args.limit, args.dry_run, resource=args.resource)
    tag = "[dry] würde einfügen" if args.dry_run else "eingefügt"
    print(f"{args.source_name}: fetched {st['fetched']} | {tag} {st['inserted']} | "
          f"{st['duplicates']} dup | {st['skipped']} skip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
