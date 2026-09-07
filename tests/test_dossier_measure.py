"""Messkette der Scouting-Dossiers (M1/M2/M4/M6, 2026-09-06).

Belegte Ausgangslage (scratchpad-Analyse „Wo der Hebel liegt", 2026-09-06):

  M1  „GLP-1 and incretin technology" erzeugt 0 Patent-Volltexttreffer und
      schaltete damit die gesamte Messkette ab (dossiers.id=13,
      quant = {"off_topic": true}); „GLP-1 receptor agonist" trifft >= 2.000.
  M2  leadtime()["tiers"][t]["series"] und trajectory()["points"] wurden
      gerechnet und vor dem ersten Modell-Hop weggeworfen; die Messnotiz war
      notes[0] und flog beim FIFO-Verwurf als Erstes aus dem Report-Prompt.
  M4  46,7 % der Zitat-Instanzen des Perowskit-Laufs wurden gestrichen, weil
      das Modell katalogfremde URLs aus dem Gedaechtnis vervollstaendigte.
  M6  Der Paper-/Patent-Sweep lief nur bei Audit-Befund, seine Kappen (12/8)
      banden in 12 von 13 Laeufen, und ein Lauf nahm ein Patent auf, das der
      Bericht selbst als „unrelated to GLP-1 technology" bezeichnete.

Alles hier laeuft ohne DB und ohne GPU.
"""
import sys
import types

import pytest

from pipeline import dossier_quant as dq
from pipeline.dossier_check import check_result
from scripts import corpus_research as cr

# --- ein realistisches analyze_query()-Ergebnis (GLP-1-nah) ----------------
ANALYSIS = {
    "query": "GLP-1 incretin",
    "off_topic": False,
    "candidates": [
        {"symbol": "A61K38/26", "title": "Glucagons", "dist": 0.21,
         "n": 9900, "default": True},
        {"symbol": "C07K14/605", "title": "Glucagons", "dist": 0.24,
         "n": 6177, "default": True},
    ],
    "selection": ["A61K38/26", "C07K14/605"],
    "trajectory": {
        "direction": "maturing", "direction_de": "reift", "K_median": 9.4,
        "K_latest": 10.1, "calibrated": True, "rel_change": -0.1,
        "n_total": 13714,
        "points": [{"year": y, "K": 8.0 + (y - 2000) * 0.1, "n": 400 + y,
                    "complete": y <= 2019, "early_sparse": False}
                   for y in range(2000, 2024)],
        # Peak 2016; 2017-2019 sind ebenfalls "gesetzte" Jahrgaenge (2026-7),
        # 2020+ liegen im Zitations-Nachlauf und zaehlen nicht mit.
        "x_by_year": {str(y): [0.30 + (0.30 if y == 2016 else 0.0), 250]
                      for y in range(2010, 2027)},
    },
    "leadtime": {
        "tiers": {
            "science": {"n": 3200, "first": 2011, "takeoff": 2014,
                        "median": 2021, "is_share": True,
                        "series": {str(y): float(y - 2010) for y in range(2011, 2026)}},
            "patent": {"n": 13714, "first": 1990, "takeoff": 2016,
                       "median": 2018, "is_share": False,
                       "series": {str(y): float(200 + 40 * (y - 2010))
                                  for y in range(2010, 2026)}},
            "funding": {"n": 90, "first": 2014, "takeoff": None,
                        "median": 2020, "is_share": True,
                        "series": {str(y): 1.0 for y in range(2014, 2026)}},
            "market": {"n": 2124, "first": 2016, "takeoff": 2023,
                       "median": 2024, "is_share": True,
                       "series": {str(y): float(max(0, y - 2020) * 8)
                                  for y in range(2016, 2026)}},
        },
        "lead_science_market": 9, "lead_patent_market": 7,
        "concurrent": False, "established": False, "market_floored": False,
    },
    "top_patents": [
        {"pub": f"US-700000{i}-B2", "cites": 500 - i, "title": f"Hub patent {i}",
         "year": "2009", "url": f"https://worldwide.espacenet.com/p{i}"}
        for i in range(6)
    ],
    "verdict": "Established field; median ~9.4%/yr over the measured history.",
}

