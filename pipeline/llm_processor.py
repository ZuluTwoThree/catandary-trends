#!/usr/bin/env python3
"""LLM Processing Pipeline for Catandary Trends.

Processes raw RSS entries through:
1. Title Dedup (no LLM)
2. Relevance Filter (Qwen3 8B)
3. Structured Extraction (Qwen3 8B)
4. NER + Classification (Qwen3 8B)
5. Embeddings + Dedup (Qwen3-Embedding)
6. Content Generation EN (Qwen3 14B)
7. Insert Trends
8. Reclassify Verticals (Qwen3 8B)
9. Auto-Publish (confidence >= 0.85)
"""

import json
import logging
import re
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import numpy as np
from rapidfuzz import fuzz
from math import sqrt

from slugify import slugify

from pipeline.config import (
    ANTHROPIC_MODEL_CLASSIFY,
    CLASSIFY_BACKEND,
    CLASSIFY_WORKERS,
    DUPLICATE_SIMILARITY_THRESHOLD,
    LOG_LEVEL,
    MODEL_CLASSIFY,
    MODEL_EMBEDDING,
    MODEL_EXTRACT,
    MODEL_FILTER,
    MODEL_GENERATE,
    EMBED_BACKEND,
    EMBED_MODEL,
    RELEVANCE_THRESHOLD,
    STAGE5_BACKEND,
    STAGE5_MIN_BODY_WORDS,
    STAGE5_MODEL,
    STAGE_8B_BACKEND,
    STAGE_8B_MODEL,
    get_mega_trend_prompt_block,
)
from pipeline.db import (
    get_recent_embeddings,
    get_recent_titles,
    get_unprocessed_entries,
    init_db,
    insert_trend,
    mark_filtered,
    mark_processed,
    save_stage_result,
)
from pipeline.models import (
    ClassificationResult,
    ExtractionResult,
    GeneratedContent,
    RelevanceResult,
)
from pipeline.auto_publisher import auto_publish
from pipeline.crs import compute_crs
from pipeline.ollama_client import chat_structured, generate_embedding
from pipeline import anthropic_client, gpu_handover, llamacpp_client
from pipeline.reclassify import reclassify_drafts

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# --- Prompts ---

RELEVANCE_SYSTEM = """\
You are a trend analyst for Catandary Trends, a cross-industry trend intelligence platform.
Your job is to determine if an RSS feed entry represents a relevant trend signal.

A relevant trend signal is:
- A new product launch, technology, research finding, or market shift
- A meaningful change in consumer behavior, regulation, or industry dynamics
- Something that indicates where an industry is heading

NOT relevant:
- Generic company earnings/quarterly results (unless they reveal a strategic shift)
- Routine personnel changes
- Opinion pieces without concrete data or developments
- Event announcements without substance
- Listicles or "top 10" without original insight"""

EXTRACTION_SYSTEM = """\
You are a precise information extractor. Extract ONLY information that is explicitly stated in the text.
Do not infer, guess, or add information. If something is not mentioned, leave it as null or empty."""

