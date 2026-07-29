"""Tests für die Horizont-Einordnung (pipeline/radar_horizons.py).

Die Fälle in test_reg_subtype_* und test_authority_* sind **echte
Fehlklassifikationen** aus dem Kalibrierlauf 2026-07-30. Sie sind hier fixiert,
weil sie das Radar still falsch gemacht hätten: eine erfundene EU-Zulassung
verwandelt ein regulatorisch blockiertes Feld in ein handlungsfähiges.
"""

from datetime import date

import pytest

from pipeline.radar_horizons import (
    couple_market_to_regulation,
    normalize_region,
    reg_authority,
    reg_subtype,
    regions_of,
    cell_regulatory,
)


# --------------------------------------------------------------------------
# Jurisdiktions-Normalisierung
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("US", "US"), ("us", "US"), ("United States", "US"),
        ("North America", "US"), ("Wisconsin", "US"), ("California", "US"),
        ("EU", "EU"), ("Europe", "EU"), ("europe", "EU"), ("Germany", "EU"),
        ("Belgium", "EU"), ("Netherlands", "EU"),
        ("UK", "UK"), ("United Kingdom", "UK"), ("England", "UK"),
        ("Israel", "IL"), ("israel", "IL"),
        ("global", "GLOBAL"), ("Global", "GLOBAL"), ("worldwide", "GLOBAL"),
        ("Singapore", "APAC"), ("Australia", "APAC"), ("China", "APAC"),
    ],
)
def test_normalize_region_folds_synonyms(raw, expected):
    assert normalize_region(raw) == expected


def test_normalize_region_refuses_to_guess():
    # Lieber keine Zelle als eine falsch zugeordnete Zulassung.
    assert normalize_region("Latin America") is None
    assert normalize_region("Africa") is None
    assert normalize_region("") is None


def test_regions_of_handles_json_and_list():
    assert regions_of({"regions": '["US", "Germany"]'}) == {"US", "EU"}
    assert regions_of({"regions": ["Israel", "Global"]}) == {"IL", "GLOBAL"}
    assert regions_of({"regions": None}) == set()


# --------------------------------------------------------------------------
# Regulatorik-Sub-Typ
# --------------------------------------------------------------------------
def _row(title, tags=None, summary=""):
    return {"title_en": title, "summary_en": summary, "tags": tags or []}


def test_reg_subtype_granted_on_real_approvals():
    assert reg_subtype(_row(
        "Remilk's Precision Fermentation Dairy Is the Second to Earn U.S. GRAS Status",
        ["gras_status"])) == "granted"
    assert reg_subtype(_row(
        "FDA Clears Precision Fermentation Lamb Protein for Dog Food",
        ["regulatory_approval"])) == "granted"
    assert reg_subtype(_row(
        "Onego Bio Receives FDA “No Questions” Letter for Egg Protein")) == "granted"


def test_reg_subtype_lobbying_is_not_an_approval():
    """Der teuerste Fehler des Kalibrierlaufs.

    Der Tag lautet 'regulatory_approval', die Aussage ist aber das Gegenteil:
    es gibt keine Zulassung, deshalb wird für eine geworben.
    """
    row = _row(
        "Precision Fermentation Leaders In Europe Form A Coalition To Advance "
        "Regulatory Approval",
        ["regulatory_approval"],
    )
    assert reg_subtype(row) != "granted"
    assert reg_subtype(row) == "forming"


def test_reg_subtype_filed_vs_forming():
    # Laufendes Verfahren → H2
    assert reg_subtype(_row(
        "Startup submitted novel food dossier, now under review")) == "filed"
    # Konsultation/Strategie → der Weg wird erst gebaut → H3
    assert reg_subtype(_row(
        "EU Opens Public Consultation on Biotech Act II")) == "forming"
    assert reg_subtype(_row(
        "Fermentation Can Futureproof the EU Food System – But Only With "
        "Regulatory Reform")) == "forming"


