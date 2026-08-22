#!/usr/bin/env python3
"""Release the Haiku-approved backlog (owner decision 2026-08-22).

109 Haiku subagents judged all 10,884 sub-threshold drafts; 7,798 were approved
(data/haiku_review/verdicts/). This releases exactly those — after re-applying
the SAME deterministic gates every release path uses (pipeline.draft_judge):
truncation, grounding against the full stored source, and dedup against the
published corpus via the partial HNSW index. Judges approved past a grounding
flag in 297 cases and past truncation in 3 — the gates catch what the judges'
truncated source snippet could not.

Publishing is sequential oldest-first, so a released article immediately guards
its near-twins via the index. auto_published stays FALSE: this is an
owner-ordered reviewed release, not the nightly automatic path.

    python -m scripts.release_haiku_approved --dry-run
    python -m scripts.release_haiku_approved --execute
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from pipeline.draft_judge import duplicate_of_published, publish_draft, release_gates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("release")


def approved_ids() -> list[int]:
    ids = []
    for p in sorted(glob.glob("data/haiku_review/verdicts/slice_*.jsonl")):
        for line in open(p):
            if not line.strip():
                continue
            v = json.loads(line)
            if v.get("publish") is True:
                ids.append(int(v["id"]))
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.execute):
        ap.error("need --dry-run or --execute")

    ids = approved_ids()
    logger.info("Haiku-approved: %d ids", len(ids))
    stats = Counter()
    reasons = Counter()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT t.id, t.title_en, t.body_en, t.status, "
            "       re.title AS re_title, re.raw_content, re.excerpt, re.extraction_json "
            "  FROM trends t LEFT JOIN raw_entries re ON re.id = t.raw_entry_id "
            " WHERE t.id = ANY(?) ORDER BY t.created_at ASC",
            (ids,),
        ).fetchall()
    rows = [dict(r) for r in rows]

    for d in rows:
        if d["status"] != "draft":
            stats["not_draft"] += 1
            continue
        ok, reason = release_gates(d["title_en"], d["body_en"], d["re_title"],
                                   d["raw_content"], d["excerpt"], d["extraction_json"])
        if not ok:
            stats["gate_blocked"] += 1
            reasons[reason.split(":")[0]] += 1
            continue
        with get_connection() as conn:
            dup = duplicate_of_published(conn, d["id"])
            if dup:
                stats["dup_blocked"] += 1
                continue
            if args.execute:
                if publish_draft(conn, d["id"], auto=False):
                    stats["released"] += 1
                else:
                    stats["race_lost"] += 1
            else:
                stats["released"] += 1
        n = stats["released"]
        if n and n % 1000 == 0:
            logger.info("  %d released...", n)

    mode = "EXECUTED" if args.execute else "DRY RUN"
    logger.info("%s: %s", mode, dict(stats))
    if reasons:
        logger.info("gate reasons: %s", dict(reasons))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
