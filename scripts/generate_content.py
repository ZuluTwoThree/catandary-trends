#!/usr/bin/env python3
"""Decoupled local content generation for signal-mode trends.

Picks `status='signal'` trends (foresight signals with classification + embedding
but no article), generates the EN article locally on qwen (the same Stage-6
`step_generate_content_en`), writes title/summary/body, and promotes the row to
`published` (or `draft` if confidence < AUTO_PUBLISH_CONFIDENCE).

Runs on the GPU on your schedule — independent of the (off-GPU, API-classified)
signal backfill. Three modes:

    # lazy — specific signals (e.g. on first view / promotion)
    python scripts/generate_content.py --ids 1234,1235

    # batch — a targeted subset
    python scripts/generate_content.py --vertical FOOD --since 2023-01-01 --limit 500

    # full — everything, in chunks
    python scripts/generate_content.py --all --chunk 200
"""
from __future__ import annotations
import argparse
import logging
import sys
import time
from contextlib import nullcontext
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import gpu_handover
from pipeline.config import AUTO_PUBLISH_CONFIDENCE, STAGE5_BACKEND, STAGE5_MODEL
from pipeline.db import get_connection, _now_iso
from pipeline.llm_processor import step_generate_content_en
from pipeline.models import ClassificationResult, ExtractionResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def select_signals(ids, vertical, since, limit):
    where = ["t.status = 'signal'"]
    params: list = []
    if ids:
        where.append(f"t.id IN ({','.join('?' * len(ids))})")
        params += ids
    if vertical:
        where.append("t.primary_vertical = ?")
        params.append(vertical)
    if since:
        where.append("r.published_date >= ?")
        params.append(since)
    sql = (
        "SELECT t.id, t.confidence, r.title, r.excerpt, r.url, "
        "       r.extraction_json, r.classification_json, s.name AS source_name "
        "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
        "LEFT JOIN sources s ON r.source_id = s.id "
        f"WHERE {' AND '.join(where)} ORDER BY r.published_date DESC"
    )
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def _load(json_str, schema, default):
    if not json_str:
        return default
    try:
        return schema.model_validate_json(json_str)
    except Exception:
        return default


def generate_for(rows) -> dict:
    stats = {"published": 0, "draft": 0, "errors": 0}
    gpu_ctx = (gpu_handover.content_gen_on_llamacpp(STAGE5_MODEL)
               if STAGE5_BACKEND == "llamacpp" else nullcontext())
    with gpu_ctx:
        for i, row in enumerate(rows, 1):
            try:
                ext = _load(row["extraction_json"], ExtractionResult, ExtractionResult())
                cls = _load(row["classification_json"], ClassificationResult,
                            ClassificationResult(verticals=[], pestel=[], tags=[],
                                                 trend_signal_type="market_shift"))
                en = step_generate_content_en(
                    row["title"], row["excerpt"] or "", ext, cls,
                    row["url"], row.get("source_name") or "Unknown")
                if en is None:
                    stats["errors"] += 1
                    continue
                publish = (row["confidence"] or 0) >= AUTO_PUBLISH_CONFIDENCE
                status = "published" if publish else "draft"
                with get_connection() as c:
                    c.execute(
                        "UPDATE trends SET title_en=?, summary_en=?, body_en=?, "
                        "status=?, published_at=?, auto_published=? WHERE id=?",
                        (en.title, en.summary, en.body, status,
                         _now_iso() if publish else None, 1 if publish else 0, row["id"]))
                stats["published" if publish else "draft"] += 1
                if i % 10 == 0:
                    logger.info("content-gen %d/%d (%d published, %d draft, %d err)",
                                i, len(rows), stats["published"], stats["draft"], stats["errors"])
            except Exception as e:  # noqa: BLE001
                logger.error("content-gen failed for trend %s: %s", row["id"], e)
                stats["errors"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="comma-separated trend ids (lazy mode)")
    ap.add_argument("--vertical")
    ap.add_argument("--since", help="article published_date >= YYYY-MM-DD")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--all", action="store_true", help="process all signals (chunked)")
    ap.add_argument("--chunk", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true", help="count matching signals only")
    args = ap.parse_args()

    ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    if not any([ids, args.vertical, args.since, args.limit, args.all]):
        print("Specify a scope: --ids / --vertical|--since|--limit / --all")
        return 2

    limit = None if args.all else (args.limit or 200)
    rows = select_signals(ids, args.vertical, args.since, limit)
    print(f"{len(rows)} signals match.")
    if args.dry_run or not rows:
        return 0

    totals = {"published": 0, "draft": 0, "errors": 0}
    for start in range(0, len(rows), args.chunk):
        chunk = rows[start:start + args.chunk]
        logger.info("chunk %d-%d of %d", start + 1, start + len(chunk), len(rows))
        s = generate_for(chunk)
        for k in totals:
            totals[k] += s[k]
    print(f"\nDone: {totals['published']} published, {totals['draft']} draft, {totals['errors']} errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
