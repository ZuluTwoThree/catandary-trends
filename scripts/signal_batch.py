#!/usr/bin/env python3
"""Batch signal-mode classifier — the scalable, cost-halved backfill path (Option 3).

The per-entry `llm_processor --signal-mode` path makes synchronous Anthropic calls
(one per stage per entry) → impractical and full-price at ~100k+ entries. This
runner does the same classification through the **Message Batches API (−50%)** plus
**batched local embeddings**, then inserts content-less `status='signal'` rows.

Flow (mirrors run_pipeline_batch --signal-mode, but batched):
    1. title dedup (rapidfuzz, no LLM)
    2. relevance   ┐
    3. extraction  │  Anthropic Haiku via batch_classify (chunked, prompt-cached)
    4. classify    ┘
    5. embeddings  (local, batched /v1/embeddings or Ollama list) + dedup
    7. insert status='signal'

SAFETY: dry-run by default — builds every request, projects cost, submits NOTHING.
Pass --execute to actually submit batches (the only step that costs money).

Usage:
    python scripts/signal_batch.py --limit 5000                # dry-run + cost projection
    python scripts/signal_batch.py --limit 5000 --execute      # really submit (−50% batch)
"""
from __future__ import annotations
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from slugify import slugify

from pipeline import anthropic_client, ollama_client
from pipeline.config import (
    ANTHROPIC_MODEL_CLASSIFY, RELEVANCE_THRESHOLD, DUPLICATE_SIMILARITY_THRESHOLD,
    EMBED_BACKEND, EMBED_MODEL, MODEL_EMBEDDING,
)
from pipeline.llamacpp_client import LLAMACPP_HOST
from pipeline.crs import compute_crs
from pipeline.db import (
    get_connection, get_recent_titles, get_recent_embeddings,
    mark_filtered, mark_processed, insert_trend,
)
from pipeline.llm_processor import (
    RELEVANCE_SYSTEM, EXTRACTION_SYSTEM, CLASSIFICATION_SYSTEM,
    normalize_title, embedding_to_bytes, bytes_to_embedding,
    cosine_similarity,
)
from pipeline.models import RelevanceResult, ExtractionResult, ClassificationResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Phase-5 measured ~$2.88 / 1k entries synchronous (Haiku, cached). Batches halve
# it → ~$1.44 / 1k for the combined relevance+extraction+classification work.
COST_PER_1K_BATCHED = 1.44
MAX_REQUESTS_PER_BATCH = 40_000  # well under the 100k / 256MB API cap


# --- prompt builders (verbatim from llm_processor step_* functions) ----------

def p_relevance(title: str, excerpt: str) -> str:
    return (f"Analyze this RSS feed entry and determine if it's a relevant trend signal.\n"
            f"Classify the vertical based purely on the content, not on where the source comes from.\n\n"
            f"Title: {title}\n\nExcerpt: {excerpt[:1500]}")


def p_extraction(title: str, excerpt: str) -> str:
    return f"Extract structured information from this text.\n\nTitle: {title}\n\nText: {excerpt[:1500]}"


def p_classification(title: str, excerpt: str, ext: ExtractionResult) -> str:
    return (f"Classify this trend signal.\n\nTitle: {title}\nExcerpt: {excerpt[:1000]}\n"
            f"Brand: {ext.brand_name or 'Unknown'}\nProduct: {ext.product_name or 'Unknown'}\n"
            f"Key Claims: {', '.join(ext.key_claims[:5]) if ext.key_claims else 'None'}")


# --- batched embeddings ------------------------------------------------------

def embed_batch(texts: list[str]) -> list[list[float] | None]:
    """Embed a list of texts in one call. llama-server and Ollama both accept a
    list `input` and return embeddings in order."""
    if EMBED_BACKEND == "llamacpp":
        try:
            with httpx.Client(timeout=300) as c:
                r = c.post(f"{LLAMACPP_HOST}/v1/embeddings", json={"input": texts})
                r.raise_for_status()
                data = sorted(r.json()["data"], key=lambda d: d.get("index", 0))
            return [d["embedding"] for d in data]
        except Exception as e:  # noqa: BLE001
            logger.warning("batched llamacpp embed failed (%s) — falling back per-item", e)
            return [_embed_one(t) for t in texts]
    try:
        resp = ollama_client.client.embed(model=MODEL_EMBEDDING, input=texts)
        return list(resp.embeddings)
    except Exception as e:  # noqa: BLE001
        logger.warning("batched ollama embed failed (%s) — per-item", e)
        return [_embed_one(t) for t in texts]


def _embed_one(text: str) -> list[float] | None:
    if EMBED_BACKEND == "llamacpp":
        from pipeline import llamacpp_client
        return llamacpp_client.generate_embedding(text, model=EMBED_MODEL)
    return ollama_client.generate_embedding(MODEL_EMBEDDING, text)


