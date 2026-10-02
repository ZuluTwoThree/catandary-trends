#!/usr/bin/env python3
"""Retire kept signals that the signal rules call junk (Owner 2026-10-02).

pipeline/signal_rules.py judges patents and funding on the signal path since 02.10. The
same rules applied to what is ALREADY in the signal space found 1.8 % of the 622,000 kept
patent/funding signals to be junk: award notices without any content ("X wins $750k SBIR
Phase II award", N/A), SEC Form D real-estate / restaurant / fund vehicles, absurd Form D
amounts, plant varieties — plus 10 PUBLISHED articles written from Form D vehicles on
24./25.08., before SEC Form D stopped feeding the article cycle.

This sets their status to 'rejected' with review_reason 'junk:<rule>'. Nothing is deleted,
reviewed_at stays NULL (not a human decision), and a row a person decided on (reviewed_at
set) is never touched. Batched commits (1,000 rows) — never one big UPDATE on trends (HNSW
bloat, 2026-09-17).

    .venv/bin/python scripts/retire_rule_junk.py           # dry run: counts + examples
    .venv/bin/python scripts/retire_rule_junk.py --apply   # write

Afterwards the domain service's copy still counts them as signals until it is rebuilt:
    .venv/bin/python -m pipeline.domain_service --rebuild && systemctl --user restart catandary-domain-service
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.db import get_connection  # noqa: E402
from pipeline.signal_rules import rule_tier, verdict  # noqa: E402

BATCH = 1000


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    with get_connection() as c:
        c.execute("SET statement_timeout = '3600s'")
        rows = c.execute(
            "SELECT t.id, t.status, r.title, r.excerpt, r.pub_number, s.name AS source_name, "
            "s.source_type FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id "
            "JOIN sources s ON s.id = r.source_id "
            "WHERE t.status IN ('signal','published') AND t.reviewed_at IS NULL "
            "AND (r.pub_number IS NOT NULL OR s.source_type = 'api')").fetchall()
    picked: list[tuple[int, str]] = []
    cnt: Counter = Counter()
    ex: dict = defaultdict(list)
    for r in rows:
        r = dict(r)
        if not rule_tier(r):
            continue
        v = verdict(r)
        if v:
            picked.append((int(r["id"]), v))
            cnt[(r["status"], v)] += 1
            if len(ex[v]) < 3:
                ex[v].append((r["title"] or "")[:80])
    for k, n in sorted(cnt.items(), key=lambda kv: -kv[1]):
        print(f"  {k[0]:9s} {k[1]:16s} {n:7,}")
    for v, xs in ex.items():
        print(f"  e.g. {v}: {xs}")
    print(f"{len(picked):,} rows to retire")
    if not args.apply:
        print("DRY RUN — nothing changed. Re-run with --apply.")
        return 0
    done = 0
    with get_connection() as c:
        for k in range(0, len(picked), BATCH):
            for tid, v in picked[k:k + BATCH]:
                c.execute("UPDATE trends SET status = 'rejected', review_reason = ? "
                          "WHERE id = ? AND reviewed_at IS NULL", (f"junk:{v}", tid))
            c.commit()
            done += len(picked[k:k + BATCH])
            print(f"  retired {done:,}/{len(picked):,}", flush=True)
    print(f"APPLIED: {done:,} rows set to rejected (review_reason junk:<rule>).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
