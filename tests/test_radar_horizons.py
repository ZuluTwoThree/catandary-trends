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


def test_reg_subtype_approaching_is_not_granted():
    """Zweiter Fund desselben Musters (Kalibrierlauf 2026-07-31).

    „Approaches EU Approval" trägt den Tag `regulatory_approval` und nennt mit
    EFSA eine EU-Behörde — belegt aber das Gegenteil: es gibt noch keine
    Zulassung. Ohne diesen Guard hob der Titel ein regulatorisch blockiertes
    Feld auf H1.
    """
    row = _row(
        "Impossible Foods Approaches EU Approval Following Second Positive EFSA Opinion",
        ["regulatory_approval"],
    )
    assert reg_subtype(row) != "granted"
    assert reg_subtype(_row("Startup nears approval for novel food")) != "granted"
    assert reg_subtype(_row("Agency issues positive opinion on the dossier")) != "granted"


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
    # Begründungstexte sind nutzerseitig und daher englisch (Produktsprache),
    # während Kommentare und Docstrings deutsch bleiben.
    assert "without an approval" in out["rationale"]


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


# --------------------------------------------------------------------------
# Li-Ionen-Kalibrierung (Owner-Befund 2026-08-02): "fast durchgängig H3,
# obwohl Diffusion stattgefunden hat". Drei Ursachen, drei Fixes.
# --------------------------------------------------------------------------
from pipeline.radar_horizons import (
    ESTABLISHED_MIN_ACTIVE_YEARS,
    ESTABLISHED_MIN_FIRST_AGE,
    ESTABLISHED_MIN_LAUNCHES,
    _market_history,
    cell_adoption,
    cell_technology,
)


def _mk_rows(first_year, last_year, per_year=4, sig="product_launch"):
    return [
        {"id": y * 100 + i, "title_en": f"Launch {y}-{i}", "summary_en": "",
         "trend_signal_type": sig, "regions": ["US"], "tags": ["x"],
         "pestel": [], "semantic": True, "event_date": date(y, 6, 1)}
        for y in range(first_year, last_year + 1)
        for i in range(per_year)
    ]


class _NoAnchorConn:
    """Anker-Abfrage liefert nichts — erzwingt Fallback-Pfade."""

    def execute(self, sql, params=None):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []


def test_established_market_history_lifts_technology_to_h1():
    """Der Li-Ionen-Fall: vieljährige Markt-Historie IST der Skalen-Nachweis.

    News messen Veränderung, nicht Zustand — laufende Forschung färbte den
    Signalmix forschungsseitig und deckelte eine längst diffundierte
    Technologie auf H2/H3.
    """
    today = date(2026, 8, 2)
    rows = _mk_rows(2011, 2026)  # 16 Jahre, 64 Launches
    hist = _market_history(rows, today)
    assert hist["established"]
    cell = cell_technology(_NoAnchorConn(), rows, today)
    assert cell["horizon"] == "H1"
    assert cell["method"] == "market_history"
    assert "2011" in cell["rationale"]


def test_recent_market_history_does_not_count_as_established():
    """Gegenprobe Quantum/Precision Fermentation: Markt erst seit 2020/21 —
    egal wie viele Signale, das Etablierungs-Gate darf nicht öffnen."""
    today = date(2026, 8, 2)
    rows = _mk_rows(2020, 2026, per_year=40)  # 280 Launches, aber jung
    assert not _market_history(rows, today)["established"]
    cell = cell_technology(_NoAnchorConn(), rows, today)
    assert cell["horizon"] != "H1"


def test_established_needs_sustained_years_not_just_an_old_first_signal():
    # Ein alter Ausreißer plus junge Welle: erstes aktives Jahr alt genug,
    # aber zu wenige aktive Jahre insgesamt.
    today = date(2026, 8, 2)
    rows = _mk_rows(2010, 2010) + _mk_rows(2023, 2026)
    assert not _market_history(rows, today)["established"]


def test_unregulated_absence_is_no_call_not_blocked():
    """Batterien brauchen keine Zulassung — 'keine Zulassung gefunden' ist dort
    keine Blockade-Aussage. H3 hieße 'beobachten, Weg wird erst gebaut' für
    eine Technologie in jedem Telefon."""
    today = date(2026, 8, 2)
    rows = [
        {"id": i, "trend_signal_type": "regulation",
         "title_en": "Panel discusses battery standards roadmap",
         "summary_en": "", "tags": [], "regions": ["US"],
         "event_date": date(2026, 3, 1), "semantic": True}
        for i in range(4)
    ]
    assert cell_regulatory(rows, "US", today, regulated=False)["horizon"] is None
    # Dieselben Signale in einer regulierten Domäne: Abwesenheit = blockiert.
    assert cell_regulatory(rows, "US", today, regulated=True)["horizon"] == "H3"


def test_unregulated_explicit_bans_still_read_as_headwind():
    today = date(2026, 8, 2)
    rows = [
        {"id": i, "trend_signal_type": "regulation",
         "title_en": "City bans e-bike batteries from public transit",
         "summary_en": "", "tags": [], "regions": ["US"],
         "event_date": date(2026, 3, 1), "semantic": True}
        for i in range(3)
    ]
    cell = cell_regulatory(rows, "US", today, regulated=False)
    assert cell["horizon"] == "H3"
    assert "headwind" in cell["rationale"]


