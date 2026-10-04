"""Crossref months for research works OpenAlex dates to 1 January (scripts/history_redate.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.history_redate import bare, month_of, resolve


def dp(*parts):
    return {"date-parts": [list(parts)]}


def test_online_beats_print_and_registration():
    it = {"published-online": dp(2023, 3, 9), "published-print": dp(2023, 5), "created": dp(2023, 2, 1)}
    assert month_of(it, 2023) == (3, "published-online")


def test_year_only_fields_fall_back_to_the_doi_registration_in_the_same_year():
    it = {"issued": dp(2023), "published-online": dp(2023), "created": dp(2023, 3, 27)}
    assert month_of(it, 2023) == (3, "created")


def test_a_registration_in_a_later_year_is_a_back_filed_doi_not_a_date():
    it = {"issued": dp(2010), "created": dp(2014, 6, 2)}
    assert month_of(it, 2010) == (None, "year-only")


def test_a_month_in_another_year_does_not_count():
    it = {"published-print": dp(2012, 1), "published-online": dp(2011, 12, 20)}
    assert month_of(it, 2012) == (1, "published-print")
    assert month_of({}, 2012) == (None, "year-only")


def test_doi_urls_are_normalised():
    assert bare("https://doi.org/10.1039/D3TA00388D") == "10.1039/d3ta00388d"


def test_an_unanswered_doi_is_skipped_not_marked_year_only():
    """A batch that failed four times leaves its DOIs out of the cache. That is
    "unknown", not "not at Crossref": the row must keep month_source NULL so the
    next run asks again (review 2026-10-04: --apply used to file them as year-only
    for good, and the re-run filter never saw them again)."""
    row = {"id": 7, "doi": "10.1000/x", "y": 2021}
    assert resolve(row, {}) == ("skip", None, "crossref unreachable")
    assert resolve(row, {"10.1000/x": {}}) == ("year-only", None, "not at Crossref")
    assert resolve(row, {"10.1000/x": {"issued": dp(2021, 4)}}) == ("move", 4, "issued")
    assert resolve(row, {"10.1000/x": {"issued": dp(2021)}}) == ("year-only", None, "year-only")
    assert resolve({"id": 8, "doi": None, "y": 2021}, {}) == ("year-only", None, "no DOI")
