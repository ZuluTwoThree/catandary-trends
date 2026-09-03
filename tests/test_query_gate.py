"""Regression for the #67 query-quality gate (pipeline/query_gate.py).

Runs GPU- and DB-free against tests/fixtures/tech_query_gate.json — the live
Qwen3-Embedding-8B vectors and raw signals of the calibration set, produced by
scripts/measure_query_gate.py on 2026-09-04 (docs/tech_query_gate_2026-09-04.md).

Acceptance pinned here (issue #67):
  * 0 false accepts on the nonsense/everyday set
  * ≤ 1 non-ok verdict on the technology set, and never a hard reject
  * the example chips of the Technology tool stay `ok` (unchanged fast path)
  * "unicorn breeding" → honest question with suggestions,
    "quantum error correction" → candidate choice (ambiguous), not a number
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import query_gate as qg

FIXTURE = Path(__file__).parent / "fixtures" / "tech_query_gate.json"
CHIPS = ["processed cheese", "solid-state battery electrolyte",
         "mRNA vaccine manufacturing", "perovskite tandem solar cells"]


@pytest.fixture(scope="module")
def items() -> list[dict]:
    return json.loads(FIXTURE.read_text())["items"]


def _group(items, g):
    return [it for it in items if it["group"] == g]


def _by_query(items, q):
    return next(it for it in items if it["query"] == q)


# --- fixture sanity ---------------------------------------------------------
def test_fixture_covers_both_sets(items):
    assert len(_group(items, "tech")) >= 20
    assert len(_group(items, "nonsense")) >= 20
    for it in items:
        assert len(it["signals"]["neighbours"]) == qg.TOP_K
        assert "and_hits" in it["signals"]["fulltext"]
        assert len(it["vec"]) == 1024


# --- acceptance ---------------------------------------------------------------
def test_no_false_accept_on_nonsense(items):
    wrong = [(it["query"], qg.verdict(it["signals"])["verdict"])
             for it in _group(items, "nonsense")
             if qg.verdict(it["signals"])["verdict"] != "off_topic"]
    assert wrong == []


def test_off_topic_answers_with_suggestions(items):
    for it in _group(items, "nonsense"):
        v = qg.verdict(it["signals"])
        assert 1 <= len(v["suggestions"]) <= qg.SUGGESTIONS, it["query"]
        for s in v["suggestions"]:
            assert s["label"] and s["symbol"]
        assert v["reason"]


def test_at_most_one_non_ok_on_tech_and_never_a_reject(items):
    non_ok = [(it["query"], qg.verdict(it["signals"])["verdict"])
              for it in _group(items, "tech")
              if qg.verdict(it["signals"])["verdict"] != "ok"]
    assert len(non_ok) <= 1, non_ok
    assert all(v == "ambiguous" for _, v in non_ok), non_ok


def test_example_chips_unchanged(items):
    for q in CHIPS:
        assert qg.verdict(_by_query(items, q)["signals"])["verdict"] == "ok", q


def test_issue_case_unicorn_breeding(items):
    v = qg.verdict(_by_query(items, "unicorn breeding")["signals"])
    assert v["verdict"] == "off_topic"
    assert 2 <= len(v["suggestions"]) <= 3
    # nearest real fields, one per main group, human-readable
    assert len({s["symbol"].split("/")[0] for s in v["suggestions"]}) == len(v["suggestions"])


def test_issue_case_cat_tuesdays(items):
    # the audit's reproduction: d1 = 0.515 was under the old 0.55 gate
    it = _by_query(items, "my cat is sad on tuesdays")
    assert qg.derive(it["signals"])["d1"] < 0.55
    assert qg.verdict(it["signals"])["verdict"] == "off_topic"


def test_issue_case_quantum_error_correction(items):
    it = _by_query(items, "quantum error correction")
    v = qg.verdict(it["signals"])
    assert v["verdict"] == "ambiguous"
    f = v["features"]
    # embedding lands on classical channel coding, the words on quantum computing
    assert f["emb_subclasses"][0] == "H03M"
    assert f["ft_top_subclass"] == "G06N"
    assert "G06N" in v["reason"]
    assert v["clusters"][0]["source"] == "words"
    assert v["clusters"][0]["subclass"] == "G06N"
    assert v["clusters"][0]["symbols"]
    assert all(s.startswith("G06N") for s in v["clusters"][0]["symbols"])
    # the embedding's own field is still offered as a choice
    assert any(c["subclass"] == "H03M" and c["source"] == "embedding" for c in v["clusters"])


# --- threshold derivation (documents the measured gaps) -----------------------
def test_d20_threshold_sits_in_the_measured_gap(items):
    tech_max = max(qg.derive(it["signals"])["d20"] for it in _group(items, "tech"))
    nonsense_min = min(qg.derive(it["signals"])["d20"] for it in _group(items, "nonsense"))
    assert tech_max < qg.D20_MAX < nonsense_min, (tech_max, qg.D20_MAX, nonsense_min)


def test_nearest_distance_and_margin_do_not_separate(items):
    """The finding behind #67: the old signal (d1) overlaps, and so does the
    'margin' idea from the audit comment — d20 is what separates."""
    tech = [qg.derive(it["signals"]) for it in _group(items, "tech")]
    non = [qg.derive(it["signals"]) for it in _group(items, "nonsense")]
    assert max(f["d1"] for f in tech) > min(f["d1"] for f in non)
    assert max(f["margin20"] for f in non) > min(f["margin20"] for f in tech)
    assert min(f["margin20"] for f in non) < max(f["margin20"] for f in tech)


def test_every_technology_has_title_evidence(items):
    for it in _group(items, "tech"):
        assert qg.derive(it["signals"])["and_hits"] >= 1, it["query"]


# --- pure-function behaviour on synthetic signals ------------------------------
def _nb(symbol, dist, title="Some sentence-like title", path="A > B", n=100):
    return {"symbol": symbol, "dist": dist, "title": title, "title_path": path, "n_patents": n}


def test_empty_signals_are_off_topic():
    v = qg.verdict({"neighbours": [], "fulltext": {"and_hits": 0}})
    assert v["verdict"] == "off_topic"
    assert v["suggestions"] == []


def test_zero_title_hits_reject_even_with_tight_neighbourhood():
    nb = [_nb(f"H01M10/{i:02d}", 0.20 + i * 0.001) for i in range(20)]
    assert qg.verdict({"neighbours": nb, "fulltext": {"and_hits": 0}})["verdict"] == "off_topic"
    assert qg.verdict({"neighbours": nb, "fulltext": {"and_hits": 3}})["verdict"] == "ok"


def test_far_twentieth_neighbour_rejects_despite_close_first():
    # "recipe for pancakes": one close class, then nothing
    nb = [_nb("A21D13/44", 0.23)] + [_nb(f"A21D13/{i:02d}", 0.37 + i * 0.002) for i in range(19)]
    v = qg.verdict({"neighbours": nb, "fulltext": {"and_hits": 13}})
    assert v["verdict"] == "off_topic"
    assert "20 nearest" in v["reason"]


def test_lexical_mismatch_needs_evidence_and_dominance():
    nb = [_nb(f"H03M13/{i:02d}", 0.30 + i * 0.002) for i in range(20)]
    ft = {"and_hits": 500, "sample": 300,
          "fields": [{"subclass": "G06N", "n": 165, "title": "Computing arrangements"}],
          "top_codes": [{"symbol": "G06N10/70", "n": 90, "title": "Quantum error correction"}]}
    assert qg.verdict({"neighbours": nb, "fulltext": ft})["verdict"] == "ambiguous"
    # too little title evidence → no field estimate → ok
    thin = dict(ft, and_hits=10, sample=10, fields=[{"subclass": "G06N", "n": 8}])
    assert qg.verdict({"neighbours": nb, "fulltext": thin})["verdict"] == "ok"
    # lexical field present in the embedding's top-12 → agreement → ok
    agree = dict(ft, fields=[{"subclass": "H03M", "n": 200}])
    assert qg.verdict({"neighbours": nb, "fulltext": agree})["verdict"] == "ok"
    # dominant share below the floor → ok
    weak = dict(ft, fields=[{"subclass": "G06N", "n": 60}])
    assert qg.verdict({"neighbours": nb, "fulltext": weak})["verdict"] == "ok"


def test_suggestions_one_per_main_group_with_readable_labels():
    nb = [
        _nb("A01K2227/107", 0.35, "Rabbit", "ANIMAL HUSBANDRY > Rearing or breeding animals > Rabbit"),
        _nb("A01K2227/108", 0.36, "Swine", "ANIMAL HUSBANDRY > Rearing or breeding animals > Swine"),
        _nb("A61D19/00", 0.37, "Instruments or methods for reproduction or fertilisation", "X > Y"),
        _nb("A63F2300/8058", 0.38, "Virtual breeding, e.g. tamagotchi", "GAMES > Virtual breeding"),
    ]
    s = qg.suggestions({"neighbours": nb})
    assert [x["symbol"] for x in s] == ["A01K2227/107", "A61D19/00", "A63F2300/8058"]
    assert s[0]["label"] == "Rearing or breeding animals"     # path element, not "Rabbit"
    assert s[2]["label"].startswith("Virtual breeding")       # parentheses/e.g. stripped


def test_clusters_words_first_then_embedding_groups():
    nb = [_nb("H03M13/63", 0.30, path="CODING > Coding, decoding or code conversion"),
          _nb("H03M13/13", 0.31, path="CODING > Coding, decoding or code conversion"),
          _nb("H04L1/0057", 0.33, path="TRANSMISSION OF DIGITAL INFORMATION > Block codes")]
    ft = {"and_hits": 500, "sample": 300,
          "fields": [{"subclass": "G06N", "n": 165, "title": "Computing arrangements based on specific computational models"}],
          "top_codes": [{"symbol": "G06N10/70", "n": 90, "title": "Quantum error correction"}]}
    cl = qg.clusters({"neighbours": nb, "fulltext": ft})
    assert [c["subclass"] for c in cl] == ["G06N", "H03M", "H04L"]
    assert cl[0]["source"] == "words" and cl[0]["symbols"] == ["G06N10/70"]
    assert cl[1]["symbols"] == ["H03M13/63", "H03M13/13"]
    assert cl[1]["label"] == "Coding"


def test_summary_table_lists_every_item(items):
    md = qg.summarize(items[:3])
    assert md.count("\n") == 4          # header + separator + 3 rows
    assert "**ok**" in md or "**off_topic**" in md
