"""Förderaufrufe (EU F&T, grants.gov, NSF) — Datensätze ohne Netz geprüft (Owner 2026-10-10)."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ingest_funding_calls as f  # noqa: E402
from pipeline.tiers import is_public_funding, tier_of  # noqa: E402

FUT = (date.today() + timedelta(days=90)).isoformat()
PAST = "2024-04-18"


def test_eu_record_open_with_details():
    m = {"identifier": ["HORIZON-CL5-2027-03-D5-18"], "title": ["Enhanced battery durability"],
         "status": ["31094501"], "deadlineDate": [FUT + "T00:00:00.000+0000"], "startDate": ["2030-01-01T00:00"]}
    det = {"description": "<p>Expected&nbsp;Outcome: ships</p>", "actions": [{"status": {"abbreviation": "Forthcoming"}}],
           "budgetOverviewJSONItem": {"budgetTopicActionMap": {"x": [{"budgetYearMap": {"2027": 30000000}}]}}}
    url, title, ex, pub = f.eu_record(m, det)
    assert url.endswith("/topic-details/HORIZON-CL5-2027-03-D5-18") and title == "Enhanced battery durability"
    assert ex.startswith("[Funding call · EU HORIZON · HORIZON-CL5-2027-03-D5-18 · forthcoming · deadline " + FUT)
    assert "€30.0M" in ex and "Expected Outcome: ships" in ex
    assert pub == date.today().isoformat()               # Zukunftsdatum → heute


def test_eu_record_drops_closed_and_expired():
    base = {"identifier": ["DIGITAL-2024-X"], "title": ["T"], "status": ["31094502"]}
    assert f.eu_record({**base, "deadlineDate": [FUT]}, {"actions": [{"status": {"abbreviation": "Closed"}}]}) is None
    assert f.eu_record({**base, "deadlineDate": [PAST]}) is None
    assert f.eu_record({**base, "deadlineDate": [PAST, FUT]}) is not None    # spätere Frist noch offen


def test_grants_record_strips_contacts_and_expired():
    hit = {"id": "1", "number": "DE-FOA-1", "title": "Hydrogen hubs", "agency": "DOE", "oppStatus": "posted",
           "openDate": "01/15/2026", "closeDate": ""}
    syn = {"synopsisDesc": "<p>Fund hubs. Contact jane.doe@doe.gov or +1 (202) 555-0100.</p>",
           "awardCeiling": "5000000", "agencyContactName": "Jane Doe"}
    url, title, ex, pub = f.grants_record(hit, syn)
    assert "@" not in ex and "555" not in ex and "Jane" not in ex
    assert "up to $5.0M per award" in ex and pub == "2026-01-15"
    assert f.grants_record({**hit, "closeDate": "01/01/2020"}, syn) is None


def test_sources_are_public_funding_tier():
    for name, _ in f.SOURCES.values():
        assert is_public_funding(name)
        assert tier_of(name, "api") == "funding"
