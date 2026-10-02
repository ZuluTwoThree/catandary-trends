#!/usr/bin/env python3
"""Requeue the dropped patents/funding that pass the rules but have NO stored vector (02.10.2026).

recover_rule_signals.py brought back what the relevance head had dropped AND whose vector
was stored. 93,508 rows pass pipeline/signal_rules.py without a vector (mostly the July
backfill: 73,534 SEC Form D, 19,242 NIH, plus NSF/OpenAIRE and 289 patents); they need the
embedder. This script selects them, writes their ids, and with --apply sets them back to
unprocessed so the regular signal path picks exactly these up:

    .venv/bin/python scripts/requeue_rule_signals.py              # dry run: counts + ids file
    .venv/bin/python scripts/requeue_rule_signals.py --apply      # processed/filtered_out -> FALSE
    .venv/bin/python scripts/signal_batch_embedded.py --ids-file data/requeue_rule_signals.ids

filter_reason becomes 'requeued:<old reason>' — the signal path overwrites it if it drops
the row again (duplicate, rule), and leaves it as the record of where a kept row came from.
Batched (1,000 rows per commit). Only raw_entries is touched; nothing is deleted.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import DATA_DIR  # noqa: E402
from pipeline.db import get_connection  # noqa: E402
from pipeline.signal_rules import rule_tier, verdict  # noqa: E402

IDS_FILE = DATA_DIR / "requeue_rule_signals.ids"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    with get_connection() as c:
        c.execute("SET statement_timeout = '3600s'")
        rows = c.execute(
            "SELECT r.id, r.title, r.excerpt, r.pub_number, r.filter_reason, "
            "s.name AS source_name, s.source_type "
            "FROM raw_entries r JOIN sources s ON s.id = r.source_id "
            "WHERE r.filtered_out AND r.embedding_blob IS NULL "
            "AND r.filter_reason LIKE 'not_relevant%%' "
            "AND (r.pub_number IS NOT NULL OR s.source_type = 'api') ORDER BY r.id").fetchall()
    picked, cnt = [], Counter()
    for r in rows:
        r = dict(r)
        tier = rule_tier(r)
        if not tier:
            continue
        v = verdict(r)
        cnt[f"{tier}/{'requeue' if not v else 'rule:' + v}"] += 1
        if not v:
            picked.append((r["id"], r["filter_reason"]))
    IDS_FILE.write_text("\n".join(str(i) for i, _ in picked) + "\n", encoding="utf-8")
    print(dict(cnt))
    print(f"{len(picked):,} ids -> {IDS_FILE}")
    if not args.apply:
        print("DRY RUN — nothing changed. Re-run with --apply.")
        return 0
    done = 0
    with get_connection() as c:
        for k in range(0, len(picked), 1000):
            for i, old in picked[k:k + 1000]:
                c.execute("UPDATE raw_entries SET processed = FALSE, filtered_out = FALSE, "
                          "filter_reason = ? WHERE id = ? AND filtered_out", (f"requeued:{old}"[:200], i))
            c.commit()
            done += len(picked[k:k + 1000])
            print(f"  requeued {done:,}/{len(picked):,}", flush=True)
    print(f"APPLIED: {done:,} rows back to unprocessed. Next: "
          f".venv/bin/python scripts/signal_batch_embedded.py --ids-file {IDS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
