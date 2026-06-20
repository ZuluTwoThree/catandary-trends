#!/usr/bin/env python3
"""Ingest historical works from a journal via the free OpenAlex API.

For the academic/journal sources, OpenAlex gives complete dated histories with
abstracts — no scraping, no key, no Firecrawl. The journal is resolved to an
OpenAlex source id by name; works in the date range are pulled (cursor-paginated)
and inserted as raw_entries with the publication date and reconstructed abstract.

Usage:
    python scripts/ingest_openalex.py --source-name "Food Policy" \
        --after 2015-01-01 --before 2023-01-01 --dry-run
    python scripts/ingest_openalex.py --source-name "Nature Food" --after 2021-01-01
"""
from __future__ import annotations
import argparse
import logging
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline import db
from pipeline.config import load_sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OPENALEX = "https://api.openalex.org"
HEADERS = {"User-Agent": "CatandaryTrends/1.0 (mailto:trends@catandary.de)"}


def find_source_entry(name: str) -> dict | None:
    cfg = load_sources()
    for vert, groups in cfg.get("verticals", {}).items():
        for key in ("sources", "science"):
            for s in groups.get(key, []) or []:
                if isinstance(s, dict) and s.get("name") == name:
                    return {**s, "vertical": vert}
    for grp in cfg.get("cross_industry", {}).values():
        if isinstance(grp, list):
            for s in grp:
                if isinstance(s, dict) and s.get("name") == name:
                    return {**s, "vertical": "CROSS"}
    return None


def resolve_source_id(client: httpx.Client, name: str) -> tuple[str, str] | None:
    """Return (openalex_source_id, display_name) for the best name match."""
    r = client.get(f"{OPENALEX}/sources", params={"search": name, "per_page": 5}, timeout=30)
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    return (results[0]["id"], results[0]["display_name"]) if results else None


def reconstruct_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))[:2000]


def iter_works(client: httpx.Client, source_id: str, after: str, before: str):
    sid = source_id.rsplit("/", 1)[-1]  # S12345
    filt = (f"primary_location.source.id:{sid},"
            f"from_publication_date:{after},to_publication_date:{before}")
    cursor = "*"
    while cursor:
        r = client.get(f"{OPENALEX}/works", params={
            "filter": filt, "per_page": 200, "cursor": cursor,
            "select": "id,title,publication_date,abstract_inverted_index,doi,primary_location",
        }, timeout=40)
        if r.status_code != 200:
            logger.error("OpenAlex works %s: %s", r.status_code, r.text[:160])
            return
        data = r.json()
        for w in data.get("results", []):
            yield w
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.2)


def landing_url(work: dict) -> str:
    loc = work.get("primary_location") or {}
    return loc.get("landing_page_url") or work.get("doi") or work.get("id") or ""


def ingest(name: str, after: str, before: str, dry_run: bool) -> dict:
    src = find_source_entry(name)
    vertical = src["vertical"] if src else "CROSS"
    stats = {"works": 0, "inserted": 0, "duplicates": 0, "skipped": 0}

    with httpx.Client(headers=HEADERS) as client:
        resolved = resolve_source_id(client, name)
        if not resolved:
            logger.error("OpenAlex: could not resolve source '%s'", name)
            return stats
        sid, disp = resolved
        logger.info("[openalex] %s -> %s (%s) | %s..%s", name, sid, disp, after, before)

        source_id = -1 if dry_run else db.upsert_source(
            name=name, feed_url=(src or {}).get("feed_url", sid),
            source_type="trade_media", vertical=vertical)  # CHECK-safe source_type

        for w in iter_works(client, sid, after, before):
            stats["works"] += 1
            url = landing_url(w)
            title = (w.get("title") or "").strip()
            excerpt = reconstruct_abstract(w.get("abstract_inverted_index"))
            pub = w.get("publication_date")
            if not url or not title:
                stats["skipped"] += 1
                continue
            if dry_run:
                stats["inserted"] += 1
                continue
            eid = db.insert_raw_entry(source_id, url, title, excerpt[:2000], pub)
            stats["duplicates" if eid is None else "inserted"] += 1

    tag = "[dry] würde einfügen" if dry_run else "eingefügt"
    print(f"{name}: {stats['works']} works | {tag} {stats['inserted']} | "
          f"{stats['duplicates']} dup | {stats['skipped']} skip")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-name", required=True)
    ap.add_argument("--after", required=True, help="YYYY-MM-DD")
    ap.add_argument("--before", required=True, help="YYYY-MM-DD")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    s = ingest(args.source_name, args.after, args.before, args.dry_run)
    if not args.dry_run and s["inserted"]:
        print(f"  -> {s['inserted']} neue datierte raw_entries (processed=0)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