# --- batch classify over chunks ----------------------------------------------

def batch_over_chunks(items: list[tuple[str, str]], schema, system, model) -> dict:
    out: dict = {}
    for i in range(0, len(items), MAX_REQUESTS_PER_BATCH):
        chunk = items[i:i + MAX_REQUESTS_PER_BATCH]
        logger.info("  submitting batch chunk %d-%d (%d requests)", i + 1, i + len(chunk), len(chunk))
        out.update(anthropic_client.batch_classify(chunk, schema, system, model))
    return out


def pull_unprocessed(limit: int, include: list[str], exclude: list[str]) -> list[dict]:
    """Unprocessed entries, optionally scoped by source vertical (include/exclude)."""
    where = ["re.processed = 0", "re.filtered_out = 0"]
    params: list = []
    if include:
        where.append(f"s.vertical IN ({','.join('?' * len(include))})")
        params += include
    if exclude:
        where.append(f"s.vertical NOT IN ({','.join('?' * len(exclude))})")
        params += exclude
    sql = ("SELECT re.*, s.name AS source_name, s.vertical AS source_vertical, "
           "s.source_type AS source_type FROM raw_entries re JOIN sources s ON re.source_id = s.id "
           f"WHERE {' AND '.join(where)} ORDER BY re.fetched_at ASC")
    if limit and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def title_dedup(entries: list[dict], commit: bool) -> list[dict]:
    """O(n) exact-normalized title dedup, scalable to 100k+ entries.

    Uses set membership on the normalized title (against recent DB titles and
    within the batch) instead of the live pipeline's O(n^2) all-pairs fuzzy
    match — infeasible at backfill scale. Near-duplicates with slightly different
    wording are caught downstream by the Stage-5 embedding dedup (cosine), so
    this only removes exact normalized-title repeats. Side-effect-free when
    commit=False (dry-run)."""
    existing = {normalize_title(t) for t in get_recent_titles(days=30)}
    survivors: list[dict] = []
    seen: set[str] = set()
    for e in entries:
        norm = normalize_title(e["title"] or "")
        if norm and (norm in existing or norm in seen):
            if commit:
                mark_filtered(e["id"], "title_duplicate_exact")
            continue
        if norm:
            seen.add(norm)
        survivors.append(e)
    return survivors


