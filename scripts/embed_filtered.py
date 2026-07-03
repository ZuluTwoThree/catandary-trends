#!/usr/bin/env python3
"""Embed ALL filtered-out raw entries (issue #10 / owner decision 2026-07-02).

Why: (a) trend-drift hedge — signals filtered as irrelevant today may become
relevant tomorrow; with embeddings they can be re-scored without re-ingesting.
(b) training data for the distillation relevance head (positives = trends,
negatives = filtered_out) — the missing piece of the #10 prototype.

The single GPU step of the eager path: hands the GPU over to the llama.cpp
embedding server (same handover as cycle Stage 5), embeds `title\n excerpt`
(same composition as step_dedup_check), writes `raw_entries.embedding_blob`.
Resumable (WHERE embedding_blob IS NULL); batch commits; concurrent requests
against the --parallel server.

    python scripts/embed_filtered.py --limit 50      # smoke
    python scripts/embed_filtered.py                 # full run (~265k)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import gpu_handover, llamacpp_client
from pipeline.config import EMBED_MODEL, LOG_LEVEL
from pipeline.db import get_connection
from pipeline.llm_processor import embedding_to_bytes

logging.basicConfig(level=LOG_LEVEL,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("embed_filtered")

FETCH_SQL = (
    "SELECT id, title, excerpt FROM raw_entries "
    "WHERE filtered_out = TRUE AND embedding_blob IS NULL AND title IS NOT NULL "
    "ORDER BY id"
)


def load_todo(limit: int) -> list[dict]:
    sql = FETCH_SQL + (" LIMIT ?" if limit else "")
    with get_connection() as c:
        return [dict(r) for r in c.execute(sql, (limit,) if limit else ()).fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Embed filtered-out raw entries (#10)")
    ap.add_argument("--limit", type=int, default=0, help="max entries (0 = all)")
    ap.add_argument("--workers", type=int, default=16,
                    help="concurrent requests against the --parallel llama-server")
    ap.add_argument("--commit-every", type=int, default=500)
    args = ap.parse_args()

    todo = load_todo(args.limit)
    logger.info("filtered_out entries without embedding: %d", len(todo))
    if not todo:
        return 0

    t0 = time.time()
    done = errors = 0
    buf: list[tuple[bytes, int]] = []

    def flush():
        nonlocal buf
        if not buf:
            return
        with get_connection() as c:
            c.executemany(
                "UPDATE raw_entries SET embedding_blob = ? WHERE id = ?", buf)
        buf = []

    def work(row: dict):
        text = f"{row['title']}\n{(row['excerpt'] or '')[:500]}"
        return row["id"], llamacpp_client.generate_embedding(text, model=EMBED_MODEL)

    with gpu_handover.embed_on_llamacpp(EMBED_MODEL):
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            for rid, emb in ex.map(work, todo):
                done += 1
                if emb is None:
                    errors += 1
                else:
                    buf.append((embedding_to_bytes(emb), rid))
                if len(buf) >= args.commit_every:
                    flush()
                if done % 5000 == 0:
                    rate = done / (time.time() - t0)
                    eta_min = (len(todo) - done) / rate / 60 if rate else 0
                    logger.info("%d/%d (%.0f/s, %d errors, ETA %.0f min)",
                                done, len(todo), rate, errors, eta_min)
        flush()

    logger.info("Done in %.0fs: %d embedded, %d errors (of %d)",
                time.time() - t0, done - errors, errors, len(todo))
    return 0 if errors < len(todo) * 0.05 else 1


if __name__ == "__main__":
    raise SystemExit(main())