DYNAMICS = {"cycle_time": {"years": 11.0, "edges": 10864, "reason": None,
                           "since": "2015"}}


# ===========================================================================
# M1 — die Messung darf nicht still ausfallen
# ===========================================================================

class TestM1Normalization:
    def test_filler_words_are_removed(self):
        assert dq.normalize_topic("GLP-1 and incretin technology") == "GLP-1 incretin"
        assert dq.normalize_topic("solid-state battery market") == "solid-state battery"

    def test_cascade_starts_with_the_literal_order_phrase(self):
        c = dq.topic_cascade("GLP-1 and incretin technology")
        assert c[0] == "GLP-1 and incretin technology"
        assert c[1] == "GLP-1 incretin"
        assert "incretin" in c and "GLP-1" in c

    def test_cascade_is_deduplicated(self):
        c = dq.topic_cascade("incretin")
        assert c == ["incretin"]

    def _stub(self, monkeypatch, query_fn, codes_fn=None):
        mod = types.ModuleType("scripts.tech_analyze")
        mod.analyze_query = query_fn
        mod.analyze_codes = codes_fn or (lambda codes: {"selection": codes,
                                                        "trajectory": None,
                                                        "top_patents": []})
        monkeypatch.setitem(sys.modules, "scripts.tech_analyze", mod)

    def test_the_two_measured_phrases(self, monkeypatch):
        """Genau der gemessene Fall: die volle Auftragsphrase trifft 0 Patent-
        titel (off_topic), der Fachbegriff >= 2.000 (ok). Vorher endete das im
        stillen Ausfall; jetzt gewinnt die Rueckfallstufe."""
        seen = []

        def analyze(q, codes=None):
            seen.append(q)
            if q == "GLP-1 and incretin technology":
                return {"off_topic": True, "nearest_dist": 0.266,
                        "gate": {"verdict": "off_topic",
                                 "reason": "no patent title contains these terms together"},
                        "trajectory": None, "leadtime": None, "selection": []}
            return {**ANALYSIS, "query": q}

        self._stub(monkeypatch, analyze)
        found = dq.measure_topic("GLP-1 and incretin technology")
        assert found["analysis"] is not None
        assert found["phrase"] == "GLP-1 incretin"
        assert seen[:2] == ["GLP-1 and incretin technology", "GLP-1 incretin"]
        assert found["attempts"][0]["verdict"] == "off_topic"

    def test_ambiguous_gate_is_resolved_by_its_own_candidates(self, monkeypatch):
        def analyze(q, codes=None):
            if codes:
                return {**ANALYSIS, "selection": list(codes)}
            return {"off_topic": False, "nearest_dist": 0.2,
                    "gate": {"verdict": "ambiguous", "reason": "too broad"},
                    "candidates": [], "selection": ["A61K38/26"],
                    "trajectory": None, "leadtime": None}

        self._stub(monkeypatch, analyze)
        found = dq.measure_topic("incretin")
        assert found["analysis"] is not None
        assert "gate candidates" in found["resolved_via"]

    def test_corpus_cpc_is_the_last_fallback(self, monkeypatch):
        def analyze(q, codes=None):
            if codes:
                return {**ANALYSIS, "selection": list(codes)}
            return {"off_topic": True, "nearest_dist": 0.9,
                    "gate": {"verdict": "off_topic", "reason": "nothing"},
                    "trajectory": None, "leadtime": None, "selection": []}

        self._stub(monkeypatch, analyze)
        # signal_cpc kennt nur die 4-stellige Ebene; die feine Auswahl entsteht
        # als Schnitt mit der Embedding-Nachbarschaft.
        monkeypatch.setattr(dq, "corpus_cpc_codes", lambda t, **k: ["A61K", "A61P"])
        monkeypatch.setattr(dq, "fine_codes_in",
                            lambda p, subs, **k: ["A61K38/26"] if subs else [])
        found = dq.measure_topic("GLP-1 and incretin technology")
        assert found["analysis"] is not None
        assert "corpus-anchored CPC" in found["resolved_via"]
        assert "A61K38/26" in found["resolved_via"]

    def test_broad_subclasses_are_only_the_last_resort(self, monkeypatch):
        def analyze(q, codes=None):
            if codes == ["A61K"]:
                return {**ANALYSIS, "selection": list(codes)}
            if codes:
                return {"off_topic": False, "trajectory": None, "leadtime": None,
                        "gate": {"verdict": "ok"}, "selection": list(codes)}
            return {"off_topic": True, "nearest_dist": 0.9,
                    "gate": {"verdict": "off_topic", "reason": "nothing"},
                    "trajectory": None, "leadtime": None, "selection": []}

        self._stub(monkeypatch, analyze)
        monkeypatch.setattr(dq, "corpus_cpc_codes", lambda t, **k: ["A61K"])
        monkeypatch.setattr(dq, "fine_codes_in", lambda p, subs, **k: ["A61K38/99"])
        found = dq.measure_topic("GLP-1 and incretin technology")
        assert found["analysis"] is not None
        assert "broad" in found["resolved_via"]

    def test_total_failure_keeps_every_attempt(self, monkeypatch):
        def analyze(q, codes=None):
            return {"off_topic": True, "nearest_dist": 0.9,
                    "gate": {"verdict": "off_topic", "reason": "no signature"},
                    "trajectory": None, "leadtime": None, "selection": []}

        self._stub(monkeypatch, analyze)
        monkeypatch.setattr(dq, "corpus_cpc_codes", lambda t, **k: [])
        monkeypatch.setattr(dq, "fine_codes_in", lambda p, subs, **k: [])
        found = dq.measure_topic("purple unicorn vibes")
        assert found["analysis"] is None
        assert len(found["attempts"]) >= 2

    def test_failed_measurement_is_visible_in_the_dossier(self, monkeypatch):
        """Der zentrale M1-Punkt: faellt die Messung aus, steht das im
        Dokument — vorher verschwand sie spurlos."""
        def analyze(q, codes=None):
            return {"off_topic": True, "nearest_dist": 0.9,
                    "gate": {"verdict": "off_topic", "reason": "no signature"},
                    "trajectory": None, "leadtime": None, "selection": []}

        self._stub(monkeypatch, analyze)
        monkeypatch.setattr(dq, "corpus_cpc_codes", lambda t, **k: [])
        monkeypatch.setattr(dq, "fine_codes_in", lambda p, subs, **k: [])
        out = dq.build_quant_evidence("purple unicorn vibes")
        assert out["ok"] is False
        assert out["appendix"] and dq.MEASURE_HEADINGS[0] in out["appendix"]
        assert "failed" in out["appendix"]
        assert "purple unicorn vibes" in out["appendix"]
        assert "off_topic" in out["appendix"]

    def test_ambiguous_no_longer_claims_a_measurement(self):
        """Der alte Q1-Snippet-Default behauptete im ambiguous-Fall eine
        TIR-Messung, die nicht stattgefunden hatte."""
        amb = {"off_topic": False, "candidates": [], "selection": ["A61K38/26"],
               "trajectory": None, "leadtime": None}
        assert dq._measurable(amb) is False


