#!/usr/bin/env python3
"""Repair truncated (mid-sentence) published article bodies via the Anthropic API (#18).

Off-GPU, synchronous, concurrent. Targets published trends whose `body_en` does
not end in sentence-terminal punctuation (the truncation proxy), rebuilds the
content-gen context from the cached extraction/classification, regenerates with
Claude Sonnet 5, and writes back ONLY if the new body is complete (passes the
same content guard). Status stays 'published' — this repairs in place.

    python scripts/repair_truncated_articles.py --dry-run            # count only
    python scripts/repair_truncated_articles.py --limit 5            # small test
    python scripts/repair_truncated_articles.py                      # full run
    python scripts/repair_truncated_articles.py --model claude-sonnet-5
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import anthropic_client
from pipeline.auto_publisher import _body_complete
from pipeline.config import STAGE5_MIN_BODY_WORDS
from pipeline.db import get_connection
from pipeline.llm_processor import CONTENT_EN_SYSTEM
from pipeline.models import GeneratedContent


def _acceptable(gc: GeneratedContent) -> bool:
    """Repair acceptance: the new body must be COMPLETE (not truncated) and long
    enough — but we do NOT reject on clichés here (a complete slightly-clichéd
    body still beats leaving a truncated one in place)."""
    body = (gc.body or "").strip()
    return len(body.split()) >= STAGE5_MIN_BODY_WORDS and _body_complete(body)

TRUNCATED_SQL = (
    "SELECT t.id AS tid, r.title, r.excerpt, r.extraction_json, r.classification_json, "
    "       t.verticals, t.pestel, t.trend_signal_type, t.mega_trend, "
    "       t.source_name, t.source_url "
    "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
    "WHERE t.status='published' AND t.body_en IS NOT NULL AND t.body_en!='' "
    "AND TRIM(t.body_en) NOT GLOB '*[.!?\"'')’”]'"
)


def _load(limit: int) -> list[dict]:
    sql = TRUNCATED_SQL + (" LIMIT ?" if limit else "")
    with get_connection() as c:
        rows = [dict(r) for r in (c.execute(sql, (limit,) if limit else ()).fetchall())]
    return rows


def _ctx(row: dict) -> str:
    """Rebuild the content-gen context from cached extraction/classification, with
    fallback to the trend's own classification fields."""
    ext, cls = {}, {}
    try:
        ext = json.loads(row["extraction_json"]) if row["extraction_json"] else {}
    except Exception:
        pass
    try:
        cls = json.loads(row["classification_json"]) if row["classification_json"] else {}
    except Exception:
        pass
    verticals = cls.get("verticals") or _jl(row["verticals"])
    pestel = cls.get("pestel") or _jl(row["pestel"])
    claims = ext.get("key_claims") or []
    return (
        f"Original Title: {row['title']}\n"
        f"Original Excerpt: {(row['excerpt'] or '')[:1000]}\n"
        f"Brand: {ext.get('brand_name') or 'Unknown'}\n"
        f"Product: {ext.get('product_name') or 'Unknown'}\n"
        f"Key Claims: {', '.join(claims[:5]) if claims else 'N/A'}\n"
        f"Verticals: {', '.join(verticals)}\n"
        f"PESTEL: {', '.join(pestel)}\n"
        f"Signal Type: {cls.get('trend_signal_type') or row['trend_signal_type'] or 'N/A'}\n"
        f"Mega Trend: {cls.get('mega_trend') or row['mega_trend'] or 'N/A'}\n"
        f"Source: {row['source_name']} ({row['source_url']})"
    )


def _jl(v):
    try:
        return json.loads(v) if v else []
    except Exception:
        return []


def _regen(row: dict, model: str) -> GeneratedContent | None:
    prompt = ("Write a trend article in English based on this information.\n"
              "The source below may be in German or another language — translate it "
              "and write the title and body entirely in English.\n\n"
              f"{_ctx(row)}\n\n")
    # temperature=None: the Claude 5 family rejects the param; omit it to avoid a
    # wasted first round-trip per call.
    return anthropic_client.chat_structured(
        model=model, prompt=prompt, schema=GeneratedContent,
        system=CONTENT_EN_SYSTEM, temperature=None)


def main() -> int:
    ap = argparse.ArgumentParser(description="Repair truncated article bodies (#18) via Anthropic")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--limit", type=int, default=0, help="max articles (0 = all)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="count matching, generate nothing")
    args = ap.parse_args()

    rows = _load(args.limit)
    print(f"truncated published articles in scope: {len(rows)}")
    if args.dry_run or not rows:
        if args.dry_run:
            print("DRY-RUN — nothing regenerated.")
        return 0

    t0 = time.time()
    fixed = still_bad = failed = 0
    done = 0

    def work(row):
        try:
            gc = _regen(row, args.model)
        except Exception as e:  # noqa: BLE001
            return row["tid"], "error", str(e)[:80], None
        if gc is None:
            return row["tid"], "error", "None result", None
        if not _acceptable(gc):
            return row["tid"], "still_bad", None, None
        return row["tid"], "ok", None, gc

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for tid, status, err, gc in ex.map(work, rows):
            done += 1
            if status == "ok":
                with get_connection() as c:
                    c.execute(
                        "UPDATE trends SET title_en=?, summary_en=?, body_en=? WHERE id=?",
                        (gc.title, gc.summary, gc.body, tid))
                fixed += 1
            elif status == "still_bad":
                still_bad += 1
            else:
                failed += 1
                if err:
                    print(f"  [{tid}] {err}")
            if done % 25 == 0:
                print(f"  {done}/{len(rows)}  (fixed {fixed}, still_bad {still_bad}, "
                      f"failed {failed}, {done/(time.time()-t0):.1f}/s)")

    print(f"\nDone in {time.time()-t0:.0f}s: {fixed} repaired, {still_bad} still truncated "
          f"(left as-is), {failed} errors (from {len(rows)}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
