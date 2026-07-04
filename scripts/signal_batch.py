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
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import numpy as np
from slugify import slugify

from pipeline import anthropic_client, ollama_client, llamacpp_client
from pipeline.config import (
    ANTHROPIC_MODEL_CLASSIFY, RELEVANCE_THRESHOLD, DUPLICATE_SIMILARITY_THRESHOLD,
    EMBED_BACKEND, EMBED_MODEL, MODEL_EMBEDDING, STAGE_8B_MODEL,
)
from pipeline.llamacpp_client import LLAMACPP_HOST
from pipeline.crs import compute_crs
from pipeline.db import (
    get_connection, get_recent_titles, get_recent_embeddings,
    mark_filtered, mark_processed, insert_trend,
)
from pipeline.llm_processor import (
    RELEVANCE_SYSTEM, EXTRACTION_SYSTEM, CLASSIFICATION_SYSTEM, is_advertorial,
    normalize_title, embedding_to_bytes,
)
from pipeline.models import RelevanceResultSlim, ExtractionResult, ClassificationResult

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


def assert_local_classify_model() -> None:
    """Fail fast if :8090 isn't serving the expected 8B classify model.

    A GPU-handover restore bug once left the embedding server (start-qwen3-emb.sh)
    on :8090; a full 63k-entry run then crawled ~10h at 15 req/min — every request
    failed schema validation against an embedding endpoint — before anyone noticed.
    Verify the loaded model id matches STAGE_8B_MODEL before firing tens of
    thousands of requests at it."""
    try:
        r = httpx.get(f"{LLAMACPP_HOST}/v1/models", timeout=10)
        r.raise_for_status()
        loaded = [m.get("id", "") for m in r.json().get("data", [])]
    except Exception as e:
        raise SystemExit(
            f"backend=local: llama-server at {LLAMACPP_HOST} unreachable ({e}). "
            f"Start the 208k classifier (start-qwen3-8b-208k.sh) first.")
    want = STAGE_8B_MODEL
    if not any(m == want or Path(m).name == want for m in loaded):
        raise SystemExit(
            f"backend=local: :8090 serves {loaded or '[]'}, expected '{want}'. "
            f"The GPU-handover symlink likely points to the wrong model "
            f"(e.g. start-qwen3-emb.sh). Repoint start-active.sh -> "
            f"start-qwen3-8b-208k.sh and restart llama-server.service, then re-run.")
    logger.info("Preflight OK: :8090 serves the expected classifier (%s)", want)


def local_classify(items: list[tuple[str, str]], schema, system, workers: int) -> dict:
    """Classify concurrently against the local llama-server (port 8090) with a
    thread pool — exploits the server's parallel slots. Drop-in for batch_classify;
    same {custom_id: schema-instance | None} contract."""
    out: dict = {}
    done = 0

    def one(item):
        cid, prompt = item
        return cid, llamacpp_client.chat_structured(
            model=STAGE_8B_MODEL, prompt=prompt, schema=schema,
            system=system, temperature=0.0)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for cid, res in ex.map(one, items):
            out[cid] = res
            done += 1
            if done % 500 == 0:
                logger.info("  local classify %d/%d (%.0f req/min)",
                            done, len(items), done / (time.time() - t0) * 60)
    return out


def classify_stage(items, schema, system, backend: str, workers: int) -> dict:
    """Run a classification stage via the chosen backend (anthropic batch | local)."""
    if backend == "local":
        return local_classify(items, schema, system, workers)
    return batch_over_chunks(items, schema, system, ANTHROPIC_MODEL_CLASSIFY)


LLAMA_UNIT = "llama-server.service"
MIN_FREE_VRAM_MIB = 8000


