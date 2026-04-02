"""Pydantic schemas for LLM pipeline structured outputs."""

import logging
from typing import Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# --- Verticals & PESTEL ---

Vertical = Literal[
    "FOOD", "TECH", "HEALTH", "ECO", "DESIGN",
    "FASHION", "BIZ", "CULTURE", "SOCIAL", "LUXURY",
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


# --- Step 2: Structured Extraction ---

class ExtractionResult(BaseModel):
    """Output of the structured extraction step (purely extractive)."""
    brand_name: str | None = Field(default=None, description="Brand or company name mentioned")
    product_name: str | None = Field(default=None, description="Product or service name")
    source_type: str | None = Field(default=None, description="Type of source (press release, article, etc.)")
    key_claims: list[str] = Field(default_factory=list, description="Key claims from the text")


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
        # Try normalizing: lowercase, replace spaces/hyphens with underscores
        normalized = v.lower().strip().replace("-", "_").replace(" ", "_")
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
