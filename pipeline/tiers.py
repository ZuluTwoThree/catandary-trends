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


def tier_case_sql(t: str = "t", s: str = "s") -> tuple[str, list[str]]:
    """SQL CASE expression that assigns the same tier as `tier_of`, row by row.

    Used to fill and refresh `trends.tier` (2026-09-17), the column the
    per-tier HNSW indexes are built on. `t` is the trends alias (source_name,
    trend_signal_type), `s` the sources alias (source_type). Same precedence as
    `tier_of`; rows that belong to no tier get 'none' so they are never
    re-examined. Returns (expression, params) with `?` placeholders.
    """
    name = f"LOWER(TRIM(COALESCE({t}.source_name, '')))"
    stype = f"LOWER(TRIM(COALESCE({s}.source_type, '')))"
    sig = f"LOWER(TRIM(COALESCE({t}.trend_signal_type, '')))"
    params: list[str] = []
    patent = " OR ".join([f"{name} LIKE ?"] * len(PATENT_PREFIXES))
    params += [p + "%" for p in PATENT_PREFIXES]
    funding = " OR ".join([f"{name} LIKE ?"] * len(FUNDING_PREFIXES))
    params += [p + "%" for p in FUNDING_PREFIXES]
    science = f"{stype} = 'research' OR " + " OR ".join([f"{name} LIKE ?"] * len(SCIENCE_MARKERS))
    params += [f"%{m}%" for m in SCIENCE_MARKERS]
    market_types = ", ".join(f"'{x}'" for x in sorted(MARKET_TYPES))
    expr = (
        "CASE"
        f" WHEN {patent} THEN 'patent'"
        f" WHEN {funding} THEN 'funding'"
        f" WHEN {science} THEN 'science'"
        f" WHEN {stype} IN ({market_types}) THEN"
        f"  CASE WHEN {sig} = 'funding' THEN 'funding' ELSE 'market' END"
        f" WHEN {name} LIKE ? THEN 'science'"
        " ELSE 'none' END"
    )
    params.append("openalex%")
    return expr, params