def free_vram_for_embeddings() -> bool:
    """Free GPU for the local embedding stage iff VRAM is too tight. Stops the
    systemd llama-server.service AND any manually-started build/bin/llama-server
    (the parallel 8B classifier used by backend=local holds ~22 GB). Returns True
    if something was stopped (caller restarts the systemd unit afterwards)."""
    if EMBED_BACKEND != "ollama":
        return False
    try:
        free = int(subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            text=True).strip().splitlines()[0])
    except Exception:
        return False
    if free >= MIN_FREE_VRAM_MIB:
        return False
    logger.info("Stage 5: freeing VRAM for embeddings (free=%d MiB)", free)
    subprocess.run(["systemctl", "--user", "stop", LLAMA_UNIT])
    subprocess.run(["pkill", "-f", "build/bin/llama-server"])  # manual parallel 8B
    time.sleep(6)
    return True


def restart_llama() -> None:
    logger.info("Stage 5 done: restarting %s", LLAMA_UNIT)
    subprocess.run(["systemctl", "--user", "start", LLAMA_UNIT])


def _norm_rows(M: np.ndarray) -> np.ndarray:
    """L2-normalize each row so a dot product equals cosine similarity. Zero rows
    are left as zeros (→ cosine 0), matching the old cosine_similarity contract."""
    n = np.linalg.norm(M, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return M / n


def pull_unprocessed(limit: int, include: list[str], exclude: list[str],
                     min_id: int = 0, source_type: str = "") -> list[dict]:
    """Unprocessed entries, optionally scoped by source vertical (include/exclude),
    by source_type (e.g. 'api' = the funding ingests only), and to id > min_id
    (to classify only a fresh ingest, not older backlog)."""
    where = ["re.processed = FALSE", "re.filtered_out = FALSE"]
    params: list = []
    if source_type:
        where.append("s.source_type = ?")
        params.append(source_type)
    if min_id:
        where.append("re.id > ?")
        params.append(min_id)
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
        # Deterministic advertorial guard (paid placement, not a signal)
        if is_advertorial(e["title"] or "", e.get("excerpt") or ""):
            if commit:
                mark_filtered(e["id"], "sponsored/advertorial")
            continue
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
        include: list[str], exclude: list[str],
        backend: str = "anthropic", workers: int = 24, min_id: int = 0,
        source_type: str = "") -> int:
    t0 = time.time()
    entries = pull_unprocessed(limit, include, exclude, min_id, source_type)
    scope = (f"include={include}" if include else "") + (f" exclude={exclude}" if exclude else "") \
            + (f" source_type={source_type}" if source_type else "")
    print(f"Unprocessed in scope ({scope or 'ALL'}): {len(entries)}")
    if not entries:
        return 0

    from collections import Counter
    by_v = Counter(e.get("source_vertical") or "?" for e in entries)
    print("  per vertical:", dict(by_v.most_common()))

    if not execute:
        if backend == "local":
            print("\nbackend=local (llama.cpp :8090) — $0, ~165 req/min/stage at saturation.")
        else:
            est_cost = (len(entries) / 1000.0) * COST_PER_1K_BATCHED
            print(f"\nProjected Batch-API cost (−50%, ~${COST_PER_1K_BATCHED}/1k): ~${est_cost:.2f} for {len(entries)} entries.")
        print("  (relevance on all; extraction+classify on the ~60-65% that pass relevance.)")
        print("  Note: actual run title-dedups first; Stage-5 dedup is local/free.")
        print("\nDRY-RUN — nothing submitted. Re-run with --execute to classify.")
        return 0

    if backend == "local":
        assert_local_classify_model()

    survivors = title_dedup(entries, commit=True)
    print(f"After title dedup: {len(survivors)} (filtered {len(entries) - len(survivors)})")

    # ---- Stage 2: relevance (batch) ----
    rel_items = [(str(e["id"]), p_relevance(e["title"] or "", e["excerpt"] or "")) for e in survivors]
    logger.info("Stage 2 relevance: %d requests (backend=%s)", len(rel_items), backend)
    rel = classify_stage(rel_items, RelevanceResultSlim, RELEVANCE_SYSTEM, backend, workers)
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
    logger.info("Stage 3 extraction: %d requests", len(ext_items))
    ext = classify_stage(ext_items, ExtractionResult, EXTRACTION_SYSTEM, backend, workers)
    for e in survivors:
        e["_extraction"] = ext.get(str(e["id"])) or ExtractionResult()

    # ---- Stage 4: classification (batch) ----
    cls_items = [(str(e["id"]), p_classification(e["title"] or "", e["excerpt"] or "", e["_extraction"]))
                 for e in survivors]
    logger.info("Stage 4 classification: %d requests", len(cls_items))
    cls = classify_stage(cls_items, ClassificationResult, CLASSIFICATION_SYSTEM, backend, workers)
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

    # ---- Stage 5: embeddings (batched) + dedup (numpy-vectorized) ----
    # Cosine via L2-normalized dot products done as matrix multiplies (BLAS): each
    # embedding batch is compared against the recent-30d matrix and the running
    # kept matrix in one matmul, instead of the old O(n^2) per-pair Python loop
    # that hangs at 10k+. Identical threshold/semantics; just feasible at scale.
    # Load recent embeddings straight into a numpy matrix via np.frombuffer — NOT as
    # Python float-lists (bytes_to_embedding). At ~290k recent embeddings the
    # list-of-lists ballooned to ~38 GB and OOM-killed the run (FASHION, 2026-06-28);
    # frombuffer into a preallocated matrix is ~290k*4096*4 ≈ 5 GB.
    _recent = get_recent_embeddings(days=30)
    logger.info("Stage 5: %d recent embeddings for dedup", len(_recent))
    if _recent:
        _dim = len(_recent[0][1]) // 4
        R = np.empty((len(_recent), _dim), dtype=np.float32)
        for _i, (_, _b) in enumerate(_recent):
            R[_i] = np.frombuffer(_b, dtype=np.float32)
        R = _norm_rows(R)
    else:
        R = None
    thr = DUPLICATE_SIMILARITY_THRESHOLD

    _llama_stopped = free_vram_for_embeddings()  # GPU only needed from here on
    kept_buf: np.ndarray | None = None  # preallocated (len(survivors) x dim), filled in place
    kept_count = 0
    keep = []
    for i in range(0, len(survivors), embed_chunk):
        chunk = survivors[i:i + embed_chunk]
        texts = [f"{e['title']}\n{(e['excerpt'] or '')[:500]}" for e in chunk]
        vecs = embed_batch(texts)
        valid = []
        for e, v in zip(chunk, vecs):
            if v is None:
                mark_filtered(e["id"], "embedding_error")
            else:
                valid.append((e, v))
        if not valid:
            continue
        Bn = _norm_rows(np.asarray([v for _, v in valid], dtype=np.float32))  # (m, dim)
        if kept_buf is None:
            kept_buf = np.empty((len(survivors), Bn.shape[1]), dtype=np.float32)
        rec_max = (Bn @ R.T).max(axis=1) if R is not None and R.shape[0] else np.zeros(len(valid))
        prev_max = ((Bn @ kept_buf[:kept_count].T).max(axis=1)
                    if kept_count else np.zeros(len(valid)))
        chunk_start = kept_count
        for j, (e, v) in enumerate(valid):
            is_dup = rec_max[j] > thr or prev_max[j] > thr
            if not is_dup and kept_count > chunk_start:  # vs vectors kept earlier in THIS chunk
                if float((kept_buf[chunk_start:kept_count] @ Bn[j]).max()) > thr:
                    is_dup = True
            if is_dup:
                mark_filtered(e["id"], "duplicate: embedding")
                continue
            e["_embedding"] = v          # store the ORIGINAL (unnormalized) vector
            kept_buf[kept_count] = Bn[j]
            kept_count += 1
            keep.append(e)
        logger.info("  embedded %d/%d (kept %d)", min(i + embed_chunk, len(survivors)),
                    len(survivors), kept_count)
    survivors = keep
    logger.info("Stage 5 done: %d non-duplicate signals", len(survivors))
    if _llama_stopped:
        restart_llama()

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