def test_adoption_absence_is_no_call_when_market_is_established():
    """Wer kauft sonst die Produkte? Adoption H3 neben Markt H1 war inkohärent."""
    today = date(2026, 8, 2)
    rows = [
        {"id": 1, "trend_signal_type": "market_shift", "title_en": "x",
         "summary_en": "", "tags": ["t"], "regions": ["US"],
         "event_date": date(2026, 1, 1), "semantic": True}
        for _ in range(5)
    ]
    assert cell_adoption(rows, "US", today, market_horizon="H1")["horizon"] is None
    # Ohne etablierten Markt bleibt Abwesenheit eine echte H3-Aussage.
    assert cell_adoption(rows, "US", today, market_horizon="H3")["horizon"] == "H3"
    assert cell_adoption(rows, "US", today)["horizon"] == "H3"


# --------------------------------------------------------------------------
# Kalibrierlauf 2026-08-02, zweite Runde: sechs Suchbegriffe gegen die Realität
# geprüft (u. a. per Websuche). Vier Fehlaussagen, vier Fixes.
# --------------------------------------------------------------------------
from pipeline.radar_horizons import MARKET_PILOT, MIN_N_GRANTED, cell_market, compute_cells


def _reg(title, region="EU", tags=None, day=(2026, 3, 1)):
    return {"id": abs(hash(title)) % 10**6, "trend_signal_type": "regulation",
            "title_en": title, "summary_en": "", "tags": tags or [],
            "regions": [region], "event_date": date(*day), "semantic": True}


def test_regulatory_friction_is_not_a_blockade():
    """Gene Therapy stand in der EU auf H3 'expliziter Gegenwind' — bei 11+
    EMA-Zulassungen in der Realität. Ausloeser waren 'Regulatory Uncertainty'
    und 'FDA shifts'. Unsicherheit verlangsamt einen offenen Weg, sie
    verschliesst ihn nicht."""
    today = date(2026, 8, 2)
    rows = [_reg("Regulatory Uncertainty Shapes Global Gene Therapy Strategy"),
            _reg("Regulatory complexity creates barriers and delays for developers"),
            _reg("Industry flags hurdles and lag in the approval pipeline")]
    cell = cell_regulatory(rows, "EU", today, regulated=False)
    assert cell["horizon"] is None, "Reibung darf keine Blockade-Aussage erzeugen"


def test_explicit_ban_still_counts_as_blockade():
    today = date(2026, 8, 2)
    # Bewusst ohne Verfahrensvokabular: "pending"/"under review" wären ein
    # LAUFENDES Verfahren (H2) und würden die Blockade-Aussage zu Recht schlagen.
    rows = [_reg("Regulator rejects the dairy analogue outright"),
            _reg("Member state bans the product from sale")]
    cell = cell_regulatory(rows, "EU", today, regulated=False)
    assert cell["horizon"] == "H3"
    assert "headwind" in cell["rationale"]


def test_single_approval_does_not_carry_a_jurisdiction():
    """Ein einzelnes Silage-Signal hob Precision Fermentation in der EU auf H1;
    dieselbe Mechanik machte aus einer Tierfutter-Zulassung eine Aussage ueber
    Humanlebensmittel (Proposal §7.3). Echte Zulassungen werden mehrfach
    berichtet."""
    today = date(2026, 8, 2)
    noise = [_reg(f"EU consultation round {i} on the framework") for i in range(8)]
    one = [_reg("Bene Meat Receives First-Ever EU Approval for Pet Food",
                tags=["regulatory_approval"])]
    assert cell_regulatory(noise + one, "EU", today)["horizon"] != "H1"
    two = one + [_reg("Second firm secures EU approval for the same process",
                      tags=["regulatory_approval"], day=(2026, 5, 1))]
    assert cell_regulatory(noise + two, "EU", today)["horizon"] == "H1"
    assert MIN_N_GRANTED == 2


def test_pilot_plants_do_not_prove_a_market():
    """Direct Air Capture stand in der EU auf H1 'on the market' — gestuetzt auf
    Ucaneos Berliner Anlage mit 150 t CO2/Jahr, kommerzieller Ausbau ab 2027.
    Eine Pilotanlage belegt Machbarkeit, nicht Kaeuflichkeit."""
    today = date(2026, 8, 2)
    rows = [{"id": i, "trend_signal_type": "product_launch",
             "title_en": "Ucaneo launches first-of-a-kind pilot DAC facility in Berlin",
             "summary_en": "", "tags": ["x"], "regions": ["EU"], "pestel": [],
             "event_date": date(2026, 5, 1), "semantic": True} for i in range(6)]
    cell = cell_market(rows, "EU", today)
    assert cell["horizon"] == "H2"
    assert "pilot" in cell["rationale"].lower()
    assert MARKET_PILOT.search("first-of-a-kind pilot plant")


def test_technology_cannot_be_pre_competitive_beside_approvals():
    """Gene Therapy: 70 erteilte US-Zulassungen im Korpus, Technologie trotzdem
    H3 — weil klinische Forschung 98 % des Signalvolumens stellt. Das ist die
    Signatur eines reifen regulierten Felds, nicht eines unreifen."""
    today = date(2026, 8, 2)
    rows = ([{"id": 1000 + i, "trend_signal_type": "research", "title_en": "trial",
              "summary_en": "", "tags": ["t"], "regions": ["US"], "pestel": [],
              "event_date": date(2026, 1, 1), "semantic": True} for i in range(40)]
            + [_reg("FDA approves the therapy for a rare disease", region="US",
                    tags=["regulatory_approval"]),
               _reg("FDA clears a second gene therapy for market", region="US",
                    tags=["regulatory_approval"], day=(2026, 4, 1))])
    cells = compute_cells(_NoAnchorConn(), rows, regions=["US"], today=today)
    tech = [c for c in cells if c["dimension"] == "technology"][0]
    assert tech["horizon"] == "H2", "Zulassungen widerlegen 'vorwettbewerblich'"
    assert "coherence" in tech["method"]
    # Aber nicht bis H1: Skalen- und Kostenreife bleibt unbelegt.
    assert tech["horizon"] != "H1"
