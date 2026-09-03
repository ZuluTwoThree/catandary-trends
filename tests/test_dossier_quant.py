"""Quant-Vorstufe (pipeline/dossier_quant.py): Formatierung + Degradierung.

format_quant_evidence ist rein und wird gegen ein realistisches
analyze_query()-Ergebnis geprüft; build_quant_evidence muss jeden Fehler
(kein Postgres, kein Embedding-Endpunkt) in einen Fehlgrund verwandeln,
nie in einen Absturz.
"""
import sys
import types

from pipeline.dossier_quant import (MAX_HUB_PATENTS, build_quant_evidence,
                                    format_quant_evidence)

ANALYSIS = {
    "query": "solid-state batteries",
    "off_topic": False,
    "candidates": [
        {"symbol": "H01M10/0562", "title": "Solid electrolyte cells",
         "dist": 0.31, "n": 12345, "default": True},
        {"symbol": "H01M10/052", "title": "Li-accumulators",
         "dist": 0.35, "n": 54321, "default": False},
    ],
    "selection": ["H01M10/0562"],
    "trajectory": {"direction": "accelerating", "K_median": 14.2,
                   "K_latest": 19.0, "calibrated": True, "rel_change": 0.4},
    "leadtime": {
        "tiers": {
            "science": {"n": 320, "first": 2011, "takeoff": 2014, "median": 2021},
            "patent": {"n": 8100, "first": 1995, "takeoff": 2013, "median": 2018},
            "funding": {"n": 40, "first": 2016, "takeoff": 2019, "median": 2022},
            "market": {"n": 45, "first": 2020, "takeoff": 2022, "median": 2025},
        },
        "lead_science_market": 8, "lead_patent_market": 9,
        "concurrent": False, "established": False, "market_floored": False,
    },
    "top_patents": [
        {"pub": f"US-100000{i}-B2", "cites": 900 - i, "title": f"Hub patent {i}",
         "year": "2015", "url": f"https://worldwide.espacenet.com/p{i}"}
        for i in range(7)
    ],
    "verdict": "Research ran ~8+ years ahead of the market; improving fast "
               "(median ~14.2%/yr over the measured history).",
}


class TestFormat:
    def test_measurement_source_is_citable(self):
        out = format_quant_evidence(ANALYSIS, "solid-state batteries")
        q1 = out["sources"][0]
        assert q1["id"] == "Q1" and q1["kind"] == "measurement"
        assert q1["fetched"] is True            # zitierfähig ohne Web-Fetch
        assert "technology?q=solid-state%20batteries" in q1["url"]

    def test_hub_patents_capped_and_marked(self):
        out = format_quant_evidence(ANALYSIS, "t")
        pats = [s for s in out["sources"] if s["kind"] == "patent"]
        assert len(pats) == MAX_HUB_PATENTS
        assert all("never a working product" in p["snippet"] for p in pats)

    def test_note_carries_figures_and_honesty_limits(self):
        note = format_quant_evidence(ANALYSIS, "t")["note"]
        assert "~14.2%/yr" in note
        assert "research→market lead: ~8 years" in note
        assert "calibrated only to ~2019" in note
        assert "never a working product" in note

    def test_established_field_claims_no_lead(self):
        a = {**ANALYSIS,
             "leadtime": {**ANALYSIS["leadtime"], "established": True,
                          "lead_science_market": None, "lead_patent_market": None}}
        note = format_quant_evidence(a, "t")["note"]
        assert "no research→market lead can honestly be claimed" in note
        assert "market lead: ~" not in note

    def test_off_topic_has_no_sources_but_a_note(self):
        out = format_quant_evidence(
            {"off_topic": True, "nearest_dist": 0.71}, "vibes")
        assert out["sources"] == []
        assert "did not resolve" in out["note"]
        assert out["summary"]["off_topic"] is True

    def test_summary_reports_only_calibrated_rates(self):
        a = {**ANALYSIS, "trajectory": {"direction": "insufficient_data",
                                        "K_median": 99.0, "calibrated": None}}
        out = format_quant_evidence(a, "t")
        assert out["summary"]["K_median"] is None


class TestBuildDegradation:
    def _stub(self, monkeypatch, fn):
        mod = types.ModuleType("scripts.tech_analyze")
        mod.analyze_query = fn
        monkeypatch.setitem(sys.modules, "scripts.tech_analyze", mod)

    def test_measurement_error_becomes_reason(self, monkeypatch):
        def boom(_):
            raise RuntimeError("relation patent_cpc_full does not exist")
        self._stub(monkeypatch, boom)
        out = build_quant_evidence("t")
        assert out["ok"] is False
        assert "patent_cpc_full" in out["reason"]
        assert out["sources"] == []

    def test_embed_systemexit_becomes_reason(self, monkeypatch):
        def die(_):
            raise SystemExit("embedding failed")
        self._stub(monkeypatch, die)
        out = build_quant_evidence("t")
        assert out["ok"] is False and "embedding failed" in out["reason"]

    def test_success_passes_through(self, monkeypatch):
        self._stub(monkeypatch, lambda _t: ANALYSIS)
        out = build_quant_evidence("solid-state batteries")
        assert out["ok"] is True
        assert out["sources"][0]["id"] == "Q1"
        assert out["summary"]["K_median"] == 14.2