def _distill_signal_type(e: dict) -> str:
    """Deterministic trend_signal_type from the source (distill heads don't emit
    it). Mirrors the lead-time tier map — patents/preprints/funding are the
    early-tier signals that matter most for foresight."""
    st = (e.get("source_type") or "").lower()
    sn = (e.get("source_name") or "").lower()
    if e.get("pub_number"):
        return "patent"
    if st == "research" or any(m in sn for m in ("arxiv", "rxiv", "preprint")):
        return "research"
    if st == "api" and any(m in sn for m in ("nsf", "nih", "reporter", "openaire", "ukri", "form d")):
        return "funding"
    return "market_shift"


def run_distill(limit: int, execute: bool, embed_chunk: int,
                include: list[str], exclude: list[str], workers: int = 24,
                min_id: int = 0, source_type: str = "",
                relevance_threshold: float = 0.5) -> int:
    """Mass-ingest classification WITHOUT the LLM: embed each survivor, then run
    the distilled heads (pipeline/distill) for relevance/vertical/mega/PESTEL.
    ~0 marginal cost per item; the only GPU step is the shared embedding pass.
    Taxonomy-bounded — novelty stays with the discovery loop."""
    from pipeline.distill import DistillClassifier
    t0 = time.time()
    try:
        clf = DistillClassifier.load()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 2
    print(f"distill heads: {clf.meta['heads']} | relevance head: {clf.has_relevance_head}")
    if not clf.has_relevance_head:
        print("  WARNING: no relevance head — every embedded, non-duplicate entry is "
              "kept as a signal (train it via embed_filtered.py + train_distill_heads.py).")

    entries = pull_unprocessed(limit, include, exclude, min_id, source_type)
    print(f"Unprocessed in scope: {len(entries)}")
    if not entries:
        return 0
    if not execute:
        print(f"\nDRY-RUN (backend=distill) — would embed + distill-classify {len(entries)} "
              "entries at ~0 cost. Re-run with --execute.")
        return 0

    survivors = title_dedup(entries, commit=True)
    print(f"After title dedup: {len(survivors)}")

    # ---- embed + distill-classify + vectorized dedup (single pass) ----
    _recent = get_recent_embeddings(days=30)
    R = None
    if _recent:
        _dim = len(_recent[0][1]) // 4
        R = np.empty((len(_recent), _dim), dtype=np.float32)
        for _i, (_, _b) in enumerate(_recent):
            R[_i] = np.frombuffer(_b, dtype=np.float32)
        R = _norm_rows(R)
    thr = DUPLICATE_SIMILARITY_THRESHOLD
    logger.info("distill: %d recent embeddings for dedup", len(_recent))

    _llama_stopped = free_vram_for_embeddings()
    kept_buf: np.ndarray | None = None
    kept_count = filtered = created = not_relevant = 0
    for i in range(0, len(survivors), embed_chunk):
        chunk = survivors[i:i + embed_chunk]
        texts = [f"{e['title']}\n{(e['excerpt'] or '')[:500]}" for e in chunk]
        vecs = embed_batch(texts)
        valid = [(e, v) for e, v in zip(chunk, vecs) if v is not None]
        for e, v in zip(chunk, vecs):
            if v is None:
                mark_filtered(e["id"], "embedding_error"); filtered += 1
        if not valid:
            continue
        B = np.asarray([v for _, v in valid], dtype=np.float32)
        Bn = _norm_rows(B)
        preds = clf.classify_batch(B)  # distill handles its own normalization
        if kept_buf is None:
            kept_buf = np.empty((len(survivors), Bn.shape[1]), dtype=np.float32)
        rec_max = (Bn @ R.T).max(axis=1) if R is not None and R.shape[0] else np.zeros(len(valid))
        prev_max = ((Bn @ kept_buf[:kept_count].T).max(axis=1)
                    if kept_count else np.zeros(len(valid)))
        chunk_start = kept_count
        for j, (e, v) in enumerate(valid):
            pred = preds[j]
            # relevance gate (only when the head exists)
            if pred["relevance"] is not None and pred["relevance"] < relevance_threshold:
                mark_filtered(e["id"], f"not_relevant_distill:{pred['relevance']:.2f}")
                not_relevant += 1
                continue
            is_dup = rec_max[j] > thr or prev_max[j] > thr
            if not is_dup and kept_count > chunk_start:
                if float((kept_buf[chunk_start:kept_count] @ Bn[j]).max()) > thr:
                    is_dup = True
            if is_dup:
                mark_filtered(e["id"], "duplicate: embedding"); filtered += 1
                continue
            kept_buf[kept_count] = Bn[j]
            kept_count += 1
            # insert as signal
            try:
                title = e["title"] or "(untitled signal)"
                vert = pred["primary_vertical"]
                conf = pred["relevance"] if pred["relevance"] is not None else pred["vertical_confidence"]
                sig_type = _distill_signal_type(e)
                insert_trend(e["id"], {
                    "title_en": title, "title_de": None, "summary_en": None,
                    "summary_de": None, "body_en": None, "body_de": None,
                    "slug": f"{slugify(title, max_length=70)}-{e['id']}",
                    "verticals": [vert], "primary_vertical": vert,
                    "pestel": pred["pestel"], "tags": [],
                    "trend_signal_type": sig_type, "mega_trend": pred["mega_trend"],
                    "trend_level": "micro", "brands": [], "regions": [],
                    "trend_score": compute_crs(
                        confidence=conf, num_verticals=1, num_pestel=len(pred["pestel"]),
                        signal_type=sig_type, source_type=e.get("source_type")) / 100.0,
                    "confidence": conf, "source_url": e["url"],
                    "source_name": e.get("source_name", "Unknown"),
                    "embedding": embedding_to_bytes(v), "status": "signal",
                })
                mark_processed(e["id"])
                created += 1
            except Exception as exc:  # noqa: BLE001
                logger.error("[%s] distill insert error: %s", e["id"], exc)
                mark_processed(e["id"])
        if (i // embed_chunk) % 20 == 0:
            logger.info("  distill %d/%d (kept %d, not_relevant %d)",
                        min(i + embed_chunk, len(survivors)), len(survivors), created, not_relevant)
    if _llama_stopped:
        restart_llama()
    print(f"\nDone in {time.time()-t0:.0f}s: {created} signals inserted, "
          f"{not_relevant} not-relevant, {filtered} filtered (from {len(entries)}).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = no limit (whole scope)")
    ap.add_argument("--verticals", help="only these source verticals (comma list)")
    ap.add_argument("--exclude-verticals", help="skip these source verticals (comma list)")
    ap.add_argument("--embed-chunk", type=int, default=64, help="texts per embedding request")
    ap.add_argument("--execute", action="store_true",
                    help="actually classify (Anthropic = costs money); default is dry-run")
    ap.add_argument("--backend", choices=["anthropic", "local", "distill"], default="anthropic",
                    help="local = concurrent llama.cpp :8090 ($0); anthropic = Message "
                         "Batches; distill = embedding heads, no LLM (mass backfill)")
    ap.add_argument("--relevance-threshold", type=float, default=0.5,
                    help="distill backend: min relevance-head prob to keep (if head trained)")
    ap.add_argument("--workers", type=int, default=24, help="local backend concurrency")
    ap.add_argument("--min-id", type=int, default=0,
                    help="only entries with id > MIN_ID — scope to a fresh ingest (e.g. patents)")
    ap.add_argument("--source-type", default="",
                    help="only sources of this source_type (e.g. 'api' = the funding ingests)")
    args = ap.parse_args()
    inc = [v.strip().upper() for v in args.verticals.split(",")] if args.verticals else []
    exc = [v.strip().upper() for v in args.exclude_verticals.split(",")] if args.exclude_verticals else []
    if args.backend == "distill":
        return run_distill(args.limit, args.execute, args.embed_chunk, inc, exc,
                           args.workers, args.min_id, args.source_type,
                           args.relevance_threshold)
    return run(args.limit, args.execute, args.embed_chunk, inc, exc,
               args.backend, args.workers, args.min_id, args.source_type)


if __name__ == "__main__":
    raise SystemExit(main())
