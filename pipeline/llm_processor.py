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
    MIN_SOURCE_TEXT_CHARS,
    EMBED_BACKEND,
    EMBED_MODEL,
    RELEVANCE_THRESHOLD,
    RSS_CLASSIFY_MODE,
    DISTILL_REL_HIGH,
    DISTILL_REL_LOW,
    STAGE5_BACKEND,
    STAGE5_MIN_BODY_WORDS,
    EXTRACTION_STRICT,
    STAGE5_TARGET_BODY_WORDS,
    STAGE5_MAX_BODY_WORDS,
    STAGE5_MODEL,
    STAGE6_SOURCE_MAX_CHARS,
    STAGE_8B_BACKEND,
    STAGE_8B_MODEL,
    get_mega_trend_prompt_block,
    source_relevance_min,
)
from pipeline.db import (
    get_recent_embeddings,
    get_recent_titles,
    get_unprocessed_entries,
    init_db,
    insert_trend,
    mark_filtered,
    mark_processed,
    save_stage_result, slug_exists,
)
from pipeline.models import (
    ClassificationResult,
    ExtractionResult,
    GeneratedContent,
    RelevanceResult,
)
from pipeline.auto_publisher import auto_publish
from pipeline.content_guard import GarbledOutputError, garbage_reasons
from pipeline.crs import compute_crs
from pipeline.grounding import (figures_with_context, source_from_parts,
                                ungrounded_specifics, verbatim_only)
from pipeline.ollama_client import chat_structured, generate_embedding
from pipeline import anthropic_client, gpu_handover, llamacpp_client
from pipeline.reclassify import gate_mega_trends, reclassify_drafts

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# How much of the source text each stage reads. Since #11 `excerpt` carries the
# fetched full article (raw_content, ~4.4k chars avg) when available, not just the
# ~400-char RSS teaser — so the old 1000/1500 caps threw away ~77% of it and the
# full-text lever stayed unrealised (measured: fabrication 35.1% full-text vs
# 31.1% excerpt, i.e. no gain). Extraction and content-gen now read the article.
# Relevance stays short (decidable from the opening); the 8B runs at 208K ctx, so
# this is cheap.
#
# DO NOT raise the dedup slice (title + excerpt[:500], step_dedup_check): the 1.1M
# stored embeddings were computed with exactly that recipe — changing it breaks
# cosine comparability against the entire history.
# How much source text the extraction stage reads. Raised 4000 -> 12000 on
# 2026-08-20 after measuring the real corpus: of the articles that carry full
# text (article_fetcher, 28 % of articles and ~95 % of freshly polled RSS),
# the median is 4,680 chars and p90 is 8,043 — so the old limit cut 58 % of
# them mid-article, and the extraction never saw the figures and dates in the
# second half. 12000 matches article_fetcher.MAX_TEXT_CHARS exactly: nothing
# longer is ever stored, so a larger value would be dead configuration.
#
# Safe only together with the capped lists in ExtractionResult: more input
# means more extractable items, which is precisely what used to overrun
# max_tokens. The caps bound the OUTPUT, this bounds the INPUT.
EXTRACT_CHARS = 12_000
# Content-gen reads only the OPENING of the source (head, no tail) — see the
# STAGE6_SOURCE_MAX_CHARS rationale in config.py (default 4000, env-tunable).
CONTENT_CHARS = STAGE6_SOURCE_MAX_CHARS
RELEVANCE_CHARS = 1500

# --- Prompts ---

RELEVANCE_SYSTEM = """\
You are a trend analyst for Catandary Trends, a cross-industry trend intelligence platform.
Your job is to determine if an RSS feed entry represents a relevant trend signal.

A relevant trend signal is:
- A new product launch, technology, research finding, or market shift
- A meaningful change in consumer behavior, regulation, or industry dynamics
- Something that indicates where an industry is heading

NOT relevant:
- Sponsored posts, advertorials, paid/partner content, or any vendor advertising
  (these are paid placements, not independent trend signals — never relevant)
- Generic company earnings/quarterly results (unless they reveal a strategic shift)
- Routine personnel changes
- Opinion pieces without concrete data or developments
- Event announcements without substance
- Listicles or "top 10" without original insight"""

