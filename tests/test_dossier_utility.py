"""Nutzen U je Dossier-Lauf (Stufe 0, docs/plan_dossier_agent_2026-09-18.md).

Alles hier ist Replay über kleine Fixture-Dicts in der Form von
dossiers.result — ohne Modell, ohne Netz, ohne GPU. Die Tabelle
dossier_run_outcomes wird gegen eine temporäre SQLite geprüft.
"""
from __future__ import annotations

import json
import os

import pytest


def _result(*, per100_after=2.4, per100_before=1.2, reader=True, answers=True,
            findings_after=None, contradiction=False, ranks=(0, 1, 2, None),
            seconds=1500, brave=10, searxng=0, with_structure=True,
            maturity=True, kinds=("article", "signal", "web", "measurement")):
    sources = [{"id": f"S{i}", "rank": r, "kind": kinds[i % len(kinds)]}
               for i, r in enumerate(ranks)]
    cited = [s["id"] for s in sources]
    structure = None
    if with_structure:
        structure = {
            "density_before": {"per100": per100_before, "words": 2000},
            "density_after": {"per100": per100_after, "words": 1900},
            "findings": ["Faktenquote 1.2 …"],
            "findings_after": findings_after if findings_after is not None else [],
            # Scouting-Umbau: Reifegrad-Sektion ist Bedingung der dritten Ampel
            "maturity_present": maturity,
        }
        if reader:
            rd = {"overall": "The dossier answers the question." if not contradiction
                  else "The summary contradicts the evidence section.",
                  "answers_question": answers,
                  "findings": [{"kind": "coherence" if contradiction else "missing",
                                "issue": "x"}]}
            structure["reader_after"] = rd
    return {"structure": structure, "sources": sources, "cited": cited,
            "seconds": seconds, "web": {"cache": {"brave_api": brave, "searxng_api": searxng,
                                                  "brave_cached": 5}},
            "mode": "technology", "dr": True}


class TestComponents:
    def test_full_run(self):
        from pipeline.dossier_utility import components
        c = components(_result(), {"ok": True}, None)
        assert c["density_norm"] == 1.0                 # 2.4 / 2.0 gedeckelt
        assert c["primary_share"] == 0.5                # Rang 0 + 1 von vier; None = 2
        assert c["no_contradiction"] == 1
        assert c["tables_on_topic"] == 1.0
        assert c["reader_answers"] == 1
        assert c["answered_must"] is None               # ohne Auftrag (vor Stufe 1)
        assert c["cost_minutes"] == 25.0
        assert c["web_calls"] == 10
        assert c["signed_off"] is False

    def test_density_fallback_before_then_zero(self):
        from pipeline.dossier_utility import components
        r = _result(per100_after=None, per100_before=1.0)
        r["structure"]["density_after"] = {}
        assert components(r, None, None)["density_norm"] == 0.5
        assert components(_result(with_structure=False), None, None)["density_norm"] == 0.0

    def test_missing_rank_counts_as_secondary(self):
        from pipeline.dossier_utility import components
        c = components(_result(ranks=(None, None, 1)), None, None)
        assert c["primary_share"] == pytest.approx(1 / 3, abs=1e-4)

    def test_cited_id_absent_from_catalog_is_secondary(self):
        from pipeline.dossier_utility import components
        r = _result(ranks=(0,))
        r["cited"].append("GHOST")
        assert components(r, None, None)["primary_share"] == 0.5

    def test_no_citations_is_unmeasured(self):
        from pipeline.dossier_utility import components
        r = _result()
        r["cited"] = []
        assert components(r, None, None)["primary_share"] is None

    def test_missing_reader(self):
        from pipeline.dossier_utility import components
        c = components(_result(reader=False), None, None)
        assert c["reader_answers"] is None
        assert c["no_contradiction"] == 1               # kein Prüfer ≠ Befund

    def test_contradiction_by_kind_and_by_text(self):
        from pipeline.dossier_utility import components
        assert components(_result(contradiction=True), None, None)["no_contradiction"] == 0
        r = _result()
        r["structure"]["reader_after"]["findings"] = [
            {"kind": "missing", "issue": "The summary contradicts section 4."}]
        assert components(r, None, None)["no_contradiction"] == 0

    def test_reader_before_used_when_no_reader_after(self):
        from pipeline.dossier_utility import components
        r = _result(reader=False)
        r["structure"]["reader"] = {"answers_question": False, "findings": []}
        assert components(r, None, None)["reader_answers"] == 0

    def test_tables_off_topic_capped(self):
        from pipeline.dossier_utility import components
        one = ["'What happens next': 3 Zeile(n) datiert und belegt, aber nicht zum Thema"]
        three = one + ["actor table: 6 off topic", "calendar: off-topic rows"]
        assert components(_result(findings_after=one), None, None)["tables_on_topic"] == 0.5
        assert components(_result(findings_after=three), None, None)["tables_on_topic"] == 0.0
        assert components(_result(with_structure=False), None, None)["tables_on_topic"] is None

    def test_accepts_json_strings_and_signed_off(self):
        from pipeline.dossier_utility import components
        c = components(json.dumps(_result()), json.dumps({"ok": True}), "2026-09-03 10:00")
        assert c["signed_off"] is True and c["reader_answers"] == 1


