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
import os
import re
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
# OpenAlex is now a freemium credit service: $0.10/day with no key, $1/day with a
# free key. A persistent 429 = the daily budget is exhausted (resets midnight UTC),
# NOT a reputation throttle — backoff alone won't recover it, the api_key will.
# Get a free key at openalex.org/settings/api and set OPENALEX_API_KEY.
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "")
MAILTO = "trends@catandary.de"  # legacy polite-pool hint; harmless under the new model
HEADERS = {"User-Agent": f"CatandaryTrends/1.0 (mailto:{MAILTO})"}


def _get(client: httpx.Client, url: str, params: dict, timeout: int = 40,
         tries: int = 6) -> dict | None:
    """GET with the polite-pool `mailto` param and exponential backoff on 429.

    The first ingest hit the common-pool rate limit (mailto only in the UA, not
    as a query param) → resolve calls returned 429 → sources were silently
    skipped. Sending `mailto` puts us in the polite pool; on 429/5xx we back off
    and retry instead of treating it as 'no results'."""
    params = {**params, "mailto": MAILTO}
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY
    for i in range(tries):
        try:
            r = client.get(url, params=params, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — transient network
            logger.warning("OpenAlex request error (%s), retry %d/%d", e, i + 1, tries)
            time.sleep(2 ** i)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            # Daily budget exhausted (resets midnight UTC) OR >100 req/s burst. A
            # short burst clears with backoff; an exhausted budget will not — bail
            # after the retries rather than block forever (caller skips the source).
            remaining = r.headers.get("X-RateLimit-Remaining")
            wait = min(30, 2 ** i + 1)
            logger.warning("OpenAlex 429 (remaining=%s%s) — backoff %ds (try %d/%d)",
                           remaining, "" if OPENALEX_API_KEY else ", NO api_key set",
                           wait, i + 1, tries)
            time.sleep(wait)
            continue
        if r.status_code in (500, 502, 503):
            time.sleep(min(30, 2 ** i + 1))
            continue
        logger.error("OpenAlex %s: %s", r.status_code, r.text[:160])
        return None
    logger.error("OpenAlex: exhausted retries for %s (daily budget? set OPENALEX_API_KEY)", url)
    return None


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
    """Return (openalex_source_id, display_name) for the best name match.

    Picks the candidate with the most works (the real top journal dwarfs tiny
    same-named sources — fixes Nature/Science/PNAS resolving to an empty/wrong
    source), preferring journal-type sources. Tries the name with sources.yaml
    annotations like '(main)' stripped, then the raw name."""
    cleaned = re.sub(r"\s*\([^)]*\)", "", name).strip()
    for q in dict.fromkeys([cleaned, name]):  # de-dup, keep order
        data = _get(client, f"{OPENALEX}/sources",
                    {"search": q, "per_page": 10,
                     "select": "id,display_name,works_count,type"})
        results = (data or {}).get("results", [])
        if not results:
            continue
        best = max(results, key=lambda r: ((r.get("type") == "journal"),
                                           r.get("works_count") or 0))
        return best["id"], best["display_name"]
    return None


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
        data = _get(client, f"{OPENALEX}/works", {
            "filter": filt, "per_page": 100, "cursor": cursor,  # 100 = API max
            "select": "id,title,publication_date,abstract_inverted_index,doi,primary_location",
        })
        if data is None:
            return
        for w in data.get("results", []):
            yield w
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.2)


def landing_url(work: dict) -> str:
    loc = work.get("primary_location") or {}
    return loc.get("landing_page_url") or work.get("doi") or work.get("id") or ""


