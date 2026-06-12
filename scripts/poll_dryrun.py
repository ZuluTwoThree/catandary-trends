"""Dry-run feed poll: fetch all feeds, check which URLs are not yet in
raw_entries, but do NOT insert. Reports per-vertical and per-source counts.
"""
from __future__ import annotations

import sys
from collections import defaultdict

from pipeline.config import load_sources
from pipeline.db import get_connection
from pipeline.feed_poller import fetch_feed


def load_known_urls() -> set[str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT url FROM raw_entries").fetchall()
    return {r["url"] for r in rows}


def main():
    known = load_known_urls()
    print(f"Known URLs in DB: {len(known)}")

    config = load_sources()
    new_by_vertical: dict[str, int] = defaultdict(int)
    fetched_by_vertical: dict[str, int] = defaultdict(int)
    per_source_new: list[tuple[str, str, int, int]] = []  # (vertical, name, new, fetched)
    errors = 0

    verticals = config.get("verticals", {})
    for v, cfg in verticals.items():
        all_sources = cfg.get("sources", []) + cfg.get("science", []) + cfg.get("radar", [])
        for s in all_sources:
            if s.get("active") is False:
                continue
            name = s["name"]
            try:
                entries = fetch_feed(name, s["feed_url"])
            except Exception as e:
                print(f"  ERROR {name}: {e}", file=sys.stderr)
                errors += 1
                continue
            new = sum(1 for e in entries if e["url"] not in known)
            fetched_by_vertical[v] += len(entries)
            new_by_vertical[v] += new
            per_source_new.append((v, name, new, len(entries)))

    cross = config.get("cross_industry", {})
    for category, items in cross.items():
        for s in items:
            if s.get("type") == "api" or s.get("active") is False:
                continue
            name = s["name"]
            try:
                entries = fetch_feed(name, s["feed_url"])
            except Exception as e:
                print(f"  ERROR {name}: {e}", file=sys.stderr)
                errors += 1
                continue
            new = sum(1 for e in entries if e["url"] not in known)
            fetched_by_vertical["CROSS"] += len(entries)
            new_by_vertical["CROSS"] += new
            per_source_new.append(("CROSS", name, new, len(entries)))

    total_new = sum(new_by_vertical.values())
    total_fetched = sum(fetched_by_vertical.values())

    print()
    print("=" * 70)
    print(f"Total fetched: {total_fetched}")
    print(f"Total NEW (not yet in DB): {total_new}")
    print(f"Errors: {errors}")
    print()
    print("By vertical:")
    for v in sorted(new_by_vertical.keys()):
        print(f"  {v:<10} new={new_by_vertical[v]:>4}  fetched={fetched_by_vertical[v]:>4}")

    print()
    print("Top 15 sources by new-entry count:")
    per_source_new.sort(key=lambda x: -x[2])
    for v, name, new, fetched in per_source_new[:15]:
        print(f"  {new:>3}/{fetched:<3}  [{v:<9}]  {name}")


if __name__ == "__main__":
    main()
