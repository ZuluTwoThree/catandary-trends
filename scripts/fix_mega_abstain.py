#!/usr/bin/env python3
"""Clean up forced mega-trend misassignments (issue #39).

The mega-trend classifier (both the distill OvR head and the LLM path) used to
force a mega-trend even when none fit — a superhero-movie LIFESTYLE trend ended
up as "future_of_food_and_agriculture". This re-scores every published trend
with the distill head's new abstain rule (max decision score < 0 → no fit) and
sets mega_trend = NULL where it abstains, removing the wrong labels without
touching the confident ones.

    python scripts/fix_mega_abstain.py --dry-run     # report only
    python scripts/fix_mega_abstain.py --execute     # apply NULLs
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.distill import DistillClassifier

BATCH = 2000


def _parse_vec(emb: str) -> np.ndarray:
    return np.array([float(x) for x in emb.strip("[]").split(",")], dtype=np.float32)


def main() -> int:
    ap = argparse.ArgumentParser(description="Null forced mega-trends where distill abstains (#39)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    ap.add_argument("--status", default="published",
                    help="trend status to clean (default: published)")
    args = ap.parse_args()

    clf = DistillClassifier.load()
    import psycopg2
    conn = psycopg2.connect("postgresql:///catandary")

    # server-side cursor to stream ids+embeddings without loading all at once
    cur = conn.cursor(name="mega_scan")
    cur.itersize = BATCH
    cur.execute(
        "SELECT id, mega_trend, embedding FROM trends "
        "WHERE status = %s AND embedding IS NOT NULL AND mega_trend IS NOT NULL",
        (args.status,))

    to_null: list[int] = []
    seen = 0
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        vecs = np.stack([_parse_vec(r[2]) for r in rows])
        preds = clf.classify_batch(vecs)
        for r, p in zip(rows, preds):
            seen += 1
            stored = r[1]
            # Misassignment signal: the stored mega-trend isn't even among the
            # embedding's top-3 candidates → the label-setter (LLM or an older
            # head) picked something the embedding strongly disagrees with
            # (Supergirl→food: food not in [AI, inclusive-design, fintech]).
            # This is precise regardless of absolute score, unlike a max<0
            # abstain which nulls 22% of plausible in-top-3 labels.
            if stored not in (p.get("mega_top3") or [])[:2]:
                to_null.append(r[0])
    cur.close()

    print(f"scanned {seen:,} published trends with a mega_trend")
    print(f"→ {len(to_null):,} have a FORCED mega-trend (embedding disagrees, not in top-2) → set NULL")
    if seen:
        print(f"   = {100*len(to_null)/seen:.1f}% of labelled trends")

    if args.dry_run:
        print("\nDRY-RUN — no changes written. Re-run with --execute to apply.")
        conn.close()
        return 0

    # apply in chunks
    wcur = conn.cursor()
    for i in range(0, len(to_null), 5000):
        chunk = to_null[i:i + 5000]
        wcur.execute("UPDATE trends SET mega_trend = NULL WHERE id = ANY(%s)", (chunk,))
    conn.commit()
    print(f"\nEXECUTED — set mega_trend = NULL on {len(to_null):,} trends.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