# Deterministic advertorial markers (checked before any LLM call). Paid/sponsored
# content is advertising, not a trend signal (CLAUDE.md: only independent
# primary-source content). The LLM relevance filter judges *topic* relevance and
# happily passes an on-topic advertorial with high confidence, so a cheap
# code-level prefix guard is the reliable gate. Prefix-anchored (no \b) so the
# run-together "SponsoredOptimized…" headline some newsrooms emit is still caught.
_ADVERTORIAL_RE = re.compile(
    r"^\s*(sponsored|advertorial|paid post|partner content)",
    re.IGNORECASE,
)
# German "ANZEIGE" ad label, but only as a standalone label (followed by space or
# colon) — so "Anzeigenmotiv"/"Anzeigenblätter" (legit trade journalism about
# advertising) are NOT caught. And exclude "Anzeige gegen/wegen…" (a criminal
# complaint = real news). Bare "advertisement"/"promoted" are intentionally NOT
# markers: they catch ad-tech patents and research/company names, not advertorials.
_ANZEIGE_RE = re.compile(r"^\s*anzeige(?=[:\s,])", re.IGNORECASE)
_ANZEIGE_NEWS_RE = re.compile(
    r"^\s*anzeige\s+(gegen|wegen|erstattet|erstatten|gestellt|nach|läuft)",
    re.IGNORECASE,
)


def is_advertorial(title: str, excerpt: str = "") -> bool:
    """True if the entry is sponsored/advertorial (paid placement, not a signal)."""
    t = (title or "").lstrip()
    if _ADVERTORIAL_RE.match(t):
        return True
    if _ANZEIGE_RE.match(t) and not _ANZEIGE_NEWS_RE.match(t):
        return True
    return False

EXTRACTION_SYSTEM = """\
You are a precise information extractor. Extract ONLY information that is explicitly stated in the text.
Do not infer, guess, or add information. If something is not mentioned, leave it as null or empty.
Copy figures, dates and direct quotes VERBATIM, exactly as they appear (keep the original number and date formatting); never round, convert, rephrase or invent them."""

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
9. **Mining, oil & gas, metals, minerals, commodities, raw-material extraction / exploration / drilling → ECO** (resources, energy, environment) — or **BIZ** if purely the company's finance/M&A/earnings. **NEVER FOOD** unless it is about edible agricultural produce. (No dedicated "materials/resources" vertical exists; without this rule mining PR mis-routes to FOOD.)
10. **Most trends belong to ONE primary vertical.** Only add secondaries when the trend genuinely cannot be understood without two industries.

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

HARD RULE — LANGUAGE: The source material is often in another language (e.g. German). Your ENTIRE output — both the `title` and the `body` — MUST be written in fluent English. Translate and rewrite any non-English source into English; never echo the source language, and never leave the title or body in the source language. English only, in every field.

Voice:
- Lead with the concrete fact: who did what, the number, the product, the filing, the company. Use specifics from the source, not abstractions.
- Plain declarative sentences. Vary how each sentence opens — never start two sentences the same way.
- Analytical, not promotional. Explain the mechanism (why it works, what concretely changes), not vague significance.
- Substantially reworded from the source; never copy its phrasing.
- Close with a concrete, falsifiable consequence — not a generic forecast.

HARD RULE — never open a sentence with a template like "This trend/development/shift signals/underscores/reflects/highlights…" or "Looking ahead…". Open with the concrete subject instead.

  ✗ "This development underscores a broader shift toward automation in logistics."
  ✓ "Maersk's new system reroutes containers automatically when a port congests, cutting dwell time."

