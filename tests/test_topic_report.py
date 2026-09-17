"""Topic engine — the pure parts (no DB, no embedder)."""
from collections import Counter
from datetime import datetime

import numpy as np
import pytest

from pipeline import topic_report as T


def _rows(sims, tier="science", source="Src", start=("2024", 1), tags=None, names=None, per_month=1):
    out = []
    for i, s in enumerate(sims):
        y, m = int(start[0]), start[1]
        m2 = m + i // per_month
        y2 = y + (m2 - 1) // 12
        m2 = (m2 - 1) % 12 + 1
        out.append({"id": i + 1, "sim": s, "tier": tier, "source_name": source,
                    "title_en": f"Title {i}", "primary_vertical": "TECH",
                    "published_date": datetime(int(y2), m2, 15),
                    "tags": tags or [], "brands": names or [], "companies": []})
    return out


# --- assess_tier ---------------------------------------------------------------

def test_a_tier_below_its_head_minimum_answers_nothing_whatever_lies_above_the_floor():
    rows = _rows([0.66, 0.65, 0.64, 0.63, 0.63, 0.62, 0.62], tier="science")
    a = T.assess_tier(rows, "science")
    assert a["status"] == "none" and a["hits"] == []
    assert a["head"] == pytest.approx(0.642, abs=1e-3)


def test_the_cut_follows_the_head_and_is_reported():
    rows = _rows([0.90, 0.89, 0.88, 0.87, 0.86, 0.80, 0.75, 0.70, 0.65], tier="science")
    a = T.assess_tier(rows, "science")
    assert a["status"] == "ok"
    assert a["cut"] == pytest.approx(0.88 - T.DROP, abs=1e-3)
    assert [r["sim"] for r in a["hits"]] == [0.90, 0.89, 0.88, 0.87, 0.86, 0.80]


def test_the_cut_never_goes_below_the_floor():
    rows = _rows([0.70, 0.70, 0.69, 0.69, 0.69, 0.63, 0.61], tier="market")
    a = T.assess_tier(rows, "market")
    assert a["cut"] == T.FLOOR
    assert len(a["hits"]) == 6


def test_patents_have_their_own_lower_head_minimum():
    """Patent register: the best match sits ~0.08 below the science head for
    the same topic. 0.676 answered 14 perovskite patents on 2026-09-17."""
    rows = _rows([0.68, 0.68, 0.67, 0.67, 0.67, 0.64, 0.63], tier="patent")
    assert T.assess_tier(rows, "patent")["status"] == "ok"
    assert T.assess_tier(rows, "science")["status"] == "none"


def test_fewer_than_min_hits_is_thin_not_ok():
    rows = _rows([0.80, 0.79, 0.78, 0.77, 0.76, 0.50, 0.40], tier="funding")
    a = T.assess_tier(rows, "funding")
    assert a["status"] == "ok" and len(a["hits"]) == 5
    rows = _rows([0.80, 0.79, 0.78, 0.77, 0.50, 0.50, 0.40], tier="funding")
    assert T.assess_tier(rows, "funding")["status"] == "thin"


def test_a_full_window_above_the_cut_is_marked_capped():
    rows = _rows([0.9] * T.NEIGHBOURS, tier="science")
    a = T.assess_tier(rows, "science")
    assert a["capped"] is True
    rows = _rows([0.9] * 50 + [0.5] * (T.NEIGHBOURS - 50), tier="science")
    assert T.assess_tier(rows, "science")["capped"] is False


# --- curves --------------------------------------------------------------------

def test_month_series_counts_on_the_corpus_axis_and_ignores_months_off_it():
    months = ["2024-01", "2024-02", "2024-03"]
    rows = _rows([0.9, 0.9, 0.9, 0.9], start=("2024", 1))
    assert T.month_series(rows, months) == [1, 1, 1]


def test_damping_caps_a_source_at_its_own_median_but_leaves_short_series_alone():
    months = [f"2024-{m:02d}" for m in range(1, 13)]
    rows = []
    # one source: 1 per month for 11 months, then 20 in December
    for m in range(1, 12):
        rows += [{"published_date": datetime(2024, m, 1), "source_name": "A"}]
    rows += [{"published_date": datetime(2024, 12, 1), "source_name": "A"}] * 20
    # another source: only 3 active months, spiky — untouched
    rows += [{"published_date": datetime(2024, 5, 1), "source_name": "B"}] * 9
    rows += [{"published_date": datetime(2024, 6, 1), "source_name": "B"}]
    rows += [{"published_date": datetime(2024, 7, 1), "source_name": "B"}]
    assert T.damped_total(rows, months) == 11 + 1 + 11


# --- ambiguity -----------------------------------------------------------------

def test_a_short_query_spread_over_verticals_becomes_a_question():
    rows = []
    for i, v in enumerate(["TECH", "FOOD", "HEALTH", "ECO"] * 10):
        rows.append({"sim": 0.8 - i * 0.001, "primary_vertical": v, "title_en": f"t{i}"})
    amb = T.ambiguity("rag", rows)
    assert amb and len(amb["fields"]) == 3 and amb["fields"][0]["share"] == 0.25


def test_a_short_query_with_one_dominant_vertical_and_a_strong_head_is_not_ambiguous():
    rows = [{"sim": 0.8, "primary_vertical": "LIFESTYLE", "title_en": "x"}] * 30
    rows += [{"sim": 0.7, "primary_vertical": "HEALTH", "title_en": "y"}] * 5
    assert T.ambiguity("hyrox", rows, best_head=0.80) is None


