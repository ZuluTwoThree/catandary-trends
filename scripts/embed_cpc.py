#!/usr/bin/env python3
"""Embed the CPC definitions into the shared vector space (issue #28).

Turns the 653 parsed CPC subclass definitions into embeddings (same Qwen3
multilingual model + GPU handover as the pipeline), so any signal from any tier
can be projected onto CPC by nearest-neighbour search — the common technology
backbone for cross-tier lead-time alignment.

Resumable (WHERE embedding IS NULL). Builds an HNSW index on the 1024-d prefix.

    python scripts/embed_cpc.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import gpu_handover, llamacpp_client
from pipeline.config import EMBED_MODEL
from pipeline.db import USE_POSTGRES, get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("embed_cpc")


def load_todo() -> list[dict]:
    with get_connection() as c:
        rows = c.execute(
            "SELECT symbol, title, definition FROM cpc_definitions "
            "WHERE embedding IS NULL AND definition IS NOT NULL").fetchall()
    return [dict(r) for r in rows]


def main() -> int:
    if not USE_POSTGRES:
        logger.error("CPC embedding backbone targets Postgres (pgvector)."); return 1
    todo = load_todo()
    logger.info("CPC definitions to embed: %d (model=%s)", len(todo), EMBED_MODEL)
    if not todo:
        logger.info("nothing to do — already embedded."); return 0

    done, errors = 0, 0
    with gpu_handover.embed_on_llamacpp(EMBED_MODEL):
        with get_connection() as conn:
            cur = conn._conn.cursor()
            for i, row in enumerate(todo, 1):
                text = f"{row['title']}\n{row['definition']}"
                try:
                    emb = llamacpp_client.generate_embedding(text, model=EMBED_MODEL)
                except Exception as e:  # noqa: BLE001
                    logger.warning("  %s: embed error %s", row["symbol"], type(e).__name__)
                    errors += 1
                    continue
                if not emb:
                    errors += 1
                    continue
                cur.execute(
                    "UPDATE cpc_definitions SET embedding = %s::vector, "
                    "embedding_1024 = %s::vector WHERE symbol = %s",
                    (str(list(emb)), str(list(emb[:1024])), row["symbol"]))
                done += 1
                if i % 100 == 0:
                    conn._conn.commit()
                    logger.info("  %d/%d embedded", i, len(todo))
            conn._conn.commit()

    # ANN index on the Matryoshka 1024-d prefix (cosine), for signal→CPC lookup
    with get_connection() as conn:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cpc_emb1024 ON cpc_definitions "
            "USING hnsw (embedding_1024 vector_cosine_ops)")
    logger.info("Done: %d embedded, %d errors. HNSW index ready.", done, errors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
