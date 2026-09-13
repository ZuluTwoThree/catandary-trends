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

    def test_generated_sources_list_is_cut_before_grounding(self):
        # Regression 2026-09-04 (zweiter #96-Dry-Run): die Ordinalzahlen "12."/"14."
        # der code-generierten Quellenliste zählten als unbelegte Zahlen.
        report = ("Meta settled [Meta's settlement](https://catandary.de/trends/x-1).\n\n"
                  "---\n\n## Sources\n\n"
                  + "\n".join(f"{i}. [Source {i}](https://s.example/{i}) — outlet — 2024-06-04 *(patent filing)*"
                               for i in range(1, 15)))
        res = {"report": report, "evidence": ["Meta settled"], "sources": [],
               "cited": ["T1"], "stripped_citations": 0, "ledger": []}
        c = check_result(res)
        assert c["ungrounded"] == []
        assert c["words"] < 10          # die 14 Listenzeilen zählen nicht mit


class TestOkDescribesTheDeliveredDocument:
    """2026-09-12 (LFP v4): 13 Saetze nach dem Neuwurf gestrichen/gekennzeichnet,
    Dokument danach sauber — das ist ein Befund im Nachweis, keine Sperre."""

    def test_post_rewrite_cleanup_is_reported_but_not_blocking(self):
        r = _result("Fine.")
        r["structure"] = {
            "dropped_sentences": 3, "weakclaim_after": 2, "off_topic_after": 1,
            "cite_findings_after": [{"kind": "weakclaim", "sentence": "x"}],
            "findings_after": []}
        c = check_result(r)
        assert c["ok"] is True
        assert any("gestrichen" in f for f in c["findings"])

    def test_a_structural_finding_after_cleanup_still_blocks(self):
        r = _result("Fine.")
        r["structure"] = {"findings_after": ["Option 2: Pflichtfeld fehlt"]}
        assert check_result(r)["ok"] is False


def test_cite_driven_fetch_is_reported_not_blocking():
    r = _result("Fine.")
    r["structure"] = {"adopted_sources": 2, "precanon_stripped": 1, "findings_after": []}
    c = check_result(r)
    assert c["ok"] is True
    assert any("Zitatgetriebener Abruf: 2" in f for f in c["findings"])


def test_fetched_page_text_grounds_a_figure_even_if_the_notes_only_hold_passages():
    r = _result("Stationary storage packs averaged $56/kWh in 2025.",
                evidence=["Key passages: prices fell again in 2025."],
                sources=[{"title": "BNEF survey", "snippet": "", "date": "2025-12-09", "outlet": "BNEF",
                          "text": "… stationary storage systems at $56/kWh …"}])
    c = check_result(r)
    assert c["ungrounded"] == [] and c["ok"] is True


def test_reader_notes_are_reported_but_never_block():
    r = _result("Fine.")
    r["structure"] = {"findings_after": [], "reader_after": {
        "answers_question": True, "overall": "Solid.",
        "findings": [{"section": "Options", "severity": "major", "issue": "Option 2 has no trigger.",
                      "suggestion": "Tie it to the 2027 pilot."},
                     {"section": "Body", "severity": "minor", "issue": "padding", "suggestion": "cut"}]}}
    c = check_result(r)
    assert c["ok"] is True and c["reader_ok"] is False
    assert any("Leser (nicht sperrend) [Options]" in f for f in c["findings"])
    r["structure"]["reader_after"] = {"answers_question": True, "overall": "Good.", "findings": []}
    c = check_result(r)
    assert c["reader_ok"] is True and any("keine wesentlichen Einwaende" in f for f in c["findings"])
