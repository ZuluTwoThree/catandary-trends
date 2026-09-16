"""Which lead-time tier a signal belongs to.

Owner 2026-09-15: "ein science trend ist nicht das selbe wie ein markttrend,
selbst wenn thematisch deckungsgleich". Perovskite is researched, then
patented, then funded for scale-up, then argued about in the trade press — four
conversations about one topic, each starting at its own time. A detector that
pools them dates the earliest one and calls it the trend.

The four tiers are the ones the lead-time layer already uses
(`foresight.TIER_FILTERS`). This module is the row-level twin of those SQL
conditions: the same rules, applied in Python while streaming, so a tier can be
attached to every document without a second query.

Keep the two in step. TIER_FILTERS decides what a tier-scoped QUERY returns,
`tier_of` decides what a streamed row is counted as; if they disagree, the
lead-time page and the emerging page disagree about the same document.
"""
from __future__ import annotations

TIERS = ("science", "patent", "funding", "market")

# Matched against source_name, case-insensitive, as prefixes.
PATENT_PREFIXES = ("google patents", "epo ")
FUNDING_PREFIXES = ("nih reporter", "nsf ", "openaire", "ukri", "sec form d",
                    "sbir/sttr", "sbir ", "cordis")
SCIENCE_MARKERS = ("preprints",)
MARKET_TYPES = {"trade_media", "press_wire", "brand"}


def tier_of(source_name: str | None, source_type: str | None,
            signal_type: str | None = None) -> str | None:
    """science | patent | funding | market | None.

    Order matters: funding registries and patent offices are both stored as
    source_type='api' and are only told apart by name, and a preprint server is
    'api' too while belonging to science.

    `signal_type` (trends.trend_signal_type) refines the market tier, on the
    owner's definition of 2026-09-16: research means research BY INSTITUTIONS,
    a startup raising money is a funding signal however loudly the trade press
    reports it, and the market conversation only starts when products actually
    launch. A trade-press item classified 'funding' therefore counts as
    funding, not market — 39,852 of 661,416 trade-press rows, measured. The
    classification is the pipeline's judgement, not a fact, so this refines the
    tier rather than defining it.
    """
    name = (source_name or "").strip().lower()
    stype = (source_type or "").strip().lower()
    if name.startswith(PATENT_PREFIXES):
        return "patent"
    if name.startswith(FUNDING_PREFIXES):
        return "funding"
    if stype == "research" or any(m in name for m in SCIENCE_MARKERS):
        return "science"
    if stype in MARKET_TYPES:
        return "funding" if (signal_type or "").strip().lower() == "funding" else "market"
    if name.startswith("openalex"):
        return "science"
    return None


def tier_counts(rows) -> dict[str, int]:
    out = {t: 0 for t in TIERS}
    for r in rows:
        t = tier_of(r.get("source_name"), r.get("source_type"),
                    r.get("trend_signal_type"))
        if t:
            out[t] += 1
    return out
