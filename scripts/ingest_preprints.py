#!/usr/bin/env python3
"""Ingest preprints as dated raw_entries — the earliest lead-time tier (issue #4).

Preprints precede journal publication by months and market moves by years;
together with grants (ingest_funding) and patents (ingest_patents) they feed
the research→patent→funding→product→market lead-time chain of the foresight
engine. All backends are free, keyless, official APIs.

Backends:
  arxiv     arXiv Atom API (export.arxiv.org/api/query) — curated
            category→vertical shards (like the CPC mapping in ingest_patents),
            title + abstract + date, paginated, date-filtered client-side.
  biorxiv   bioRxiv REST API (api.biorxiv.org/details/biorxiv/...) — biology
            preprints, server-side date interval, JSON, paginated by cursor.
  medrxiv   same API family, server 'medrxiv' — health/medical preprints.

Each record becomes a raw_entry (processed=0) under a per-source row
(source_type='api', vertical='CROSS'); the signal pipeline classifies the real
vertical/PESTEL/mega-trend. The excerpt is prefixed `[Preprint · <shard>]` so
the tier survives into the embedding (mirrors the funding-prefix pattern).

    python scripts/ingest_preprints.py --backend arxiv --since 2024-01-01 --dry-run
    python scripts/ingest_preprints.py --backend all --since 2024-01-01 --limit 5000
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_preprints")

UA = "CatandaryTrends/1.0 (mailto:trends@catandary.de)"
HEADERS = {"User-Agent": UA}

# Curated arXiv categories per foresight vertical — deliberately narrow (the
# arXiv firehose problem): frontier categories with product lead-time, not the
# whole of maths/physics.
ARXIV_SHARDS: dict[str, list[str]] = {
    "TECH": ["cs.AI", "cs.LG", "cs.RO", "cs.CV", "cs.CL", "quant-ph", "cs.AR", "cs.ET"],
    "HEALTH": ["q-bio.QM", "q-bio.GN", "q-bio.NC"],
    "ECO": ["physics.ao-ph", "cond-mat.mtrl-sci"],
    "BIZ": ["econ.GN", "q-fin.TR"],
}

ARXIV_API = "https://export.arxiv.org/api/query"
BIORXIV_API = "https://api.biorxiv.org/details/{server}/{since}/{until}/{cursor}"
ATOM = "{http://www.w3.org/2005/Atom}"


def _get(client: httpx.Client, url: str, *, params=None, tries: int = 6,
         timeout: int = 45) -> httpx.Response | None:
    """GET with exponential backoff on 429/5xx (pattern from ingest_funding)."""
    for i in range(tries):
        try:
            r = client.get(url, params=params, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — transient network
            logger.warning("request error (%s), retry %d/%d", e, i + 1, tries)
            time.sleep(2 ** i)
            continue
        if r.status_code == 200:
            return r
        if r.status_code in (429, 500, 502, 503, 504):
            logger.warning("HTTP %d, backoff retry %d/%d", r.status_code, i + 1, tries)
            time.sleep(2 ** i)
            continue
        logger.error("HTTP %d from %s", r.status_code, url)
        return None
    return None


def _safe_insert(source_id: int, url: str, title: str, excerpt: str,
                 pub: str | None, tries: int = 6) -> int | None:
    """insert_raw_entry with retry on SQLite write-lock contention (the signal
    pipeline may be writing the same DB). Duplicate URLs return None."""
    for i in range(tries):
        try:
            return db.insert_raw_entry(source_id, url, title, excerpt, pub)
        except Exception as e:  # noqa: BLE001
            if "locked" in str(e).lower() and i < tries - 1:
                time.sleep(0.5 * (i + 1))
                continue
            raise
    return None


def _excerpt(shard: str, abstract: str) -> str:
    return (f"[Preprint · {shard}] " + " ".join((abstract or "").split()))[:2000]


# ------------------------------------------------------------------------ arXiv

def ingest_arxiv(since: str, limit: int, dry_run: bool) -> dict:
    stats = {"seen": 0, "inserted": 0, "duplicates": 0, "skipped": 0, "old": 0}
    source_id = -1 if dry_run else db.upsert_source(
        "arXiv Preprints", ARXIV_API, "api", "CROSS")
    cats = [c for cs in ARXIV_SHARDS.values() for c in cs]
    per_shard = max(100, limit // max(1, len(cats)))
    page = 100  # arXiv recommends <=1000; 100 keeps memory + retries small
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        for cat in cats:
            got, start, stop = 0, 0, False
            while got < per_shard and stats["seen"] < limit and not stop:
                r = _get(client, ARXIV_API, params={
                    "search_query": f"cat:{cat}",
                    "sortBy": "submittedDate", "sortOrder": "descending",
                    "start": start, "max_results": page})
                if r is None:
                    break
                try:
                    root = ET.fromstring(r.text)
                except ET.ParseError as e:
                    logger.warning("[arxiv:%s] XML parse error: %s", cat, e)
                    break
                entries = root.findall(f"{ATOM}entry")
                if not entries:
                    break
                for e in entries:
                    pub = (e.findtext(f"{ATOM}published") or "")[:10]
                    if pub and pub < since:   # sorted desc → rest is older
                        stats["old"] += 1
                        stop = True
                        break
                    stats["seen"] += 1
                    got += 1
                    url = (e.findtext(f"{ATOM}id") or "").strip()
                    title = " ".join((e.findtext(f"{ATOM}title") or "").split())
                    abstract = e.findtext(f"{ATOM}summary") or ""
                    if not url or not title:
                        stats["skipped"] += 1
                        continue
                    if dry_run:
                        stats["inserted"] += 1
                        continue
                    eid = _safe_insert(source_id, url, title,
                                       _excerpt(f"arXiv:{cat}", abstract), pub or None)
                    stats["duplicates" if eid is None else "inserted"] += 1
                start += page
                time.sleep(3.1)  # arXiv ToU: no more than 1 request per 3 s
            logger.info("[arxiv:%s] seen=%d inserted=%d old=%d",
                        cat, stats["seen"], stats["inserted"], stats["old"])
    return stats


# ------------------------------------------------------------- bioRxiv/medRxiv

def _ingest_rxiv(server: str, since: str, limit: int, dry_run: bool) -> dict:
    stats = {"seen": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    source_id = -1 if dry_run else db.upsert_source(
        f"{server} Preprints", f"https://api.biorxiv.org/details/{server}",
        "api", "CROSS")
    until = date.today().isoformat()
    cursor = 0
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        while stats["seen"] < limit:
            url = BIORXIV_API.format(server=server, since=since, until=until,
                                     cursor=cursor)
            r = _get(client, url)
            if r is None:
                break
            try:
                data = r.json()
            except Exception:
                logger.warning("[%s] non-JSON response", server)
                break
            coll = data.get("collection") or []
            if not coll:
                break
            for p in coll:
                stats["seen"] += 1
                doi = (p.get("doi") or "").strip()
                title = " ".join((p.get("title") or "").split())
                if not doi or not title:
                    stats["skipped"] += 1
                    continue
                url_p = f"https://doi.org/{doi}"
                cat = (p.get("category") or "").strip() or server
                pub = (p.get("date") or "")[:10] or None
                if dry_run:
                    stats["inserted"] += 1
                    continue
                eid = _safe_insert(source_id, url_p, title,
                                   _excerpt(f"{server}:{cat}", p.get("abstract") or ""),
                                   pub)
                stats["duplicates" if eid is None else "inserted"] += 1
            # cursor pagination: the API serves 30 per page and reports the
            # interval total as a string in messages[0].total
            try:
                total = int((data.get("messages") or [{}])[0].get("total") or 0)
            except (TypeError, ValueError):
                total = 0
            cursor += len(coll)
            if not total or cursor >= total:
                break
            time.sleep(1.0)
    return stats


def ingest_biorxiv(since: str, limit: int, dry_run: bool) -> dict:
    return _ingest_rxiv("biorxiv", since, limit, dry_run)


def ingest_medrxiv(since: str, limit: int, dry_run: bool) -> dict:
    return _ingest_rxiv("medrxiv", since, limit, dry_run)


BACKENDS = {"arxiv": ingest_arxiv, "biorxiv": ingest_biorxiv, "medrxiv": ingest_medrxiv}


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest preprints as raw_entries")
    ap.add_argument("--backend", required=True, choices=["all", *BACKENDS.keys()])
    ap.add_argument("--since", default="2024-01-01", help="YYYY-MM-DD")
    ap.add_argument("--limit", type=int, default=8000, help="max records per backend")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    backends = list(BACKENDS) if args.backend == "all" else [args.backend]
    grand = {"seen": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    for b in backends:
        logger.info("=== backend=%s since=%s limit=%d dry=%s ===",
                    b, args.since, args.limit, args.dry_run)
        s = BACKENDS[b](args.since, args.limit, args.dry_run)
        for k in grand:
            grand[k] += s.get(k, 0)
        tag = "[dry] would insert" if args.dry_run else "inserted"
        print(f"{b:8s}: seen {s['seen']:6d} | {tag} {s['inserted']:6d} | "
              f"{s['duplicates']} dup | {s['skipped']} skip")
    print(f"{'TOTAL':8s}: seen {grand['seen']:6d} | inserted {grand['inserted']:6d} | "
          f"{grand['duplicates']} dup | {grand['skipped']} skip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