# --- Concept-expansion mode (issue #4): pull the SCIENCE tier by topic across ALL
# journals, not journal-by-journal. Targets the pre-2020 research history the
# lead-time validation found missing (science->market lead reads ~0 because the
# research tier only reaches ~2020). Curated concepts per vertical keep it out of
# the OpenAlex firehose; a citations gate removes predatory/irrelevant noise
# (works pre-2020 have accumulated citations, so the gate is meaningful there).
CONCEPT_SHARDS: dict[str, list[str]] = {
    "TECH": ["artificial intelligence", "machine learning", "robotics",
             "quantum computing", "semiconductor", "computer vision"],
    "HEALTH": ["immunotherapy", "gene therapy", "obesity", "neurodegeneration",
               "precision medicine", "microbiome"],
    "FOOD": ["food science", "alternative protein", "fermentation",
             "sustainable agriculture", "food security"],
    "ECO": ["renewable energy", "carbon capture", "battery", "photovoltaics",
            "climate change mitigation"],
    "BIZ": ["financial technology", "supply chain management", "electronic commerce"],
    "FASHION": ["textile", "biomaterials", "cosmetics"],
    "DESIGN": ["sustainable architecture", "urban design"],
    "LIFESTYLE": ["social media", "video games", "creator economy"],
}


def resolve_concept_id(client: httpx.Client, name: str) -> tuple[str, str] | None:
    """Return (concept_id, display_name) for the best-matching OpenAlex concept.
    Picks the highest works_count match (the canonical broad concept, not a niche
    same-named one)."""
    data = _get(client, f"{OPENALEX}/concepts",
                {"search": name, "per_page": 10,
                 "select": "id,display_name,works_count,level"})
    results = (data or {}).get("results", [])
    if not results:
        return None
    best = max(results, key=lambda r: r.get("works_count") or 0)
    return best["id"], best["display_name"]


def iter_works_by_concept(client: httpx.Client, cid: str, after: str, before: str,
                          min_citations: int):
    """Cursor-paginate works for a concept in the date range, gated on citations.
    Sorted by cited_by_count desc so the most-established works come first (and a
    per-shard cap can stop early on the long low-citation tail)."""
    c = cid.rsplit("/", 1)[-1]  # C12345
    filt = (f"concepts.id:{c},from_publication_date:{after},"
            f"to_publication_date:{before},cited_by_count:>{min_citations}")
    cursor = "*"
    while cursor:
        data = _get(client, f"{OPENALEX}/works", {
            "filter": filt, "per_page": 100, "cursor": cursor,
            "sort": "cited_by_count:desc",
            "select": "id,title,publication_date,abstract_inverted_index,doi,"
                      "primary_location,cited_by_count",
        })
        if data is None:
            return
        for w in data.get("results", []):
            yield w
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.2)


