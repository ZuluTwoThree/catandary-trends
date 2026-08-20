"""Pydantic schemas for LLM pipeline structured outputs."""

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# --- Verticals & PESTEL ---

Vertical = Literal[
    "FOOD", "TECH", "HEALTH", "ECO", "DESIGN",
    "FASHION", "BIZ", "LIFESTYLE",
]

PestelDimension = Literal["P", "E", "S", "T", "En", "L"]

TrendSignalType = Literal[
    "product_launch", "research", "market_shift",
    "consumer_behavior", "regulation", "funding",
    "partnership", "patent",
]

TrendLevel = Literal["mega", "macro", "micro"]


# --- Step 1: Relevance Filter ---

class RelevanceResult(BaseModel):
    """Output of the relevance filter step."""
    is_relevant: bool = Field(description="Whether this is a relevant trend signal")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0-1")
    primary_vertical: Vertical = Field(description="Primary industry vertical")
    reason: str = Field(description="Brief reason for relevance decision")


class RelevanceResultSlim(BaseModel):
    """Relevance filter without the free-text `reason` field, for the backfill
    classifier. Under constrained JSON decoding every schema field MUST be
    generated, and `reason` (a full sentence) roughly doubled the relevance
    output tokens → halved throughput (92 vs ~165 req/min). Dropping it is the
    main local-throughput lever; `reason` is unused in signal-mode (gate only)."""
    is_relevant: bool = Field(description="Whether this is a relevant trend signal")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0-1")
    primary_vertical: Vertical = Field(description="Primary industry vertical")


# --- Step 2: Structured Extraction ---

class ExtractionResult(BaseModel):
    """Output of the structured extraction step (purely extractive).

    Every list is capped. Uncapped, the model dutifully enumerated every place
    and date in a long article and ran past max_tokens mid-JSON — 55 truncated
    extractions in one run (2026-08-20), 14 of which gave up after three
    identical retries and fell back to an EMPTY result. Measured list sizes in
    normal operation: median 0, p95 0-3 items. A cap of 10 therefore never
    truncates real content; it only stops the runaway enumeration.
    """
    brand_name: str | None = Field(default=None, description="Brand or company name mentioned")
    product_name: str | None = Field(default=None, description="Product or service name")
    source_type: str | None = Field(default=None, description="Type of source (press release, article, etc.)")
    key_claims: list[str] = Field(default_factory=list, max_length=10,
                                  description="Up to 10 key claims from the text")
    # --- Richer extraction (#11): purely extractive specifics. Copy tokens
    # VERBATIM as they appear (keep the source's number/date formatting); never
    # infer. Besides being useful metadata, key_figures/dates feed the grounding
    # gate (pipeline.grounding): a figure the source actually states is added to
    # the "grounded" set, so a correctly-cited number in the body is no longer
    # held as fabricated by the auto-publish gate — the source that gate rebuilds
    # is otherwise narrower than the full text the content model saw. That link
    # is why an empty extraction is not harmless: it shrinks the grounding
    # source and makes correctly-cited figures look invented.
    key_figures: list[str] = Field(default_factory=list, max_length=10,
                                   description="Up to 10 specific numbers, statistics, amounts or percentages stated verbatim in the text (e.g. '7,980 jobs', '29,5 %', '$2B')")
    quotes: list[str] = Field(default_factory=list, max_length=5,
                              description="Up to 5 direct quotations from the text")
    dates: list[str] = Field(default_factory=list, max_length=10,
                             description="Up to 10 dates, years or timeframes explicitly stated in the text (e.g. '2027', 'by Q3 2025')")
    geography: list[str] = Field(default_factory=list, max_length=10,
                                 description="Up to 10 places, regions, countries or jurisdictions mentioned in the text")


# --- Step 3: NER + Classification ---

def _get_canonical_keys() -> set[str]:
    """Lazily load canonical mega-trend keys. Cached after first call."""
    if not hasattr(_get_canonical_keys, "_cache"):
        try:
            from pipeline.config import get_mega_trend_keys
            _get_canonical_keys._cache = set(get_mega_trend_keys())
        except Exception:
            _get_canonical_keys._cache = set()
    return _get_canonical_keys._cache


class ClassificationResult(BaseModel):
    """Output of NER and classification step."""
    verticals: list[Vertical] = Field(description="Applicable verticals (can be cross-vertical)")
    pestel: list[PestelDimension] = Field(description="PESTEL dimensions")
    tags: list[str] = Field(description="Descriptive tags")
    trend_signal_type: TrendSignalType = Field(description="Type of trend signal")
    regions: list[str] = Field(default_factory=lambda: ["Global"], description="Geographic regions")
    mega_trend: str | None = Field(default=None, description="Canonical mega-trend key from mega_trends.yaml")

    @field_validator("mega_trend", mode="before")
    @classmethod
    def validate_mega_trend(cls, v: str | None) -> str | None:
        if v is None or v == "" or v == "null":
            return None
        canonical = _get_canonical_keys()
        if not canonical:
            return v  # No taxonomy loaded, accept as-is
        if v in canonical:
            return v
        # Try normalizing: lowercase, strip brackets/annotations, replace spaces/hyphens with underscores
        normalized = re.sub(r"\s*\[.*?\]", "", v)  # strip LLM annotations like "[declining]"
        normalized = normalized.lower().strip().replace("-", "_").replace(" ", "_")
        if normalized in canonical:
            return normalized
        # No match — log and set to None rather than storing garbage
        logger.warning("LLM returned non-canonical mega_trend '%s', setting to None", v)
        return None


# --- Step 5: Content Generation ---

class GeneratedContent(BaseModel):
    """Output of content generation step."""
    title: str = Field(description="Article title")
    summary: str = Field(description="2-3 sentence summary")
    body: str = Field(description="Full article body (150-250 words)")
    source_attribution: str = Field(description="Source attribution line with URL")
