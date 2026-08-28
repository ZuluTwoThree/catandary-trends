#!/usr/bin/env python3
"""Apply source-hygiene deactivations found during the #81 quellen-audit (2026-08-28).

Root cause this closes: `sources.yaml` `active: false` is a config-time signal
only. `pipeline.feed_poller.poll_vertical_sources`/`poll_cross_industry` skip a
source marked `active: false` *before* ever calling `upsert_source` — so the
DB row's `active` flag is never touched. And `upsert_source` itself only
INSERTs on a new `feed_url`; it never UPDATEs an existing row's `active`
column (see its docstring: "Existing sources keep their stored flag — like
every other column, upsert does not overwrite"). Net effect: marking a source
inactive in `sources.yaml` stops it from being polled, but its DB row silently
stays `active=true` forever, so any *DB-side* accounting of "active sources"
(dashboards, CLAUDE.md's source count, etc.) drifts from reality.

Verified 2026-08-28: MobiHealthNews, Healthcare IT News and BMJ were all
marked `active: false` in `sources.yaml` back on 2026-06-12 (bot-blocked from
a Mac dev IP) and are STILL `active=true` in Postgres today.

This script does two things:

  1. For every source in `sources.yaml` with `active: false` (matched to its
     DB row by `feed_url`, the same key `upsert_source` uses), set
     `sources.active = false` in the DB if it isn't already.
  2. For DB-only orphans found during the #81 audit — rows that exist in the
     `sources` table but have NO corresponding `sources.yaml` entry at all, so
     `pipeline.feed_poller` never polls them because it iterates
     `load_sources()`, not the DB (`Environmental Leader`: feed_url now 404s,
     and the source was never re-added to `sources.yaml`) — deactivate those
     too. See EXTRA_DEACTIVATE below.

Idempotent: a source already `active=false` in the DB is left alone and
reported as "already inactive". Running twice is a no-op the second time.

This script performs real UPDATEs when run with --apply. It was written (and
its --dry-run output verified against a read-only DB check) during an audit
session that was NOT permitted to run write DB operations, so it has NOT been
executed yet — review the dry-run output, then run with --apply.

    python scripts/apply_source_hygiene.py              # dry run (default), prints the plan
    python scripts/apply_source_hygiene.py --apply       # actually UPDATE sources.active
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO))

from pipeline.config import load_sources  # noqa: E402

# DB-only orphans found during the 2026-08-28 (#81) audit: rows present in the
# `sources` table with no matching sources.yaml entry (so pipeline.feed_poller
# never polls them — it iterates load_sources(), never the DB). Matched by
# feed_url, the same key upsert_source uses to find/create a row.
# (feed_url, human-readable reason)
EXTRA_DEACTIVATE: list[tuple[str, str]] = [
    ("https://www.environmentalleader.com/feed/",
     "Environmental Leader — no sources.yaml entry (was never added, or fell "
     "out during an edit; git history for sources.yaml has no trace of it), "
     "so it was never polled. Feed URL itself now 404s too (site redirects to "
     "environmentenergyleader.com, which has no discoverable RSS feed)."),
]


def yaml_inactive_feed_urls(cfg: dict | None = None) -> list[tuple[str, str]]:
    """[(feed_url, source_name), ...] for every sources.yaml entry with
    `active: false`. Pure function of the loaded config — pass `cfg` directly
    in tests to avoid touching the real sources.yaml/DB."""
    cfg = load_sources() if cfg is None else cfg
    out: list[tuple[str, str]] = []

    def scan(entries):
        for s in entries or []:
            if s.get("active") is False and s.get("feed_url"):
                out.append((s["feed_url"], s["name"]))

    for _vertical, group in (cfg.get("verticals") or {}).items():
        scan(group.get("sources"))
        scan(group.get("science"))
    for _group_name, entries in (cfg.get("cross_industry") or {}).items():
        scan(entries)
    return out


def plan_deactivations(targets: list[tuple[str, str]],
                        db_rows: dict[str, dict]) -> dict[str, list]:
    """Pure planning step, testable without a DB connection.

    `targets`: [(feed_url, reason), ...] to deactivate.
    `db_rows`: {feed_url: {"id": int, "name": str, "active": bool}} — the
    current DB state for those feed_urls (whatever rows exist; missing
    feed_urls are simply absent from the dict).

    Returns {"deactivate": [...], "already_inactive": [...], "missing": [...]}
    where each list holds (feed_url, reason, row_or_None) tuples.
    """
    deactivate, already_inactive, missing = [], [], []
    for feed_url, reason in targets:
        row = db_rows.get(feed_url)
        if row is None:
            missing.append((feed_url, reason, None))
        elif not row["active"]:
            already_inactive.append((feed_url, reason, row))
        else:
            deactivate.append((feed_url, reason, row))
    return {"deactivate": deactivate, "already_inactive": already_inactive, "missing": missing}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sync sources.yaml active:false + known DB-only orphans into sources.active (#81)")
    ap.add_argument("--apply", action="store_true",
                    help="actually run the UPDATEs (default: dry-run, prints the plan only)")
    args = ap.parse_args()

    from pipeline.db import get_connection, USE_POSTGRES  # deferred: only needed for the real run

    targets = yaml_inactive_feed_urls() + EXTRA_DEACTIVATE
    # de-dupe (a source could in principle appear in both lists)
    seen = set()
    deduped = []
    for feed_url, reason in targets:
        if feed_url in seen:
            continue
        seen.add(feed_url)
        deduped.append((feed_url, reason))
    targets = deduped

    with get_connection() as conn:
        db_rows = {}
        for feed_url, _reason in targets:
            row = conn.execute(
                "SELECT id, name, active FROM sources WHERE feed_url = ?", (feed_url,)
            ).fetchone()
            if row is not None:
                db_rows[feed_url] = {"id": row["id"], "name": row["name"], "active": bool(row["active"])}

        plan = plan_deactivations(targets, db_rows)

        for feed_url, reason, row in plan["deactivate"]:
            verb = "DEACTIVATED" if args.apply else "WOULD DEACTIVATE"
            print(f"{verb}: id={row['id']} name={row['name']!r}\n  reason: {reason}\n  {feed_url}")
            if args.apply:
                active_val = False if USE_POSTGRES else 0
                conn.execute("UPDATE sources SET active = ? WHERE id = ?", (active_val, row["id"]))
        for feed_url, reason, row in plan["already_inactive"]:
            print(f"already inactive: id={row['id']} name={row['name']!r}  {feed_url}")
        for feed_url, reason, _ in plan["missing"]:
            print(f"SKIP (no DB row for this feed_url): {reason}\n  {feed_url}")

    n_deact, n_already, n_missing = len(plan["deactivate"]), len(plan["already_inactive"]), len(plan["missing"])
    print(f"\n{n_deact} {'deactivated' if args.apply else 'would be deactivated'}, "
          f"{n_already} already inactive, {n_missing} not found in DB")
    if not args.apply and n_deact:
        print("Dry run only — re-run with --apply to write these changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