_CLASSIFICATION_SYSTEM_TEMPLATE = """\
You are a trend classifier for Catandary Trends, a cross-industry trend intelligence platform.

## Your task
Classify a single trend signal into the Catandary taxonomy. You must assign:
1. Verticals (1-3, first one is the primary)
2. PESTEL dimensions (1-3)
3. Tags (3-8, specific, lowercase)
4. Signal type
5. Regions
6. Mega-trend (exactly one from the canonical list below, or null if none fits)

## Verticals
- FOOD: Food & beverage, ingredients, restaurants, agriculture, nutrition science
- TECH: Technology, AI, software, hardware, robotics, IoT, biotech, quantum, materials science, R&D breakthroughs
- HEALTH: Clinical medicine, pharma drugs in trials/market, mental health, supplements, body physiology, healthcare delivery
- ECO: Sustainability, energy, climate, circular economy, packaging, environmental policy
- DESIGN: Architecture, product design, interiors, UX, urban planning
- FASHION: Apparel, beauty, cosmetics, textiles, jewelry (the products themselves)
- BIZ: Business strategy, retail, e-commerce, fintech, banking, payments, M&A, funding
- LIFESTYLE: Culture, media, entertainment, gaming, social impact, education, luxury experiences, travel, sport (athletes, events, communities, gym/studio culture, fitness as lifestyle)

## Disambiguation rules (CRITICAL — apply in order)
1. **Biotech, gene editing, synthetic biology, lab research → TECH** (not HEALTH). HEALTH is for clinical/patient-facing topics.
2. **AI/tech applied to a specific industry → that industry.** E.g. "AI for drug discovery" = HEALTH, "AI chip architecture" = TECH.
3. **Fintech, payments, banking, crypto finance → BIZ** (not TECH), unless it's about the underlying tech stack.
4. **Sustainable materials for a specific industry → that industry.** E.g. bio-textiles = FASHION, compostable food packaging = FOOD.
5. **Sustainability as the core topic → ECO** (carbon credits, circular economy policy, renewables).
6. **M&A, funding rounds, IPOs, earnings → BIZ**, unless the deal only makes sense within one vertical.
7. **Scientific research papers (biology, chemistry, physics) → TECH**, unless clearly clinical/patient-focused.
8. **Sport & fitness routing:**
   - Athletes, sport events, sport communities, gyms/studios as lifestyle, fitness culture → LIFESTYLE
   - Clinical/physiological wellness, supplements, body health, medical aspects of fitness → HEALTH
   - Sport apparel, footwear, athleisure → FASHION
   - Sport business, M&A, brand strategy → BIZ
   - Sport architecture, stadiums, facility design → DESIGN
   - Sport nutrition products → FOOD
   - Sport wearables / biometrics tech itself → TECH
9. **Most trends belong to ONE primary vertical.** Only add secondaries when the trend genuinely cannot be understood without two industries.

## Vertical classification examples
- "CRISPR Advances Enable Faster Gene Editing in Crops" → verticals: ["TECH", "FOOD"]
- "New Alzheimer's Drug Shows Promise in Phase 3 Trial" → verticals: ["HEALTH"]
- "Stripe Launches Embedded Banking for SMBs" → verticals: ["BIZ"]
- "LVMH Acquires Luxury Watchmaker in 2B Deal" → verticals: ["BIZ", "FASHION"]
- "Bacterial Flagellar Adaptation Reveals Evolutionary Mechanism" → verticals: ["TECH"]
- "Biodegradable Packaging for Fresh Produce Hits Shelves" → verticals: ["FOOD", "ECO"]
- "Quantum Computing Breakthrough in Drug Discovery" → verticals: ["TECH", "HEALTH"]
- "Hyrox Expands Reach Through Strategic Tech Partnership" → verticals: ["LIFESTYLE"]
- "Nike's Retreat from Physical Fitness Spaces Signals Brand Strategy Shift" → verticals: ["BIZ"]

## PESTEL dimensions
P (Political), E (Economic), S (Social), T (Technological), En (Environmental), L (Legal)

## Signal types
product_launch, research, market_shift, consumer_behavior, regulation, funding, partnership, patent

## Mega-trend assignment rules

A mega-trend is a structural shift with a 10-25 year time horizon that is NOT dependent on a single \
company, technology, or product. It describes WHERE an entire industry or society is heading.

Pick exactly one mega-trend from this canonical list. If the trend signal does not clearly fit any \
mega-trend, set mega_trend to null — do NOT invent new mega-trend names.

To decide which mega-trend fits, ask yourself: "If I removed this structural shift from the world, \
would this trend signal still exist?" If the answer is no, that is the correct mega-trend.

### Canonical mega-trends:
{mega_trend_block}

## Important
- Use ONLY keys from the canonical mega-trend list above. Never invent new mega-trend names.
- A product launch can still map to a mega-trend if it is a manifestation of that structural shift.
- When in doubt between two mega-trends, pick the one that describes the deeper structural driver."""


def _build_classification_system() -> str:
    """Build the classification system prompt with current mega-trend taxonomy."""
    return _CLASSIFICATION_SYSTEM_TEMPLATE.format(
        mega_trend_block=get_mega_trend_prompt_block()
    )


# Built once at import time; rebuilt if mega_trends.yaml changes (restart required)
CLASSIFICATION_SYSTEM = _build_classification_system()

CONTENT_EN_SYSTEM = """\
You are a trend analyst writing for Catandary Trends. Write a sharp, specific trend article in English (150-250 words).

Voice:
- Lead with the concrete fact: who did what, the number, the product, the filing, the company. Use specifics from the source, not abstractions.
- Plain declarative sentences. Vary how each sentence opens — never start two sentences the same way.
- Analytical, not promotional. Explain the mechanism (why it works, what concretely changes), not vague significance.
- Substantially reworded from the source; never copy its phrasing.
- Close with a concrete, falsifiable consequence — not a generic forecast.

BANNED — never use these filler phrases or any close variant. They are the reason most AI articles read identically:
- Template openers: "Looking ahead…", "This trend/shift/development/move signals/underscores/reflects/highlights…", "The era of…", "The rise of…", "Companies that fail…"
- Filler verbs/phrases: "underscores", "signals a shift/move", "highlights a/the/its growing", "reflects a broader", "aligns with", "marks a significant", "paving the way", "plays a crucial/key role", "stands to", "continues to evolve", "positions … as a"
- Empty endings: "in the coming years", "the years to come", "in the digital age", "on a global scale", "a competitive edge", "competitive landscape", "key differentiator", "growing need/demand for", "broader industry shift toward"
- Empty intensifiers: "it's worth noting", "increasingly", "rapidly evolving", "ever-changing", "in today's world"

Test every sentence: if it could open an article in any other industry, delete it and write the specific detail instead. Write the article, not a template."""


# Data-driven cliché guard: the phrases below were the highest-frequency fillers
# across the published corpus (e.g. "underscores"/"signals a shift"/"highlights"
# each in ~45-48% of bodies, "looking ahead" opening ~8k paragraphs). The content
# guard rejects any body/summary containing them so the model retries with cleaner
# prose. (chat_structured returns the last attempt anyway, so a stubborn case never
# loses the entry — it just isn't blocked.)
_CLICHE_RE = re.compile(
    r"\b("
    r"looking ahead|underscore|signals? a (shift|move|broader|growing|new)|"
    r"highlight(s|ing) (a|an|the|its|growing|broader|emerging)|"
    r"reflects? a (broader|growing|significant|fundamental|larger)|aligns? with|"
    r"marks? a (significant|pivotal|major|new|key)|pav(e|es|ing) the way|"
    r"plays? a (crucial|key|pivotal|critical|significant|vital) role|the era of|"
    r"stands? to (benefit|gain|reshape|transform|capitalize)|continues? to evolve|"
    r"positions? .{0,30} as a|in the coming years|years to come|in the digital age|"
    r"on a global scale|competitive (edge|landscape)|key differentiator|"
    r"growing (need|demand|emphasis) for|broader (industry |market )?(shift|move|trend) toward|"
    r"it'?s worth noting|ever[- ](changing|evolving)|in today'?s world"
    r")\b", re.IGNORECASE)


