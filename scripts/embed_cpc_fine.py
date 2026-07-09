#!/usr/bin/env python3
"""Embed the fine CPC codes into the shared vector space (issue #42).

parse_cpc_scheme.py built cpc_fine (261k codes). This embeds the ones that carry
enough patents to matter (n_patents >= MIN_PATENTS) so a free-text query resolves
to the RIGHT fine code (A23C20/025 = plant-based cheese), not just a coarse
subclass. Embeds the title_path (title + ancestor context) with the same
multilingual model + GPU handover as the pipeline.

Batched against llama-server's OpenAI /v1/embeddings (list input) — ~50-100x
fewer round-trips than one-per-code. Resumable (WHERE embedding_1024 IS NULL).

    python scripts/embed_cpc_fine.py                 # embed all >= MIN_PATENTS
    python scripts/embed_cpc_fine.py --min-patents 200
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import gpu_handover
from pipeline.config import EMBED_MODEL
from pipeline.llamacpp_client import LLAMACPP_HOST
from pipeline.db import USE_POSTGRES, get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("embed_cpc_fine")

MIN_PATENTS = 50
BATCH = 48


def embed_batch(texts: list[str]) -> list[list[float] | None]:
    """One /v1/embeddings call for a list of texts (OpenAI batch)."""
    try:
        with httpx.Client(timeout=180) as client:
            r = client.post(f"{LLAMACPP_HOST}/v1/embeddings", json={"input": texts})
            r.raise_for_status()
            data = r.json()["data"]
        # data is ordered by index per the OpenAI contract, but be defensive
        out: list[list[float] | None] = [None] * len(texts)
        for item in data:
            out[item.get("index", 0)] = item["embedding"]
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("batch embed error (%s) — falling back to singles", type(e).__name__)
        return [None] * len(texts)


def load_todo(min_patents: int) -> list[dict]:
    with get_connection() as c:
        rows = c.execute(
            "SELECT symbol, title_path FROM cpc_fine "
            "WHERE embedding_1024 IS NULL AND title_path IS NOT NULL "
            "  AND n_patents >= ? ORDER BY symbol", (min_patents,)).fetchall()
    return [dict(r) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description="Embed fine CPC codes (#42)")
    ap.add_argument("--min-patents", type=int, default=MIN_PATENTS)
    args = ap.parse_args()
    if not USE_POSTGRES:
        logger.error("targets Postgres (pgvector)")
        return 1
    todo = load_todo(args.min_patents)
    logger.info("fine CPC codes to embed: %d (>=%d patents, model=%s)",
                len(todo), args.min_patents, EMBED_MODEL)
    if not todo:
        logger.info("nothing to do")
        # still (re)build the index in case it's missing
    done = err = 0
    t0 = time.time()
    with gpu_handover.embed_on_llamacpp(EMBED_MODEL):
        with get_connection() as conn:
            cur = conn._conn.cursor()
            for start in range(0, len(todo), BATCH):
                chunk = todo[start:start + BATCH]
                embs = embed_batch([r["title_path"] for r in chunk])
                for row, emb in zip(chunk, embs):
                    if not emb:
                        err += 1
                        continue
                    cur.execute(
                        "UPDATE cpc_fine SET embedding_1024 = %s::vector WHERE symbol = %s",
                        (str(list(emb[:1024])), row["symbol"]))
                    done += 1
                if start % (BATCH * 20) == 0:
                    conn._conn.commit()
                    rate = done / max(time.time() - t0, 1e-9)
                    logger.info("  %d/%d embedded (%.0f/s, %d err)",
                                start + len(chunk), len(todo), rate, err)
            conn._conn.commit()

    with get_connection() as conn:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cpc_fine_emb1024 ON cpc_fine "
            "USING hnsw (embedding_1024 vector_cosine_ops)")
    logger.info("Done: %d embedded, %d errors in %.0fs. HNSW index ready.",
                done, err, time.time() - t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
