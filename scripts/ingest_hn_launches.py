#!/usr/bin/env python3
"""Hacker-News-Launch-Signale: „Launch HN" + „Show HN" (#87 Phase 2).

Algolia-HN-Search-API (frei, ohne Key, ~10k req/h; HN-API selbst ist MIT).
„Launch HN: Foo (YC W21) — …" ist der offizielle YC-Batch-Launch — der
legale Ersatz für das gesperrte YC-Directory. „Show HN" ist das breitere
Produkt-Launch-Signal. Score/Kommentare kommen als Resonanz-Proxy ins meta.

Paginierung über created_at-Fenster (Algolia deckelt 1.000 Treffer pro
Query). Firmen-Match konservativ über pipeline/startup_match.

    python scripts/ingest_hn_launches.py --dry-run
    python scripts/ingest_hn_launches.py
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline.startup_match import (
    insert_events, load_unique_name_index, match, refresh_aggregates,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_hn_launches")

API = "https://hn.algolia.com/api/v1/search_by_date"
UA = {"User-Agent": "CatandaryTrends research (trends@catandary.de)"}
SINCE = int(datetime(2013, 1, 1, tzinfo=timezone.utc).timestamp())

# "Launch HN: Cardinal Gray (YC S24) – concierge for medicare" -> Name + Batch
_LAUNCH_RE = re.compile(
    r"^Launch HN:\s*(.+?)\s*(?:\((YC [A-Z][0-9]{2})\))?\s*(?:[–—-]|$)")
# "Show HN: Foo – the bar for baz" -> Produkt-/Firmenname vor dem Dash
_SHOW_RE = re.compile(r"^Show HN:\s*(.+?)\s*(?:[–—-]|$)")


def parse_title(title: str) -> tuple[str, str | None, str] | None:
    """-> (name, yc_batch|None, kind) oder None."""
    m = _LAUNCH_RE.match(title or "")
    if m:
        return (m.group(1).strip(), m.group(2), "launch_hn")
    m = _SHOW_RE.match(title or "")
    if m:
        return (m.group(1).strip(), None, "show_hn")
    return None


def fetch(client: httpx.Client, query: str, start: int, end: int) -> list[dict]:
    out, lo = [], start
    while lo < end:
        r = client.get(API, params={
            "query": query, "tags": "story",
            "numericFilters": f"created_at_i>{lo},created_at_i<{end}",
            "hitsPerPage": 1000, "restrictSearchableAttributes": "title",
        }, timeout=60)
        r.raise_for_status()
        hits = r.json().get("hits", [])
        if not hits:
            break
        # search_by_date liefert absteigend — Fenster von oben abtragen
        out += hits
        oldest = min(h["created_at_i"] for h in hits)
        if len(hits) < 1000:
            break
        end = oldest
        time.sleep(0.4)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="HN-Launch-Signale (#87 Phase 2)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    idx = load_unique_name_index()
    now = int(time.time())
    st = {"hits": 0, "parsed": 0, "matched": 0}
    events: list[tuple] = []
    with httpx.Client(headers=UA) as client:
        for phrase in ('"Launch HN"', '"Show HN"'):
            # Jahresfenster halten jede Query unter dem 1.000er-Deckel-Loop
            for y0 in range(SINCE, now, 365 * 24 * 3600):
                hits = fetch(client, phrase, y0, min(y0 + 365 * 24 * 3600, now))
                st["hits"] += len(hits)
                for h in hits:
                    title = h.get("title") or ""
                    if not title.startswith(phrase.strip('"')):
                        continue
                    p = parse_title(title)
                    if not p:
                        continue
                    st["parsed"] += 1
                    name, batch, kind = p
                    cid = match(idx, name)
                    if not cid:
                        continue
                    st["matched"] += 1
                    date = datetime.fromtimestamp(h["created_at_i"],
                                                  tz=timezone.utc).date().isoformat()
                    url = f"https://news.ycombinator.com/item?id={h['objectID']}"
                    meta = {"kind": kind, "score": h.get("points"),
                            "comments": h.get("num_comments"), "title": title[:200]}
                    if batch:
                        meta["yc_batch"] = batch
                    events.append((cid, "launch", date, None, None, None,
                                   "[]", json.dumps(meta), "Hacker News", url, None))
                time.sleep(0.4)
    logger.info("HN: %(hits)d Treffer, %(parsed)d geparst, %(matched)d gematcht", st)
    if args.dry_run:
        logger.info("DRY-RUN — nichts geschrieben.")
        return 0
    n = insert_events(events)
    refresh_aggregates()
    logger.info("%d Launch-Events geschrieben.", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