def content_is_clean(c: "GeneratedContent") -> bool:
    """Content guard. Retries only on AI slop or a broken body — NOT on brevity:
    a short, complete, cliché-free article is accepted as-is (clear short text
    beats slop + wasted retries). Rejects only (a) a near-empty stub (garbage
    floor), (b) a body cut off mid-sentence (no terminal punctuation), or
    (c) banned cliché phrases."""
    body = c.body.strip()
    if len(body.split()) < STAGE5_MIN_BODY_WORDS:
        return False                                   # near-empty stub = real failure
    if not body.endswith((".", "!", "?", '"', "”")):   # cut off mid-sentence → retry
        return False
    return not _CLICHE_RE.search(f"{c.body}\n{c.summary}")


def embedding_to_bytes(embedding: list[float]) -> bytes:
    """Pack a float list into bytes for storage."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def bytes_to_embedding(data: bytes) -> list[float]:
    """Unpack bytes back to float list."""
    n = len(data) // 4
    return list(struct.unpack(f"{n}f", data))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _norm_rows(M: np.ndarray) -> np.ndarray:
    """L2-normalize matrix rows so a dot product equals cosine similarity."""
    M = np.asarray(M, dtype=np.float32)
    if M.ndim == 1:
        M = M.reshape(1, -1)
    n = np.linalg.norm(M, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return M / n


def _concurrent(fn, items, workers=CLASSIFY_WORKERS):
    """Map fn over items, concurrently when workers>1. The step_* LLM calls are
    pure (no DB writes), so dispatching them across the llama-server's parallel
    slots is safe; results come back in input order. workers=0/1 → sequential."""
    if workers and workers > 1 and len(items) > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(fn, items))
    return [fn(x) for x in items]


def step_relevance_filter(title: str, excerpt: str, source_vertical: str) -> RelevanceResult | None:
    """Step 1: Determine if the entry is a relevant trend signal."""
    prompt = f"""Analyze this RSS feed entry and determine if it's a relevant trend signal.
Classify the vertical based purely on the content, not on where the source comes from.

Title: {title}

Excerpt: {excerpt[:1500]}"""

    if CLASSIFY_BACKEND == "anthropic":
        return anthropic_client.chat_structured(
            model=ANTHROPIC_MODEL_CLASSIFY,
            prompt=prompt,
            schema=RelevanceResult,
            system=RELEVANCE_SYSTEM,
            temperature=0.0,
        )

    if STAGE_8B_BACKEND == "llamacpp":
        return llamacpp_client.chat_structured(
            model=STAGE_8B_MODEL,
            prompt=prompt,
            schema=RelevanceResult,
            system=RELEVANCE_SYSTEM,
            temperature=0.0,
        )

    return chat_structured(
        model=MODEL_FILTER,
        prompt=prompt,
        schema=RelevanceResult,
        system=RELEVANCE_SYSTEM,
        temperature=0.0,
        fallback_model="qwen3:8b",
    )


def step_extraction(title: str, excerpt: str) -> ExtractionResult | None:
    """Step 2: Extract structured data from the entry."""
    prompt = f"""Extract structured information from this text.

Title: {title}

Text: {excerpt[:1500]}"""

    # Effective model after the NuExtract→qwen3:8b fallback (NuExtract disabled).
    resolved_model = MODEL_EXTRACT if MODEL_EXTRACT != "nuextract" else "qwen3:8b"

    if CLASSIFY_BACKEND == "anthropic":
        return anthropic_client.chat_structured(
            model=ANTHROPIC_MODEL_CLASSIFY,
            prompt=prompt,
            schema=ExtractionResult,
            system=EXTRACTION_SYSTEM,
            temperature=0.0,
        )

    if STAGE_8B_BACKEND == "llamacpp" and resolved_model == "qwen3:8b":
        return llamacpp_client.chat_structured(
            model=STAGE_8B_MODEL,
            prompt=prompt,
            schema=ExtractionResult,
            system=EXTRACTION_SYSTEM,
            temperature=0.0,
        )

    return chat_structured(
        model=resolved_model,
        prompt=prompt,
        schema=ExtractionResult,
        system=EXTRACTION_SYSTEM,
        temperature=0.0,
        fallback_model="qwen3:8b",
    )


def step_classification(title: str, excerpt: str, extraction: ExtractionResult) -> ClassificationResult | None:
    """Step 3: NER + Classification."""
    prompt = f"""Classify this trend signal.

