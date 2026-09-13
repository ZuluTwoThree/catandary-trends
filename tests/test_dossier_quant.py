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


# --- CPC-Anker (2026-09-13) --------------------------------------------------------

def test_measure_anchor_uses_the_owner_code_before_the_cascade(monkeypatch):
    import types, sys
    from pipeline import dossier_quant as dq
    good = {"selection": ["H01M4/5825"], "trajectory": [{"year": 2020, "k": 0.1}] * 3,
            "gate": {"verdict": "ok"}, "off_topic": False}
    monkeypatch.setattr(dq, "_measurable", lambda a: bool(a and a.get("trajectory")))
    fake = types.SimpleNamespace(analyze_query=lambda q, codes=None: (_ for _ in ()).throw(RuntimeError("no embed")),
                                 analyze_codes=lambda codes: dict(good, codes=codes))
    monkeypatch.setitem(sys.modules, "scripts.tech_analyze", fake)
    found = dq.measure_anchor("LFP cells", "h01m 4/5825")
    assert found["resolved_via"] == "anchor H01M4/5825"
    assert found["analysis"]["codes"] == ["H01M4/5825"]
    assert [a["verdict"] for a in found["attempts"]] == ["error", "ok"]


def test_measure_anchor_falls_back_when_the_code_has_no_trajectory(monkeypatch):
    import types, sys
    from pipeline import dossier_quant as dq
    monkeypatch.setattr(dq, "_measurable", lambda a: bool(a and a.get("trajectory")))
    fake = types.SimpleNamespace(analyze_query=lambda q, codes=None: {"trajectory": []},
                                 analyze_codes=lambda codes: {"trajectory": []})
    monkeypatch.setitem(sys.modules, "scripts.tech_analyze", fake)
    found = dq.measure_anchor("x", "B60L58/10")
    assert found["analysis"] is None
    assert found["attempts"][-1]["verdict"] == "no_trajectory"


def test_head_phrase_strips_application_tail_and_parentheticals():
    from pipeline.dossier_quant import head_phrase, topic_cascade
    assert head_phrase("lithium iron phosphate (LFP) cells for stationary storage and EVs") == "lithium iron phosphate cells"
    assert head_phrase("perovskite tandem photovoltaics") == "perovskite tandem photovoltaics"
    assert head_phrase("GLP-1 and incretin technology — obesity market") == "GLP-1 and incretin technology"
    casc = topic_cascade("lithium iron phosphate (LFP) cells for stationary storage and EVs")
    assert casc[1] == "lithium iron phosphate cells"          # gleich nach der vollen Phrase


def test_dense_candidates_pick_the_sharp_class_out_of_the_gate_list(monkeypatch):
    from pipeline import dossier_quant as dq
    analysis = {"candidates": [{"symbol": "H01M10/052"}, {"symbol": "H01M4/5825"}, {"symbol": "H01M4/136"}]}
    monkeypatch.setattr(dq, "topical_precision", lambda codes, topic: {
        "H01M4/5825": {"total": 16000, "hits": 900, "precision": 0.056},
        "H01M4/136": {"total": 3000, "hits": 10, "precision": 0.003},
    })
    assert dq.dense_candidates(analysis, "lithium iron phosphate (LFP) cells for storage",
                               exclude=["H01M10/052"]) == ["H01M4/5825"]
    monkeypatch.setattr(dq, "topical_precision", lambda codes, topic: {})
    assert dq.dense_candidates(analysis, "x") == []


def test_sharper_title_class_prefers_the_dense_cathode_class(monkeypatch):
    from pipeline import dossier_quant as dq
    monkeypatch.setattr(dq, "title_candidates", lambda topic, fams, limit=12: ["H01M10/0525", "H01M4/5825"])
    def prec(codes, topic, strict=False):
        assert strict is True
        table = {"H01M10/052": 0.019, "H01M10/0525": 0.023, "H01M4/5825": 0.259}
        return {c: {"total": 1, "with_text": 1, "hits": 60, "precision": table[c]} for c in codes}
    monkeypatch.setattr(dq, "topical_precision", prec)
    got = dq.sharper_title_class("lithium iron phosphate (LFP) cells for storage", ["H01M10/052"], None, ["H01M10/052"])
    assert got and got[0] == "H01M4/5825" and got[1] > got[2] * dq.TITLE_SHARPER_RATIO


def test_sharper_title_class_stays_quiet_when_nothing_is_denser(monkeypatch):
    from pipeline import dossier_quant as dq
    monkeypatch.setattr(dq, "title_candidates", lambda topic, fams, limit=12: ["H01M4/13"])
    monkeypatch.setattr(dq, "topical_precision", lambda codes, topic, strict=False: {
        c: {"total": 1, "with_text": 1, "hits": 60, "precision": 0.2} for c in codes})
    assert dq.sharper_title_class("x y", ["H01M10/052"], None, ["H01M10/052"]) is None