def run(limit: int, execute: bool, embed_chunk: int,
        include: list[str], exclude: list[str]) -> int:
    t0 = time.time()
    entries = pull_unprocessed(limit, include, exclude)
    scope = (f"include={include}" if include else "") + (f" exclude={exclude}" if exclude else "")
    print(f"Unprocessed in scope ({scope or 'ALL'}): {len(entries)}")
    if not entries:
        return 0

    from collections import Counter
    by_v = Counter(e.get("source_vertical") or "?" for e in entries)
    print("  per vertical:", dict(by_v.most_common()))

    if not execute:
        # Cost projection on the scoped count (title-dedup will trim it slightly).
        est_cost = (len(entries) / 1000.0) * COST_PER_1K_BATCHED
        print(f"\nProjected Batch-API cost (−50%, ~${COST_PER_1K_BATCHED}/1k): "
              f"~${est_cost:.2f} for {len(entries)} entries.")
        print("  (relevance on all; extraction+classify on the ~60-65% that pass relevance.)")
        print("  Note: actual run title-dedups first (reduces count slightly); Stage-5 dedup is local/free.")
        print("\nDRY-RUN — nothing submitted, no API cost. Re-run with --execute to classify.")
        return 0

    survivors = title_dedup(entries, commit=True)
    print(f"After title dedup: {len(survivors)} (filtered {len(entries) - len(survivors)})")

    # ---- Stage 2: relevance (batch) ----
    rel_items = [(str(e["id"]), p_relevance(e["title"] or "", e["excerpt"] or "")) for e in survivors]
    logger.info("Stage 2 relevance: %d requests", len(rel_items))
    rel = batch_over_chunks(rel_items, RelevanceResult, RELEVANCE_SYSTEM, ANTHROPIC_MODEL_CLASSIFY)
    keep = []
    for e in survivors:
        r = rel.get(str(e["id"]))
        if r is None or not r.is_relevant or r.confidence < RELEVANCE_THRESHOLD:
            mark_filtered(e["id"], "not_relevant" if r else "relevance_error")
            continue
        e["_relevance"] = r
        keep.append(e)
    survivors = keep
    logger.info("Stage 2 done: %d relevant", len(survivors))

    # ---- Stage 3: extraction (batch) ----
    ext_items = [(str(e["id"]), p_extraction(e["title"] or "", e["excerpt"] or "")) for e in survivors]
    ext = batch_over_chunks(ext_items, ExtractionResult, EXTRACTION_SYSTEM, ANTHROPIC_MODEL_CLASSIFY)
    for e in survivors:
        e["_extraction"] = ext.get(str(e["id"])) or ExtractionResult()

    # ---- Stage 4: classification (batch) ----
    cls_items = [(str(e["id"]), p_classification(e["title"] or "", e["excerpt"] or "", e["_extraction"]))
                 for e in survivors]
    cls = batch_over_chunks(cls_items, ClassificationResult, CLASSIFICATION_SYSTEM, ANTHROPIC_MODEL_CLASSIFY)
    keep = []
    for e in survivors:
        c = cls.get(str(e["id"]))
        if c is None:
            mark_filtered(e["id"], "classification_error")
            continue
        e["_classification"] = c
        keep.append(e)
    survivors = keep
    logger.info("Stage 4 done: %d classified", len(survivors))

    # ---- Stage 5: embeddings (batched) + dedup ----
    recent_vecs = [bytes_to_embedding(b) for _, b in get_recent_embeddings(days=30)]
    logger.info("Stage 5: %d recent embeddings for dedup", len(recent_vecs))
    batch_vecs: list[list[float]] = []
    keep = []
    for i in range(0, len(survivors), embed_chunk):
        chunk = survivors[i:i + embed_chunk]
        texts = [f"{e['title']}\n{(e['excerpt'] or '')[:500]}" for e in chunk]
        vecs = embed_batch(texts)
        for e, v in zip(chunk, vecs):
            if v is None:
                mark_filtered(e["id"], "embedding_error")
                continue
            dup = any(cosine_similarity(v, rv) > DUPLICATE_SIMILARITY_THRESHOLD
                      for rv in recent_vecs) or \
                  any(cosine_similarity(v, bv) > DUPLICATE_SIMILARITY_THRESHOLD for bv in batch_vecs)
            if dup:
                mark_filtered(e["id"], "duplicate: embedding")
                continue
            e["_embedding"] = v
            batch_vecs.append(v)
            keep.append(e)
        logger.info("  embedded %d/%d", min(i + embed_chunk, len(survivors)), len(survivors))
    survivors = keep
    logger.info("Stage 5 done: %d non-duplicate signals", len(survivors))

    # ---- Stage 7: insert signals ----
    created = 0
    for e in survivors:
        try:
            rel_r, ext_r, cls_r = e["_relevance"], e["_extraction"], e["_classification"]
            title = e["title"] or "(untitled signal)"
            trend_data = {
                "title_en": title,
                "title_de": None, "summary_en": None, "summary_de": None,
                "body_en": None, "body_de": None,
                "slug": f"{slugify(title, max_length=70)}-{e['id']}",
                "verticals": cls_r.verticals,
                "primary_vertical": cls_r.verticals[0] if cls_r.verticals else rel_r.primary_vertical,
                "pestel": cls_r.pestel, "tags": cls_r.tags,
                "trend_signal_type": cls_r.trend_signal_type,
                "mega_trend": cls_r.mega_trend, "trend_level": "micro",
                "brands": [ext_r.brand_name] if ext_r.brand_name else [],
                "regions": cls_r.regions,
                "trend_score": compute_crs(
                    confidence=rel_r.confidence, num_verticals=len(cls_r.verticals),
                    num_pestel=len(cls_r.pestel), signal_type=cls_r.trend_signal_type,
                    source_type=e.get("source_type")) / 100.0,
                "confidence": rel_r.confidence,
                "source_url": e["url"], "source_name": e.get("source_name", "Unknown"),
                "embedding": embedding_to_bytes(e["_embedding"]),
                "status": "signal",
            }
            insert_trend(e["id"], trend_data)
            mark_processed(e["id"])
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] insert error: %s", e["id"], exc)
            mark_processed(e["id"])
    print(f"\nDone in {time.time()-t0:.0f}s: {created} signals inserted "
          f"(from {len(entries)} entries).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = no limit (whole scope)")
    ap.add_argument("--verticals", help="only these source verticals (comma list)")
    ap.add_argument("--exclude-verticals", help="skip these source verticals (comma list)")
    ap.add_argument("--embed-chunk", type=int, default=64, help="texts per embedding request")
    ap.add_argument("--execute", action="store_true",
                    help="actually submit batches (costs money); default is dry-run")
    args = ap.parse_args()
    inc = [v.strip().upper() for v in args.verticals.split(",")] if args.verticals else []
    exc = [v.strip().upper() for v in args.exclude_verticals.split(",")] if args.exclude_verticals else []
    return run(args.limit, args.execute, args.embed_chunk, inc, exc)


if __name__ == "__main__":
    raise SystemExit(main())