Title: {title}
Excerpt: {excerpt[:1000]}
Brand: {extraction.brand_name or 'Unknown'}
Product: {extraction.product_name or 'Unknown'}
Key Claims: {', '.join(extraction.key_claims[:5]) if extraction.key_claims else 'None'}"""

    if CLASSIFY_BACKEND == "anthropic":
        return anthropic_client.chat_structured(
            model=ANTHROPIC_MODEL_CLASSIFY,
            prompt=prompt,
            schema=ClassificationResult,
            system=CLASSIFICATION_SYSTEM,
            temperature=0.0,
        )

    if STAGE_8B_BACKEND == "llamacpp":
        return llamacpp_client.chat_structured(
            model=STAGE_8B_MODEL,
            prompt=prompt,
            schema=ClassificationResult,
            system=CLASSIFICATION_SYSTEM,
            temperature=0.0,
        )

    return chat_structured(
        model=MODEL_CLASSIFY,
        prompt=prompt,
        schema=ClassificationResult,
        system=CLASSIFICATION_SYSTEM,
        temperature=0.0,
        fallback_model="qwen3:8b",
    )


def step_dedup_check(title: str, excerpt: str) -> tuple[bool, float, list[float] | None]:
    """Step 4: Check for duplicates using embeddings.

    Returns (is_duplicate, max_similarity, embedding).
    """
    text = f"{title}\n{excerpt[:500]}"
    if EMBED_BACKEND == "llamacpp":
        embedding = llamacpp_client.generate_embedding(text, model=EMBED_MODEL)
    else:
        embedding = generate_embedding(MODEL_EMBEDDING, text)
    if embedding is None:
        return False, 0.0, None

    recent = get_recent_embeddings(days=30)
    max_sim = 0.0
    for _, stored_bytes in recent:
        stored = bytes_to_embedding(stored_bytes)
        sim = cosine_similarity(embedding, stored)
        max_sim = max(max_sim, sim)
        if sim > DUPLICATE_SIMILARITY_THRESHOLD:
            return True, sim, embedding

    return False, max_sim, embedding


def step_generate_content_en(title: str, excerpt: str, extraction: ExtractionResult,
                              classification: ClassificationResult,
                              source_url: str, source_name: str) -> GeneratedContent | None:
    """Step 5: Generate English trend article."""
    context = f"""Original Title: {title}
Original Excerpt: {excerpt[:1000]}
Brand: {extraction.brand_name or 'Unknown'}
Product: {extraction.product_name or 'Unknown'}
Key Claims: {', '.join(extraction.key_claims[:5]) if extraction.key_claims else 'N/A'}
Verticals: {', '.join(classification.verticals)}
PESTEL: {', '.join(classification.pestel)}
Signal Type: {classification.trend_signal_type}
Mega Trend: {classification.mega_trend or 'N/A'}
Source: {source_name} ({source_url})"""

    prompt_en = f"""Write a trend article in English based on this information.

{context}