def test_a_short_query_with_a_weak_best_head_is_a_question_even_when_one_vertical_dominates():
    """'rag' embedded as cloth: 134 science rows at head 0.686, one vertical."""
    rows = [{"sim": 0.68, "primary_vertical": "HEALTH", "title_en": "x"}] * 30
    amb = T.ambiguity("rag", rows, best_head=0.686)
    assert amb and "weak" in amb["reason"]


def test_a_long_query_is_never_ambiguous():
    rows = [{"sim": 0.8, "primary_vertical": v, "title_en": "x"} for v in ["A", "B", "C", "D"] * 5]
    assert T.ambiguity("precision fermentation of dairy proteins", rows, best_head=0.60) is None


# --- vocabulary walk candidates ---------------------------------------------------

def test_chain_candidates_are_repeated_pairs_not_already_in_the_query():
    titles = ["Artificial cow milk hits the market", "artificial cow milk startup raises",
              "Animal-free dairy protein via fermentation", "animal-free dairy is here",
              "Precision fermentation of dairy proteins scales"]
    cands = T.chain_candidates(titles, "precision fermentation of dairy proteins")
    assert "artificial cow" in cands and "cow milk" in cands and "animal-free dairy" in cands
    assert "precision fermentation" not in cands
    assert "dairy proteins" not in cands


# --- actors ----------------------------------------------------------------------

def test_actor_windows_and_sets():
    months = [f"20{y:02d}-{m:02d}" for y in range(20, 26) for m in range(1, 13)]
    w = T.actor_windows(months)
    assert w == ("2023-12", "2025-01")
    rows = [{"published_date": datetime(2022, 3, 1), "brands": ["Muufri"], "companies": []},
            {"published_date": datetime(2025, 6, 1), "brands": ["Perfect Day"], "companies": ["Formo"]},
            {"published_date": datetime(2024, 6, 1), "brands": ["Between"], "companies": []}]
    assert T.actor_sets(rows, w) == {"early": 1, "late": 2}
    assert T.actor_sets(rows, None) == {"early": 0, "late": 0}


# --- report assembly ----------------------------------------------------------------

def _corpus(months):
    return {"months": months, "totals": [100] * len(months),
            "tier_totals": {t: [25] * len(months) for t in T.TIERS},
            "source_first": {"Old Journal": months[0], "New Feed": months[-3]},
            "computed_at": "2026-09-17T00:00:00+00:00"}


def test_build_report_dates_each_tier_separately_and_orders_them():
    months = [f"20{y:02d}-{m:02d}" for y in range(18, 26) for m in range(1, 13)]
    sci = _rows([0.9] * 30, tier="science", source="Old Journal", start=("2019", 1), per_month=3)
    mkt = _rows([0.85] * 12, tier="market", source="New Feed", start=("2024", 1), per_month=3)
    results = {
        "science": T.assess_tier(sci, "science"),
        "market": T.assess_tier(mkt, "market"),
        "patent": T.assess_tier(_rows([0.5] * 10, tier="patent"), "patent"),
    }
    rep = T.build_report("q", ["science", "patent", "market"], results, _corpus(months),
                         [], [], {"science": True, "market": False, "patent": True}, None)
    assert rep["status"] == "ok"
    assert rep["tiers"]["science"]["first_month"] == "2019-01"   # 3 hits in a month (TIER_MIN_HITS)
    assert rep["tiers"]["science"]["first_hit"] == "2019-01"
    assert rep["tiers"]["market"]["first_month"] == "2024-01"
    assert rep["tiers"]["patent"]["status"] == "none"
    assert rep["overall"]["tier_order"] == ["science", "market"]
    assert rep["overall"]["science_to_market_months"] == 60
    assert rep["tiers"]["science"]["index"] == "tier" and rep["tiers"]["market"]["index"] == "scan"
    # 30 of 42 hits come from a source read since the start of the axis
    assert rep["overall"]["established_share"] == pytest.approx(30 / 42, abs=1e-3)
    assert rep["tiers_key"] == "science,patent,market"
    text = T.render_text(rep)
    assert "science → market +60 months" in text and "market   ok" in text


def test_build_report_says_nothing_when_no_tier_answers():
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    results = {t: T.assess_tier(_rows([0.5] * 10, tier=t), t) for t in ["science", "market"]}
    rep = T.build_report("harpsichord", ["science", "market"], results, _corpus(months), [], [], {}, None)
    assert rep["status"] == "nothing"
    assert "Nothing close" in T.render_text(rep)


def test_an_ambiguous_report_renders_as_a_question():
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    results = {"market": T.assess_tier(_rows([0.8] * 10, tier="market"), "market")}
    amb = {"reason": "short", "fields": [{"vertical": "TECH", "share": 0.3, "titles": ["a"]}]}
    rep = T.build_report("rag", ["market"], results, _corpus(months), [], [], {}, amb)
    assert rep["status"] == "ambiguous"
    assert T.render_text(rep).startswith("Topic: rag\n\nWhich field?")


# --- invariants ----------------------------------------------------------------------

def test_the_fts_expression_matches_the_researchers_one_textually():
    """Both must equal idx_trends_fts or the GIN index is not used."""
    import re
    src = open("scripts/corpus_research.py", encoding="utf-8").read()
    m = re.search(r'FTS_VECTOR = \("(.*?)"\s*\n\s*"(.*?)"\)', src, re.S)
    assert m, "FTS_VECTOR not found in corpus_research.py"
    assert T.FTS_VECTOR == m.group(1) + m.group(2)


def test_query_normalisation_is_the_cache_key():
    assert T.normalise_query("  GLP-1   Agonists ") == "glp-1 agonists"
    assert T.query_tokens("the RAG of things") == ["rag", "things"]
