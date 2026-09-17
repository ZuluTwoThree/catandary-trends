"""Row-level tier mapping — the twin of foresight.TIER_FILTERS."""

from pipeline.tiers import TIERS, tier_counts, tier_of


def test_patents_are_told_apart_from_funding_although_both_are_api():
    assert tier_of("Google Patents (TECH)", "api") == "patent"
    assert tier_of("EPO DOCDB (HEALTH)", "api") == "patent"
    assert tier_of("NIH RePORTER (US Biomedical Funding)", "api") == "funding"
    assert tier_of("SBIR/STTR Awards (US Startup R&D Funding)", "api") == "funding"
    assert tier_of("CORDIS EU Research Projects", "api") == "funding"
    assert tier_of("SEC Form D", "api") == "funding"


def test_preprint_servers_are_science_even_though_they_are_stored_as_api():
    assert tier_of("arXiv Preprints", "api") == "science"
    assert tier_of("biorxiv Preprints", "api") == "science"
    assert tier_of("OpenAlex Science (HEALTH)", "api") == "science"
    assert tier_of("OpenAlex fresh: Batteries", "api") == "science"


def test_journals_are_science_and_trade_press_is_market():
    assert tier_of("Nature Medicine", "research") == "science"
    assert tier_of("TechCrunch", "trade_media") == "market"
    assert tier_of("PR Newswire", "press_wire") == "market"
    assert tier_of("Siemens Newsroom", "brand") == "market"


def test_an_unknown_row_belongs_to_no_tier_rather_than_a_wrong_one():
    assert tier_of(None, None) is None
    assert tier_of("Something", "api") is None


def test_tier_counts_sums_a_batch():
    rows = [
        {"source_name": "arXiv Preprints", "source_type": "api"},
        {"source_name": "TechCrunch", "source_type": "trade_media"},
        {"source_name": "TechCrunch", "source_type": "trade_media"},
        {"source_name": "Mystery", "source_type": None},
    ]
    counts = tier_counts(rows)
    assert counts == {"science": 1, "patent": 0, "funding": 0, "market": 2}
    assert set(counts) == set(TIERS)


def test_the_python_rules_agree_with_the_sql_tier_filters():
    """If these drift apart, the lead-time page and the emerging page disagree
    about the same document."""
    from pipeline.foresight import TIER_FILTERS
    assert set(TIER_FILTERS) == set(TIERS)
    # the SQL patterns for patents and funding, as row-level cases
    assert tier_of("Google Patents (ECO)", "api") == "patent"
    assert tier_of("EPO DOCDB (TECH)", "api") == "patent"
    for name in ("NIH RePORTER x", "NSF Awards", "OpenAIRE projects", "UKRI grants",
                 "SEC Form D"):
        assert tier_of(name, "api") == "funding"


# --- Owner-Definition 2026-09-16 -------------------------------------------
# "Forschung ist Forschung von Institutionen, keine vagen Startup-Berichte.
#  Startups sind für mich verbunden mit Funding und erst ein möglicher
#  Markttrend, wenn sie Produkte wirklich lancieren."

def test_a_startup_raising_money_is_funding_however_loudly_the_press_reports_it():
    assert tier_of("AgFunderNews", "trade_media", "funding") == "funding"
    assert tier_of("vegconomist", "trade_media", "funding") == "funding"
    assert tier_of("PR Newswire", "press_wire", "funding") == "funding"


def test_the_market_starts_at_the_product():
    assert tier_of("vegconomist", "trade_media", "product_launch") == "market"
    assert tier_of("Food Dive", "trade_media", "market_shift") == "market"
    assert tier_of("Food Dive", "trade_media", "regulation") == "market"


def test_press_coverage_of_a_study_is_still_press_not_institutional_research():
    # a trade-press piece ABOUT research is coverage; the research tier holds
    # what institutions themselves publish
    assert tier_of("Food Navigator", "trade_media", "research") == "market"
    assert tier_of("Nature Food", "research", "research") == "science"


def test_the_signal_type_never_moves_a_registry_or_a_patent_office():
    assert tier_of("NIH RePORTER (US)", "api", "product_launch") == "funding"
    assert tier_of("Google Patents (FOOD)", "api", "funding") == "patent"
    assert tier_of("arXiv Preprints", "api", "funding") == "science"


def test_without_a_signal_type_the_mapping_is_unchanged():
    assert tier_of("TechCrunch", "trade_media") == "market"
    assert tier_of("TechCrunch", "trade_media", None) == "market"