def test_reg_subtype_gap():
    assert reg_subtype(_row(
        "Startups tackle the black box of the EU novel foods process, where no "
        "approval exists")) in {"forming", "gap"}


# --------------------------------------------------------------------------
# Behörden-Attribution
# --------------------------------------------------------------------------
def test_authority_beats_company_home_country():
    """`regions` markiert den Firmensitz, nicht die zulassende Jurisdiktion.

    Vivici ist niederländisch (regions=[EU]), die Zulassung ist eine US-GRAS-
    Entscheidung. Ohne Behörden-Attribution landet sie in der EU-Zelle.
    """
    text = "Vivici Secures FDA 'No Questions' Letter for Animal-Free Whey"
    assert reg_authority(text) == "US"


def test_authority_from_explicit_jurisdiction():
    # Kein Ministerium genannt, Jurisdiktion aber eindeutig.
    assert reg_authority(
        "Remilk Is the First Precision Fermentation Dairy Approval In Israel") == "IL"
    assert reg_authority("Bene Meat Receives First-Ever EU Approval") == "EU"


def test_authority_none_when_unattributable():
    assert reg_authority(
        "Regulatory Renewal Signals Deepening Integration of Synthetic Biology"
    ) is None


def test_regulatory_cell_ignores_approvals_of_other_jurisdictions():
    today = date(2026, 7, 30)
    rows = [
        {"id": 1, "trend_signal_type": "regulation",
         "title_en": "Vivici Secures FDA 'No Questions' Letter for Animal-Free Whey",
         "summary_en": "", "tags": ["fda_approval"], "regions": ["EU"],
         "event_date": date(2026, 3, 1), "semantic": True},
        {"id": 2, "trend_signal_type": "regulation",
         "title_en": "EU Opens Public Consultation on Biotech Act II",
         "summary_en": "", "tags": [], "regions": ["EU"],
         "event_date": date(2026, 5, 1), "semantic": True},
    ]
    eu = cell_regulatory(rows, "EU", today)
    # Die US-Zulassung darf die EU nicht handlungsfähig machen.
    assert eu["horizon"] == "H3"
    us = cell_regulatory(rows, "US", today)
    # Umgekehrt zählt sie für die USA, obwohl regions=[EU] steht.
    assert us["horizon"] == "H1"


# --------------------------------------------------------------------------
# Kopplung Markt ↔ Zulassung
# --------------------------------------------------------------------------
def test_market_cannot_outrank_regulation_in_regulated_domain():
    market = {"horizon": "H1", "score": 0.9, "method": "gates",
              "rationale": "16 Produktstarts in EU.", "n_signals": 40}
    regulatory = {"horizon": "H3", "score": 0.15, "method": "gates",
                  "rationale": "Keine Zulassung.", "n_signals": 4}
    out = couple_market_to_regulation(market, regulatory, "EU")
    assert out["horizon"] == "H3"
    assert "reg_coupled" in out["method"]
    assert "ohne Zulassung" in out["rationale"]


def test_coupling_leaves_consistent_cells_alone():
    market = {"horizon": "H2", "score": 0.5, "method": "gates",
              "rationale": "x", "n_signals": 5}
    regulatory = {"horizon": "H1", "score": 1.0, "method": "gates",
                  "rationale": "y", "n_signals": 5}
    out = couple_market_to_regulation(market, regulatory, "US")
    assert out["horizon"] == "H2"
    assert out["method"] == "gates"


def test_coupling_is_noop_without_a_known_regulatory_horizon():
    market = {"horizon": "H1", "score": 0.9, "method": "gates",
              "rationale": "x", "n_signals": 9}
    regulatory = {"horizon": None, "score": None, "method": "gates",
                  "rationale": "zu wenig", "n_signals": 1}
    assert couple_market_to_regulation(market, regulatory, "UK")["horizon"] == "H1"