# ===========================================================================
# M2 — Zeitreihen und Messanhang
# ===========================================================================

class TestM2Series:
    def test_note_carries_the_year_series(self):
        note = dq.format_quant_evidence(ANALYSIS, "GLP-1 incretin", None, "en",
                                        DYNAMICS)["note"]
        assert "patents by year" in note
        assert "improvement rate K(t) by year" in note
        assert "market by year" in note
        assert "Cycle time" in note and "11.0 years" in note
        assert "centrality" in note.lower()

    def test_appendix_is_code_generated_and_complete(self):
        app = dq.measurement_appendix(ANALYSIS, "GLP-1 incretin",
                                      {"resolved_via": "normalized phrase"},
                                      "en", DYNAMICS)
        assert dq.MEASURE_HEADINGS[0] in app
        assert "| year | research | patents | funding | market |" in app
        assert "Improvement-rate curve K(t)" in app
        assert "Lead time patents → market: ~7 years" in app
        assert "patent take-off 2016" in app and "market take-off 2023" in app
        assert "Cycle time: 11.0 years" in app
        assert "Centrality peak: 2016" in app
        assert "most recent cohorts are excluded" in app
        assert "Centrality has fallen since" in app
        assert "13,714 patents" in app
        assert "calibrated only to ~2019" in app

    def test_appendix_german(self):
        app = dq.measurement_appendix(ANALYSIS, "GLP-1", {}, "de", DYNAMICS)
        assert dq.MEASURE_HEADINGS[1] in app
        assert "Zykluszeit: 11.0 Jahre" in app
        assert "Zentralitäts-Peak: 2016" in app

    def test_centrality_peak_needs_density(self):
        assert dq.centrality_peak({"x_by_year": {"2019": [0.6, 10]}}) is None
        peak = dq.centrality_peak(ANALYSIS["trajectory"])
        assert peak["year"] == 2016 and peak["n"] == 250
        assert peak["falling"] is True

    def test_centrality_peak_ignores_unsettled_cohorts(self):
        """Der GLP-1-Lauf vom 2026-09-07 meldete 2026 als Peak — das letzte
        Jahr, dessen Zitationen noch einlaufen — und behauptete dazu
        „seither rückläufig". Jahrgänge innerhalb von TRUNC_YEARS zählen
        nicht mehr mit."""
        traj = {"x_by_year": {"2015": [0.30, 500], "2026": [0.99, 500]}}
        peak = dq.centrality_peak(traj)
        assert peak["year"] == 2015
        assert peak["falling"] is False        # kein spaeteres gesetztes Jahr

    def test_centrality_peak_none_when_everything_is_unsettled(self):
        assert dq.centrality_peak({"x_by_year": {"2025": [0.9, 900]}}) is None

    def test_summary_carries_the_new_scalars(self):
        out = dq.format_quant_evidence(ANALYSIS, "GLP-1", {"resolved_via": "x",
                                                           "phrase": "GLP-1"},
                                       "en", DYNAMICS)
        s = out["summary"]
        assert s["cycle_time_years"] == 11.0
        assert s["centrality_peak_year"] == 2016
        assert s["n_patents"] == 13714
        assert s["takeoffs"]["patent"] == 2016 and s["takeoffs"]["market"] == 2023

    def test_q1_snippet_is_no_longer_a_60_char_placeholder(self):
        q1 = dq.format_quant_evidence(ANALYSIS, "GLP-1", None, "en",
                                      DYNAMICS)["sources"][0]
        assert "A61K38/26" in q1["snippet"]
        assert "cycle time" in q1["snippet"]
        assert len(q1["snippet"]) > 100

    def test_evidence_block_pins_the_measurement_note(self, monkeypatch):
        monkeypatch.setattr(cr, "MAX_EVIDENCE_CHARS", 400)
        notes = ["MEASURED-BLOCK", "x" * 300, "y" * 300, "z" * 300]
        out = cr.evidence_block(notes, pinned=1)
        assert "MEASURED-BLOCK" in out
        # ohne Pinning fliegt genau sie zuerst raus (der gemessene Altzustand)
        assert "MEASURED-BLOCK" not in cr.evidence_block(notes, pinned=0)

    def test_check_cuts_the_measurement_appendix_off(self):
        from pipeline import dossier_check as dc
        report = ("Body text with 2016.\n"
                  + dq.MEASURE_HEADINGS[0] + "\n| 1999 | 4711 | 8.8 |\n")
        assert "4711" not in dc._report_body(report)


