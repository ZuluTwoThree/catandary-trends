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
    # Seit 2026-08-02 NICHT mehr 'granted': eine Freigabe für Hundefutter räumt
    # den Lebensmittelpfad nicht frei. Genau diese Verwechslung setzte die
    # EU-Zelle von Cultivated Meat auf "clear to act" (Bene Meat, Eintrag im
    # Futtermittel-Katalog).
    assert reg_subtype(_row(
        "FDA Clears Precision Fermentation Lamb Protein for Dog Food",
        ["regulatory_approval"])) == "other"
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
    # Die US-Zulassung darf die EU nicht handlungsfähig machen. Seit der
    # asymmetrischen Beweislast (2026-08-02) ist die EU-Antwort hier "keine
    # Aussage" statt H3: EIN Konsultationssignal traegt keine Behauptung ueber
    # das Fehlen eines Zulassungswegs.
    assert eu["horizon"] is None
    assert eu["basis"] == "silent"
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
                  "rationale": "Zulassung verweigert.", "n_signals": 4,
                  "basis": "denied"}
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
        for i in range(MIN_N_NEGATIVE)
    ]
    # Damit die Absenz überhaupt lesbar ist, muss das Feld ANDERSWO eine
    # Zulassung zeigen — sonst ist "keine gefunden" ein Sensor-Ausfall, kein
    # Befund. Hier: eine EFSA-Zulassung, also EU, während wir US bewerten.
    elsewhere = {"id": 99, "trend_signal_type": "regulation",
                 "title_en": "EFSA approves the battery coating additive",
                 "summary_en": "", "tags": [], "regions": ["EU"],
                 "event_date": date(2026, 2, 1), "semantic": True}
    rows = rows + [elsewhere]
    # Seit der zweiten Prüfrunde gilt das UNABHÄNGIG vom Regulierungs-Schalter:
    # die Absenz-H3 ist ersatzlos gestrichen. Sie lag in jedem geprüften Fall
    # falsch, weil Zulassungen oft nachrangig erteilt werden (Bundesstaat,
    # Notified Body, Norm) oder älter sind als das Nachrichtenfenster. H3 setzt
    # nur noch ein positiv festgestelltes Hindernis.
    assert cell_regulatory(rows, "US", today, regulated=False)["horizon"] is None
    assert cell_regulatory(rows, "US", today, regulated=True)["horizon"] is None
    # Mit einem echten Hindernis sagt dieselbe Zelle sehr wohl H3.
    blocked = rows + [
        {"id": 500 + i, "trend_signal_type": "regulation",
         "title_en": "State bans the battery chemistry from sale outright",
         "summary_en": "", "tags": [], "regions": ["US"],
         "event_date": date(2026, 3, 1), "semantic": True} for i in range(3)]
    assert cell_regulatory(blocked, "US", today, regulated=True,
                           field_terms=["battery", "chemistry"])["horizon"] == "H3"


def test_unregulated_explicit_bans_still_read_as_headwind():
    today = date(2026, 8, 2)
    rows = [
        {"id": i, "trend_signal_type": "regulation",
         "title_en": "City bans e-bike batteries from public transit",
         "summary_en": "", "tags": [], "regions": ["US"],
         "event_date": date(2026, 3, 1), "semantic": True}
        for i in range(3)
    ]
    cell = cell_regulatory(rows, "US", today, regulated=False,
                           field_terms=["batter", "e-bike"])
    assert cell["horizon"] == "H3"
    assert "blockade" in cell["rationale"]
    # Ohne Feldbezug zaehlt ein mehrdeutiges "bans" NICHT — sonst macht ein
    # Verbot der Konkurrenztechnologie das eigene Feld blockiert.
    assert cell_regulatory(rows, "US", today, regulated=False)["horizon"] is None


def test_adoption_absence_is_no_call_when_market_is_established():
    """Wer kauft sonst die Produkte? Adoption H3 neben Markt H1 war inkohärent."""
    today = date(2026, 8, 2)
    rows = [
        {"id": 1, "trend_signal_type": "market_shift", "title_en": "x",
         "summary_en": "", "tags": ["t"], "regions": ["US"],
         "event_date": date(2026, 1, 1), "semantic": True}
        for _ in range(MIN_N_NEGATIVE)
    ]
    assert cell_adoption(rows, "US", today, market_horizon="H1")["horizon"] is None
    # Ohne etablierten Markt bleibt Abwesenheit eine echte H3-Aussage.
    assert cell_adoption(rows, "US", today, market_horizon="H3")["horizon"] == "H3"
    assert cell_adoption(rows, "US", today)["horizon"] == "H3"


