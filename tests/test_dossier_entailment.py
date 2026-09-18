"""Stufe 4 „Pruefen statt Streichen" (2026-09-19, docs/plan_dossier_agent_2026-09-18.md):
Aussagenpruefung, Subjektabgleich per Stamm, Reparatur vor Streichung,
Quoten aus dem Material, vergangene Kalendertermine, PDF-Titel.

Alles ohne DB, ohne Netz, ohne GPU — das Modell ist ein Fake."""
from datetime import date

import pytest

from pipeline import dossier_entailment as de
from pipeline import dossier_structure as ds
from pipeline.dossier_check import check_result
from scripts import corpus_research as cr


PAGE_DATA_ACT = (
    "The Data Act applies to providers of data processing services offered to "
    "customers in the Union, regardless of the provider's size. Providers of "
    "data processing services shall remove obstacles to switching. Article 23 "
    "obliges providers to enable customers to switch to another provider.")
PAGE_BSI = (
    "Seite 1 von 8\nSYS.1.5 Virtualisierung\n1. Beschreibung\n1.1. Einleitung\n"
    "Der Baustein SYS.1.5 Virtualisierung beschreibt, wie Virtualisierungsserver "
    "abzusichern sind. Die Anforderungen des Bausteins gelten fuer alle Hypervisoren.")

SRC_ACT = {"id": "L1", "kind": "legal", "url": "https://eur-lex.example/data-act",
           "title": "Regulation (EU) 2023/2854", "text": PAGE_DATA_ACT, "fetched": True,
           "rank": 0}
SRC_BSI = {"id": "T900000000", "kind": "web", "url": "https://bsi.example/SYS_1_5.pdf",
           "title": "SYS.1.5 Virtualisierung", "text": PAGE_BSI, "fetched": True, "rank": 0}
SRC_ARTICLE = {"id": "T1", "kind": "article", "url": "https://catandary.de/trends/a-1",
               "title": "corpus", "text": "x"}

DOC = """# Dossier

## Decision summary

The EU Data Act does not apply to the firm's B2B service-provider model [[L1]]. For unclassified workloads the BSI Baustein SYS.1.5 remains the baseline [[T900000000]]. A third statement rests on corpus material [[T1]].

## What is moving

Providers must enable switching under the Data Act [[L1]].

## Regulatory and IP status

Article 23 of the Data Act obliges providers to enable switching [[L1]].

## What happens next

| Date | Event | Source | Why it matters |
|---|---|---|---|
| Q4 2027 | Data Act switching charges end [[L1]] | [[L1]] | cost |

## What the evidence does not support

Nothing here.

## Decision points and watch items

- Watch the BSI edition cycle [[T900000000]].

## Open questions and limits

Open.
"""


class FakeChat:
    """Antwortet je Seite nach einer Tabelle {url: {index: (verdict, quote)}}."""

    def __init__(self, table):
        self.table, self.calls, self.prompts = table, 0, []

    def __call__(self, *, model, schema, system, prompt, **kw):
        self.calls += 1
        self.prompts.append(prompt)
        url = prompt.split("\n", 1)[0].replace("Page: ", "").strip()
        n = prompt.count("\n") and len([ln for ln in prompt.split("<untrusted_sentences>")[1]
                                        .split("</untrusted_sentences>")[0].strip().split("\n") if ln.strip()])
        verdicts = []
        for i in range(n):
            v, q = self.table.get(url, {}).get(i, ("supported", "quote"))
            verdicts.append(de.EntailmentVerdict(sentence_index=i, verdict=v, quote=q))
        return de.EntailmentReview(verdicts=verdicts)


