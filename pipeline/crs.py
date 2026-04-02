"""Catandary Relevance Score (CRS)

A composite score (0–100) measuring trend relevance across five dimensions:

1. Signal Clarity (25%)    — How clearly identifiable is the trend signal?
2. Cross-Industry (25%)    — How many industry verticals does it affect?
3. PESTEL Breadth (20%)    — How broadly does it impact society/economy/tech?
4. Source Authority (15%)  — How authoritative is the original source?
5. Signal Maturity (15%)   — What type of signal is it? (research > product launch)

The CRS is designed to differentiate trend signals by structural importance,
not just source quality. A research finding affecting 3 verticals across
political and technological dimensions scores higher than a single-vertical
product launch from a press wire.
"""

# --- Dimension weights (must sum to 1.0) ---
W_CLARITY = 0.25
W_CROSS_INDUSTRY = 0.25
W_PESTEL = 0.20
W_SOURCE = 0.15
W_MATURITY = 0.15

# --- Signal Maturity: score by signal type (0.0–1.0) ---
SIGNAL_TYPE_SCORES = {
    "research": 1.0,        # Academic/scientific — highest structural impact
    "patent": 0.95,         # IP filings signal committed R&D investment
    "regulation": 0.90,     # Regulatory signals reshape entire industries
    "market_shift": 0.75,   # Structural market changes
    "funding": 0.70,        # Capital allocation signals market confidence
    "partnership": 0.60,    # Strategic alliances indicate convergence
    "consumer_behavior": 0.55,  # Demand-side shifts
    "product_launch": 0.40, # Individual products — lowest structural weight
}

# --- Source Authority: score by source type (0.0–1.0) ---
SOURCE_TYPE_SCORES = {
    "trade_media": 1.0,     # Specialized industry press — highest authority
    "press_wire": 0.75,     # Official press releases — authoritative but promotional
    "brand": 0.65,          # Brand newsrooms — first-party but biased
    "api": 0.60,            # API data (Exploding Topics etc.)
    "radar": 0.45,          # Discovery layer (Trendhunter excerpts) — lowest
}


def compute_crs(
    confidence: float,
    num_verticals: int,
    num_pestel: int,
    signal_type: str,
    source_type: str | None,
) -> int:
    """Compute the Catandary Relevance Score (0–100).

    Args:
        confidence: LLM confidence score (0.0–1.0)
        num_verticals: Number of assigned verticals (1–10)
        num_pestel: Number of PESTEL dimensions (0–6)
        signal_type: One of the TrendSignalType values
        source_type: Source type from sources table

    Returns:
        Integer score 0–100
    """
    # 1. Signal Clarity: map confidence 0.6–1.0 to 0.0–1.0
    #    (below 0.6 is filtered out by the pipeline)
    clarity = min(1.0, max(0.0, (confidence - 0.6) / 0.4))

    # 2. Cross-Industry Impact: logarithmic scaling
    #    1 vertical = 0.3, 2 = 0.65, 3 = 0.85, 4+ = 1.0
    cross_map = {1: 0.30, 2: 0.65, 3: 0.85}
    cross_industry = cross_map.get(num_verticals, 1.0)

    # 3. PESTEL Breadth: diminishing returns
    #    0 = 0.0, 1 = 0.45, 2 = 0.75, 3 = 0.90, 4+ = 1.0
    pestel_map = {0: 0.0, 1: 0.45, 2: 0.75, 3: 0.90}
    pestel = pestel_map.get(num_pestel, 1.0)

    # 4. Source Authority
    source = SOURCE_TYPE_SCORES.get(source_type or "radar", 0.45)

    # 5. Signal Maturity
    maturity = SIGNAL_TYPE_SCORES.get(signal_type, 0.40)

    # Weighted sum
    raw = (
        W_CLARITY * clarity
        + W_CROSS_INDUSTRY * cross_industry
        + W_PESTEL * pestel
        + W_SOURCE * source
        + W_MATURITY * maturity
    )

    # Scale to 0–100 and round
    return min(100, max(0, round(raw * 100)))


def compute_crs_from_trend(trend: dict, source_type: str | None = None) -> int:
    """Compute CRS from a trend dict (as returned by db.get_trends)."""
    import json

    confidence = trend.get("confidence") or trend.get("trend_score") or 0.8

    verticals = trend.get("verticals", [])
    if isinstance(verticals, str):
        verticals = json.loads(verticals)

    pestel = trend.get("pestel", [])
    if isinstance(pestel, str):
        pestel = json.loads(pestel)

    signal_type = trend.get("trend_signal_type", "product_launch")

    return compute_crs(
        confidence=confidence,
        num_verticals=len(verticals),
        num_pestel=len(pestel),
        signal_type=signal_type,
        source_type=source_type,
    )