def ingest_concept(concept: str, vertical: str, after: str, before: str,
                   min_citations: int, cap: int, dry_run: bool) -> dict:
    """Ingest a concept's works as SCIENCE-tier raw_entries (source_type=research
    so the lead-time tier map treats them as science). Excerpt prefixed
    `[Science · <concept>]` to carry the tier into the embedding."""
    stats = {"works": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    with httpx.Client(headers=HEADERS) as client:
        resolved = resolve_concept_id(client, concept)
        if not resolved:
            logger.error("OpenAlex: could not resolve concept '%s'", concept)
            return stats
        cid, disp = resolved
        logger.info("[openalex-concept] %s -> %s (%s) | %s..%s | cited>%d cap=%d",
                    concept, cid, disp, after, before, min_citations, cap)
        source_id = -1 if dry_run else db.upsert_source(
            name=f"OpenAlex: {disp}", feed_url=f"{OPENALEX}/works?concept={cid.rsplit('/',1)[-1]}",
            source_type="research", vertical=vertical)
        for w in iter_works_by_concept(client, cid, after, before, min_citations):
            stats["works"] += 1
            url = landing_url(w)
            title = (w.get("title") or "").strip()
            if not url or not title:
                stats["skipped"] += 1
                continue
            excerpt = f"[Science · {disp}] " + reconstruct_abstract(
                w.get("abstract_inverted_index"))
            pub = w.get("publication_date")
            if dry_run:
                stats["inserted"] += 1
            else:
                eid = db.insert_raw_entry(source_id, url, title, excerpt[:2000], pub)
                stats["duplicates" if eid is None else "inserted"] += 1
            if stats["inserted"] >= cap:
                break
    tag = "[dry] würde einfügen" if dry_run else "eingefügt"
    print(f"{concept:32s}: {stats['works']:5d} works | {tag} {stats['inserted']:5d} | "
          f"{stats['duplicates']} dup | {stats['skipped']} skip")
    return stats


def ingest(name: str, after: str, before: str, dry_run: bool) -> dict:
    src = find_source_entry(name)
    vertical = src["vertical"] if src else "CROSS"
    stats = {"works": 0, "inserted": 0, "duplicates": 0, "skipped": 0}

    with httpx.Client(headers=HEADERS) as client:
        # An explicit `openalex_id` in sources.yaml wins over name search — used
        # for sources whose display name doesn't match the OpenAlex journal
        # (e.g. "Science Magazine News" -> Science S3880285, "Matter (Cell Press)"
        # where a generic "Matter" search hits physics journals instead).
        explicit = (src or {}).get("openalex_id")
        resolved = (explicit, name) if explicit else resolve_source_id(client, name)
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
    ap = argparse.ArgumentParser(
        description="Ingest OpenAlex works — by journal (--source-name) or by "
                    "concept across all journals (--concept / --vertical)")
    ap.add_argument("--source-name", help="journal mode: one source by name")
    ap.add_argument("--concept", help="concept mode: one concept name (e.g. 'obesity')")
    ap.add_argument("--vertical", help="concept mode: vertical, or ALL to run the "
                    "curated CONCEPT_SHARDS for every vertical")
    ap.add_argument("--after", default="2010-01-01", help="YYYY-MM-DD (default 2010-01-01)")
    ap.add_argument("--before", default="2020-01-01",
                    help="YYYY-MM-DD (default 2020-01-01 — the pre-2020 science gap)")
    ap.add_argument("--min-citations", type=int, default=5,
                    help="concept mode: only works with cited_by_count above this "
                         "(noise gate; meaningful for pre-2020 works)")
    ap.add_argument("--cap", type=int, default=3000, help="concept mode: max inserts per concept")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Journal mode (unchanged)
    if args.source_name:
        s = ingest(args.source_name, args.after, args.before, args.dry_run)
        if not args.dry_run and s["inserted"]:
            print(f"  -> {s['inserted']} neue datierte raw_entries (processed=0)")
        return 0

    # Concept mode
    if not (args.concept or args.vertical):
        ap.error("need --source-name (journal) or --concept/--vertical (concept mode)")

    if args.concept and args.vertical and args.vertical.upper() != "ALL":
        jobs = [(args.concept, args.vertical.upper())]
    elif args.concept:
        ap.error("--concept also needs --vertical (the tier's vertical label)")
    elif args.vertical and args.vertical.upper() == "ALL":
        jobs = [(c, v) for v, cs in CONCEPT_SHARDS.items() for c in cs]
    else:  # --vertical FOO → that vertical's curated shards
        v = args.vertical.upper()
        jobs = [(c, v) for c in CONCEPT_SHARDS.get(v, [])]
        if not jobs:
            ap.error(f"no curated concepts for vertical {v}; pass --concept explicitly")

    grand = {"works": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    for concept, vert in jobs:
        s = ingest_concept(concept, vert, args.after, args.before,
                           args.min_citations, args.cap, args.dry_run)
        for k in grand:
            grand[k] += s.get(k, 0)
    tag = "[dry] würde einfügen" if args.dry_run else "eingefügt"
    print(f"{'TOTAL':32s}: {grand['works']:5d} works | {tag} {grand['inserted']:5d} | "
          f"{grand['duplicates']} dup | {grand['skipped']} skip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
