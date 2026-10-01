"""pipeline/calendar_dating.py — a pocket dated by the research and patent calendar.

Pins: the phrases are what sets the pocket apart from its domain (not the domain term
itself), the query is anchor AND any phrase, and first year / take-off / growth follow
the stated rules on the per-million series, with the corpus start reported as an edge."""
from pipeline import calendar_dating as C


def test_phrases_set_the_pocket_apart_from_its_domain_and_skip_the_anchor():
    domain = ["Lithium battery anode coating"] * 40 + ["Battery thermal runaway in packs"] * 10
    nest = ["Thermal runaway of lithium battery packs", "Battery thermal runaway propagation",
            "Suppressing thermal runaway in battery modules", "Thermal runaway gas venting"]
    got = C.nest_phrases(nest, domain + nest, ["batteries"])
    assert got and got[0] == "thermal runaway"
    assert all("batter" not in p for p in got)


def test_query_is_anchor_and_any_phrase():
    expr, params = C._tsquery(["batteries", "battery storage"], ["redox flow", "flow battery"])
    assert expr.count("phraseto_tsquery") == 4 and ") && (" in expr
    assert params == ["batteries", "battery storage", "redox flow", "flow battery"]
    assert C._tsquery([], ["x"])[0].count("&&") == 0


def test_first_year_take_off_growth_and_edge():
    totals = {y: 1_000_000 for y in range(2010, 2027)}
    counts = {2012: 2, 2014: 3, 2016: 10, 2018: 40, 2019: 50, 2020: 60, 2021: 80, 2022: 90,
              2023: 100, 2024: 140, 2025: 150, 2026: 30}
    s = C.summarise(counts, totals, 2010, this_year=2026)
    assert s["first"] == 2014 and not s["edge"]
    assert s["takeoff"] == 2018                      # 40 >= 0.15 * 150 (peak over complete years)
    assert s["growth"] == round((100 + 140 + 150) / (80 + 90 + 60), 2)
    assert s["years"][0] == 2010 and s["per_million"][s["years"].index(2025)] == 150.0
    edge = C.summarise({2010: 5, 2011: 5}, totals, 2010, this_year=2026)
    assert edge["first"] == 2010 and edge["edge"]


def test_the_running_year_never_decides_the_take_off():
    totals = {y: 1000 for y in range(2010, 2027)}
    s = C.summarise({2026: 500, 2015: 3}, totals, 2010, this_year=2026)
    assert s["takeoff"] == 2015
