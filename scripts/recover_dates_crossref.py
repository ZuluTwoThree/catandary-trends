#!/usr/bin/env python3
"""Recover publication dates for DOI-bearing undated raw_entries via Crossref.

Bot-blocked publisher pages (e.g. Wiley onlinelibrary: EFSA Journal,
Comprehensive Reviews) can't be scraped for their date, but their URL carries
a DOI. Crossref's free API resolves the DOI to a publication date.

Usage:
    python scripts/recover_dates_crossref.py --sample 20   # test, no writes
    python scripts/recover_dates_crossref.py --apply
"""
from __future__ import annotations
import argparse, re, sys, time
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline.db import get_connection

# DOI embedded in a /doi/[pdf|full|abs|epdf]/10.xxxx/... path.
_DOI_RE = re.compile(r'/doi/(?:pdf/|full/|abs/|epdf/|e?pdfdirect/)?(10\.\d{4,}/[^/?#]+)', re.I)
CROSSREF = "https://api.crossref.org/works/"
HEADERS = {"User-Agent": "CatandaryTrends/1.0 (mailto:trends@catandary.de)"}
DELAY = 0.25  # polite spacing for Crossref


def doi_of(url: str) -> str | None:
    m = _DOI_RE.search(url)
    return m.group(1) if m else None


def _date_from_parts(parts: list) -> str | None:
    if not parts:
        return None
    p = parts[0]
    y = p[0]
    mo = p[1] if len(p) > 1 else 1
    d = p[2] if len(p) > 2 else 1
    try:
        dt = date(int(y), int(mo), int(d))
    except (ValueError, TypeError):
        return None
    if date(1990, 1, 1) <= dt <= date.today():
        return dt.isoformat()
    return None


def crossref_date(client: httpx.Client, doi: str) -> str | None:
    try:
        r = client.get(CROSSREF + doi, timeout=20, follow_redirects=True)
        if r.status_code != 200:
            return None
        msg = r.json().get("message", {})
    except Exception:
        return None
    # Prefer the earliest real publication date.
    cands = []
    for key in ("published-print", "published-online", "published", "issued", "created"):
        node = msg.get(key)
        if isinstance(node, dict):
            d = _date_from_parts(node.get("date-parts"))
            if d:
                cands.append(d)
    return min(cands) if cands else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with get_connection() as c:
        q = ("SELECT id,url FROM raw_entries WHERE processed=0 AND published_date IS NULL "
             "AND length(trim(coalesce(excerpt,'')))>0 AND url LIKE '%/doi/%' ORDER BY id")
        rows = c.execute(q + (f" LIMIT {args.sample}" if args.sample else "")).fetchall()

    items = [(r["id"], r["url"], doi_of(r["url"])) for r in rows]
    with_doi = [(i, u, d) for i, u, d in items if d]
    print(f"{len(rows)} DOI-Kandidaten, {len(with_doi)} mit extrahierbarer DOI")

    results: dict[int, str] = {}
    ok = nodate = 0
    with httpx.Client(headers=HEADERS) as client:
        for n, (eid, url, doi) in enumerate(with_doi, 1):
            d = crossref_date(client, doi)
            if d:
                ok += 1; results[eid] = d
            else:
                nodate += 1
            if n % 50 == 0:
                print(f"  {n}/{len(with_doi)} ...", flush=True)
            time.sleep(DELAY)

    tot = len(with_doi) or 1
    print(f"\nDatum via Crossref: {ok} ({100*ok//tot}%) | kein Treffer: {nodate}")
    if results:
        span = (min(results.values()), max(results.values()))
        print(f"Datumsspanne: {span[0]} .. {span[1]}")
    if args.apply and results:
        with get_connection() as c:
            c.executemany("UPDATE raw_entries SET published_date=? WHERE id=?",
                          [(d, eid) for eid, d in results.items()])
        print(f"\n{len(results)} Einträge via Crossref datiert.")
    elif not args.apply:
        print("\n(Sample-Modus, keine Writes. Mit --apply anwenden.)")


if __name__ == "__main__":
    main()