# ===========================================================================
# M4 — Zitate per Katalog-ID
# ===========================================================================

# R9-2: der Korpus-Artikel wird an seinem ORIGINAL zitiert — die eigene
# Domain ist kein Beleg (jury_13: 26 % Selbstzitate, fuer Pruefer 403).
SOURCES = [
    {"id": "T1", "kind": "article", "title": "Semaglutide trial",
     "url": "https://catandary.de/trends/semaglutide-1",
     "origin": "https://www.statnews.com/2026/01/01/semaglutide",
     "outlet": "STAT", "date": "2026-01-01"},
    {"id": "P2", "kind": "paper", "title": "Incretin review",
     "url": "https://doi.org/10.1/x", "origin": "https://doi.org/10.1/x",
     "outlet": "topic", "date": "2024"},
]


class TestM4Markers:
    def test_marker_resolves_to_the_catalog_link(self):
        body, cited, stripped = cr.canonicalize_citations(
            "Trials read out in 2026 [[T1]] and the review agrees [[P2]].",
            SOURCES, "en", markers=True)
        assert ("[Semaglutide trial](https://www.statnews.com/2026/01/01/"
                "semaglutide)") in body
        assert "catandary.de" not in body
        assert "[Incretin review](https://doi.org/10.1/x)" in body
        assert stripped == 0
        assert {s["id"] for s in cited} == {"T1", "P2"}

    def test_unknown_marker_is_deleted_and_counted(self):
        body, cited, stripped = cr.canonicalize_citations(
            "A claim [[T999]].", SOURCES, "en", markers=True)
        assert "T999" not in body
        assert stripped == 1 and cited == []

    def test_free_text_urls_are_still_stripped(self):
        body, cited, stripped = cr.canonicalize_citations(
            "Claim [[T1]] and [invented](https://example.com/made-up).",
            SOURCES, "en", markers=True)
        assert "example.com" not in body
        assert stripped == 1
        assert len(cited) == 1

    def test_the_measurement_never_carries_a_citation_anymore(self):
        """R9-2: die eigene Messung ist ueber den Rechenweg im Messanhang
        belegt, nicht ueber einen Link auf uns selbst. Ein Marker auf sie
        wird geloescht — der Satz bleibt, die Zahl steht im Anhang.
        (Bis 2026-09-07 riss ein zitierter Messblock den Lauf sogar ab:
        KeyError('measurement') in der Quellenliste.)"""
        srcs = SOURCES + [{"id": "Q1", "kind": "measurement",
                           "title": "Measured innovation-chain profile",
                           "url": "https://catandary.de/x", "origin": "",
                           "outlet": "Catandary Foresight engine",
                           "date": "2026-09-07", "fetched": True}]
        for lang in ("en", "de"):
            body, cited, stripped = cr.canonicalize_citations(
                "Patents took off in 2016 [[Q1]].", srcs, lang, markers=True)
            assert stripped == 1 and cited == []
            assert "Patents took off in 2016." in body
            assert "catandary.de" not in body

    def test_unknown_kind_does_not_kill_the_report(self):
        srcs = [{"id": "X1", "kind": "brand-new-kind", "title": "T",
                 "url": "https://x/1", "origin": "", "outlet": "", "date": ""}]
        body, cited, stripped = cr.canonicalize_citations(
            "Claim [[X1]].", srcs, "en", markers=True)
        assert stripped == 0 and len(cited) == 1

    def test_old_path_untouched(self):
        body, cited, stripped = cr.canonicalize_citations(
            "See [Semaglutide trial](https://catandary.de/trends/semaglutide-1).",
            SOURCES, "en")
        assert stripped == 0 and len(cited) == 1
        assert "[[" not in body
        # Der Link im Text wird auf das Original umgeschrieben (R9-2).
        assert "statnews.com" in body and "catandary.de" not in body

    def test_the_two_report_prompts_differ_only_in_the_citation_rule(self):
        assert "double square brackets" in cr.REPORT_SYSTEM_IDS
        assert "Cite as [Title](URL)" in cr.REPORT_SYSTEM
        assert "Cite as [Title](URL)" not in cr.REPORT_SYSTEM_IDS
        for line in ("Answer the exact question.", "Do not write a Sources"):
            assert line in cr.REPORT_SYSTEM and line in cr.REPORT_SYSTEM_IDS


