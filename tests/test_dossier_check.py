"""Endkontrolle des Agenten (pipeline/dossier_check.py).

Kernversprechen: jede konkrete Zahl im modellgeschriebenen Berichtsteil muss
im gesammelten Beweismaterial vorkommen — und der code-generierte
Coverage-Anhang (dessen Zählwerte im Code entstehen) darf dabei nie als
"Erfindung" zählen.
"""
from pipeline.dossier_check import COVERAGE_HEADING, check_result


def _result(report: str, evidence=None, sources=None, cited=None,
            stripped=0, ledger=None) -> dict:
    return {
        "report": report,
        "evidence": evidence or [],
        "sources": sources if sources is not None else
            [{"title": "A source", "snippet": "context", "date": "2026-01-01",
              "outlet": "Test"}],
        "cited": cited if cited is not None else ["T1"],
        "stripped_citations": stripped,
        "ledger": ledger or [],
        "question": "q",
    }


class TestGrounding:
    def test_german_coverage_appendix_is_stripped_too(self):
        # lang=de-Berichte (Firmen-Dossiers) tragen die deutsche Überschrift;
        # ihre Zählwerte dürfen genauso wenig als Erfindung zählen.
        r = _result("Alles belegt.\n\n---\n\n"
                    "## Recherche-Abdeckung (automatisch erzeugt)\n\n"
                    "- Lücke: 14 Paper, 7 Patente, 23 Web-Treffer 2031",
                    evidence=["Alles belegt."])
        c = check_result(r)
        assert c["ungrounded"] == []
        assert c["ok"] is True
        assert c["open_questions"] == 0

    def test_grounded_report_is_ok(self):
        r = _result("Capacity retention was 84% after 350 cycles in 2026.",
                    evidence=["Full text: retention of 84% after 350 cycles, "
                              "reported 2026."])
        c = check_result(r)
        assert c["ungrounded"] == []
        assert c["ok"] is True
        assert c["findings"] == []

    def test_fabricated_figure_is_flagged(self):
        r = _result("The market will reach $47 billion by 2031.",
                    evidence=["The market is growing strongly."])
        c = check_result(r)
        assert c["ok"] is False
        assert any("2031" in t for t in c["ungrounded"])
        assert any("ohne Beleg" in f for f in c["findings"])

    def test_coverage_annex_numbers_never_count(self):
        annex = (f"\n\n---\n\n{COVERAGE_HEADING}\n\n"
                 "1. open question\n   → research corpus: 3 paper(s) · "
                 "patents: 2 filing(s) · web: 4 queries, 5 source(s), 1 fetched")
        r = _result("The field is moving." + annex, evidence=["moving field"])
        c = check_result(r)
        assert c["ungrounded"] == []
        assert c["ok"] is True

    def test_catalog_snippets_ground_too(self):
        r = _result("Pilot line opened in 2024.",
                    sources=[{"title": "Pilot line 2024", "snippet": "",
                              "date": "", "outlet": ""}])
        assert check_result(r)["ungrounded"] == []


class TestCitationLedger:
    def test_stripped_citations_are_a_finding(self):
        c = check_result(_result("Fine.", stripped=2))
        assert c["ok"] is False
        assert any("gestrichen" in f for f in c["findings"])

    def test_no_surviving_citation_is_a_finding(self):
        c = check_result(_result("Fine.", cited=[]))
        assert c["ok"] is False
        assert any("Kanonisierung" in f for f in c["findings"])

    def test_open_questions_reported_but_not_blocking(self):
        c = check_result(_result("Fine.", ledger=[{"gap": "x"}, {"gap": "y"}]))
        assert c["open_questions"] == 2
        assert c["ok"] is True                  # offen ≠ falsch — nur sichtbar

    def test_empty_report_is_never_ok(self):
        c = check_result(_result("   "))
        assert c["ok"] is False


class TestCitationUrlsAreNotFigures:
    def test_slug_ids_and_patent_numbers_in_link_urls_never_count(self):
        # Regression 2026-09-04 (Newsletter-Deep-Dive): alle drei "unbelegten
        # Zahlen" waren die -<id>-Endungen der Artikel-Slugs in den Zitat-URLs.
        report = ("Meta settled [Meta's settlement]"
                  "(https://catandary.de/trends/meta-s-settlement-24632113) and a "
                  "[zero-trust method](https://patents.google.com/patent/CN117688608A) exists.")
        res = {"report": report, "evidence": ["Meta settled; a zero-trust method exists"],
               "sources": [], "cited": ["T1"], "stripped_citations": 0, "ledger": []}
        c = check_result(res)
        assert c["ungrounded"] == []
        assert c["ok"] is True

    def test_figure_in_the_label_still_counts(self):
        report = "[Retention of 84% after 350 cycles](https://catandary.de/trends/x-1)."
        res = {"report": report, "evidence": ["nothing about that"], "sources": [],
               "cited": ["T1"], "stripped_citations": 0, "ledger": []}
        assert set(check_result(res)["ungrounded"]) == {"84%", "350"}