class TestCandidates:
    def test_core_sentences_are_grouped_per_cited_page(self):
        groups = de.entailment_candidates(DOC, [SRC_ACT, SRC_BSI, SRC_ARTICLE], "en")
        by_url = {g["source"]["url"]: g["sentences"] for g in groups}
        # Decision summary + regip + calendar row + watch item; "What is moving" is not core.
        assert len(by_url[SRC_ACT["url"]]) == 3
        assert all("switching" in s or "does not apply" in s for s in by_url[SRC_ACT["url"]])
        assert len(by_url[SRC_BSI["url"]]) == 2
        assert not any("corpus material" in s for g in groups for s in g["sentences"])

    def test_the_token_check_is_the_prefilter(self):
        flagged = "The EU Data Act does not apply to the firm's B2B service-provider model [[L1]]."
        groups = de.entailment_candidates(DOC, [SRC_ACT], "en", skip={flagged})
        assert flagged not in groups[0]["sentences"]

    def test_unfetched_pages_are_not_asked(self):
        src = dict(SRC_ACT, text=None, fetched=False)
        assert de.entailment_candidates(DOC, [src], "en") == []


class TestCheckEntailment:
    def test_the_v3_data_act_sentence_is_contradicted_and_dropped(self):
        """datacenter-virtualization v3: kein Token fehlte, die Seite sagt das
        Gegenteil — bis Stufe 4 ging der Satz durch."""
        chat = FakeChat({SRC_ACT["url"]: {0: ("contradicted",
                                               "The Data Act applies to providers of data processing services")}})
        out = de.check_entailment(DOC, [SRC_ACT, SRC_BSI], "en", model="m", chat=chat)
        assert chat.calls == 2 and out["calls"] == 2 and out["pages"] == 2
        assert len(out["contradicted"]) == 1
        f = out["contradicted"][0]
        assert f["kind"] == "contradicted" and "does not apply" in f["sentence"]
        assert f["tokens"] == ["The Data Act applies to providers of data processing services"]
        assert out["supported"] == out["sentences"] - 1
        cleaned, n = ds.drop_unverified(DOC, out["contradicted"], "en")
        assert n == 1 and "does not apply" not in cleaned and "BSI Baustein" in cleaned
        text = ds.revision_prompt([], out["contradicted"], "en")
        assert "WIDERSPRICHT" in text and "does not apply" in text

    def test_unrelated_maps_to_the_subject_finding(self):
        chat = FakeChat({SRC_BSI["url"]: {1: ("unrelated", "")}})
        out = de.check_entailment(DOC, [SRC_BSI], "en", model="m", chat=chat)
        assert out["contradicted"] == []
        assert len(out["unrelated"]) == 1 and out["unrelated"][0]["kind"] == "subject"
        assert out["unrelated"][0]["url"] == SRC_BSI["url"]

    def test_a_contradiction_without_a_quote_does_not_block(self):
        chat = FakeChat({SRC_ACT["url"]: {0: ("contradicted", "")}})
        out = de.check_entailment(DOC, [SRC_ACT], "en", model="m", chat=chat)
        assert out["contradicted"] == [] and len(out["unrelated"]) == 1

    def test_verdicts_are_cached_per_sentence_and_page(self):
        chat = FakeChat({SRC_ACT["url"]: {0: ("contradicted", "applies to providers")}})
        cache: dict = {}
        out1 = de.check_entailment(DOC, [SRC_ACT, SRC_BSI], "en", model="m", chat=chat, cache=cache)
        out2 = de.check_entailment(DOC, [SRC_ACT, SRC_BSI], "en", model="m", chat=chat, cache=cache)
        assert chat.calls == 2                       # der zweite Durchgang fragt nichts
        assert out2["calls"] == 0 and out2["sentences"] == out1["sentences"]
        assert len(out2["contradicted"]) == 1 and out2["supported"] == out1["supported"]

    def test_the_page_cap_is_honoured_and_reported(self):
        srcs = [dict(SRC_ACT, id=f"L{i}", url=f"https://p{i}.example/") for i in range(4)]
        doc = "## Decision summary\n\n" + " ".join(
            f"The Data Act applies to providers of data services in case {i} [[L{i}]]." for i in range(4)) + "\n"
        chat = FakeChat({})
        out = de.check_entailment(doc, srcs, "en", model="m", chat=chat, max_pages=2)
        assert out["capped"] is True and out["calls"] == 2 and out["pages_total"] == 4

    def test_a_failing_call_is_counted_not_raised(self):
        def boom(**kw):
            raise RuntimeError("server down")
        out = de.check_entailment(DOC, [SRC_ACT], "en", model="m", chat=boom)
        assert out["failed"] == 1 and out["contradicted"] == []

    def test_env_switch(self, monkeypatch):
        monkeypatch.setenv("DOSSIER_ENTAILMENT", "0")
        assert de.entailment_enabled() is False
        monkeypatch.delenv("DOSSIER_ENTAILMENT")
        assert de.entailment_enabled() is True

    def test_summary_block(self):
        chat = FakeChat({})
        a = de.check_entailment(DOC, [SRC_ACT], "en", model="m", chat=chat)
        s = de.entailment_summary(a, None)
        assert s["enabled"] and s["calls"] == 1 and s["before"]["supported"] == 3 and s["after"] is None


