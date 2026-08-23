"""Mapping-Tests fuer den CORDIS-SME-Ingester (#87 Phase 0).

Getestet wird die reine Abbildung Beteiligung+Projekt -> raw_entry-Tupel:
SME/PRC-Filter, EUR-Formatierung, Datums-Fallback (ecSignatureDate vor
startDate), URL-Eindeutigkeit pro (Projekt, Organisation) und die
[Funding · …]-Excerpt-Konvention.
"""
from scripts.ingest_cordis import _eur, _date, _map_org


ORG = {
    "projectID": "101069359", "projectAcronym": "SolDAC",
    "organisationID": "912743326", "name": "LOMARTOV SL",
    "SME": "true", "activityType": "PRC",
    "city": "BURJASSOT", "country": "ES",
    "organizationURL": "https://lomartov.com",
    "role": "participant", "ecContribution": "299250",
}
PROJ = {
    "id": "101069359", "acronym": "SolDAC",
    "title": "Solar-to-chemicals conversion",
    "startDate": "2022-09-01", "ecSignatureDate": "2022-06-15",
    "objective": "The project develops direct air capture powered by sunlight.",
}


def test_eur_formats_scales():
    assert _eur("299250") == "EUR 299k"
    assert _eur("2500000") == "EUR 2.5M"
    assert _eur("0") == "undisclosed"
    assert _eur("") == "undisclosed"


def test_date_prefers_signature_then_start():
    assert _date("2022-06-15", "2022-09-01") == "2022-06-15"
    assert _date("", "2022-09-01") == "2022-09-01"
    assert _date("2022-06-15 10:30:00", None) == "2022-06-15"
    assert _date("", "") is None


def test_map_org_happy_path():
    url, title, excerpt, date = _map_org(ORG, PROJ, "Horizon Europe")
    assert url == "https://cordis.europa.eu/project/id/101069359#org-912743326"
    assert title == "LOMARTOV SL secures EUR 299k Horizon Europe grant (SolDAC)"
    assert excerpt.startswith("[Funding · Horizon Europe · SME · BURJASSOT, ES · EUR 299k] ")
    assert "lomartov.com" in excerpt and "direct air capture" in excerpt
    assert date == "2022-06-15"


def test_map_org_filters_non_sme_and_non_prc():
    assert _map_org({**ORG, "SME": "false"}, PROJ, "Horizon Europe") is None
    assert _map_org({**ORG, "SME": ""}, PROJ, "Horizon Europe") is None
    # Universitaet mit (irrtuemlichem) SME-Flag bleibt draussen
    assert _map_org({**ORG, "activityType": "HES"}, PROJ, "Horizon Europe") is None


def test_map_org_requires_ids_and_date():
    assert _map_org({**ORG, "organisationID": ""}, PROJ, "Horizon Europe") is None
    assert _map_org(ORG, {**PROJ, "startDate": "", "ecSignatureDate": ""},
                    "Horizon Europe") is None


def test_map_org_without_project_row_is_skipped():
    # organization.csv-Zeile, deren Projekt (noch) nicht im Dump ist
    assert _map_org(ORG, {}, "Horizon Europe") is None
