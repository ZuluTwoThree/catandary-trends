"""Rules instead of the relevance head for patents and funding (Owner 2026-10-02).

The distill relevance head was trained on the 8B's verdicts on PRESS entries ("does
this make a trend article?"). On the signal path (scripts/signal_batch.py) it decided
alone, at 0.5, for research, patents and funding too. Measured (docs/filter_audit_2026-
10-02.md): of the patents it dropped, 92-96 % were signals in every score band — the only
misses were plant varieties; of the funding it dropped, 42-87 % — the true misses were
recognisable by rule (real-estate and services Reg-D vehicles, NIH subproject bookings,
rows without any description, absurd amounts). For press and research the head separates
and stays.

So: patents and funding are judged by the rules below, everything else by the head.
`verdict(entry)` returns None when the entry is NOT a rule tier (→ head decides), "" to
keep it, or a short reason to drop it (stored as filter_reason "rule:<reason>").
"""
from __future__ import annotations

import re

from pipeline.tiers import tier_of

RULE_TIERS = ("patent", "funding")

# plant varieties and cultivars (CPC A01H / US plant patents): "SOYBEAN CULTIVAR 01220205",
# "Phalaenopsis plant named 'PHA964388'", "HYBRID TOMATO VARIETY …" — but not "a variety of"
PLANT = re.compile(r"\bcultivars?\b|\bplant named\b|\bvariet(?:y|ies)\b(?!\s+of\b)", re.I)

# SEC Form D industries that are not company or technology finance: real-estate vehicles
# ("Commercial": 18,630 dropped, 833 kept), services, construction, restaurants, travel,
# insurance, investment vehicles. Technology, biotech, pharma, health, energy,
# manufacturing, agriculture, telecom, computers and retail stay.
FORM_D_OUT = {
    "commercial", "business services", "construction", "restaurants", "other travel",
    "tourism and travel services", "airlines and airports", "health insurance",
    "coal mining", "residential", "reits and finance", "other real estate",
    "pooled investment fund", "investing", "commercial banking", "insurance", "lodging",
    "other banking and financial services", "investment banking", "hedge fund",
    "private equity fund", "venture capital fund", "other investment fund",
}
VEHICLE = re.compile(r"\b(DST|Fund|Funds|Holdings?|HoldCo|Properties|Apartments|Partners|"
                     r"Realty|REIT|Investors|Portfolio)\b", re.I)
INDUSTRY = re.compile(r"Industry:\s*([^.]+)\.")
OFFERING = re.compile(r"Total offering \$([\d,.]+)\s*([MK]?)")
NIH_SUBPROJECT = "This subproject is one of many research subprojects"
MIN_OFFERING_USD = 25_000
MIN_DESCRIPTION = 40
AWARD_NOTICE = re.compile(r"\b(wins|secures|receives)\b.*\b(award|grant|STTR|SBIR)\b", re.I)


def rule_tier(entry: dict) -> str | None:
    if entry.get("pub_number"):
        return "patent"
    t = tier_of(entry.get("source_name"), entry.get("source_type"))
    return t if t in RULE_TIERS else None


def _description(excerpt: str) -> str:
    """The funding text without its "[Funding · …]" header and N/A filler."""
    text = re.sub(r"^\s*\[[^\]]*\]\s*", "", excerpt or "")
    text = re.sub(r"\bN/A\b|ABSTRACT NOT PROVIDED|DESCRIPTION \(provided by applicant\):", "", text)
    text = re.sub(r"[^:]{0,120}\(\d+ employees[^)]*\):", "", text)   # SBIR company line
    return " ".join(text.split())


def _offering_usd(excerpt: str) -> float | None:
    m = OFFERING.search(excerpt or "")
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return v * (1e6 if m.group(2) == "M" else 1e3 if m.group(2) == "K" else 1)


def verdict(entry: dict) -> str | None:
    tier = rule_tier(entry)
    if tier is None:
        return None
    title = entry.get("title") or ""
    excerpt = entry.get("excerpt") or ""
    if tier == "patent":
        return "plant_variety" if PLANT.search(title) else ""
    # funding
    if "Form D" in (entry.get("source_name") or "") or "SEC Form D" in excerpt:
        m = INDUSTRY.search(excerpt)
        if m and m.group(1).strip().lower() in FORM_D_OUT:
            return "form_d_industry"
        if VEHICLE.search(title):
            return "form_d_vehicle"
        usd = _offering_usd(excerpt)
        if usd is not None and usd < MIN_OFFERING_USD:
            return "form_d_amount"
        return ""
    if NIH_SUBPROJECT in excerpt:
        return "nih_subproject"
    if len(_description(excerpt)) >= MIN_DESCRIPTION:
        return ""
    # No abstract. A grant's own title usually names the project ("Strategic and digital
    # improvements of a drain water microalgae product") and carries the topic; an award
    # notice ("X wins $70k SBIR Phase I award") names only the company — no topic, so it
    # would only add an "award" blob to the space.
    if AWARD_NOTICE.search(title) or len(title.split()) < 4:
        return "no_description"
    return ""