"""

    if STAGE5_BACKEND == "llamacpp":
        # Route content gen to llama-server (GPU handover managed by the caller).
        # The word-count guard retries on premature grammar string-termination.
        return llamacpp_client.chat_structured(
            model=STAGE5_MODEL,
            prompt=prompt_en,
            schema=GeneratedContent,
            system=CONTENT_EN_SYSTEM,
            temperature=0.7,
            validate=content_is_clean,
        )

    return chat_structured(
        model=MODEL_GENERATE,
        prompt=prompt_en,
        schema=GeneratedContent,
        system=CONTENT_EN_SYSTEM,
        temperature=0.7,
    )




# --- Title-level dedup helpers ---

_TITLE_NORMALIZE_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = _TITLE_NORMALIZE_RE.sub(" ", (title or "").lower())
    return " ".join(t.split())


def is_title_duplicate(title: str, existing_norm: list[str], threshold: float = 0.90) -> tuple[bool, float]:
    """Return (is_dup, best_similarity) via length-prefiltered rapidfuzz ratio.

    rapidfuzz.fuzz.ratio (C backend, ~50-100x faster than difflib) matches
    SequenceMatcher.ratio to 3 decimals in the >=0.90 range that matters here;
    score_cutoff lets the C side short-circuit comparisons below threshold.
    """
    norm = normalize_title(title)
    if not norm:
        return False, 0.0
    best = 0.0
    nlen = len(norm)
    cutoff = threshold * 100.0
    for other in existing_norm:
        olen = len(other)
        if olen == 0:
            continue
        # Length prefilter: skip if lengths differ by >40%
        if min(nlen, olen) / max(nlen, olen) < 0.6:
            continue
        sim = fuzz.ratio(norm, other, score_cutoff=cutoff) / 100.0
        if sim >= threshold:
            return True, sim
        if sim > best:
            best = sim
    return False, best


def process_entry(entry: dict) -> dict | None:
    """Process a single raw entry through the full LLM pipeline.

    Returns the trend data dict or None if filtered/duplicate.
    """
    entry_id = entry["id"]
    title = entry["title"]
    excerpt = entry["excerpt"] or ""
    source_vertical = entry.get("source_vertical", "TECH")
    source_name = entry.get("source_name", "Unknown")
    source_url = entry["url"]

    logger.info("Processing [%d]: %s", entry_id, title[:80])
    t0 = time.time()

    # Step 1: Relevance Filter
    relevance = step_relevance_filter(title, excerpt, source_vertical)
    if relevance is None:
        logger.warning("[%d] Relevance filter returned None, skipping", entry_id)
        mark_filtered(entry_id, "relevance_filter_error")
        return None

    if not relevance.is_relevant or relevance.confidence < RELEVANCE_THRESHOLD:
        logger.info("[%d] Filtered out: %s (conf=%.2f)", entry_id, relevance.reason, relevance.confidence)
        mark_filtered(entry_id, f"not_relevant: {relevance.reason}")
        return None

    logger.info("[%d] Relevant (conf=%.2f, vertical=%s)", entry_id, relevance.confidence, relevance.primary_vertical)

    # Step 2: Structured Extraction
    extraction = step_extraction(title, excerpt)
    if extraction is None:
        logger.warning("[%d] Extraction failed, using defaults", entry_id)
        extraction = ExtractionResult()

    logger.info("[%d] Extracted: brand=%s, product=%s", entry_id, extraction.brand_name, extraction.product_name)

    # Step 3: NER + Classification
    classification = step_classification(title, excerpt, extraction)
    if classification is None:
        logger.warning("[%d] Classification failed, skipping", entry_id)
        mark_filtered(entry_id, "classification_error")
        return None

    logger.info("[%d] Classified: verticals=%s, pestel=%s, type=%s",
                entry_id, classification.verticals, classification.pestel, classification.trend_signal_type)

    # Step 4: Duplicate Check
    is_dup, max_sim, embedding = step_dedup_check(title, excerpt)
    if is_dup:
        logger.info("[%d] Duplicate detected (similarity=%.3f), skipping", entry_id, max_sim)
        mark_filtered(entry_id, f"duplicate: similarity={max_sim:.3f}")
        return None

    logger.info("[%d] Not duplicate (max_sim=%.3f)", entry_id, max_sim)

    # Step 5: Content Generation EN
    content_en = step_generate_content_en(
        title, excerpt, extraction, classification, source_url, source_name
    )

    if content_en is None:
        logger.warning("[%d] EN content generation failed", entry_id)
        mark_filtered(entry_id, "content_generation_error")
        return None

    # Build trend data — append entry_id to slug for uniqueness
    base_slug = slugify(content_en.title, max_length=70)
    slug = f"{base_slug}-{entry_id}"
    trend_data = {
        "title_en": content_en.title,
        "title_de": None,
        "slug": slug,
        "summary_en": content_en.summary,
        "summary_de": None,
        "body_en": content_en.body,
        "body_de": None,
        "verticals": classification.verticals,
        "primary_vertical": classification.verticals[0] if classification.verticals else relevance.primary_vertical,
        "pestel": classification.pestel,
        "tags": classification.tags,
        "trend_signal_type": classification.trend_signal_type,
        "mega_trend": classification.mega_trend,
        "trend_level": "micro",  # Default; macro/mega assigned later
        "brands": [extraction.brand_name] if extraction.brand_name else [],
        "regions": classification.regions,
        "trend_score": compute_crs(
            confidence=relevance.confidence,
            num_verticals=len(classification.verticals),
            num_pestel=len(classification.pestel),
            signal_type=classification.trend_signal_type,
            source_type=entry.get("source_type"),
        ) / 100.0,
        "confidence": relevance.confidence,
        "source_url": source_url,
        "source_name": source_name,
        "embedding": embedding_to_bytes(embedding) if embedding else None,
    }

    # Insert into DB
    trend_id = insert_trend(entry_id, trend_data)
    mark_processed(entry_id)

    elapsed = time.time() - t0
    logger.info("[%d] → Trend #%d created: '%s' (%.1fs)", entry_id, trend_id, content_en.title[:60], elapsed)

    return trend_data


def run_pipeline_batch(limit: int = 200, signal_mode: bool = False, min_id: int = 0):
    """Stage-by-stage batch pipeline.

    signal_mode=True skips Stage 6 (content generation), inserts content-less
    `status='signal'` rows (foresight signals, no public article), and skips the
    reclassify + auto-publish stages. Articles are generated later, decoupled, by
    scripts/generate_content.py (which promotes signal -> published). Used for the
    one-time historical backfill where classification runs on the Anthropic API.

    Minimizes model reloads by processing all surviving entries through one
    stage before moving to the next. Model load order: Qwen3 8B (stages 2-4)
    → Qwen3-Embedding (stage 5) → Qwen3 14B (stages 6-7).
    """
    start = time.time()
    init_db()

    entries = get_unprocessed_entries(limit=limit, min_id=min_id)
    logger.info("BATCH: loaded %d unprocessed entries (min_id=%d)", len(entries), min_id)
    if not entries:
        return {"processed": 0, "created": 0, "filtered": 0, "errors": 0}

    created = 0
    filtered = 0
    errors = 0

    # ---- Stage 1: Title dedup (no LLM) ----
    t_stage = time.time()
    existing_titles_norm = [normalize_title(t) for t in get_recent_titles(days=30)]
    logger.info("Stage 1 (title dedup): %d existing titles loaded", len(existing_titles_norm))

    survivors: list[dict] = []
    batch_titles_norm: list[str] = []
    for entry in entries:
        title = entry["title"] or ""
        is_dup, sim = is_title_duplicate(title, existing_titles_norm)
        if is_dup:
            mark_filtered(entry["id"], f"title_duplicate: sim={sim:.3f}")
            filtered += 1
            continue
        # Also check against intra-batch titles
        is_dup, sim = is_title_duplicate(title, batch_titles_norm)
        if is_dup:
            mark_filtered(entry["id"], f"title_duplicate_intra_batch: sim={sim:.3f}")
            filtered += 1
            continue
        batch_titles_norm.append(normalize_title(title))
        survivors.append(entry)
    logger.info("Stage 1 done in %.1fs: %d → %d (%d title dups)",
                time.time() - t_stage, len(entries), len(survivors), filtered)

    # ---- Stages 2-4: Relevance / Extraction / Classification (Qwen3 8B) ----
    # When STAGE_8B_BACKEND=llamacpp, swap the GPU to the 8B llama-server for
    # the duration of these three contiguous loops; restore the symlink on
    # exit so Stage 6's 35B handover finds start-active.sh as expected.
    gpu_ctx_8b = (gpu_handover.eight_b_on_llamacpp(STAGE_8B_MODEL)
                  if STAGE_8B_BACKEND == "llamacpp" and survivors
                  else nullcontext())
    with gpu_ctx_8b:
        # ---- Stage 2: Relevance filter (Qwen3 8B) ----
        t_stage = time.time()
        next_survivors = []
        cache_hits_stage2 = 0
        # Dispatch the LLM calls for uncached entries concurrently, then apply the
        # cache/save/filter logic sequentially (DB writes stay single-threaded).
        to_call = [e for e in survivors if not e.get("relevance_json")]
        rel_res = dict(zip((e["id"] for e in to_call), _concurrent(
            lambda e: step_relevance_filter(e["title"], e["excerpt"] or "", e.get("source_vertical", "TECH")), to_call)))
        for entry in survivors:
            try:
                cached = entry.get("relevance_json")
                if cached:
                    rel = RelevanceResult.model_validate_json(cached)
                    cache_hits_stage2 += 1
                else:
                    rel = rel_res.get(entry["id"])
                    if rel is not None:
                        save_stage_result(entry["id"], "relevance", rel)
                if rel is None:
                    mark_filtered(entry["id"], "relevance_filter_error")
                    filtered += 1
                    continue
                if not rel.is_relevant or rel.confidence < RELEVANCE_THRESHOLD:
                    mark_filtered(entry["id"], f"not_relevant: {rel.reason}")
                    filtered += 1
                    continue
                entry["_relevance"] = rel
                next_survivors.append(entry)
            except Exception as e:
                logger.error("[%d] relevance error: %s", entry["id"], e)
                mark_processed(entry["id"])
                errors += 1
        survivors = next_survivors
        logger.info("Stage 2 done in %.1fs: %d survivors (%d cache hits, workers=%d)",
                    time.time() - t_stage, len(survivors), cache_hits_stage2, CLASSIFY_WORKERS)

        # ---- Stage 3: Extraction (Qwen3 8B) ----
        t_stage = time.time()
        cache_hits_stage3 = 0
        to_call = [e for e in survivors if not e.get("extraction_json")]
        ext_res = dict(zip((e["id"] for e in to_call), _concurrent(
            lambda e: step_extraction(e["title"], e["excerpt"] or ""), to_call)))
        for entry in survivors:
            try:
                cached = entry.get("extraction_json")
                if cached:
                    entry["_extraction"] = ExtractionResult.model_validate_json(cached)
                    cache_hits_stage3 += 1
                else:
                    ext = ext_res.get(entry["id"]) or ExtractionResult()
                    save_stage_result(entry["id"], "extraction", ext)
                    entry["_extraction"] = ext
            except Exception as e:
                logger.error("[%d] extraction error: %s", entry["id"], e)
                entry["_extraction"] = ExtractionResult()
        logger.info("Stage 3 done in %.1fs (%d cache hits)", time.time() - t_stage, cache_hits_stage3)

        # ---- Stage 4: Classification (Qwen3 8B) ----
        t_stage = time.time()
        next_survivors = []
        cache_hits_stage4 = 0
        to_call = [e for e in survivors if not e.get("classification_json")]
        cls_res = dict(zip((e["id"] for e in to_call), _concurrent(
            lambda e: step_classification(e["title"], e["excerpt"] or "", e["_extraction"]), to_call)))
        for entry in survivors:
            try:
                cached = entry.get("classification_json")
                if cached:
                    cls = ClassificationResult.model_validate_json(cached)
                    cache_hits_stage4 += 1
                else:
                    cls = cls_res.get(entry["id"])
                    if cls is not None:
                        save_stage_result(entry["id"], "classification", cls)
                if cls is None:
                    mark_filtered(entry["id"], "classification_error")
                    filtered += 1
                    continue
                entry["_classification"] = cls
                next_survivors.append(entry)
            except Exception as e:
                logger.error("[%d] classification error: %s", entry["id"], e)
                mark_processed(entry["id"])
                errors += 1
        survivors = next_survivors
        logger.info("Stage 4 done in %.1fs: %d survivors (%d cache hits)",
                    time.time() - t_stage, len(survivors), cache_hits_stage4)

    # ---- Stage 5: Embeddings + dedup (load recent embeddings ONCE) ----
    # When EMBED_BACKEND=llamacpp, hand the GPU over to a llama-server in
    # --embedding mode for the duration of this loop only; restore the symlink
    # on exit so Stage 6's 35B handover finds start-active.sh as expected.
    t_stage = time.time()
    recent = get_recent_embeddings(days=30)
    recent_vecs = [bytes_to_embedding(b) for _, b in recent]
    logger.info("Stage 5: %d recent embeddings loaded", len(recent_vecs))

    next_survivors = []
    cache_hits_stage5 = 0
    needs_embed = any(not e.get("embedding_blob") for e in survivors)
    gpu_ctx_embed = (gpu_handover.embed_on_llamacpp(EMBED_MODEL)
                     if EMBED_BACKEND == "llamacpp" and needs_embed
                     else nullcontext())
    def _embed_one(text):
        return (llamacpp_client.generate_embedding(text, model=EMBED_MODEL)
                if EMBED_BACKEND == "llamacpp" else generate_embedding(MODEL_EMBEDDING, text))

    # Pass 1: resolve each survivor's embedding (cached or generated concurrently),
    # persist it, and drop embedding errors. Collect (entry, vec) for the dedup.
    embedded: list[tuple[dict, list[float]]] = []
    with gpu_ctx_embed:
        to_embed = [e for e in survivors if not e.get("embedding_blob")]
        emb_res = dict(zip((e["id"] for e in to_embed), _concurrent(
            lambda e: _embed_one(f"{e['title']}\n{(e['excerpt'] or '')[:500]}"), to_embed)))
        for entry in survivors:
            cached_emb = entry.get("embedding_blob")
            if cached_emb:
                emb = bytes_to_embedding(cached_emb)
                cache_hits_stage5 += 1
            else:
                emb = emb_res.get(entry["id"])
                if emb is not None:
                    save_stage_result(entry["id"], "embedding", embedding_to_bytes(emb))
            if emb is None:
                mark_filtered(entry["id"], "embedding_error")
                filtered += 1
                continue
            embedded.append((entry, emb))

    # Pass 2: vectorized dedup (numpy/BLAS) — replaces the O(n*recent) pure-Python
    # cosine loop that idled the GPU for ~hours once `recent` grew to ~28k. Each new
    # vector is checked against the recent set in one matmul and against the running
    # kept-buffer incrementally (so intra-batch near-duplicates are still caught).
    if embedded:
        thr = DUPLICATE_SIMILARITY_THRESHOLD
        R = _norm_rows(np.asarray(recent_vecs, dtype=np.float32)) if recent_vecs else None
        B = _norm_rows(np.asarray([e for _, e in embedded], dtype=np.float32))
        rec_max = ((B @ R.T).max(axis=1) if R is not None and R.shape[0]
                   else np.zeros(len(embedded), dtype=np.float32))
        kept_buf = np.empty_like(B)
        kept_count = 0
        for j, (entry, emb) in enumerate(embedded):
            v = B[j]
            max_sim = float(rec_max[j])
            is_dup = max_sim > thr
            if not is_dup and kept_count:
                kmax = float((kept_buf[:kept_count] @ v).max())
                max_sim = max(max_sim, kmax)
                is_dup = kmax > thr
            if is_dup:
                mark_filtered(entry["id"], f"duplicate: similarity={max_sim:.3f}")
                filtered += 1
                continue
            entry["_embedding"] = emb
            kept_buf[kept_count] = v
            kept_count += 1
            next_survivors.append(entry)
    survivors = next_survivors
    logger.info("Stage 5 done in %.1fs: %d survivors (%d cache hits)",
                time.time() - t_stage, len(survivors), cache_hits_stage5)

    # ---- Stage 6: Content generation EN (Qwen3 14B, or llama.cpp 35B) ----
    # Skipped in signal-mode: signals carry no public article. Content is
    # generated later (decoupled, local) by scripts/generate_content.py.
    if signal_mode:
        logger.info("Stage 6 skipped (signal-mode): %d signals, no content generation",
                    len(survivors))
    else:
        # When STAGE5_BACKEND=llamacpp, hand the GPU over to llama-server for the
        # duration of this contiguous loop only (Ollama VRAM is freed, then reloaded
        # on demand for Stage 8). All entries needing fresh generation run inside the
        # handover; fully-cached batches skip it (no survivors → no handover).
        t_stage = time.time()
        next_survivors = []
        total_stage6 = len(survivors)
        cache_hits_stage6 = 0
        needs_gen = any(not e.get("content_en_json") for e in survivors)
        gpu_ctx = (gpu_handover.content_gen_on_llamacpp(STAGE5_MODEL)
                   if STAGE5_BACKEND == "llamacpp" and needs_gen
                   else nullcontext())
        with gpu_ctx:
            for i, entry in enumerate(survivors, 1):
                try:
                    cached = entry.get("content_en_json")
                    if cached:
                        en = GeneratedContent.model_validate_json(cached)
                        cache_hits_stage6 += 1
                    else:
                        en = step_generate_content_en(
                            entry["title"], entry["excerpt"] or "",
                            entry["_extraction"], entry["_classification"],
                            entry["url"], entry.get("source_name", "Unknown"),
                        )
                        if en is not None:
                            save_stage_result(entry["id"], "content_en", en)
                    if en is None:
                        mark_filtered(entry["id"], "content_generation_error")
                        filtered += 1
                        continue
                    entry["_content_en"] = en
                    next_survivors.append(entry)
                    if i % 10 == 0 or i == total_stage6:
                        logger.info("Stage 6 progress: %d/%d (%.0f%%)", i, total_stage6, i / total_stage6 * 100)
                except Exception as e:
                    logger.error("[%d] content EN error: %s", entry["id"], e)
                    mark_processed(entry["id"])
                    errors += 1
        survivors = next_survivors
        logger.info("Stage 6 done in %.1fs: %d survivors (%d cache hits)",
                    time.time() - t_stage, len(survivors), cache_hits_stage6)

    # ---- Stage 7: Insert trends ----
    t_stage = time.time()
    for entry in survivors:
        try:
            rel = entry["_relevance"]
            ext = entry["_extraction"]
            cls = entry["_classification"]
            common = {
                "title_de": None,
                "summary_de": None,
                "body_de": None,
                "verticals": cls.verticals,
                "primary_vertical": cls.verticals[0] if cls.verticals else rel.primary_vertical,
                "pestel": cls.pestel,
                "tags": cls.tags,
                "trend_signal_type": cls.trend_signal_type,
                "mega_trend": cls.mega_trend,
                "trend_level": "micro",
                "brands": [ext.brand_name] if ext.brand_name else [],
                "regions": cls.regions,
                "trend_score": compute_crs(
                    confidence=rel.confidence,
                    num_verticals=len(cls.verticals),
                    num_pestel=len(cls.pestel),
                    signal_type=cls.trend_signal_type,
                    source_type=entry.get("source_type"),
                ) / 100.0,
                "confidence": rel.confidence,
                "source_url": entry["url"],
                "source_name": entry.get("source_name", "Unknown"),
                "embedding": embedding_to_bytes(entry["_embedding"]),
            }
            if signal_mode:
                title = entry["title"] or "(untitled signal)"
                trend_data = {
                    **common,
                    "title_en": title,
                    "slug": f"{slugify(title, max_length=70)}-{entry['id']}",
                    "summary_en": None,
                    "body_en": None,
                    "status": "signal",
                }
            else:
                en = entry["_content_en"]
                trend_data = {
                    **common,
                    "title_en": en.title,
                    "slug": f"{slugify(en.title, max_length=70)}-{entry['id']}",
                    "summary_en": en.summary,
                    "body_en": en.body,
                }
            insert_trend(entry["id"], trend_data)
            mark_processed(entry["id"])
            created += 1
        except Exception as e:
            logger.error("[%d] insert error: %s", entry["id"], e, exc_info=True)
            mark_processed(entry["id"])
            errors += 1
    logger.info("Stage 7 done in %.1fs", time.time() - t_stage)

    # ---- Stage 8: Reclassify drafts (Qwen3 8B) ----  /  ---- Stage 9: Auto-publish ----
    # Both skipped in signal-mode: signals keep their API classification (the
    # chosen quality bar) and are not auto-published (no article yet). reclassify
    # would also re-touch unrelated drafts. Content-gen promotes signals later.
    published = 0
    if signal_mode:
        logger.info("Stages 8+9 skipped (signal-mode): signals stay status='signal'")
    else:
        # Same GPU-handover pattern as Stages 2-4 when STAGE_8B_BACKEND=llamacpp.
        # The Stage-6 35B handover above has already exited and stopped llama-server;
        # this brings it back up with the 8B GGUF for the reclassify pass.
        t_stage = time.time()
        gpu_ctx_8b_reclass = (gpu_handover.eight_b_on_llamacpp(STAGE_8B_MODEL)
                              if STAGE_8B_BACKEND == "llamacpp"
                              else nullcontext())
        with gpu_ctx_8b_reclass:
            reclass_stats = reclassify_drafts()
        logger.info("Stage 8 done in %.1fs: %d reclassified (%d changed)",
                    time.time() - t_stage, reclass_stats["total"], reclass_stats["changed"])

        t_stage = time.time()
        pub_stats = auto_publish()
        published = pub_stats["published"]
        logger.info("Stage 9 done in %.1fs: %d published, %d skipped",
                    time.time() - t_stage, published, pub_stats["skipped"])

    elapsed = time.time() - start
    logger.info(
        "BATCH complete in %.1fs: %d entries, %d created, %d filtered, %d errors, %d published",
        elapsed, len(entries), created, filtered, errors, published,
    )
    return {"processed": len(entries), "created": created, "filtered": filtered,
            "errors": errors, "published": published}


def run_pipeline(limit: int = 50):
    """Process unprocessed raw entries through the LLM pipeline."""
    start = time.time()
    init_db()

    entries = get_unprocessed_entries(limit=limit)
    logger.info("Found %d unprocessed entries", len(entries))

    processed = 0
    created = 0
    filtered = 0
    errors = 0

    for i, entry in enumerate(entries):
        try:
            result = process_entry(entry)
            processed += 1
            if result:
                created += 1
            else:
                filtered += 1
        except Exception as e:
            logger.error("Error processing entry %d: %s", entry["id"], e, exc_info=True)
            mark_processed(entry["id"])  # Skip on error so we don't get stuck
            errors += 1

        # Progress update every 10 entries
        if (i + 1) % 10 == 0:
            logger.info("Progress: %d/%d (created=%d, filtered=%d, errors=%d)",
                        i + 1, len(entries), created, filtered, errors)

    elapsed = time.time() - start
    logger.info(
        "Pipeline complete in %.1fs: %d processed, %d trends created, %d filtered, %d errors",
        elapsed, processed, created, filtered, errors,
    )
    return {"processed": processed, "created": created, "filtered": filtered, "errors": errors}


if __name__ == "__main__":
    args = sys.argv[1:]
    mode_batch = "--legacy" not in args
    signal_mode = "--signal-mode" in args
    min_id = next((int(a.split("=", 1)[1]) for a in args if a.startswith("--min-id=")), 0)
    positional = [a for a in args if not a.startswith("--")]
    limit = int(positional[0]) if positional else 200
    if mode_batch:
        run_pipeline_batch(limit=limit, signal_mode=signal_mode, min_id=min_id)
    else:
        run_pipeline(limit=limit)