Also avoid (reword, don't just swap synonyms): "paving the way", "the era of", "continues to evolve", "in the coming years / years to come", "in the digital age", "on a global scale", "a competitive edge", "companies that fail to…", and empty intensifiers ("increasingly", "rapidly evolving", "in today's world").

Test each sentence: if it could open an article in any other industry, delete it and write the specific detail instead. Write the article, not a template."""


# --- Content prompt v2 (issue #11): signal-type framing + forced concreteness.
# Built on top of the v1 voice/language rules; adds (a) a concreteness mandate
# that forces at least one specific figure/name/date from the source, with an
# explicit no-fabrication clause, and (b) a per-signal-type angle injected into
# the user prompt via signal_type_framing(). Validated A/B against v1 with
# scripts/ab_test_prompt.py before wiring into the live path.
CONTENT_EN_SYSTEM_V2 = CONTENT_EN_SYSTEM + """

GROUNDING — every specific must come from the source:
- Preserve the exact specifics the source gives — figures, proper names, dates. Don't blur "7,980 jobs" into "thousands" or drop the company name.
- NEVER introduce a number, date, statistic, or named entity that is not present in the source text. Do not estimate, extrapolate, or invent a timeline (e.g. do not write "rolled out in May" unless the source says so). If the source is thin, write a shorter, more general article — an invented specific is a factual error, not a stylistic choice.
- Never add first names, titles, affiliations, dates or figures that are not in the source; refer to people exactly as the source does (if the source says "Henkel-Chef Knobel", write "Henkel CEO Knobel" — do not supply a first name).
- Prefer the mechanism over the claim: state what concretely changes and how, not that something is "significant" or "growing"."""


# Per-signal-type angle — the single biggest lever after concreteness: a funding
# note, a regulation, a research finding and a product launch each demand a
# different lead. Injected into the user prompt (not the system) so it travels
# with the row's classification.
SIGNAL_TYPE_FRAMING = {
    "product_launch": "Lead with what the product does differently and for whom; name the concrete capability, not the marketing promise.",
    "research": "State the finding and how it was shown (method, sample size); separate what the evidence demonstrates from what is still speculation.",
    "regulation": "Name the rule, the jurisdiction, who must comply and by when; state the concrete operational consequence for the affected players.",
    "funding": "State the amount, stage and lead investor and what the capital concretely buys; avoid framing a single round as 'the future of' anything.",
    "market_shift": "Name the specific companies or segments moving and the measurable change; avoid generic 'growing demand' language.",
    "consumer_behavior": "Cite the specific behaviour change and the evidence for it (survey size, sales delta); avoid 'consumers are increasingly'.",
    "partnership": "State who partnered, what each side brings, and the concrete first deliverable or milestone.",
    "patent": "State what the patent claims and the practical capability it would enable; note it is a filing, not a shipped product.",
}


def signal_type_framing(signal_type: str | None) -> str | None:
    """The v2 per-signal-type angle for the content prompt, or None if unknown."""
    return SIGNAL_TYPE_FRAMING.get((signal_type or "").strip().lower())


# Cliché guard — NARROW on purpose: only the template *signatures* that are both
# high-signal and easily avoidable (sentence-opener templates + a few set phrases).
# Earlier the guard also banned common-but-borderline fillers ("highlights",
# "aligns with", "reflects a broader" …); those fired on ~45% of bodies and caused
# heavy retries while the model kept reproducing them. The system prompt still
# discourages all of them — but only these few trigger a re-roll, so retries stay
# rare and content-gen stays fast.
_CLICHE_RE = re.compile(
    r"\b("
    r"looking ahead|"
    r"this (trend|shift|development|move|signal|announcement) "
    r"(signals|underscores|reflects|highlights|marks|represents|demonstrates)|"
    r"signals? a (shift|move|broader|new era)|underscores? a (broader|growing|fundamental)|"
    r"pav(e|es|ing) the way|the era of|continues? to evolve|companies that fail|"
    r"in the coming years|years to come|in the digital age|on a global scale"
    r")\b", re.IGNORECASE)


# --- Grounding guard (#11): the concreteness push, and the base model itself,
# invent plausible specifics ~1/3 of the time (a fake "by 2025" compliance
# deadline, invented percentages). ungrounded_specifics lives in pipeline.grounding
# (dependency-free, shared with the auto-publish gate). We re-roll such bodies —
# and, because bounded re-rolls don't fully remove it, auto_publisher also HOLDS
# any still-ungrounded body for review instead of publishing it.
def make_content_guard(source: str):
    """content_is_clean + a grounding gate bound to this row's source text.
    Used as the llama.cpp `validate` callback so ungrounded-specific bodies get
    re-rolled within the existing retry budget."""
    def guard(c: "GeneratedContent") -> bool:
        return content_is_clean(c) and not ungrounded_specifics(c.body, source)
    return guard


def make_garbage_guard(source: str):
    """The HARD guard for llamacpp_client.chat_structured(hard_validate=...):
    returns the garbage reasons for a generated body (empty = usable), judged
    against this row's source so a leaked foreign-script token counts."""
    def guard(c: "GeneratedContent") -> list[str]:
        return garbage_reasons(c.body, source)
    return guard


def content_is_clean(c: "GeneratedContent") -> bool:
    """Content guard. Rejects (→ re-roll) on: (a) a near-empty stub (hard garbage
    floor), (b) a body cut off mid-sentence (no terminal punctuation), (c) banned
    cliché phrases, or (d) BREVITY — below STAGE5_TARGET_BODY_WORDS.

    On brevity: the prompt asks for 150-250 words and the model reliably lands
    near 100. The owner accepted ~100 as the working length (2026-08-19), so the
    floor sits there and only catches genuine stubs. It deliberately does NOT
    match the prompt: asking high is what produces ~100 in the first place, and
    lowering the ASK would likely shorten the output further. The floor is a
    safety net, not the target.

    The brevity re-roll is bounded by max_validate_retries, after which a
    short-but-clean body is accepted rather than looping forever."""
    body = c.body.strip()
    words = len(body.split())
    if words < STAGE5_MIN_BODY_WORDS:
        return False                                   # near-empty stub = real failure
    if not body.endswith((".", "!", "?", '"', "”")):   # cut off mid-sentence → retry
        return False
    if words < STAGE5_TARGET_BODY_WORDS:                # Option B: too short → re-roll
        return False
    if STAGE5_MAX_BODY_WORDS and words > STAGE5_MAX_BODY_WORDS:  # #11: runaway → re-roll
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

Excerpt: {excerpt[:RELEVANCE_CHARS]}"""

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
            verify_model=True,  # #98: abort if :8090 no longer serves the 8B
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

Text: {excerpt[:EXTRACT_CHARS]}"""

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
            # Every field of ExtractionResult has a default, so Pydantic marked
            # none as required and the grammar let the model omit them — it did,
            # for brand_name, key_claims and quotes on all 14 test articles.
            require_all_fields=EXTRACTION_STRICT,
            verify_model=True,
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
            verify_model=True,
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


def build_content_prompt(title: str, excerpt: str, extraction: ExtractionResult,
                         classification: ClassificationResult,
                         source_url: str, source_name: str) -> tuple[str, str]:
    """The production Stage-6 user prompt and the grounding source for one row.

    Split out of step_generate_content_en (2026-09-05) so
    scripts/repro_stage6_garbage.py can replay EXACTLY what production sends —
    the same slice of the excerpt, the same extraction blocks, the same framing.
    Returns (prompt_en, source_text)."""
    # Everything the extraction found goes in. Until 2026-08-21 the prompt used
    # three of eight fields and dropped key_figures, dates, quotes and geography
    # — precisely the four the grounding gate then judged the finished body
    # against. The writer was asked for an evidence-dense article and handed no
    # evidence, which is the likeliest driver of the 43.7 % speculation rate.
    def _block(label: str, items: list[str], sep: str = "\n  - ") -> str:
        return f"{label}:{sep}{sep.join(items)}\n" if items else ""

    context = f"""Original Title: {title}
Original Excerpt: {excerpt[:CONTENT_CHARS]}
Brand: {extraction.brand_name or 'Unknown'}
Product: {extraction.product_name or 'Unknown'}
{_block("Figures stated in the source (verbatim — use these, invent none)", extraction.key_figures)}\
{_block("Key Claims", extraction.key_claims[:8])}\
{_block("Dates stated in the source", extraction.dates, sep=", ")}\
{_block("Quotes", extraction.quotes[:3])}\
{_block("Places", extraction.geography, sep=", ")}\
Verticals: {', '.join(classification.verticals)}
PESTEL: {', '.join(classification.pestel)}
Signal Type: {classification.trend_signal_type}
Mega Trend: {classification.mega_trend or 'N/A'}
Source: {source_name} ({source_url})"""

    # v2 prompt (#11): per-signal-type angle injected with the row's classification.
    # Proven judge win over v1 across a 30-trend stratified A/B
    # (scripts/ab_test_prompt.py; every rubric dimension improved).
    framing = signal_type_framing(classification.trend_signal_type)
    framing_block = f"Signal-type framing: {framing}\n\n" if framing else ""
    prompt_en = f"""Write a trend article in English based on this information.
The source below may be in German or another language — translate it and write the title and body entirely in English.

{framing_block}{context}

"""

    # Grounding gate (#11): re-roll bodies that introduce a number/date not in the
    # source. The model sees the excerpt (raw_content when available) + the
    # extracted specifics, so anything else is fabricated (the harness measured
    # ~1/3 of bodies inventing a specific). Build the source from the same parts
    # the auto-publish gate rebuilds, so the two stay consistent.
    source_text = source_from_parts(title, excerpt, extraction.key_claims,
                                    extraction.key_figures, extraction.dates,
                                    extraction.quotes, extraction.geography)
    return prompt_en, source_text


def step_generate_content_en(title: str, excerpt: str, extraction: ExtractionResult,
                              classification: ClassificationResult,
                              source_url: str, source_name: str) -> GeneratedContent | None:
    """Step 5: Generate English trend article."""
    prompt_en, source_text = build_content_prompt(title, excerpt, extraction, classification,
                                                  source_url, source_name)
    guard = make_content_guard(source_text)
    # HARD guard (#11, 2026-09-05): token soup is never accepted, not even after
    # the soft budget — the soft guard's "accept the last result" is exactly how
    # 22 garbage bodies became drafts. Checked against the source so a leaked
    # CJK token in an otherwise fluent body counts too.
    hard_guard = make_garbage_guard(source_text)

    if STAGE5_BACKEND == "llamacpp":
        # Route content gen to llama-server (GPU handover managed by the caller).
        # The word-count guard retries on premature grammar string-termination.
        return llamacpp_client.chat_structured(
            model=STAGE5_MODEL,
            prompt=prompt_en,
            schema=GeneratedContent,
            system=CONTENT_EN_SYSTEM_V2,
            temperature=0.7,
            validate=guard,
            max_validate_retries=3,  # Option B: allow re-rolls toward target length, then accept
            # #98: identity gate before the first request and every re-roll.
            # 2026-09-05 the embedding server answered these requests with
            # 200 OK; the cliché guard rejected each body and the stage
            # re-rolled for hours. A mismatch now raises ModelMismatchError.
            verify_model=True,
            hard_validate=hard_guard,  # raises GarbledOutputError, never returns soup
        )

    result = chat_structured(
        model=MODEL_GENERATE,
        prompt=prompt_en,
        schema=GeneratedContent,
        system=CONTENT_EN_SYSTEM_V2,
        temperature=0.7,
    )
    # The Ollama client has no validate hook; apply the hard guard after the fact
    # so the fallback path can't store garbage either.
    if result is not None:
        garbage = hard_guard(result)
        if garbage:
            raise GarbledOutputError(
                f"GeneratedContent: Ollama {MODEL_GENERATE} produced garbage "
                f"({', '.join(garbage[:4])}) — nothing stored")
    return result




# --- Title-level dedup helpers ---

_TITLE_NORMALIZE_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = _TITLE_NORMALIZE_RE.sub(" ", (title or "").lower())
    return " ".join(t.split())


def unique_slug(title: str, entry_id: int) -> str:
    """Slug = slugified title + raw-entry id — unique per entry, until the same
    entry is written AGAIN ("Write again", 2026-09-08 mass rewrite): its retired
    predecessor still holds the slug (UNIQUE), and a colliding insert used to be
    logged as an error and the entry marked processed — the story silently lost
    (548 of 813 that evening). A collision now gets a -r2/-r3 suffix instead."""
    base = f"{slugify(title, max_length=70)}-{entry_id}"
    slug, n = base, 1
    while slug_exists(slug):
        n += 1
        slug = f"{base}-r{n}"
    return slug


def publish_stages_needed(created: int) -> bool:
    """Stages 8 (reclassify over ALL drafts, ~20 min per pass) and 9 (auto-publish)
    only change anything when this batch inserted at least one draft. A batch
    that created nothing — e.g. a single entry that Stage 6 leaves garbled every
    run — used to trigger both anyway: 2026-09-09 spent 4 × 22 min on one such
    entry. Drafts a crashed run left unpublished are picked up by the next batch
    that creates something, or by scripts/resume_cycle.sh."""
    return created > 0


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
    # Prefer the fetched full article text (raw_content, #11) over the short RSS
    # excerpt when present — the stages slice the first ~1-1.5k chars, which is
    # far richer than a ~70-word teaser and cuts the fabrication rate.
    excerpt = (entry.get("raw_content") or entry["excerpt"] or "")
    source_vertical = entry.get("source_vertical", "TECH")
    source_name = entry.get("source_name", "Unknown")
    source_url = entry["url"]

    logger.info("Processing [%d]: %s", entry_id, title[:80])
    t0 = time.time()

    # Step 0: Advertorial guard (deterministic, pre-LLM)
    if is_advertorial(title, excerpt):
        logger.info("[%d] Filtered out: sponsored/advertorial", entry_id)
        mark_filtered(entry_id, "sponsored/advertorial")
        return None

    # Step 0b: minimum source text (#97, 2026-09-09) — same guard as the batch
    # path. A bare title gives the grounding gate nothing to check against.
    if len(excerpt.strip()) < MIN_SOURCE_TEXT_CHARS:
        logger.info("[%d] Filtered out: insufficient source text (%d chars)",
                    entry_id, len(excerpt.strip()))
        mark_filtered(entry_id, "insufficient_source_text")
        return None

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

    # key_figures come from the SOURCE, not the model. Measured 2026-08-21 on 14
    # articles: of 44 LLM-produced key_figures exactly ONE was both verbatim and
    # actually a number — the model writes summarising sentences ("Over £13
    # billion lost on the FTSE 100") rather than extracting tokens. Correct in
    # substance, but its own words, so a verbatim check rejects them and the
    # grounding gate cannot use them. The regex found 188 figures across the same
    # articles, verbatim by construction, at zero GPU cost. Each entry carries the
    # sentence around the number, because "$70" alone is not evidence.
    extraction.key_figures = figures_with_context(excerpt)
    # Quotes and places must be copied, not paraphrased — anything the source
    # does not literally contain is dropped. key_claims are deliberately exempt:
    # a claim condenses, so a verbatim rule would empty the field.
    if EXTRACTION_STRICT:
        extraction.quotes = verbatim_only(extraction.quotes, excerpt)
        extraction.geography = verbatim_only(extraction.geography, excerpt)

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
    try:
        content_en = step_generate_content_en(
            title, excerpt, extraction, classification, source_url, source_name
        )
    except GarbledOutputError as e:
        # Every attempt was token soup. Store nothing, mark nothing — the entry
        # stays unprocessed and gets a fresh chance next run (#11, 2026-09-05).
        logger.error("[%d] content generation GARBLED, entry left unprocessed: %s", entry_id, e)
        return None

    if content_en is None:
        logger.warning("[%d] EN content generation failed", entry_id)
        mark_filtered(entry_id, "content_generation_error")
        return None

    # Build trend data — slug = title + entry_id, suffixed if a retired
    # predecessor of this very entry still holds it
    slug = unique_slug(content_en.title, entry_id)
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


_DISTILL_CLF = None  # cached DistillClassifier


def relevance_band(rel: float | None, has_head: bool,
                   low: float = DISTILL_REL_LOW, high: float = DISTILL_REL_HIGH) -> str:
    """Hybrid relevance routing (pure, unit-tested): 'keep' / 'drop' / 'llm'.
    Distill decides the confident tails; the uncertain middle (and the no-head
    case) go to the 8B LLM."""
    if not has_head or rel is None:
        return "llm"
    if rel >= high:
        return "keep"
    if rel < low:
        return "drop"
    return "llm"


def _distill_signal_type(e: dict) -> str:
    """Deterministic trend_signal_type (distill heads don't emit it) — mirrors
    scripts/signal_batch._distill_signal_type / the lead-time tier map."""
    st = (e.get("source_type") or "").lower()
    sn = (e.get("source_name") or "").lower()
    if e.get("pub_number"):
        return "patent"
    if st == "research" or any(m in sn for m in ("arxiv", "rxiv", "preprint")):
        return "research"
    if st == "api" and any(m in sn for m in ("nsf", "nih", "reporter", "openaire", "ukri", "form d")):
        return "funding"
    return "market_shift"


def hybrid_classify(survivors: list[dict]) -> tuple[list[dict], int, int]:
    """#41 embed-first + distill classification with a HYBRID relevance gate.

    Embeds every survivor, runs the distill heads (vertical/mega/PESTEL/relevance),
    and gates relevance in three bands: distill keeps the confident-relevant
    (>= DISTILL_REL_HIGH), drops the confident-irrelevant (< DISTILL_REL_LOW), and
    routes ONLY the uncertain middle to the 8B LLM relevance filter (the fallback
    that the eval showed is still needed there). Extraction stays on the 8B for the
    survivors (brand names for content-gen). Sets entry['_relevance'],
    ['_extraction'], ['_classification'] and persists the embedding so Stage 5
    finds it cached and only dedups. Returns (survivors, filtered_delta, errors).

    Raises if the distill heads can't load — the caller falls back to the LLM path.
    """
    global _DISTILL_CLF
    if _DISTILL_CLF is None:
        from pipeline.distill import DistillClassifier
        _DISTILL_CLF = DistillClassifier.load()
    clf = _DISTILL_CLF
    filtered = errors = 0

    # ---- embed-first (persist so Stage 5 finds it cached → dedup only) ----
    def _embed_one(text):
        return (llamacpp_client.generate_embedding(text, model=EMBED_MODEL)
                if EMBED_BACKEND == "llamacpp" else generate_embedding(MODEL_EMBEDDING, text))
    to_embed = [e for e in survivors if not e.get("embedding_blob")]
    gpu_ctx_embed = (gpu_handover.embed_on_llamacpp(EMBED_MODEL)
                     if EMBED_BACKEND == "llamacpp" and to_embed else nullcontext())
    with gpu_ctx_embed:
        emb_res = dict(zip((e["id"] for e in to_embed), _concurrent(
            lambda e: _embed_one(f"{e['title']}\n{(e['excerpt'] or '')[:500]}"), to_embed)))
    embedded = []
    for entry in survivors:
        cached = entry.get("embedding_blob")
        emb = bytes_to_embedding(cached) if cached else emb_res.get(entry["id"])
        if emb is None:
            mark_filtered(entry["id"], "embedding_error"); filtered += 1
            continue
        if not cached:
            blob = embedding_to_bytes(emb)
            save_stage_result(entry["id"], "embedding", blob)
            entry["embedding_blob"] = blob   # Stage 5 will now treat it as cached
        entry["_emb_vec"] = emb
        embedded.append(entry)

    # ---- distill heads (CPU, batched) ----
    X = np.asarray([e["_emb_vec"] for e in embedded], dtype=np.float32)
    preds = clf.classify_batch(X) if len(embedded) else []
    has_rel = clf.has_relevance_head

    # ---- hybrid relevance: confident tails by distill, uncertain band → 8B ----
    kept, uncertain = [], []
    rel_min = source_relevance_min()
    for entry, pred in zip(embedded, preds):
        entry["_distill"] = pred
        rel = pred.get("relevance")
        # Per-source cap (#13/value-report): raise the drop-gate for low-foresight
        # sources so their marginal content is filtered, while borderline still
        # goes to the 8B and strong signals pass unchanged.
        src_min = rel_min.get(entry.get("source_name") or "", 0.0)
        band = relevance_band(rel, has_rel, low=max(DISTILL_REL_LOW, src_min))
        if band == "keep":
            kept.append(entry)
        elif band == "drop":
            mark_filtered(entry["id"], f"not_relevant_distill:{rel:.2f}"); filtered += 1
        else:
            uncertain.append(entry)                        # grey band / no head → 8B
    logger.info("Hybrid relevance: %d distill-kept, %d → 8B fallback, %d distill-dropped",
                len(kept), len(uncertain), filtered)

    # 8B relevance only for the uncertain band + extraction for all kept survivors
    gpu_ctx_8b = (gpu_handover.eight_b_on_llamacpp(STAGE_8B_MODEL)
                  if STAGE_8B_BACKEND == "llamacpp" and (uncertain or kept) else nullcontext())
    with gpu_ctx_8b:
        if uncertain:
            rel_res = dict(zip((e["id"] for e in uncertain), _concurrent(
                lambda e: step_relevance_filter(e["title"], e["excerpt"] or "",
                                                e.get("source_vertical", "TECH")), uncertain)))
            for entry in uncertain:
                r = rel_res.get(entry["id"])
                thr = max(RELEVANCE_THRESHOLD,
                          rel_min.get(entry.get("source_name") or "", 0.0))
                if r is None or not r.is_relevant or r.confidence < thr:
                    mark_filtered(entry["id"], "not_relevant: (8B band)"); filtered += 1
                    continue
                kept.append(entry)
        # extraction (brand names) on the 8B for the kept survivors
        to_ext = [e for e in kept if not e.get("extraction_json")]
        ext_res = dict(zip((e["id"] for e in to_ext), _concurrent(
            lambda e: step_extraction(e["title"], e["excerpt"] or ""), to_ext)))

    # build the per-entry RelevanceResult / ClassificationResult from distill
    out = []
    for entry in kept:
        try:
            pred = entry["_distill"]
            ext = (ExtractionResult.model_validate_json(entry["extraction_json"])
                   if entry.get("extraction_json") else (ext_res.get(entry["id"]) or ExtractionResult()))
            if not entry.get("extraction_json"):
                save_stage_result(entry["id"], "extraction", ext)
            entry["_extraction"] = ext
            conf = pred.get("relevance") or pred.get("vertical_confidence") or 0.7
            entry["_relevance"] = RelevanceResult(
                is_relevant=True, confidence=float(conf),
                primary_vertical=pred["primary_vertical"], reason="distill")
            cls = ClassificationResult(
                verticals=[pred["primary_vertical"]], pestel=pred["pestel"], tags=[],
                trend_signal_type=_distill_signal_type(entry),
                mega_trend=pred["mega_trend"], regions=[])
            save_stage_result(entry["id"], "classification", cls)
            entry["_classification"] = cls
            out.append(entry)
        except Exception as e:  # noqa: BLE001
            logger.error("[%d] hybrid build error: %s", entry["id"], e)
            mark_processed(entry["id"]); errors += 1
    return out, filtered, errors


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

    # Prefer the fetched full article text over the short RSS teaser — the same
    # rule process_entry has followed since #11. This path did NOT: every stage
    # below reads entry["excerpt"], so article_fetcher.fetch_batch wrote
    # raw_content that the production cycle never looked at (found 2026-09-09;
    # measured gap for opt-in sources: excerpt 124-456 chars vs raw_content
    # 2.4k-6.3k). Normalising once here keeps both paths identical.
    for entry in entries:
        full = entry.get("raw_content")
        if full and len(full) > len(entry.get("excerpt") or ""):
            entry["excerpt"] = full

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
        # Stage 0: advertorial guard (deterministic, pre-LLM)
        if is_advertorial(title, entry.get("excerpt") or ""):
            mark_filtered(entry["id"], "sponsored/advertorial")
            filtered += 1
            continue
        # Stage 0b: minimum source text (#97, 2026-09-09). Without a body there
        # is nothing for the grounding gate to check, so anything the model
        # invents passes silently — never generate from a bare title.
        if len((entry.get("excerpt") or "").strip()) < MIN_SOURCE_TEXT_CHARS:
            mark_filtered(entry["id"], "insufficient_source_text")
            filtered += 1
            continue
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

    # ---- Stages 2-4: Relevance / Extraction / Classification ----
    # #41 hybrid (default): embed-first + distill heads for vertical/mega/PESTEL +
    # hybrid relevance (8B only for the uncertain band), extraction on the 8B.
    # Falls back to the full 8B path on any distill error or RSS_CLASSIFY_MODE=llm.
    used_hybrid = False
    if RSS_CLASSIFY_MODE == "hybrid" and survivors:
        try:
            t_stage = time.time()
            survivors, f_delta, e_delta = hybrid_classify(survivors)
            filtered += f_delta
            errors += e_delta
            used_hybrid = True
            logger.info("Stages 2-4 (hybrid distill) done in %.1fs: %d survivors",
                        time.time() - t_stage, len(survivors))
        except llamacpp_client.ModelMismatchError:
            raise  # #98: the 8B band hit a swapped server — the LLM path would too
        except Exception as e:  # noqa: BLE001 — never break the cycle on distill issues
            logger.warning("Hybrid classify unavailable (%s) — falling back to 8B LLM path", e)

    # When STAGE_8B_BACKEND=llamacpp, swap the GPU to the 8B llama-server for
    # the duration of these three contiguous loops; restore the symlink on
    # exit so Stage 6's 35B handover finds start-active.sh as expected.
    gpu_ctx_8b = (gpu_handover.eight_b_on_llamacpp(STAGE_8B_MODEL)
                  if STAGE_8B_BACKEND == "llamacpp" and survivors and not used_hybrid
                  else nullcontext())
    if not used_hybrid:
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
    # Build the recent-embedding matrix straight via np.frombuffer — NOT as Python
    # float-lists (bytes_to_embedding). At ~355k recent embeddings the list-of-lists
    # ballooned to ~46 GB and OOM-killed run_full_cycle (cycle, 2026-06-29);
    # frombuffer into a preallocated matrix is ~355k*4096*4 ≈ 5.8 GB. Pre-normalized
    # so the dedup matmul can use it directly. (Mirrors the signal_batch fix.)
    recent = get_recent_embeddings(days=30)
    logger.info("Stage 5: %d recent embeddings loaded", len(recent))
    if recent:
        _rdim = len(recent[0][1]) // 4
        R_recent = np.empty((len(recent), _rdim), dtype=np.float32)
        for _ri, (_, _rb) in enumerate(recent):
            R_recent[_ri] = np.frombuffer(_rb, dtype=np.float32)
        R_recent = _norm_rows(R_recent)
    else:
        R_recent = None

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
        R = R_recent  # prebuilt + pre-normalized via frombuffer above (no Python lists)
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

    garbled_ids: list[int] = []   # left unprocessed by Stage 6 — reported to the caller
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
        garbled_stage6 = 0
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
                except GarbledOutputError as e:
                    # #11 (2026-09-05): all attempts were token soup. Nothing is
                    # stored and the entry is neither marked processed nor
                    # filtered — it stays in the queue for the next run. Counted
                    # separately so the summary line shows the episode.
                    logger.error("[%d] content generation GARBLED, entry left unprocessed: %s",
                                 entry["id"], e)
                    garbled_stage6 += 1
                    garbled_ids.append(entry["id"])
                except llamacpp_client.ModelMismatchError as e:
                    # #98: another job swapped :8090 under us. Stop generating —
                    # this entry and every remaining one stay UNPROCESSED (not
                    # marked, not filtered) for the next run; the entries already
                    # generated continue into Stage 7. Counted as errors so
                    # run_full_cycle exits non-zero.
                    remaining = total_stage6 - i + 1
                    logger.error("Stage 6 ABORTED at %d/%d: %s — %d entries left unprocessed",
                                 i, total_stage6, e, remaining)
                    errors += remaining
                    break
                except Exception as e:
                    logger.error("[%d] content EN error: %s", entry["id"], e)
                    mark_processed(entry["id"])
                    errors += 1
        survivors = next_survivors
        logger.info("Stage 6 done in %.1fs: %d survivors (%d cache hits, %d garbled → left unprocessed)",
                    time.time() - t_stage, len(survivors), cache_hits_stage6, garbled_stage6)

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
                    "slug": unique_slug(title, entry["id"]),
                    "summary_en": None,
                    "body_en": None,
                    "status": "signal",
                }
            else:
                en = entry["_content_en"]
                trend_data = {
                    **common,
                    "title_en": en.title,
                    "slug": unique_slug(en.title, entry["id"]),
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
    elif not publish_stages_needed(created):
        logger.info("Stages 8+9 skipped: no new trends in this batch (reclassify over all "
                    "drafts costs ~20 min per pass; scripts/resume_cycle.sh runs them on demand)")
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

        # Mega-trend plausibility gate (#39): null LLM-forced mega-trends the
        # embedding disagrees with. CPU-only, no GPU handover needed.
        mega_stats = gate_mega_trends()
        logger.info("Stage 8b (mega-gate): %d/%d drafts nulled",
                    mega_stats["nulled"], mega_stats["checked"])

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
            "errors": errors, "published": published, "garbled_ids": garbled_ids}


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
