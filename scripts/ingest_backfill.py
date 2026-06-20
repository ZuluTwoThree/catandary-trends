#!/usr/bin/env python3
"""All-vertical historical backfill router.

Classifies every active source (probe_source_apis.classify) and routes it to the
right free ingester — WordPress REST API, OpenAlex, or sitemap fallback — for the
given date window. Writes dated raw_entries (processed=0); the signal-mode
pipeline (CLASSIFY_BACKEND=anthropic) picks them up afterwards.

Usage:
    # dry-run one vertical (counts only, no writes)
    python scripts/ingest_backfill.py --vertical FOOD --after 2018-01-01 --before 2023-01-01 --dry-run

    # real run, all verticals
    python scripts/ingest_backfill.py --after 2018-01-01 --before 2023-01-01
"""
from __future__ import annotations
import argparse
import logging
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import load_sources
from scripts.probe_source_apis import classify, collect_sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SCRIPTS = {"WP": "ingest_wordpress.py", "ACADEMIC": "ingest_openalex.py", "OTHER": "ingest_sitemap.py"}
_COUNT = re.compile(r"(?:eingefügt|einfügen|inserted)\s+(\d+)", re.I)
_DISCOVERED = re.compile(r"(\d+)\s+(?:URLs in range|works|posts|sitemap URLs)", re.I)
ROOT = Path(__file__).parent.parent


def run_source(name: str, category: str, after: str, before: str, dry_run: bool) -> tuple[int, str]:
    script = SCRIPTS[category]
    cmd = [sys.executable, str(ROOT / "scripts" / script),
           "--source-name", name, "--after", after, "--before", before]
    if dry_run:
        cmd.append("--dry-run")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=1800).stdout
    except Exception as e:  # noqa: BLE001
        return 0, f"ERROR {type(e).__name__}"
    line = next((l for l in reversed(out.splitlines())
                 if name in l or "inserted" in l or "URLs" in l), "")
    m = _COUNT.search(line) or _DISCOVERED.search(line)
    return (int(m.group(1)) if m else 0), line.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vertical", help="limit to one vertical (else all)")
    ap.add_argument("--after", required=True)
    ap.add_argument("--before", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", choices=["WP", "ACADEMIC", "OTHER"], help="route only this category")
    args = ap.parse_args()

    sources = collect_sources(load_sources())
    if args.vertical:
        sources = [s for s in sources if s["vertical"] == args.vertical.upper()]
    print(f"Routing {len(sources)} sources | {args.after}..{args.before} | dry_run={args.dry_run}\n")

    by_cat = defaultdict(lambda: {"sources": 0, "count": 0})
    total = 0
    for s in sources:
        name = s.get("name", "?")
        cat, _, _ = classify(s)
        if args.only and cat != args.only:
            continue
        n, line = run_source(name, cat, args.after, args.before, args.dry_run)
        by_cat[cat]["sources"] += 1
        by_cat[cat]["count"] += n
        total += n
        print(f"  [{cat:<8}] {name[:34]:<34} {n:>6}  {line[-50:] if line else ''}")

    print(f"\n{'Kategorie':<12}{'Quellen':>9}{'Eintraege':>12}")
    for cat, d in sorted(by_cat.items()):
        print(f"  {cat:<10}{d['sources']:>9}{d['count']:>12}")
    verb = "würde einfügen" if args.dry_run else "eingefügt"
    print(f"\nGESAMT {verb}: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
