"""Belegprüfung (pipeline/report_check.py) und Eingrenzungs-Helfer der Korpus-API (08.10.2026).

Ohne Datenbank: Lookups werden als Callables hereingereicht, die Themenzuordnung als Dict.
"""
import pytest

from pipeline import report_check as rc

RESULTS = [
    {"tool": "term_counts", "text": '{"terms": [{"term": "electrolyzed water", "science": 953, "patent": 3429}]}'},
    {"tool": "eurlex_search", "text": '{"results": [{"celex": "32021R0364", "title": "approving active chlorine"}]}'},
    {"tool": "search_research", "text": '{"results": [{"doi": "https://doi.org/10.1016/j.real.2021.1", "cited_by": 24, "fwci": 1.234}]}'},
]
TOOLS = ["term_counts", "eurlex_search", "search_research", "fetch_url", "emerging_nests"]

REPORT = """## 3.1 Messung
| electrolyzed water | 953 | 3 429 |
Wir haben mit fetch_url gelesen.
1. Echte Arbeit, DOI 10.1016/j.real.2021.1, zitiert 24-mal, FWCI 1,23.
2. Erfunden, DOI 10.9999/fake.2020.7, zitiert 87-mal.
3. Falscher Titel „Hydrogen bacteria protein" – DOI 10.1128/mbio.02020-20.
Rechtsakte 32021R0364 und 32022R9999. Patent EP-3535216-B1 und EP 1234567 A1.
Im Jahr 2025 stieg es um 140 Werke; Abschnitt 4. CPC A23L3/32.
"""


def lookups():
    corpus = {"10.1128/mbio.02020-20": "Experimental Human Challenge Defines Distinct Pneumococcal Kinetic Profiles"}
    return dict(doi_lookup=lambda ds: {d: corpus[d] for d in ds if d in corpus},
                patent_lookup=lambda ps: {"EP-3535216-B1", "EP-3535216"},
                doi_external=lambda d: None,
                celex_lookup=lambda c: None)


def test_report_check_flags_fabrications():
    out = rc.check_report(REPORT, RESULTS, TOOLS, **lookups())
    st = {d["doi"]: d["status"] for d in out["dois"]}
    assert st == {"10.1016/j.real.2021.1": "in_results", "10.9999/fake.2020.7": "not_found",
                  "10.1128/mbio.02020-20": "title_mismatch"}
    assert {c["celex"]: c["status"] for c in out["celex"]} == {"32021R0364": "in_results", "32022R9999": "not_found"}
    assert {p["patent"]: p["status"] for p in out["patents"]} == {"EP-3535216-B1": "exists_not_from_tools",
                                                                 "EP-1234567-A1": "not_in_corpus"}
    assert out["tools"]["mentioned_not_called"] == ["fetch_url"]
    unsupported = {n["number"] for n in out["numbers_unsupported"]}
    assert {"87", "140"} <= unsupported
    assert not {"953", "3 429", "24", "1,23"} & unsupported        # belegt, auch gerundet / mit Tausenderleerzeichen
    assert out["summary"]["verdict"] == "problems"


def test_report_check_ok_when_everything_from_tools():
    text = "Gemessen: 953 Arbeiten und 3 429 Patente (term_counts). Quelle 32021R0364."
    out = rc.check_report(text, RESULTS, TOOLS, **lookups())
    assert out["summary"]["verdict"] == "ok", out


def test_number_parsing_and_masking():
    assert rc.parse_number("3 429") == 3429 and rc.parse_number("3,429") == 3429 and rc.parse_number("6,4") == 6.4
    toks = [t for t, _, _ in rc.report_numbers("Seit 2016 (K ≈ 6,4) 1. Punkt 2024-03-01 DOI 10.1016/x.123456 A23L3/32 und 420 Werke")]
    assert toks == ["6,4", "420"]


def test_find_patents_normalises_variants():
    assert rc.find_patents("EP3535216B1, US 12722991 B2, WO2024/123456 A1, CN-116622681-A") == [
        "EP-3535216-B1", "US-12722991-B2", "WO-2024123456-A1", "CN-116622681-A"]


def test_scope_topics_and_cpc_prefixes():
    from pipeline import corpus_api as c
    tmap = {"Food Safety and Hygiene": ("Food Science", "Agricultural and Biological Sciences"),
            "Electrocatalysts for Energy Conversion": ("Catalysis", "Chemical Engineering")}
    assert c.scope_topics(["food science"], tmap=tmap) == ["Food Safety and Hygiene"]
    assert c.scope_topics(None, None, tmap=tmap) is None
    with pytest.raises(c.ToolError, match="closest"):
        c.scope_topics(["Food Sciences"], tmap=tmap)
    assert c.cpc_prefixes(["a23", "A23L 3/32", "C02F"]) == ["A23", "A23L3/32", "C02F"]
    with pytest.raises(c.ToolError):
        c.cpc_prefixes(["food"])
    assert c.cpc_prefixes(None) is None


def test_result_log_is_bounded_and_skips_verify(monkeypatch):
    from pipeline import corpus_api as c
    monkeypatch.setattr(c, "RESULT_LOG_MAX_CHARS", 100)
    c._RESULT_LOG.clear()
    monkeypatch.setattr(c, "_RESULT_CHARS", 0)
    for i in range(10):
        c.record_result("term_counts", {}, {"i": i, "pad": "x" * 20})
    c.record_result("verify_report", {}, {"x": 1})
    recent = c.recent_results(5)
    assert recent and all(r["tool"] == "term_counts" for r in recent)
    assert sum(len(r["text"]) for r in recent) <= 100