# ===========================================================================
# M6 — Sweep vom Audit entkoppeln, Kappen, Relevanzschwelle
# ===========================================================================

class TestM6Sweep:
    def test_caps_were_raised(self):
        assert (cr.SWEEP_PAPERS, cr.SWEEP_PATENTS) == (12, 8)
        assert (cr.SWEEP_PAPERS_MEASURED, cr.SWEEP_PATENTS_MEASURED) == (24, 16)

    def test_anchor_terms_cover_the_hyphen_form(self):
        t = cr.anchor_terms("GLP-1 and incretin technology")
        assert "glp-1" in t and "glp1" in t and "incretin" in t
        # "technology" waere kein Anker, sondern ein Freifahrtschein
        assert "technology" not in t

    def test_off_topic_hit_is_dropped(self):
        terms = cr.anchor_terms("GLP-1 and incretin technology")
        on = {"title": "Semaglutide (GLP-1) dosing", "snippet": ""}
        off = {"title": "Roof integrated solar power system", "snippet": "shingle"}
        assert cr.on_topic(on, terms) is True
        assert cr.on_topic(off, terms) is False
        assert cr.on_topic(off, []) is True     # ohne Anker keine Filterung

    def test_sweep_consumes_one_shared_budget(self, monkeypatch):
        monkeypatch.setattr(cr, "_anchored_tsquery", lambda t, g: g)
        monkeypatch.setattr(cr, "search_research", lambda q, n, o="cited": [
            {"id": f"P{q}{o}{i}", "kind": "paper", "title": "incretin work",
             "snippet": "", "date": "2025", "url": f"https://doi/{q}{o}{i}"}
            for i in range(n)])
        monkeypatch.setattr(cr, "search_patents", lambda q, n: [
            {"id": f"N{q}{i}", "kind": "patent", "title": "GLP-1 analogue",
             "snippet": "", "date": "2024", "url": f"https://pat/{q}{i}"}
            for i in range(n)])
        sources, notes, ledger = [], [], []
        budget = {"papers": 5, "patents": 2}
        cr.sweep_internal(["gap a", "gap b", "gap c"], "GLP-1 incretin",
                          sources, set(), set(), notes, ledger, budget,
                          cr.anchor_terms("GLP-1 incretin"))
        assert budget["papers"] == 0 and budget["patents"] == 0
        assert sum(e["papers"] for e in ledger) == 5
        assert sum(e["patents"] for e in ledger) == 2
        assert len(ledger) == 3

    def test_sweep_records_off_topic_drops(self, monkeypatch):
        monkeypatch.setattr(cr, "_anchored_tsquery", lambda t, g: "x")
        monkeypatch.setattr(cr, "search_research", lambda q, n, o="cited": [])
        monkeypatch.setattr(cr, "search_patents", lambda q, n: [
            {"id": "N1", "kind": "patent", "title": "Photovoltaic shingle system",
             "snippet": "roof", "date": "2011", "url": "https://pat/1"}])
        sources, notes, ledger = [], [], []
        cr.sweep_internal(["gap"], "GLP-1 incretin", sources, set(), set(),
                          notes, ledger, {"papers": 4, "patents": 4},
                          cr.anchor_terms("GLP-1 incretin"))
        assert sources == []
        assert ledger[0]["off_topic_dropped"] == 1
        assert "off-topic" in notes[0]

    def test_research_split_between_fame_and_recency(self, monkeypatch):
        calls = []
        monkeypatch.setattr(cr, "_anchored_tsquery", lambda t, g: "x")
        monkeypatch.setattr(cr, "search_research",
                            lambda q, n, o="cited": calls.append(o) or [])
        monkeypatch.setattr(cr, "search_patents", lambda q, n: [])
        cr.sweep_internal(["gap"], "t", [], set(), set(), [], [],
                          {"papers": 4, "patents": 4}, [], split_recency=True)
        assert calls == ["cited", "recent"]

    def test_plan_entries_are_not_counted_as_open_questions(self):
        res = {"report": "text", "sources": [], "evidence": [], "cited": [],
               "stripped_citations": 0,
               "ledger": [{"gap": "a", "kind": "gap"},
                          {"gap": "b", "kind": "plan"},
                          {"gap": "c", "kind": "followup"}]}
        assert check_result(res)["open_questions"] == 2


