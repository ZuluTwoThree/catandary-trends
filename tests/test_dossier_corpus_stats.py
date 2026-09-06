"""M3 — Korpus-Kennzahlen als zweite deterministische Vorstufe.

Formatierung und Degradierung sind rein testbar; die beiden Messfunktionen
brauchen Postgres und werden hier gestubbt.
"""
from pipeline import dossier_corpus_stats as cs
from pipeline.dossier_check import MEASUREMENT_HEADINGS, _report_body

STATS = {
    "ok": True, "reason": None, "tsquery": "glp-1 | incretin",
    "measured_on": "2026-09-07", "seconds": 18.2,
    "market": {"ok": True, "n": 1366, "published": 495, "signals": 862,
               "first": 2016, "last": 2026, "seconds": 14.0,
               "years": {2016: 2, 2023: 46, 2024: 169, 2025: 215, 2026: 915},
               "verticals": [("HEALTH", 1199), ("FOOD", 96)],
               "signal_types": [("research", 643), ("market_shift", 360)],
               "outlets": [("STAT News", 165), ("MedCity News", 87)]},
    "science": {"ok": True, "n": 21590, "reviews": 3746, "citations": 542118,
                "seconds": 3.1,
                "years": {2010: 442, 2020: 966, 2024: 2997, 2025: 4569},
                "funders": [("National Institutes of Health", 937),
                            ("Novo Nordisk", 841)]},
}


class TestQuery:
    def test_terms_come_from_the_normalized_topic(self):
        assert cs.topic_tsquery("GLP-1 and incretin technology") == "glp-1 | incretin"

    def test_empty_topic_yields_nothing(self):
        assert cs.topic_tsquery("the of and") == ""


class TestFormat:
    def test_q0_is_citable_and_carries_figures(self):
        out = cs.format_corpus_stats(STATS, "GLP-1 and incretin technology")
        q0 = out["sources"][0]
        assert q0["id"] == "Q0" and q0["kind"] == "measurement"
        assert q0["fetched"] is True
        assert "1,366 market signals" in q0["snippet"]
        assert "21,590 research works" in q0["snippet"]

    def test_note_carries_year_series_and_actors(self):
        note = cs.format_corpus_stats(STATS, "t")["note"]
        assert "entries by year" in note and "2024:169" in note
        assert "works by year" in note
        assert "National Institutes of Health 937" in note
        assert "by vertical: HEALTH 1,199" in note
        assert "measures coverage, not the world" in note

    def test_appendix_is_a_table_not_prose(self):
        app = cs.format_corpus_stats(STATS, "t")["appendix"]
        assert cs.CORPUS_HEADINGS[0] in app
        assert "| year | entries |" in app and "| year | works |" in app
        assert "**1,366 entries**" in app
        assert "420,564 startup events" in app        # die benannte Grenze
        assert "~350 s" in app

    def test_appendix_german(self):
        app = cs.format_corpus_stats(STATS, "t", "de")["appendix"]
        assert cs.CORPUS_HEADINGS[1] in app
        assert "**1,366 Einträge**" in app

    def test_partial_failure_is_reported_not_hidden(self):
        stats = {**STATS, "science": {"ok": False, "reason": "not measured (timeout)"}}
        app = cs.format_corpus_stats(stats, "t")["appendix"]
        assert "Research layer: not measured (timeout)" in app
        assert "Market and signal layer" in app

    def test_summary_scalars(self):
        s = cs.format_corpus_stats(STATS, "t")["summary"]
        assert s["market_n"] == 1366 and s["science_n"] == 21590
        assert s["top_funder"] == "National Institutes of Health"

    def test_check_cuts_the_corpus_appendix_off(self):
        assert cs.CORPUS_HEADINGS[0] in MEASUREMENT_HEADINGS
        report = "Body.\n" + cs.CORPUS_HEADINGS[0] + "\n| 2024 | 4711 |\n"
        assert "4711" not in _report_body(report)


class TestDegradation:
    def test_no_terms_is_a_reason(self, monkeypatch):
        out = cs.build_corpus_evidence("the of and")
        assert out["ok"] is False and out["appendix"] is None

    def test_db_error_becomes_a_reason(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("relation trends does not exist")
        monkeypatch.setattr(cs, "_rows", boom)
        out = cs.build_corpus_evidence("GLP-1 incretin")
        assert out["ok"] is False
        assert "no corpus block" in out["reason"]

    def test_one_block_is_enough(self, monkeypatch):
        monkeypatch.setattr(cs, "measure_market", lambda q: STATS["market"])
        monkeypatch.setattr(cs, "measure_science",
                            lambda q: {"ok": False, "reason": "not measured"})
        out = cs.build_corpus_evidence("GLP-1 incretin")
        assert out["ok"] is True
        assert "not measured" in out["appendix"]


class TestTally:
    def test_years_and_tally_are_pure(self):
        rows = [{"yr": "2024-01-02", "v": "A"}, {"yr": "2024", "v": "A"},
                {"yr": None, "v": "B"}, {"yr": "1899", "v": "B"}]
        assert cs._years(rows) == {2024: 2}
        assert cs._tally(rows, "v") == [("A", 2), ("B", 2)]
