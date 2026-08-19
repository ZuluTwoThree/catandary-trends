"""Tests fuer die Regex-Stufe der Presse-Funding-Extraktion (#87 Phase 0).

Die LLM-Stufe wird nicht getestet (externer Endpoint); hier geht es um
Betrags-/Runden-/Firmen-Parsing aus Titeln und den VC-Fonds-Filter.
"""
from scripts.extract_press_rounds import (
    _parse_amount, _parse_company, _parse_round, regex_extract,
)


def test_amount_usd_million():
    assert _parse_amount("Acme raises $50M Series B") == (50e6, "USD", "$50M")


def test_amount_eur_spelled_out():
    val, cur, _ = _parse_amount("Solarize raises €12 million Series A")
    assert (val, cur) == (12e6, "EUR")


def test_amount_billion_and_commas():
    val, cur, _ = _parse_amount("Megacorp secures £1.2bn")
    assert (val, cur) == (1.2e9, "GBP")
    val, cur, _ = _parse_amount("raises $100,000 in pre-seed")
    assert (val, cur) == (1e5, "USD")


def test_amount_rejects_pocket_change():
    # "$50 gift card" darf keine Runde werden
    assert _parse_amount("win a $50 gift card")[0] is None


def test_round_labels():
    assert _parse_round("closes $5M Seed round") == "Seed"
    assert _parse_round("raises Series B extension") == "Series B"
    assert _parse_round("lands pre-seed funding") == "Pre-Seed"
    assert _parse_round("quarterly results") is None


def test_company_before_verb_and_based_prefix():
    assert _parse_company("Solarize raises €12 million") == "Solarize"
    assert _parse_company("Berlin-based Solarize raises €12M") == "Solarize"
    assert _parse_company("Exclusive: Acme Robotics secures $8M") == "Acme Robotics"
    assert _parse_company("No funding verb here") is None


def test_regex_extract_full_confidence():
    res = regex_extract("Acme Robotics raises $8M Seed led by XYZ", "")
    assert res["company"] == "Acme Robotics"
    assert res["amount_value"] == 8e6
    assert res["round_label"] == "Seed"
    assert res["confidence"] == 0.8


def test_regex_extract_vc_fund_noise_filtered():
    res = regex_extract("Sequoia raises $850M new fund", "")
    assert res["round_label"] == "vc_fund"
    assert res["confidence"] == 0.0


def test_regex_extract_amount_fallback_from_excerpt():
    res = regex_extract("Acme secures fresh capital",
                        "The startup announced a $25 million Series C.")
    assert res["amount_value"] == 25e6
    assert res["round_label"] == "Series C"


def test_company_descriptor_titles_reduced_to_name():
    assert _parse_company("Australian wind farm monitoring startup Ping raises $1.3M") == "Ping"
    assert _parse_company("WebOps platform Pantheon raises $100M") == "Pantheon"


def test_company_generic_subjects_rejected():
    assert _parse_company("This startup raised $43M to build a hive mind") is None
    assert _parse_company("The company raises $10M") is None


def test_fund_noise_not_triggered_by_investor_fund_names():
    res = regex_extract("WebOps platform Pantheon raises $100M from SoftBank Vision Fund", "")
    assert res["round_label"] != "vc_fund"
    assert res["company"] == "Pantheon"
    res = regex_extract("Sequoia closes $850M new fund", "")
    assert res["round_label"] == "vc_fund"
