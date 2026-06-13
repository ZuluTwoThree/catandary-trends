#!/usr/bin/env python3
"""Pass-rate re-check for the noisy new RSS feeds flagged on 2026-06-13.

Background: the first large run of the product/trend-radar sources surfaced
several new feeds well below the expected relevance-filter pass-rate
(see BACKLOG.md → "Rauschige neue Feeds beobachten — Qualitätscheck am
2026-06-20"). This script re-measures, per watched feed, how many of its
processed entries passed the relevance filter (processed=1, filtered_out=0)
over the last N days, so a feed can be kept / re-scoped / disabled.

It reads the LOCAL SQLite DB only — no network, no LLM. Output goes to stdout
and to a timestamped report file under ~/logs/.

Usage:
    python scripts/feed_quality_recheck.py [--days 7] [--min-volume 20] [--threshold 0.35]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sqlite3
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(REPO, "data", "catandary.db")
LOG_DIR = os.path.expanduser("~/logs")

# Feeds flagged as noisy in the 2026-06-13 post-run report.
WATCHED = [
    "GlobeNewswire",
    "Guardian Food",
    "Guardian Culture",
    "Architectural Record",
    "TextilWirtschaft",
    "EU Parliament Press",
    "NYT Science",
    "OMR",
    "EFSA News",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Noisy-feed pass-rate re-check")
    ap.add_argument("--days", type=int, default=7, help="look-back window in days")
    ap.add_argument("--min-volume", type=int, default=20,
                    help="min processed entries to judge a feed")
    ap.add_argument("--threshold", type=float, default=0.35,
                    help="pass-rate below this (at volume) => action recommended")
    args = ap.parse_args()

    if not os.path.exists(DB):
        print(f"ERROR: DB not found at {DB}", file=sys.stderr)
        return 2

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    window = f"r.processed=1 AND r.fetched_at >= datetime('now','-{args.days} days')"

    lines: list[str] = []

    def emit(s: str = "") -> None:
        lines.append(s)

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    emit("=" * 64)
    emit(f"Catandary noisy-feed pass-rate re-check — {now}")
    emit(f"window: last {args.days} days | min-volume: {args.min_volume} | "
         f"action threshold: {args.threshold:.0%}")
    emit("=" * 64)

    # Overall by source type (context).
    emit("\n-- pass-rate by source type (window) --")
    for row in cur.execute(f"""
        SELECT s.source_type st, COUNT(*) tot,
               SUM(CASE WHEN r.filtered_out=0 THEN 1 ELSE 0 END) passed
        FROM raw_entries r JOIN sources s ON r.source_id=s.id
        WHERE {window}
        GROUP BY s.source_type ORDER BY tot DESC
    """):
        tot = row["tot"]
        pr = row["passed"] / tot if tot else 0.0
        emit(f"  {str(row['st']):<12} {tot:>5} proc  {row['passed']:>5} pass  {pr:6.1%}")

    # Per watched feed.
    emit("\n-- watched feeds --")
    flagged: list[tuple[str, int, float]] = []
    for name in WATCHED:
        row = cur.execute(f"""
            SELECT COUNT(*) tot,
                   SUM(CASE WHEN r.filtered_out=0 THEN 1 ELSE 0 END) passed
            FROM raw_entries r JOIN sources s ON r.source_id=s.id
            WHERE {window} AND s.name=?
        """, (name,)).fetchone()
        tot = row["tot"] or 0
        passed = row["passed"] or 0
        pr = passed / tot if tot else 0.0
        if tot < args.min_volume:
            verdict = "insufficient volume"
        elif pr < args.threshold:
            verdict = "*** BELOW THRESHOLD — action ***"
            flagged.append((name, tot, pr))
        else:
            verdict = "ok"
        emit(f"  {name:<24} {tot:>4} proc  {pr:6.1%} pass   {verdict}")

    # Recommendation block.
    emit("\n-- recommendation --")
    if not flagged:
        emit("  No watched feed is below threshold at relevant volume. "
             "Keep all; consider closing the BACKLOG item.")
    else:
        emit("  These feeds remain noisy after the window — pick one action each:")
        emit("  (a) per-source relevance threshold, (b) more specific section feed URL, "
             "(c) active:false in sources.yaml.")
        for name, tot, pr in flagged:
            emit(f"    - {name}: {pr:.0%} pass over {tot} entries")
    con.close()

    report = "\n".join(lines)
    print(report)

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
        path = os.path.join(LOG_DIR, f"catandary-feedcheck-{stamp}.log")
        with open(path, "w") as fh:
            fh.write(report + "\n")
        print(f"\n[report written to {path}]")
    except OSError as e:
        print(f"\n[WARN: could not write report file: {e}]", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
