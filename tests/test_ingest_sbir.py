"""Mapping-Tests fuer den SBIR/STTR-Ingester (#87 Phase 0).

Der Ingester liest den offiziellen Bulk-CSV; hier wird die reine
Zeilen-Abbildung getestet (DB-frei): Betrags-/Datums-Parsing, URL-Bau
aus Contract/Tracking, Skip-Regeln und die Excerpt-Konventionen des
Funding-Tiers ([Funding · …]-Praefix, 2000-Zeichen-Kappung).
"""
from scripts.ingest_sbir import _amount, _award_date, _map_row


def _row(**over):
    base = {
        "Company": "AGILE DATA DECISIONS, INC.",
        "Award Title": "AI-DLCS: AI for Data Labeling",
        "Agency": "Department of Homeland Security",
        "Phase": "Phase I",
        "Program": "SBIR",
        "Agency Tracking Number": "24.1 DHS241-002-0076-I",
        "Contract": "70RSAT24C00000033",
        "Proposal Award Date": "05/07/2024",
        "Award Year": "2024",
        "Award Amount": "171,433",
        "Number Employees": "6",
        "Company Website": "http://agiledd.ai",
        "City": "Houston",
        "State": "TX",
        "Abstract": "The Department of Homeland Security grapples with vast datasets.",
    }
    base.update(over)
    return base


def test_amount_parses_commas_and_scales():
    assert _amount("171,433") == "$171k"
    assert _amount("2,500,000") == "$2.5M"
    assert _amount("950") == "$950"
    assert _amount("") == "undisclosed"
    assert _amount("0") == "undisclosed"
    assert _amount(None) == "undisclosed"


def test_award_date_prefers_real_date_and_falls_back_to_year():
    assert _award_date(_row()) == "2024-05-07"
    assert _award_date(_row(**{"Proposal Award Date": ""})) == "2024-01-01"
    assert _award_date(_row(**{"Proposal Award Date": "", "Award Year": ""})) is None
    # Unplausibles Jahr wird nicht als Datum erfunden
    assert _award_date(_row(**{"Proposal Award Date": "", "Award Year": "1901"})) is None


def test_map_row_happy_path():
    url, title, excerpt, date = _map_row(_row())
    assert url == "https://www.sbir.gov/awards?keyword=70RSAT24C00000033"
    assert title == ("AGILE DATA DECISIONS, INC. wins $171k SBIR Phase I award "
                     "(Department of Homeland Security)")
    assert excerpt.startswith("[Funding · SBIR Phase I · Department of Homeland Security "
                              "· Houston, TX · $171k] ")
    assert "6 employees" in excerpt and "agiledd.ai" in excerpt
    assert date == "2024-05-07"


def test_map_row_skips_without_company_or_key():
    assert _map_row(_row(Company="")) is None
    assert _map_row(_row(**{"Contract": "", "Agency Tracking Number": ""})) is None


def test_map_row_falls_back_to_tracking_number_url():
    mapped = _map_row(_row(Contract=""))
    assert mapped is not None
    assert mapped[0] == "https://www.sbir.gov/awards?keyword=24.1%20DHS241-002-0076-I"


def test_map_row_caps_excerpt_and_strips_nul():
    mapped = _map_row(_row(Abstract="x" * 5000, Company="Nul\x00Corp"))
    assert mapped is not None
    assert len(mapped[2]) <= 2000
    assert "\x00" not in mapped[1] and "\x00" not in mapped[2]


def test_award_date_rejects_source_typo_years():
    # Realer Fund im Bulk-CSV: "07/01/1905" — faellt auf das Award-Jahr zurueck
    row = _row(**{"Proposal Award Date": "07/01/1905", "Award Year": "2005"})
    assert _award_date(row) == "2005-01-01"