# --------------------------------------------------------------------------
# Kalibrierlauf 2026-08-02, zweite Runde: sechs Suchbegriffe gegen die Realität
# geprüft (u. a. per Websuche). Vier Fehlaussagen, vier Fixes.
# --------------------------------------------------------------------------
from pipeline.radar_horizons import (MARKET_PILOT, MIN_N_GRANTED,
                                     MIN_N_NEGATIVE, cell_market,
                                     compute_cells)


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
    rows = [_reg("Regulator rejects cultivated meat for the retail market"),
            _reg("Member state bans cultivated meat from sale", day=(2026, 4, 1)),
            _reg("Second member state prohibits cultivated meat outright",
                 day=(2026, 5, 1))]
    cell = cell_regulatory(rows, "EU", today, regulated=False,
                           field_terms=["cultivated", "meat"])
    assert cell["horizon"] == "H3"
    assert "blockade" in cell["rationale"]


def test_single_approval_does_not_carry_a_jurisdiction():
    """Ein einzelnes Silage-Signal hob Precision Fermentation in der EU auf H1;
    dieselbe Mechanik machte aus einer Tierfutter-Zulassung eine Aussage ueber
    Humanlebensmittel (Proposal §7.3). Echte Zulassungen werden mehrfach
    berichtet."""
    today = date(2026, 8, 2)
    noise = [_reg(f"EU consultation round {i} on the framework") for i in range(8)]
    # Das Tierfutter-Signal zählt inzwischen GAR NICHT mehr — anderer
    # Regulierungspfad. Für die Schwellen-Aussage hier ein Signal auf dem
    # richtigen Pfad, das aber allein bleibt.
    assert reg_subtype(_reg("Bene Meat Receives First-Ever EU Approval for Pet Food",
                            tags=["regulatory_approval"])) == "other"
    one = [_reg("EFSA authorises the novel food for sale",
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


# ==========================================================================
# Kalibrierlauf 2026-08-02, dritte Runde: 52 Technologiefelder, sieben
# Fach-Scouts mit Websuche. ~340 geprüfte Zellen, 150+ belegte Fehlaussagen.
# Die Scouts fanden UNABHÄNGIG VONEINANDER dieselben Mechanismen; jeder Test
# hier fixiert einen davon, nicht den Einzelfall.
# ==========================================================================
from pipeline.radar_horizons import (  # noqa: E402
    ANCHOR_MIN_CONTAINMENT, ESSAY_TITLE, MIN_N_NEGATIVE, MIN_N_REGULATORY,
    REG_COVERAGE_SHARE,
    WORLD, blockade_match, dedupe_events, field_terms_of, in_jurisdiction,
    mentions_field, reg_subtype,
)


class _NoCpc:
    """cell_technology fragt den CPC-Anker ab; hier gibt es keinen."""
    def execute(self, *a, **k):
        return self
    def fetchone(self):
        return None


def _sig(title, typ="product_launch", region="US", day=(2026, 3, 1), tags=("t",)):
    return {"id": abs(hash(title)) % 10**7, "trend_signal_type": typ,
            "title_en": title, "summary_en": "", "tags": list(tags),
            "regions": [region], "event_date": date(*day), "semantic": True}


# -- 1. Schweigen ist kein Befund ------------------------------------------
def test_unmatched_regulation_signal_is_other_not_forming():
    """Der folgenschwerste Fehler: 'forming' war der DEFAULT-Rückgabewert, also
    die Antwort auf 'kein Muster hat gegriffen'. Korpusweit fielen 92,6 % aller
    Regulatorik-Signale in einen Eimer, dessen Bedeutung 'der Zulassungsweg wird
    erst gebaut' ist."""
    assert reg_subtype(_sig("Gene therapy makers wonder if they can make a "
                            "profit in Europe", "regulation", tags=[])) == "other"
    assert reg_subtype(_sig("Uniqure hemophilia B programme on hold after a "
                            "patient cancer diagnosis", "regulation",
                            tags=[])) == "other"
    # Ein echtes Pfad-Signal bleibt 'forming'.
    assert reg_subtype(_sig("EU opens a public consultation on the novel food "
                            "pathway", "regulation", tags=[])) == "forming"


def test_negative_calls_need_more_evidence_than_positive_ones():
    """Alle sieben Scouts fanden dasselbe: das Radar verweigerte die Aussage bei
    n=2 und behauptete 'kein Weg zum Markt' bei n=3. Eine positive Aussage stützt
    sich auf einen gefundenen Beleg, eine negative darauf, dass einer gefunden
    worden WÄRE."""
    assert MIN_N_NEGATIVE > MIN_N_REGULATORY
    assert MIN_N_NEGATIVE > MIN_N_GRANTED


def test_absence_is_never_a_call_in_a_thinly_covered_jurisdiction():
    """Gemessen: 93,4 % der zuordenbaren Zulassungen sind US-amerikanisch, 4,1 %
    europäisch. 'Keine EU-Zulassung gefunden' ist damit fast immer eine Aussage
    über unsere Quellen. Die Scouts fanden diese Fehlaussage für mRNA-Impfstoffe,
    CAR-T, Gentherapie, Insektenprotein und Mycoprotein — alle in der EU
    zugelassen."""
    today = date(2026, 8, 2)
    rows = [_sig(f"EU debates the approval framework, part {i}", "regulation",
                 region="EU", tags=[]) for i in range(MIN_N_NEGATIVE + 2)]
    rows.append(_sig("FDA approves the therapy", "regulation", region="US"))
    cell = cell_regulatory(rows, "EU", today, regulated=True)
    assert cell["horizon"] is None
    assert cell["basis"] == "uncovered"
    assert REG_COVERAGE_SHARE["EU"] < REG_COVERAGE_SHARE["US"]


def test_absence_needs_an_approval_visible_somewhere_in_the_field():
    """SAF wird von einer bindenden EU-Beimischungsquote und elf ASTM-Pfaden
    getragen, von denen keiner als 'Zulassung' formuliert ist. Findet sich für
    ein Feld NIRGENDS eine Zulassung, ist der Erkenner blind — nicht der Weg
    versperrt."""
    today = date(2026, 8, 2)
    rows = [_sig(f"US opens a consultation on the blending mandate ({i})",
                 "regulation", tags=[]) for i in range(MIN_N_NEGATIVE + 2)]
    cell = cell_regulatory(rows, "US", today, regulated=True)
    assert cell["horizon"] is None
    assert cell["basis"] == "unreadable"


# -- 2. Vorzeichen und Stadium ---------------------------------------------
def test_a_rejection_is_not_an_approval():
    """Psychedelika standen auf 'H1, 5 approvals since 2023 — clear to act'; drei
    der vier Belege meldeten ABLEHNUNGEN. Ursache war der Tag-Pfad: bei einer
    Ablehnungsmeldung vergibt die Klassifikation plausibel 'fda approval'."""
    assert reg_subtype(_sig("FDA rejects MDMA-assisted therapy for PTSD",
                            "regulation", tags=["fda approval"])) == "denied"
    assert reg_subtype(_sig("Agency issues a complete response letter",
                            "regulation", tags=["drug approval"])) == "denied"


def test_permission_to_study_is_not_permission_to_sell():
    """'FDA approves first xenotransplantation clinical trial' hob ein Feld ohne
    einzige Marktzulassung auf 'clear to act'."""
    assert reg_subtype(_sig("FDA approves first xenotransplantation clinical trial",
                            "regulation")) == "trial"
    assert reg_subtype(_sig("FDA approves Paradromics' brain-computer interface "
                            "trial for speech restoration", "regulation")) == "trial"
    assert reg_subtype(_sig("Neuralink receives FDA approval to implant and test "
                            "its device in people", "regulation")) == "trial"


def test_a_tag_alone_never_carries_an_approval():
    """Der Tag darf nur stützen, was der Text als Entscheidung meldet."""
    assert reg_subtype(_sig("The clinical threshold of neural integration",
                            "regulation", tags=["fda approval"])) != "granted"


def test_an_approval_counts_whatever_stage_3_typed_it():
    """Die beiden FDA-Zulassungen für orales Wegovy liegen im Korpus als
    `product_launch`; die Regulatorik-Zelle sah sie nie und meldete für den
    größten Medikamentenstart der Geschichte 'kein Zulassungsweg in den USA'."""
    today = date(2026, 8, 2)
    rows = [_sig("FDA approves oral Wegovy for chronic weight management",
                 "product_launch"),
            _sig("FDA approves orforglipron, the first oral GLP-1 pill",
                 "product_launch", day=(2026, 4, 1))]
    cell = cell_regulatory(rows, "US", today, regulated=True,
                           field_terms=["wegovy", "glp", "oral"])
    assert cell["horizon"] == "H1"


# -- 3. Objektbezug einer Blockade -----------------------------------------
def test_a_ban_on_the_rival_technology_is_not_a_headwind():
    """'EU formally bans sale of gas and diesel cars from 2035' zählte als
    regulatorischer Gegenwind GEGEN Elektroautos — es ist der stärkste denkbare
    Rückenwind."""
    txt = "EU formally bans sale of gas and diesel cars from 2035"
    assert blockade_match(txt, ["electric", "vehicle"]) is None
    assert blockade_match("Italy bans cultivated meat production and sale",
                          ["cultivated", "meat"]) is not None


def test_an_unrelated_ban_never_counts():
    assert blockade_match("Norway suspends Arctic seabed mining operations",
                          ["battery", "lithium"]) is None
    assert blockade_match("eBay announces ban on private sales of electric bicycles",
                          ["vehicle", "electric car"]) is None


# -- 4. Der Scope muss das Feld auch nennen --------------------------------
def test_signals_that_never_mention_the_field_do_not_count():
    """'CIRANDA Announces Two New Baking Chips' trug die Marktzelle von 'organ on
    a chip'; 'Ponnath Secures Organic Pork Supply via Vertical Integration' die
    von 'vertical farming'."""
    terms = field_terms_of("cultivated meat")
    assert not mentions_field(_sig("Nvidia unveils a new inference accelerator"),
                              terms)
    assert mentions_field(_sig("Mosa Meat files its EU novel food dossier"), terms)
    # Bewusste Grenze: ein einzelner Begriff genügt, damit Zulassungsmeldungen
    # nicht verloren gehen, die das Feld nur mit einem Wort nennen. Homonyme
    # ("chip") bleiben damit drin — das loest erst die Teilfeld-Zerlegung.


# -- 5. Meinungsstücke sind keine Produktstarts ----------------------------
def test_commentary_is_not_a_product_launch():
    """Sodium-Ion stand in den USA auf H1 wegen '9 commercial product launches',
    deren sichtbare Belege null Produkteinführungen enthielten."""
    for t in ["The Sodium Shift: Why Lithium's Reign May End",
              "The Solid-State Illusion",
              "Beyond Lithium: Rethinking Grid Storage",
              "The Decoupling of Decarbonization: Why Heat Pump Financing Matters"]:
        assert ESSAY_TITLE.search(t), t
    for t in ["CATL launches its first sodium-ion battery pack",
              "Dexcom Stelo now available over the counter"]:
        assert not ESSAY_TITLE.search(t), t


# -- 6. Ein Ereignis, drei Meldungen ---------------------------------------
def test_the_same_event_counts_once():
    """'3 approvals since 2024' für Mycoprotein/US war EIN GRAS-Bescheid,
    berichtet von drei Fachmedien."""
    rows = [_sig("Better Meat Co secures FDA GRAS letter for mycoprotein",
                 day=(2026, 3, 1)),
            _sig("Better Meat Co wins FDA GRAS status for its mycoprotein",
                 day=(2026, 3, 3)),
            _sig("FDA grants Better Meat Co GRAS clearance for mycoprotein",
                 day=(2026, 3, 5))]
    assert len(dedupe_events(rows)) == 1
    # Zwei echte, verschiedene Ereignisse bleiben zwei.
    assert len(dedupe_events([rows[0], _sig("Onego Bio receives GRAS letter for "
                                            "animal-free egg protein")])) == 2


# -- 7. Ein etablierter Markt hört auf, sich anzukündigen -------------------
def test_running_trade_reaches_h1_without_launch_events():
    """Guardants Bluttest (>1 Mrd. $ Umsatz), NatureWorks' PLA-Werk (seit 2002)
    und Starlink (12 Mio. Kunden) galten als 'nicht am Markt', weil ihre
    Markteinführung vor dem Fenster lag."""
    today = date(2026, 8, 2)
    rows = [_sig("Guardant reports 982 million dollars of assay revenue",
                 "market_shift"),
            _sig("Natera runs 770,000 clinical MRD tests in the year",
                 "market_shift", day=(2026, 4, 1)),
            _sig("Medicare sets reimbursement at 1,495 dollars per test",
                 "market_shift", day=(2026, 5, 1)),
            _sig("Installed base passes 3.5 million users", "consumer_behavior",
                 day=(2026, 6, 1))]
    cell = cell_market(rows, "US", today)
    assert cell["horizon"] == "H1"
    assert cell["basis"] == "trading"


def test_market_absence_is_no_call_when_the_field_sells_elsewhere():
    """mRNA-Impfstoffe und CAR-T standen auf 'kein Markt in der EU'."""
    today = date(2026, 8, 2)
    rows = ([_sig(f"US retail rollout continues ({i})") for i in range(6)]
            + [_sig(f"EU regulatory commentary ({i})", "market_shift", region="EU")
               for i in range(MIN_N_NEGATIVE + 1)])
    cells = compute_cells(_NoCpc(), rows, regions=["US", "EU"], today=today)
    eu = [c for c in cells if c["dimension"] == "market" and c["region"] == "EU"][0]
    assert eu["horizon"] is None
    assert eu["basis"] == "unconfirmed"


def test_market_is_silent_when_the_field_has_no_launch_signal_at_all():
    """Für mRNA-Impfstoffe, CAR-T, Silicon Photonics und neuromorphes Rechnen
    enthält der Korpus null Produktmeldungen — in keinem Jahr, in keiner Region.
    Dann misst die Dimension nichts."""
    today = date(2026, 8, 2)
    rows = [_sig(f"Research advances again ({i})", "research")
            for i in range(MIN_N_NEGATIVE + 3)]
    cell = cell_market(rows, "US", today)
    assert cell["horizon"] is None
    assert cell["basis"] == "blind"


# -- 8. Nachfrage ist nicht nur die Verbraucherstimme ----------------------
def test_procurement_counts_as_demand():
    """Nachfrage nach Netzspeichern, Offshore-Wind oder SMR erscheint als
    Auktion, Abnahmevertrag oder Erstattungsentscheid — vier Felder mit
    veröffentlichten Zuschlagspreisen standen auf 'demand unevidenced'."""
    today = date(2026, 8, 2)
    rows = [_sig("Italy's storage auction clears 10 GWh at a set price",
                 "market_shift"),
            _sig("Google signs a 500 MW offtake contract for the reactor",
                 "partnership", day=(2026, 4, 1)),
            _sig("Utility procurement adds 24 GW of orders", "market_shift",
                 day=(2026, 5, 1))]
    cell = cell_adoption(rows, "US", today)
    assert cell["horizon"] == "H1"


# -- 9. Der Patentanker darf nicht die Reife seiner Oberklasse vererben ----
def test_anchor_containment_threshold_separates_class_from_field():
    """G06N (maschinelles Lernen insgesamt) verankerte gleichzeitig Large Language
    Models, neuromorphes Rechnen UND Brain-Computer-Interfaces und vererbte allen
    dreien seinen Markt-Takeoff 2023. Gemessenes Containment: B33Y/Additive
    Manufacturing 0,205 gegen G06N/BCI 0,014."""
    assert 0.014 < ANCHOR_MIN_CONTAINMENT < 0.205
    assert ANCHOR_MIN_CONTAINMENT > 0.035   # G06N/neuromorphic
    assert ANCHOR_MIN_CONTAINMENT < 0.101   # H10K/Perowskit


# -- 10. Die Weltspalte ist eine Frage, kein Restposten --------------------
def test_world_column_is_the_union_not_the_unlocatable_rest():
    """'GLOBAL' war das Etikett für Artikel ohne Geografie — 49-56 % aller
    Signale. Als Spalte gelesen beantwortete sie 'was steht in dem, was wir nicht
    verorten konnten?'. Jetzt heißt sie: gibt es das irgendwo?"""
    row = _sig("A launch in Japan", region="APAC")
    assert in_jurisdiction(row, WORLD)
    assert not in_jurisdiction(row, "US")


def test_world_regulatory_counts_an_approval_from_any_authority():
    today = date(2026, 8, 2)
    rows = [_sig("Singapore Food Agency approves the cultivated product",
                 "regulation", region="APAC"),
            _sig("FDA approves the cultivated product", "regulation",
                 region="US", day=(2026, 4, 1))]
    assert cell_regulatory(rows, WORLD, today)["horizon"] == "H1"


# -- 11. Kopplung darf beobachteten Handel nicht überschreiben -------------
def test_coupling_does_not_fire_on_an_absence_derived_regulatory_call():
    """SAF/US las wörtlich: '7 commercial product launches — on the market.
    Capped at H3 …' — das Radar hatte die richtige Antwort, erkannte den
    Widerspruch und löste ihn zugunsten des schwächeren Schlusses auf."""
    market = {"horizon": "H1", "score": 0.9, "method": "gates",
              "rationale": "7 launches.", "n_signals": 40, "basis": "commercial"}
    for weak in ("absence", "silent", "uncovered", None):
        reg = {"horizon": "H3", "score": 0.15, "method": "gates",
               "rationale": "nichts gefunden", "n_signals": 6, "basis": weak}
        assert couple_market_to_regulation(market, reg, "EU")["horizon"] == "H1"


def test_coupling_still_fires_on_a_positively_identified_blockade():
    market = {"horizon": "H1", "score": 0.9, "method": "gates",
              "rationale": "x", "n_signals": 40, "basis": "commercial"}
    reg = {"horizon": "H3", "score": 0.15, "method": "gates",
           "rationale": "Italien verbietet den Verkauf.", "n_signals": 6,
           "basis": "blockade"}
    assert couple_market_to_regulation(market, reg, "EU")["horizon"] == "H3"


# ==========================================================================
# Zufallszug 2026-08-02: 50 Trendfelder gleichverteilt aus 7.037 Pipeline-Tags
# gezogen (Seed 20260802). Er traf überwiegend Querschnittsthemen statt
# Technologien — und deckte damit auf, dass das Radar sie bereitwillig platzierte:
# „cost reduction" stand in JEDER Zelle auf H1, „disruption" fast durchgehend.
# ==========================================================================
from pipeline.radar_horizons import (  # noqa: E402
    FIELD_FOCUS1_MIN, FIELD_FOCUS2_MIN, FIELD_PATENT_MIN, FIELD_PATENT_STRONG,
    field_coherence,
)


class _CpcConn:
    """Liefert eine feste Zahl CPC-zugeordneter Trends."""

    def __init__(self, matched):
        self.matched = matched

    def execute(self, *a, **k):
        return self

    def fetchone(self):
        return {"c": self.matched}


def _vert(v, n):
    return [{"id": i, "primary_vertical": v} for i in range(n)]


def test_a_concrete_field_passes_the_field_check():
    """Gemessen an echten Feldern: Elektroautos 0,87 Zwei-Branchen-Fokus,
    grüner Wasserstoff 0,97, Gentherapie 1,00."""
    rows = _vert("ECO", 65) + _vert("TECH", 22) + _vert("BIZ", 13)
    out = field_coherence(_CpcConn(25), rows)     # nur 25 % patentabgebildet
    assert out["is_field"], "Zwei Branchen tragen das Feld allein"
    assert out["note"] is None


def test_a_patent_heavy_field_passes_even_when_it_spans_industries():
    rows = _vert("ECO", 33) + _vert("TECH", 30) + _vert("BIZ", 20) + _vert("FOOD", 17)
    assert field_coherence(_CpcConn(78), rows)["is_field"]   # 78 % Patentanteil


def test_a_cross_cutting_theme_is_flagged_not_placed():
    """„cost reduction": 0,61 Zwei-Branchen-Fokus, 0,37 Patentanteil — und ein
    Radar, das in jeder Zelle H1 sagte."""
    rows = (_vert("TECH", 38) + _vert("BIZ", 23) + _vert("HEALTH", 15)
            + _vert("ECO", 12) + _vert("FOOD", 12))
    out = field_coherence(_CpcConn(37), rows)
    assert not out["is_field"]
    assert out["note"] and "cross-cutting theme" in out["note"]
    # Der Text muss dem Nutzer sagen, was er stattdessen tun soll.
    assert "concrete technology" in out["note"]


def test_field_thresholds_are_ordered_sanely():
    assert FIELD_FOCUS2_MIN > FIELD_FOCUS1_MIN
    assert FIELD_PATENT_STRONG > FIELD_PATENT_MIN
