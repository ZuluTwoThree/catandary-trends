#!/usr/bin/env python3
"""LLM Processing Pipeline for Catandary Trends.

Processes raw RSS entries through:
1. Relevance Filter (Qwen3 8B)
2. Structured Extraction (Qwen3 8B)
3. NER + Classification (Qwen3 8B)
4. Duplicate Check (Qwen3-Embedding)
5. Content Generation (Qwen3 14B) – DE + EN
"""

import json
import logging
import struct
import sys
import time
from math import sqrt

from slugify import slugify

from pipeline.config import (
    DUPLICATE_SIMILARITY_THRESHOLD,
    LOG_LEVEL,
    MODEL_CLASSIFY,
    MODEL_EMBEDDING,
    MODEL_EXTRACT,
    MODEL_FILTER,
    MODEL_GENERATE,
    RELEVANCE_THRESHOLD,
)
from pipeline.db import (
    get_recent_embeddings,
    get_unprocessed_entries,
    init_db,
    insert_trend,
    mark_filtered,
    mark_processed,
)
from pipeline.models import (
    ClassificationResult,
    ExtractionResult,
    GeneratedContent,
    RelevanceResult,
)
from pipeline.ollama_client import chat_structured, generate_embedding

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

CLASSIFICATION_SYSTEM = """\
You are a trend classifier for Catandary Trends. Classify the trend signal using these taxonomies:

VERTICALS: FOOD (Food & Beverage), TECH (Technology & AI), HEALTH (Health & Wellness),
ECO (Sustainability & Eco), DESIGN (Design & Architecture), FASHION (Fashion & Beauty),
BIZ (Business & Retail), CULTURE (Culture & Media), SOCIAL (Social Impact), LUXURY (Luxury & Premium)

PESTEL: P (Political), E (Economic), S (Social), T (Technological), En (Environmental), L (Legal)

SIGNAL TYPES: product_launch, research, market_shift, consumer_behavior, regulation, funding, partnership, patent

Assign 1-3 verticals (cross-vertical trends are common). Always include at least one PESTEL dimension.
Use specific, lowercase tags (3-8 tags). If you can identify a mega-trend, name it concisely."""

CONTENT_EN_SYSTEM = """\
You are a professional trend analyst writing for Catandary Trends, a cross-industry trend intelligence platform.
Write a concise, analytical trend article in English (150-250 words).

Requirements:
- Professional, analytical tone – not promotional
- Focus on WHY this matters and WHAT it signals for the industry
- Include the source attribution at the end
- The article must be substantially different from the source material
- Do not copy phrases from the original
- Structure: Hook sentence → Context → Analysis → Outlook"""

CONTENT_DE_SYSTEM = """\
Du bist ein professioneller Trendanalyst für Catandary Trends, eine branchenübergreifende Trend-Intelligence-Plattform.
Schreibe einen prägnanten, analytischen Trend-Artikel auf Deutsch (150-250 Wörter).

Anforderungen:
- Professioneller, analytischer Ton – nicht werblich
- Fokus auf WARUM das wichtig ist und WAS es für die Branche signalisiert
- Quellennennung am Ende
- Der Artikel muss sich substanziell vom Quellmaterial unterscheiden
- Keine Phrasen aus dem Original kopieren
- Struktur: Hook-Satz → Kontext → Analyse → Ausblick"""


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


def step_relevance_filter(title: str, excerpt: str, source_vertical: str) -> RelevanceResult | None:
    """Step 1: Determine if the entry is a relevant trend signal."""
    prompt = f"""Analyze this RSS feed entry and determine if it's a relevant trend signal.

Source vertical hint: {source_vertical}

Title: {title}

Excerpt: {excerpt[:1500]}"""

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

    return chat_structured(
        model=MODEL_EXTRACT if MODEL_EXTRACT != "nuextract" else "qwen3:8b",
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


def step_generate_content(title: str, excerpt: str, extraction: ExtractionResult,
                          classification: ClassificationResult,
                          source_url: str, source_name: str) -> tuple[GeneratedContent | None, GeneratedContent | None]:
    """Step 5: Generate trend articles in EN and DE."""
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

Include this source attribution at the end: "Source: {source_name}" """

    prompt_de = f"""Schreibe einen Trend-Artikel auf Deutsch basierend auf diesen Informationen.

{context}

Füge diese Quellenangabe am Ende ein: "Quelle: {source_name}" """

    content_en = chat_structured(
        model=MODEL_GENERATE,
        prompt=prompt_en,
        schema=GeneratedContent,
        system=CONTENT_EN_SYSTEM,
        temperature=0.7,
    )

    content_de = chat_structured(
        model=MODEL_GENERATE,
        prompt=prompt_de,
        schema=GeneratedContent,
        system=CONTENT_DE_SYSTEM,
        temperature=0.7,
    )

    return content_en, content_de


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

    # Step 5: Content Generation
    content_en, content_de = step_generate_content(
        title, excerpt, extraction, classification, source_url, source_name
    )

    if content_en is None:
        logger.warning("[%d] EN content generation failed", entry_id)
        mark_filtered(entry_id, "content_generation_error")
        return None

    # Build trend data
    slug = slugify(content_en.title, max_length=80)
    trend_data = {
        "title_en": content_en.title,
        "title_de": content_de.title if content_de else None,
        "slug": slug,
        "summary_en": content_en.summary,
        "summary_de": content_de.summary if content_de else None,
        "body_en": content_en.body,
        "body_de": content_de.body if content_de else None,
        "verticals": classification.verticals,
        "primary_vertical": relevance.primary_vertical,
        "pestel": classification.pestel,
        "tags": classification.tags,
        "trend_signal_type": classification.trend_signal_type,
        "mega_trend": classification.mega_trend,
        "trend_level": "micro",  # Default; macro/mega assigned later
        "brands": [extraction.brand_name] if extraction.brand_name else [],
        "regions": classification.regions,
        "trend_score": relevance.confidence,
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

    for entry in entries:
        try:
            result = process_entry(entry)
            processed += 1
            if result:
                created += 1
            else:
                filtered += 1
        except Exception as e:
            logger.error("Error processing entry %d: %s", entry["id"], e, exc_info=True)
            errors += 1

    elapsed = time.time() - start
    logger.info(
        "Pipeline complete in %.1fs: %d processed, %d trends created, %d filtered, %d errors",
        elapsed, processed, created, filtered, errors,
    )
    return {"processed": processed, "created": created, "filtered": filtered, "errors": errors}


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    run_pipeline(limit=limit)