class TestPageExcerpt:
    def test_short_pages_pass_whole(self):
        assert de.page_excerpt(PAGE_BSI, ["x"]) == PAGE_BSI

    def test_long_pages_keep_the_lead_and_the_matching_paragraphs(self):
        filler = "\n\n".join(f"Paragraph {i} about nothing in particular." for i in range(300))
        page = "Lead paragraph.\n\n" + filler + "\n\nArticle 23 obliges providers to enable switching."
        ex = de.page_excerpt(page, ["Article 23 of the Data Act obliges providers to enable switching."],
                             limit=600)
        assert ex.startswith("Lead paragraph.") and "Article 23 obliges" in ex and len(ex) <= 600


class TestSubjectStems:
    """v4: „'BSI Baustein' absent from …pdf" — die Seite IST der Baustein."""

    def test_bsi_baustein_is_supported_by_the_baustein_page(self):
        sent = "For unclassified workloads, the BSI Baustein SYS.1.5 (Virtualisierung) remains the baseline [[T900000000]]."
        assert "BSI Baustein" in ds.subject_names(sent)
        assert ds.unverified_subjects(sent, PAGE_BSI) == []

    def test_german_inflections_and_umlauts_match_by_stem(self):
        assert ds.unverified_subjects("The Bausteine of the Kompendium apply.",
                                      "Der Baustein gilt; das Kompendium auch.") == []
        assert ds.unverified_subjects("Müller Maschinenbau expands.",
                                      "Mueller Maschinen-Bau expandiert.") == []

    def test_a_different_subject_is_still_rejected(self):
        novo = "Novo Nordisk wins FDA approval for the Wegovy pill."
        bad = ds.unverified_subjects("Eli Lilly's orforglipron achieved approval.", novo)
        assert any("Lilly" in b for b in bad) and "orforglipron" in bad
        assert ds.unverified_subjects("The BSI Baustein applies.", "The Lego Bausteinkasten is fun.") == ["BSI Baustein"]

    def test_short_only_names_still_need_every_word(self):
        assert ds._in_source_phrase("EU AI", {"eu"}) is False
        assert ds._in_source_phrase("EU AI", {"eu", "ai"}) is True


class TestRepairBeforeDrop:
    def test_second_pass_rereads_the_page_wider_and_only_for_named_sentences(self, monkeypatch):
        prompts = []

        def fake_chat(*, model, system, prompt, **kw):
            prompts.append(prompt)
            return "Rewritten sentence with the page's figure of 4 % [[L1]]."
        monkeypatch.setattr(cr.llamacpp_client, "chat", fake_chat)
        page = "Lead.\n\n" + "\n\n".join(f"Paragraph {i} filler text here." for i in range(200)) \
            + "\n\nThe share is 4 % according to the register."
        src = [dict(SRC_ACT, text=page)]
        sent_core = "The share is 12 % according to the register [[L1]]."
        sent_filler = "Unrelated filler says 99 % [[L1]]."
        report = f"## Decision summary\n\n{sent_core}\n\n## What is moving\n\n{sent_filler}\n"
        findings = [{"sentence": sent_core, "tokens": ["12"], "kind": "figure", "url": SRC_ACT["url"]},
                    {"sentence": sent_filler, "tokens": ["99"], "kind": "figure", "url": SRC_ACT["url"]}]
        out, n = cr.repair_sentences(report, findings, src, {"temperature": 0.2}, pass_no=2, only={sent_core})
        assert n == 1 and sent_filler in out and sent_core not in out and "4 %" in out
        assert len(prompts) == 1 and "SECOND ATTEMPT" in prompts[0]
        assert "The share is 4 %" in prompts[0]        # breiter gelesen: die Zielstelle ist drin

    def test_the_unsupported_token_may_not_come_back(self, monkeypatch):
        monkeypatch.setattr(cr.llamacpp_client, "chat",
                            lambda **kw: "Still says 12 % [[L1]].")
        sent = "The share is 12 % [[L1]]."
        out, n = cr.repair_sentences(sent, [{"sentence": sent, "tokens": ["12"], "kind": "figure",
                                             "url": SRC_ACT["url"]}], [SRC_ACT], pass_no=2, only={sent})
        assert n == 0 and out == sent