class TestUtility:
    def test_presets_sum_to_one_over_quality_keys(self):
        from pipeline.dossier_utility import WEIGHT_PRESETS, MUST_ANSWER_WEIGHT
        from pipeline.dossier_utility import CORPUS_SHARE_WEIGHT
        # Scouting-Umbau (2026-09-19): corpus_share traegt 0,15 in jedem Preset,
        # die fuenf uebrigen Qualitaetsgewichte sind darauf renormiert.
        quality = ("density_norm", "primary_share", "no_contradiction",
                   "tables_on_topic", "reader_answers", "corpus_share")
        assert set(WEIGHT_PRESETS) == {"technology", "landscape", "regulatory",
                                       "market", "evidence"}
        for name, w in WEIGHT_PRESETS.items():
            assert sum(w[k] for k in quality) == pytest.approx(1.0), name
            assert w["corpus_share"] == CORPUS_SHARE_WEIGHT == 0.15
            assert w["answered_must"] == MUST_ANSWER_WEIGHT

    def test_perfect_run_scores_one(self):
        from pipeline.dossier_utility import components, utility
        assert utility(components(_result(ranks=(0, 1)), None, None)) == 1.0

    def test_renormalisation_ignores_missing(self):
        from pipeline.dossier_utility import utility
        full = {"density_norm": 1.0, "primary_share": 1.0, "no_contradiction": 1,
                "tables_on_topic": 1.0, "reader_answers": None, "answered_must": None,
                "cost_minutes": 10, "web_calls": 0}
        assert utility(full) == 1.0                    # None ist nicht 0
        half = dict(full, density_norm=0.0)
        # technology: density 0.25 von 0.75 messbar → 1 − 0.25/0.75
        assert utility(half) == pytest.approx(1 - 0.25 / 0.75, abs=1e-4)

    def test_cost_penalties(self):
        from pipeline.dossier_utility import utility
        base = {"density_norm": 1.0, "primary_share": 1.0, "no_contradiction": 1,
                "tables_on_topic": 1.0, "reader_answers": 1, "answered_must": None}
        assert utility(dict(base, cost_minutes=30, web_calls=40)) == 1.0
        assert utility(dict(base, cost_minutes=31, web_calls=40)) == pytest.approx(0.98)
        assert utility(dict(base, cost_minutes=45, web_calls=40)) == pytest.approx(0.96)
        assert utility(dict(base, cost_minutes=30, web_calls=41)) == pytest.approx(0.99)
        assert utility(dict(base, cost_minutes=30, web_calls=61)) == pytest.approx(0.97)

    def test_preset_by_name_changes_weighting(self):
        from pipeline.dossier_utility import utility
        c = {"density_norm": 0.0, "primary_share": 1.0, "no_contradiction": 1,
             "tables_on_topic": 1.0, "reader_answers": 1, "answered_must": None,
             "cost_minutes": 5, "web_calls": 0}
        assert utility(c, "regulatory") > utility(c, "market")

    def test_deterministic(self):
        from pipeline.dossier_utility import evaluate
        r = _result(findings_after=["actor table: 2 off topic"], ranks=(0, 2, None))
        a, b = evaluate(r, None, None), evaluate(r, None, None)
        assert a == b and a["preset"] == "technology"