# ===========================================================================
# Endkontrolle: Messung ausgefallen / gemessen aber ungenutzt
# ===========================================================================

class TestCheckMeasurement:
    def _res(self, report, quant):
        return {"report": report, "sources": [], "evidence": [], "cited": [],
                "stripped_citations": 0, "ledger": [], "quant": quant}

    def test_failed_measurement_is_a_finding(self):
        c = check_result(self._res("Body.", {"off_topic": True}))
        assert any("ausgefallen" in f for f in c["findings"])
        assert c["measured"] is False

    def test_measured_but_unused_is_a_finding(self):
        quant = {"off_topic": False, "selection": ["A61K38/26"], "K_median": 9.4,
                 "lead_patent_market": 7, "takeoffs": {"patent": 2016}}
        c = check_result(self._res("A dossier without a single measured figure.",
                                   quant))
        assert c["measurement_used"] is False
        assert any("nicht verwendet" in f for f in c["findings"])

    def test_measured_and_used_is_clean(self):
        quant = {"off_topic": False, "selection": ["A61K38/26"], "K_median": 9.4,
                 "lead_patent_market": 7, "takeoffs": {"patent": 2016}}
        c = check_result(self._res(
            "Patent activity in A61K38/26 took off in 2016.", quant))
        assert c["measurement_used"] is True
        assert not any("nicht verwendet" in f for f in c["findings"])


# ===========================================================================
# Der alte Pfad bleibt reproduzierbar
# ===========================================================================

class TestSwitch:
    def test_measure_false_keeps_the_single_shot_path(self, monkeypatch):
        calls = []
        mod = types.ModuleType("scripts.tech_analyze")
        mod.analyze_query = lambda q, codes=None: calls.append(q) or {
            "off_topic": True, "nearest_dist": 0.9}
        mod.analyze_codes = lambda codes: {}
        monkeypatch.setitem(sys.modules, "scripts.tech_analyze", mod)
        out = dq.build_quant_evidence("GLP-1 and incretin technology",
                                      measure=False)
        assert calls == ["GLP-1 and incretin technology"]     # keine Kaskade
        assert out["appendix"] is None
        assert out["ok"] is True and out["sources"] == []

    def test_fts_vector_matches_the_researcher(self):
        assert dq.FTS_VECTOR == cr.FTS_VECTOR


@pytest.mark.parametrize("phrase,expected", [
    ("GLP-1 and incretin technology", "GLP-1 incretin"),
    ("the future of quantum computing technology", "future quantum computing"),
    ("", ""),
])
def test_normalize_examples(phrase, expected):
    assert dq.normalize_topic(phrase) == expected