class TestQuotasFromMaterial:
    def test_minima_follow_the_material_with_floors(self):
        assert ds.actor_min_from_material(0) == 2
        assert ds.actor_min_from_material(3) == 3
        assert ds.actor_min_from_material(9) == ds.ACTOR_ROWS_MIN
        assert ds.watch_min_from_material(0) == 2
        assert ds.watch_min_from_material(2) == 2
        assert ds.watch_min_from_material(7) == ds.WATCH_MIN_ITEMS

    def test_actor_finding_names_the_applicable_minimum(self):
        head = ["| Actor | What happened | Date | Source |", "|---|---|---|---|"]
        rows = [f"| Actor {i} | GLP-1 result {i} 12% | 2026 | [[A{i}]] |" for i in range(3)]
        doc = "## What is moving\n\n" + "\n".join(head + rows) + "\n"
        assert ds.actor_findings(doc, "en", ("glp-1",), min_rows=3) == []
        f = ds.actor_findings(doc, "en", ("glp-1",))
        assert f and "at least 5 needed" in f[0]
        f2 = ds.actor_findings(doc, "en", ("glp-1",), min_rows=4)
        assert f2 and "at least 4 needed" in f2[0] and "Open questions and limits" in f2[0]

    def test_watch_finding_names_the_applicable_minimum(self):
        doc = "## Decision points and watch items\n\n- Watch GLP-1 pricing [[A1]].\n- Watch GLP-1 supply [[A2]].\n"
        assert ds.watch_findings(doc, "en", ("glp-1",), min_items=2) == []
        f = ds.watch_findings(doc, "en", ("glp-1",))
        assert f and "von mindestens 3" in f[0]
        assert ds.structure_findings(doc, "en", topic_terms=("glp-1",), watch_min=2) == \
            [x for x in ds.structure_findings(doc, "en", topic_terms=("glp-1",), watch_min=2)]
        assert not any("Decision points" in x for x in
                       ds.structure_findings(doc, "en", topic_terms=("glp-1",), watch_min=2))


def _cal(rows):
    head = ["| Date | Event | Source | Why it matters |", "|---|---|---|---|"]
    return "## Decision summary\n\nx\n\n## What happens next\n\n" + "\n".join(head + rows) + "\n"