class TestDeliveryReady:
    def test_ready(self):
        from pipeline.dossier_utility import components, delivery_ready
        assert delivery_ready(components(_result(), None, None)) is True

    @pytest.mark.parametrize("kw", [
        {"reader": False}, {"answers": False}, {"contradiction": True},
        {"per100_after": 1.9}, {"findings_after": ["calendar: off topic"]},
        {"maturity": False}])
    def test_each_gate_blocks(self, kw):
        from pipeline.dossier_utility import components, delivery_ready
        assert delivery_ready(components(_result(**kw), None, None)) is False

    def test_old_runs_without_the_maturity_field_are_never_ready(self):
        from pipeline.dossier_utility import components, delivery_ready
        res = _result()
        del res["structure"]["maturity_present"]
        c = components(res, None, None)
        assert c["maturity_present"] is None and delivery_ready(c) is False


class TestCorpusShare:
    def test_share_counts_corpus_and_measurement_kinds(self):
        from pipeline.dossier_utility import components
        # kinds cycle article, signal, web, measurement over 4 sources -> 3 of 4
        assert components(_result(), None, None)["corpus_share"] == pytest.approx(0.75)

    def test_no_citations_means_unmeasured(self):
        from pipeline.dossier_utility import components
        res = _result()
        res["cited"] = []
        assert components(res, None, None)["corpus_share"] is None


class TestStore:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
        monkeypatch.setenv("DATABASE_URL", "")
        import importlib
        from pipeline import db as db_mod
        importlib.reload(db_mod)
        from pipeline import dossier_orders, dossier_utility
        importlib.reload(dossier_orders)
        importlib.reload(dossier_utility)
        # pipeline.config wird nicht neu geladen — der Pfad bleibt die geteilte
        # Test-DB; die Tabellen deshalb frisch anlegen (sonst hinterlaesst der
        # Worker-Test eine Outcome-Zeile, die hier mit dossiers.id=1 joint).
        from pipeline.db import get_connection
        with get_connection() as conn:
            for t in ("dossier_run_outcomes", "dossiers", "dossier_orders"):
                conn.execute(f"DROP TABLE IF EXISTS {t}")
        dossier_orders.ensure_schema()
        dossier_utility.ensure_schema()
        yield

    def test_record_run_upserts_one_row(self):
        from pipeline.db import get_connection
        from pipeline import dossier_utility as du
        res = _result()
        with get_connection() as conn:
            conn.execute("INSERT INTO dossiers (slug, version, topic, question, report_md, result, model)"
                         " VALUES (?, ?, ?, ?, ?, ?, ?)",
                         ("lfp", 1, "LFP", "q?", "# r", json.dumps(res), "27B"))
        ev = du.record_run("lfp", 1, 7, res, {"ok": True})
        assert ev and ev["delivery_ready"] is True
        ev2 = du.record_run("lfp", 1, 7, res, {"ok": True}, reviewed_at="2026-09-19")
        assert ev2["signed_off"] is True
        rows = du.list_outcomes()
        assert len(rows) == 1
        assert rows[0]["order_id"] == 7 and bool(rows[0]["signed_off"]) is True
        assert rows[0]["components"]["density_norm"] == 1.0
        assert du.record_run("nope", 1, None, res, None) is None


class TestAnsweredMust:
    """Stufe 1: answered_must aus result["brief_eval"]."""

    @pytest.fixture(autouse=True)
    def _fns(self):
        from pipeline import dossier_utility as du
        global components, utility
        components, utility = du.components, du.utility

    def test_share_is_read_and_clamped(self):
        r = _result()
        r["brief_eval"] = {"answered_share": 0.6667, "items": []}
        assert components(r, None, None)["answered_must"] == 0.6667
        r["brief_eval"] = {"answered_share": 1.4}
        assert components(r, None, None)["answered_must"] == 1.0

    def test_counted_from_items_when_share_missing(self):
        r = _result()
        r["brief_eval"] = {"items": [{"answered": True}, {"answered": False}, {"answered": True}]}
        assert components(r, None, None)["answered_must"] == 0.6667

    def test_unmeasured_without_brief(self):
        r = _result()
        r["brief_eval"] = None
        assert components(r, None, None)["answered_must"] is None

    def test_it_enters_the_utility_with_its_weight(self):
        r = _result(ranks=(0, 1))
        assert utility(components(r, None, None)) == 1.0
        r["brief_eval"] = {"answered_share": 0.0}
        # 5 Qualitaetsgewichte = 1,0 bei Wert 1; answered_must 0,25 bei 0 → 1/(1,25) = 0,8
        assert utility(components(r, None, None)) == 0.8