class TestCalendarToday:
    TODAY = date(2026, 9, 19)

    def test_past_precise_dates_are_passed_not_ok(self):
        rows = ["| 12 September 2026 | GLP-1 pill launched in Germany | [[A1]] | y |",
                "| Q3 2026 | GLP-1 readout | [[A2]] | y |",
                "| July 2026 | GLP-1 price cut | [[A3]] | y |",
                "| 11 October 2027 | GLP-1 patent expiry | [[A4]] | y |",
                "| 2026 | GLP-1 guidance | [[A5]] | y |"]
        c = ds.calendar_rows(_cal(rows), "en", 2026, ("glp-1",), today=self.TODAY)
        assert c["passed"] == 2 and c["ok"] == 3
        assert ds.calendar_rows(_cal(rows), "en", 2026, ("glp-1",))["ok"] == 5
        f = ds.calendar_findings(_cal(rows), "en", 2026, ("glp-1",), min_rows=5, today=self.TODAY)
        assert f and "2 Zeile(n) mit einem Termin, der schon vergangen ist" in f[0]
        assert "vor dem heutigen Tag" in f[0]

    def test_has_date_and_date_passed(self):
        assert ds.date_passed("2026-09-18", self.TODAY) is True
        assert ds.date_passed("H1 2026", self.TODAY) is True
        assert ds.date_passed("Q4 2026", self.TODAY) is False
        assert ds.date_passed("mid-2026", self.TODAY) is False
        assert ds.date_passed("no date at all", self.TODAY) is False
        assert ds.has_date("March 2026", 2026, today=self.TODAY) is False
        assert ds.has_date("March 2026", 2026) is True
        # zwei Termine, einer noch offen: die Zeile lebt
        assert ds.date_passed("from March 2026 to Q4 2026", self.TODAY) is False

    def test_fill_calendar_skips_passed_candidates(self):
        doc = _cal(["| Q4 2027 | GLP-1 decision | [[A1]] | y |"])
        cands = [{"id": "A2", "when": "12 May 2026", "statement": "GLP-1 launch expected"},
                 {"id": "A3", "when": "Q1 2027", "statement": "GLP-1 CHMP opinion expected"}]
        out, n = ds.fill_calendar(doc, cands, "en", 2026, ("glp-1",), 2, today=self.TODAY)
        assert n == 1 and "Q1 2027" in out and "12 May 2026" not in out

    def test_structure_findings_threads_today(self):
        rows = [f"| {m} 2026 | GLP-1 event | [[A{i}]] | y |" for i, m in enumerate(("January", "February", "March"))]
        f = ds.structure_findings(_cal(rows), "en", topic_terms=("glp-1",), calendar_min=3, today=self.TODAY)
        assert any("vergangen" in x for x in f)


class TestPdfTitle:
    def test_boilerplate_titles_fall_back_to_the_file_name(self):
        url = "https://www.bsi.bund.de/x/SYS_1_5_Virtualisierung_Edition_2022.pdf?__blob=publicationFile&v=3"
        assert cr._is_pdf_url(url)
        assert cr.pdf_title(url, "Stand Februar 2022 Seite 1 von 9 SYS.1.5 Virtualisierung 1. Beschreibung") \
            == "SYS 1 5 Virtualisierung Edition 2022"
        assert cr.pdf_title(url, "Seite 1 von 8 SYS.1.5 Virtualisierung 1. Beschreibung 1.1. Einleitung") \
            == "SYS 1 5 Virtualisierung Edition 2022"

    def test_a_real_search_title_is_kept(self):
        url = "https://nsf.example/pubs/nsf18540.pdf"
        assert cr.pdf_title(url, "NSF/VMware Partnership on Edge Computing Data Infrastructure (ECDI)") \
            == "NSF/VMware Partnership on Edge Computing Data Infrastructure (ECDI)"
        assert cr.pdf_title("https://x.de/a/Data%20Management%20Guide%20(2020).pdf", "") \
            == "Data Management Guide (2020)"

    def test_html_urls_are_untouched(self):
        assert cr._is_pdf_url("https://x.de/report.pdf?dl=1")
        assert not cr._is_pdf_url("https://x.de/page.html")


class TestCheckResultReportsContradicted:
    def test_contradicted_sentences_reach_the_check_json(self):
        res = {"report": "x [a](https://a.de/b)", "sources": [SRC_ARTICLE],
               "evidence": [], "cited": ["T1"], "ledger": [],
               "structure": {"dropped_sentences": 1, "findings_after": [],
                             "cite_findings": [], "cite_findings_after": [],
                             "contradicted_after": ["The EU Data Act does not apply [[L1]]."],
                             "entailment": {"enabled": True, "calls": 3, "seconds": 41.0,
                                            "before": {"pages": 2, "sentences": 5, "supported": 4,
                                                       "contradicted": 1, "unrelated": 0, "capped": False},
                                            "after": {"contradicted": 1, "unrelated": 0}}}}
        out = check_result(res)
        assert out["contradicted"] == ["The EU Data Act does not apply [[L1]]."]
        assert any("widerspricht" in f for f in out["findings"])
        assert any("Aussagenpruefung: 3 Aufruf(e)" in f for f in out["findings"])
        assert any("1× widersprach die zitierte Seite" in f for f in out["findings"])
