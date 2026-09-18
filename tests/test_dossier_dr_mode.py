"""DR-Modus: die Arbeitsweise eines Deep-Research-Agenten (2026-09-07).

Owner-Auftrag: „Variiere die Modellparameter und den Prompt so, dass qwen eher
arbeitet wie ein Sonnet-Deep-Research-Agent." Gemessene Ausgangslage am Lauf
`dossiers.id=25` (Runde 9, zweiter Lauf):

  E1  Der Katalog trug 17 Patente (Rang 0), 28 Paper (Rang 1) und 11 Behoerden-
      seiten (Rang 0). Zitiert wurden 6 Primaerquellen und kein einziges Paper.
  E2  84 Sweep-Treffer blieben ungelesen und damit nicht zitierfaehig, darunter
      pubmed (6x), sec.gov (2x), investor.lilly.com (2x), ema.europa.eu (2x),
      cms.gov (2x) — das Leseauffangnetz liest 12 Seiten in Fundreihenfolge.
  E3  Faktenquote 0,25 datierte, primaerbelegte Angaben je 100 Woerter
      (34 datierte Aussagen, davon 3 primaerbelegt) gegen 1,83 des
      Vergleichstexts.

Geprueft wird hier, dass die drei Gegenmassnahmen mechanisch tun, was sie
sollen — ohne DB, ohne Netz, ohne GPU.
"""
from pathlib import Path

import pytest

from scripts import corpus_research as cr


# --------------------------------------------------------------------------
# 1. Sampling nach Modellkarte statt reiner Temperatur
# --------------------------------------------------------------------------

def test_sampling_is_off_in_the_old_path():
    assert cr.dr_sampling("write", False) == {}
    assert cr.dr_sampling("work", False) == {}


def test_write_sampling_follows_the_model_card():
    """Modellkarte, mit EINER begruendeten Abweichung.

    presence_penalty 0.5 statt 1.5: die 1.5 der Karte bestrafen jedes schon
    verwendete Token — in einem Entscheidungspapier sind das der Wirkstoff in
    Kalender und Option, die Katalog-Id hinter drei Saetzen, das Jahr in fuenf
    Kalenderzeilen (R13-8, 2026-09-07)."""
    s = cr.dr_sampling("write", True)
    assert s["temperature"] == 0.7 and s["top_p"] == 0.80
    assert s["top_k"] == 20 and s["presence_penalty"] == 0.5


def test_structured_calls_carry_no_presence_penalty():
    """Die Strafe traefe sonst die Schluesselnamen des JSON-Schemas."""
    assert "presence_penalty" not in cr.dr_sampling("work", True)


def test_client_sends_only_what_was_set():
    from pipeline import llamacpp_client
    payload: dict = {}
    llamacpp_client._add_sampling(payload, top_p=0.8, top_k=20)
    assert payload == {"top_p": 0.8, "top_k": 20}
    llamacpp_client._add_sampling(payload, presence_penalty=1.5)
    assert payload["presence_penalty"] == 1.5


# --------------------------------------------------------------------------
# 2. Primaerquellen zuerst lesen (E1/E2)
# --------------------------------------------------------------------------

def _src(sid, url, kind="web", **kw):
    d = {"id": sid, "url": url, "kind": kind, "title": sid, "outlet": "",
         "snippet": "", "date": "", "vertical": "", "fetched": False}
    d.update(kw)
    return d


def test_primary_first_reads_the_authority_before_the_trade_press(monkeypatch):
    read: list[str] = []

    def fake_fetch(url):
        read.append(url)
        return ("Body text of " + url + " with a date 12 May 2026.", "ok")

    monkeypatch.setattr(cr, "fetch_web_page_status", fake_fetch)
    sources = [
        _src("W1", "https://www.fiercepharma.com/a"),        # Rang 2
        _src("W2", "https://www.ema.europa.eu/en/x"),        # Rang 0
        _src("W3", "https://investor.lilly.com/news/1", entity="Eli Lilly"),
    ]
    out = cr.read_primary_first(sources, [], [], ["glp-1"],
                                entities=["Eli Lilly"])
    assert out["read"] == 2
    assert read[0].startswith("https://www.ema.europa.eu")   # Rang 0 zuerst
    assert "fiercepharma" not in " ".join(read)              # Rang 2 nie
    assert sources[1]["fetched"] and sources[2]["fetched"]
    assert sources[0]["fetched"] is False


def test_primary_first_respects_its_budget(monkeypatch):
    monkeypatch.setattr(cr, "fetch_web_page_status",
                        lambda url: ("text " * 50, "ok"))
    sources = [_src(f"W{i}", f"https://www.fda.gov/p{i}") for i in range(10)]
    out = cr.read_primary_first(sources, [], [], ["x"], budget=3)
    assert out["read"] == 3 and out["candidates"] == 10
    assert sum(1 for s in sources if s["fetched"]) == 3


def test_primary_first_leaves_an_unreachable_page_uncitable(monkeypatch):
    monkeypatch.setattr(cr, "fetch_web_page_status", lambda url: ("", "robots"))
    sources = [_src("W1", "https://www.ema.europa.eu/en/x")]
    out = cr.read_primary_first(sources, [], [], ["x"])
    assert out["read"] == 0 and out["failed"] == 1
    assert not sources[0]["fetched"]


def test_primary_first_never_touches_corpus_kinds(monkeypatch):
    monkeypatch.setattr(cr, "fetch_web_page_status",
                        lambda url: pytest.fail("must not fetch"))
    sources = [_src("P1", "https://doi.org/10.1/x", kind="paper"),
               _src("Q1", "https://espacenet.com/x", kind="patent")]
    assert cr.read_primary_first(sources, [], [], ["x"])["read"] == 0


# --------------------------------------------------------------------------
# 3. Notizen vor dem Schreiben — und ihre Gegenpruefung (E3)
# --------------------------------------------------------------------------

PAGE = ("EMA decision record, Committee for Medicinal Products for Human Use. "
        "On 12 May 2026 the CHMP adopted a positive opinion for orforglipron. "
        "The applicant reported a 14.7% mean weight reduction over 72 weeks in "
        "3,127 patients. The opinion now goes to the European Commission, "
        "which decides on the marketing authorisation for the European Union.")


def test_a_note_whose_date_is_not_on_the_page_is_dropped():
    f = cr.LedgerFact(date="3 June 2026", statement="CHMP adopted an opinion.")
    assert cr._fact_grounded(f, PAGE) is False


def test_a_note_whose_figure_is_not_on_the_page_is_dropped():
    f = cr.LedgerFact(date="12 May 2026",
                      statement="CHMP saw a 19.2% weight reduction.")
    assert cr._fact_grounded(f, PAGE) is False


def test_a_grounded_note_survives():
    f = cr.LedgerFact(date="12 May 2026",
                      statement="CHMP adopted a positive opinion for "
                                "orforglipron after a 14.7% reduction.")
    assert cr._fact_grounded(f, PAGE) is True


def test_a_note_without_a_date_is_never_a_note():
    assert cr._fact_grounded(
        cr.LedgerFact(date="", statement="CHMP adopted an opinion."), PAGE) is False


def test_the_year_alone_anchors_a_differently_written_date():
    f = cr.LedgerFact(date="May 2026", statement="CHMP adopted an opinion.")
    assert cr._fact_grounded(f, PAGE) is True


def test_harvest_takes_notes_only_from_primary_sources(monkeypatch):
    seen: list[str] = []

    def fake_structured(**kw):
        seen.append(kw["prompt"])
        return cr.LedgerFacts(facts=[
            cr.LedgerFact(date="12 May 2026",
                          statement="CHMP adopted a positive opinion."),
            cr.LedgerFact(date="1 January 2030",
                          statement="Something the page never says."),
        ])

    monkeypatch.setattr(cr.llamacpp_client, "chat_structured",
                        lambda **kw: fake_structured(**kw))
    sources = [
        {"id": "W1", "kind": "web", "rank": 0, "text": PAGE, "title": "EMA"},
        {"id": "W2", "kind": "web", "rank": 2, "text": PAGE, "title": "press"},
    ]
    facts = cr.harvest_facts(sources, "question?")
    assert len(seen) == 1                      # Rang 2 wird nicht befragt
    assert [f["id"] for f in facts] == ["W1"]  # nur die belegte Notiz bleibt
    assert facts[0]["date"] == "12 May 2026"


def test_harvest_skips_a_source_without_usable_text(monkeypatch):
    monkeypatch.setattr(cr.llamacpp_client, "chat_structured",
                        lambda **kw: pytest.fail("must not ask"))
    sources = [{"id": "P1", "kind": "paper", "rank": 1, "snippet": "short"}]
    assert cr.harvest_facts(sources, "q") == []


def test_harvest_survives_a_model_failure(monkeypatch):
    def boom(**kw):
        raise RuntimeError("model down")
    monkeypatch.setattr(cr.llamacpp_client, "chat_structured", boom)
    sources = [{"id": "W1", "kind": "web", "rank": 0, "text": PAGE}]
    assert cr.harvest_facts(sources, "q") == []


def test_the_ledger_block_carries_date_statement_and_id():
    block = cr.fact_ledger_block([
        {"id": "W1", "date": "12 May 2026", "statement": "CHMP adopted."},
        {"id": "P4", "date": "2025", "statement": "Trial read out."},
    ])
    assert block.splitlines() == [
        "- 12 May 2026 | CHMP adopted. [[W1]]",
        "- 2025 | Trial read out. [[P4]]",
    ]


# --------------------------------------------------------------------------
# 4. Ende zu Ende: derselbe Lauf, einmal ohne und einmal mit DR-Modus
# --------------------------------------------------------------------------

def _decision_module():
    """Die Bausteine des Entscheidungstests wiederverwenden statt kopieren."""
    import importlib.util
    path = Path(__file__).with_name("test_dossier_decision.py")
    spec = importlib.util.spec_from_file_location("_dossier_decision", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dr_structured(monkeypatch):
    """Wie der Stub des Entscheidungstests, aber mit dem Notiz-Schema."""
    from pipeline import llamacpp_client

    asked: list[str] = []

    def chat_structured(model, schema, prompt, system=None, **kw):
        name = schema.__name__
        asked.append(name)
        if name == "Plan":
            return schema(title="P", steps=[{"title": "S", "query": "q"}])
        if name in ("AgentAction", "WebAction"):
            extra = {"target_gap": -1} if name == "WebAction" else {}
            return schema(action="finish", title="done", argument="",
                          state={"summary": "s", "gaps": [], "unsupported": []},
                          **extra)
        if name == "Audit":
            return schema(thesis="t", supported=[], inferences=[],
                          contradictions=[], missing=["legal status"],
                          outline=["o"])
        if name == "LedgerFacts":
            return schema(facts=[cr.LedgerFact(
                date="March 2031",
                statement="The SPC runs to March 2031 in the Netherlands.")])
        raise AssertionError(name)

    monkeypatch.setattr(llamacpp_client, "chat_structured", chat_structured)
    return asked


class _RecordingChat:
    def __init__(self, report_text):
        self.calls: list[dict] = []
        self._report = report_text

    def __call__(self, model, prompt, system=None, **kw):
        self.calls.append({"prompt": prompt, "system": system or "", **kw})
        return self._report


def _dr_run(monkeypatch, dr):
    from pipeline import llamacpp_client
    dec = _decision_module()
    _dr_structured(monkeypatch)
    chat = _RecordingChat(dec._report(filler=300, dense=True))
    monkeypatch.setattr(llamacpp_client, "chat", chat)
    monkeypatch.setattr(cr, "search_corpus", lambda q, n, scope="both": [
        dict(dec.ARTICLE, id=f"T{i}", url=f"https://catandary.de/trends/a-{i}",
             origin=o)
        for i, o in enumerate(("https://www.ema.europa.eu/en/x",
                               "https://www.fda.gov/news/y",
                               "https://clinicaltrials.gov/study/z"), start=1)])
    monkeypatch.setattr(cr, "search_research", lambda *a, **k: [])
    monkeypatch.setattr(cr, "search_patents", lambda *a, **k: [])
    monkeypatch.setattr(cr, "brave_search", lambda q, n=6: [
        {"id": "W0", "trend_id": None, "kind": "web", "title": "Ruling",
         "url": f"https://www.ema.europa.eu/{abs(hash(q)) % 97}", "origin": "",
         "outlet": "EMA", "vertical": "", "date": "2026-08-05",
         "snippet": "SPC", "fetched": False}])
    monkeypatch.setattr(
        cr, "fetch_web_page_status",
        lambda url: ("The SPC runs to March 2031 in the Netherlands. " * 6,
                     "fetched"))
    out = cr.run("What should we do?", max_steps=1, max_sources=8,
                 retrieval="fts", per_query=2, web_steps=1, max_web_sources=2,
                 topic="GLP-1 and incretin technology", measure=True,
                 seed_sources=[dict(dec.SEED)], seed_notes=["seed"], dr=dr)
    return out, chat


def test_the_old_path_has_neither_ledger_nor_card_sampling(monkeypatch):
    out, chat = _dr_run(monkeypatch, dr=False)
    assert out["dr"] is False
    assert out["fact_ledger"] == [] and out["dr_read"] == {}
    assert "FACT LEDGER" not in chat.calls[0]["prompt"]
    assert chat.calls[0]["temperature"] == 0.4
    assert "top_p" not in chat.calls[0]


def test_the_dr_path_writes_from_its_notes_with_card_sampling(monkeypatch):
    out, chat = _dr_run(monkeypatch, dr=True)
    assert out["dr"] is True
    assert out["fact_ledger"], "das Faktenbuch darf nicht leer sein"
    # Die Lesestufe lief (hier bleibt nichts ungelesen uebrig, weil der Stub
    # jede Seite ausliefert — das Lesen selbst prueft die Stufe oben).
    assert set(out["dr_read"]) >= {"read", "candidates", "failed"}
    first = chat.calls[0]
    assert "FACT LEDGER" in first["prompt"]
    assert "March 2031" in first["prompt"]
    assert "HOW YOU WORK" in first["system"]
    assert first["temperature"] == 0.7 and first["top_p"] == 0.80
    assert first["top_k"] == 20 and first["presence_penalty"] == 0.5


# --------------------------------------------------------------------------
# 5. R10 — die beiden Codefehler, die jury_16 am DR-Dokument gefunden hat
# --------------------------------------------------------------------------
# „Vier Sachfehler, drei davon ganz ohne Quelle" und „eine Decision summary,
# die aus einem einzigen Satz besteht und nichts zusammenfasst, dieser Satz
# wortgleich zehn Zeilen spaeter wiederholt". Beides lief bis dahin durch jedes
# Gate: `sourceless_figures` greift nur an Praezisionszahlen, und die Laenge
# der Kurzfassung wurde nur nach OBEN geprueft.

from pipeline import dossier_structure as ds   # noqa: E402

_SRC = [{"id": "T1", "kind": "web", "rank": 0, "title": "EMA",
         "url": "https://www.ema.europa.eu/en/x",
         "origin": "https://www.ema.europa.eu/en/x", "outlet": "EMA",
         "date": "2026-05-12", "fetched": True}]


def _doc(regip: str, decision: str = "", options: str = "") -> str:
    return (f"## Decision summary\n\n{decision or 'A dated, primary claim from 12 May 2026 [[T1]].'}\n\n"
            "## What is moving\n\nSomething moved.\n\n"
            f"## Regulatory and IP status\n\n{regip}\n\n"
            "## What happens next\n\n| Date | Event | Source | Why it matters |\n"
            "|---|---|---|---|\n\n"
            "## What the evidence does not support\n\nNothing.\n\n"
            f"## Options for a mid-sized European company\n\n{options}\n\n"
            "## Open questions and limits\n\nOpen.\n")


def test_a_dated_claim_without_any_source_is_a_finding():
    md = _doc("In the US, FDA approved oral semaglutide in February 2026.")
    kinds = [e["kind"] for e in ds.weak_source_claims(md, _SRC, "en", "")]
    assert kinds.count("uncited") == 1


def test_the_same_claim_with_a_citation_is_fine():
    md = _doc("In the US, FDA approved oral semaglutide in February 2026 [[T1]].")
    assert [e for e in ds.weak_source_claims(md, _SRC, "en", "")
            if e["kind"] == "uncited"] == []


def test_an_undated_sentence_is_not_touched():
    md = _doc("The compounding rules remain contested.")
    assert [e for e in ds.weak_source_claims(md, _SRC, "en", "")
            if e["kind"] == "uncited"] == []


def test_our_own_measured_figures_need_no_citation():
    """R9-2: die eigene Messung ist ueber den Messanhang belegt."""
    md = _doc("The measured improvement rate is 3.3%/yr over 2005-2026.")
    measured = "median improvement rate 3.3%/yr (2005-2026, n=1,878)"
    assert [e for e in ds.weak_source_claims(md, _SRC, "en", measured)
            if e["kind"] == "uncited"] == []


def test_an_option_argument_may_reason_about_a_year_without_a_citation():
    """Der Optionsabschnitt ist Argumentation, kein Bericht ueber die Welt."""
    md = _doc("Everything is cited [[T1]] as of 12 May 2026.",
              options="### Option 1 — Wait\n\n"
                      "- **Risk:** The 2031 cliff is four years away.\n")
    assert [e for e in ds.weak_source_claims(md, _SRC, "en", "")
            if e["kind"] == "uncited"] == []


def test_a_plan_field_is_not_a_factual_claim():
    md = _doc("Everything is cited [[T1]] as of 12 May 2026.",
              options="### Option 1 — Launch\n\n"
                      "- **Time horizon:** Product development by Q4 2026.\n"
                      "- **Effort:** EUR 2-5 million through 2027.\n")
    assert [e for e in ds.weak_source_claims(md, _SRC, "en", "")
            if e["kind"] == "uncited"] == []


def test_the_revision_order_names_the_uncited_claim():
    order = ds.revision_prompt([], [{"sentence": "FDA approved it in February 2026.",
                                     "tokens": ["FDA approved it"],
                                     "kind": "uncited", "detail": "",
                                     "url": "", "section": "regip"}], "en")
    assert "OHNE jeden Beleg" in order and "February 2026" in order


def test_a_summary_of_one_sentence_is_a_finding():
    md = _doc("All good [[T1]] on 12 May 2026.",
              decision="Only one statement stands here [[T1]], 12 May 2026.")
    assert any(f.startswith("Kurzfassung traegt nur 1")
               for f in ds.structure_findings(md, "en"))


def test_an_empty_summary_is_the_sharpest_case():
    md = _doc("All good [[T1]] on 12 May 2026.", decision=" ")
    assert any(f.startswith("Kurzfassung traegt nur 0")
               for f in ds.structure_findings(md, "en"))


def test_a_summary_repeated_verbatim_in_the_body_is_a_finding():
    line = ("In Great Britain, a nationally representative survey conducted "
            "January to March 2025 found that 2.9% of adults had used a GLP-1 "
            "medication [[T1]].")
    md = _doc(line + " It also says more.", decision=line + "\n\nSecond claim [[T1]] from 12 May 2026.")
    assert any(f.startswith("Kurzfassung wiederholt sich")
               for f in ds.structure_findings(md, "en"))


def test_a_three_statement_summary_stays_clean():
    md = _doc("All good [[T1]] on 12 May 2026.",
              decision="1. First finding [[T1]], 12 May 2026.\n"
                       "2. Second finding [[T1]], 13 May 2026.\n"
                       "3. Third finding [[T1]], 14 May 2026.\n")
    assert [f for f in ds.structure_findings(md, "en")
            if f.startswith("Kurzfassung")] == []


def test_the_check_names_the_uncited_deletion_separately():
    """Der Pruefnachweis darf eine gestrichene unbelegte Aussage nicht als
    'die Seite enthielt die Zahl nicht' ausgeben — das war der B9-v1-Fehler
    in neuer Gestalt."""
    from pipeline import dossier_check
    res = {"report": "## Decision summary\n\nA [[T1]].\n",
           "sources": [], "cited": [], "evidence": [], "ledger": [],
           "audit": {"missing": []}, "stripped_citations": 0,
           "structure": {"dropped_sentences": 2, "uncited_after": 2,
                         "weaksource_after": 0, "weakclaim_after": 0,
                         "off_topic_after": 0, "sourceless_after": 0,
                         "distorted_after": 0, "misattributed_after": 0,
                         "measure_after": 0}}
    text = " ".join(dossier_check.check_result(res)["findings"])
    assert "2× stand eine datierte Aussage ohne jeden Beleg" in text
    # und eben NICHT die alte Sammelbegruendung
    assert "enthielt die zitierte Web-Seite" not in text


# --------------------------------------------------------------------------
# 6. R10-3 — die Streichung darf die Tabelle nicht zerreissen
# --------------------------------------------------------------------------

_TBL = ("## What happens next\n\n"
        "| Date | Event | Source | Why it matters |\n"
        "|---|---|---|---|\n"
        "| Q1 2027 | A | [[T1]] | x |\n"
        "| Q2 2027 | B | [[T1]] | y |\n"
        "| Q3 2027 | C | [[T1]] | z |\n")


def test_a_deleted_row_does_not_split_the_table():
    doc, n = ds.drop_unverified(
        _TBL, [{"sentence": "| Q2 2027 | B | [[T1]] | y |",
                "tokens": ["B"], "kind": "figure", "url": "", "section": "next"}])
    assert n == 1
    rows = [l for l in doc.splitlines() if l.startswith("|")]
    body = doc.split("|---|---|---|---|\n", 1)[1]
    assert "\n\n" not in body.strip(), "Leerzeile mitten in der Tabelle"
    assert len(rows) == 4          # Kopf, Trenner, zwei Datenzeilen


def test_two_real_tables_stay_two_tables():
    doc = (_TBL + "\n"
           "| Year | Note |\n|---|---|\n| 2027 | second table |\n")
    assert ds._mend_tables(doc) == doc


def test_the_stored_dr_document_is_repaired():
    """Gegenprobe am echten Dokument: jury_16 sah dort genau diesen Bruch."""
    from pathlib import Path as _P
    src = _P("scratchpad/glp1/DR_final.md")
    if not src.exists():                     # Scratchpad optional
        pytest.skip("DR-Dokument nicht im Baum")
    seg = ds._mend_tables(src.read_text()).split("## What happens next")[1]
    seg = seg.split("## What the evidence")[0].strip()
    assert not any(not l.strip() for l in seg.splitlines())


# --------------------------------------------------------------------------
# 7. R10-4 — die Foerderebene bekommt eine eigene Suchrichtung
# --------------------------------------------------------------------------
# jury_16 zur Abdeckung (5 gegen 9): „Foerderung praktisch abwesend — R raeumt
# selbst ein: ,3/4 chain levels'; die eigene Korpustabelle weist 96
# Funding-Signale aus, die nicht verwendet werden." Es gab Suchrichtungen fuer
# Recht und Markt, aber keine fuer Foerderung.

def _hits(n=3):
    seen: dict[str, int] = {}

    def gen(q, count=6):
        k = seen.setdefault(q, len(seen))
        return [{"id": f"W{i}", "trend_id": None, "kind": "web",
                 "title": f"Grant hit {i}", "url": f"https://f{k}.example/{i}",
                 "origin": "", "outlet": "o", "vertical": "",
                 "date": "2026-01-01",
                 "snippet": "incretin GLP-1 funding grant", "fetched": False}
                for i in range(n)]
    return gen


def test_every_funding_pattern_runs_with_its_own_budget(monkeypatch):
    asked: list[str] = []
    gen = _hits()
    monkeypatch.setattr(cr, "brave_search",
                        lambda q, n=6: (asked.append(q), gen(q))[1])
    monkeypatch.setattr(cr, "fetch_web_page_status",
                        lambda u: ("page text", "fetched"))
    sources, notes, ledger = [], [], []
    added, record = cr.sweep_funding("GLP-1 and incretin technology",
                                     sources, set(), notes, ledger)
    assert len(asked) == len(cr.FUNDING_PATTERNS)
    assert added == len(cr.FUNDING_PATTERNS) * cr.FUND_PER_PATTERN
    assert all(s["kind"] == "funding" for s in sources)
    assert all(s["id"].startswith("F") for s in sources)
    assert all(e["kind"] == "funding" for e in ledger)
    assert "FUNDING SWEEP RECORD" in record


def test_public_programmes_are_asked_before_private_rounds():
    """Ein Mittelstaendler kann ein Foerderprogramm beantragen, eine fremde
    Series B nicht — also stehen die oeffentlichen Muster vorn (die
    Volltext-Budgets werden der Reihe nach vergeben)."""
    pats = list(cr.FUNDING_PATTERNS)
    first_private = next(i for i, p in enumerate(pats)
                         if "series" in p or "venture" in p)
    assert any("Horizon Europe" in p for p in pats[:first_private])
    assert any("EIC" in p for p in pats[:first_private])
    assert any("national research funding" in p for p in pats[:first_private])


def test_an_unread_funding_hit_cannot_carry_a_citation(monkeypatch):
    """Wie bei Recht und Markt: nur im Volltext gelesene Seiten sind zitierbar."""
    monkeypatch.setattr(cr, "brave_search", _hits(1))
    monkeypatch.setattr(cr, "fetch_web_page_status", lambda u: ("", "robots"))
    sources, notes, ledger = [], [], []
    cr.sweep_funding("GLP-1", sources, set(), notes, ledger)
    assert sources and not any(s.get("fetched") for s in sources)
    # dieselbe Regel wie in run(): ungelesene Web-Arten sind nicht zitierfaehig
    citable = [s for s in sources
               if s["kind"] not in ("web", "legal", "market", "entity",
                                    "funding") or s.get("fetched")]
    assert citable == []


# --------------------------------------------------------------------------
# 8. R11 — Denken nach Modellkarte, Ertrag statt Rang bei den Notizen
# --------------------------------------------------------------------------

def test_the_thinking_preset_follows_the_model_card(monkeypatch):
    monkeypatch.setenv("DOSSIER_DR_THINK", "1")
    s = cr.dr_sampling("write", True)
    assert s == {"temperature": 1.0, "top_p": 0.95, "top_k": 20,
                 "presence_penalty": 0.0}


def test_without_the_switch_the_non_thinking_preset_stands(monkeypatch):
    monkeypatch.delenv("DOSSIER_DR_THINK", raising=False)
    assert cr.dr_sampling("write", True)["temperature"] == 0.7


def test_schema_calls_never_switch_to_the_thinking_preset(monkeypatch):
    """Der Client setzt enable_thinking=False — dann gilt auch der
    nicht-denkende Sampling-Satz."""
    monkeypatch.setenv("DOSSIER_DR_THINK", "1")
    assert cr.dr_sampling("work", True) == {"temperature": 0.2,
                                            "top_p": 0.80, "top_k": 20}


def test_read_pages_are_harvested_before_patents(monkeypatch):
    asked: list[str] = []

    def fake(**kw):
        asked.append(kw["prompt"])
        return cr.LedgerFacts(facts=[])

    monkeypatch.setattr(cr.llamacpp_client, "chat_structured",
                        lambda **kw: fake(**kw))
    long = "x " * 400
    sources = [{"id": "N1", "kind": "patent", "rank": 0, "snippet": long,
                "title": "patent"},
               {"id": "P1", "kind": "paper", "rank": 1, "snippet": long,
                "title": "paper"},
               {"id": "L1", "kind": "legal", "rank": 0, "text": long,
                "title": "authority"}]
    cr.harvest_facts(sources, "q", max_sources=3)
    order = [p.split("Source: ")[1].split(" (")[0] for p in asked]
    assert order == ["authority", "paper", "patent"]


def test_the_note_prompt_asks_for_the_dated_future_first():
    assert "TAKE THE DATED FUTURE FIRST" in cr.HARVEST_SYSTEM


def test_a_thinking_run_raises_the_client_timeout(monkeypatch):
    """Der erste Denk-Lauf starb nach 600 s mitten im Bericht — httpx brach
    die Leitung ab, und der ganze Lauf war verloren."""
    from pipeline import llamacpp_client
    monkeypatch.setenv("DOSSIER_DR_THINK", "1")
    monkeypatch.setattr(llamacpp_client, "TIMEOUT", 600.0)
    out, _chat = _dr_run(monkeypatch, dr=True)
    assert llamacpp_client.TIMEOUT >= 2400
    assert out["dr"] is True


def test_the_old_path_leaves_the_timeout_alone(monkeypatch):
    from pipeline import llamacpp_client
    monkeypatch.delenv("DOSSIER_DR_THINK", raising=False)
    monkeypatch.setattr(llamacpp_client, "TIMEOUT", 600.0)
    _dr_run(monkeypatch, dr=False)
    assert llamacpp_client.TIMEOUT == 600.0


# --------------------------------------------------------------------------
# 9. R11-1 — abgeschnittene Denkspur ist kein Berichtstext
# --------------------------------------------------------------------------

def test_deliberation_before_the_first_heading_is_cut():
    doc = ("I genuinely cannot find a 5th. I'll go with 4 and note it.\n\n"
           "Let me plan the word count.\n\n"
           "## Decision summary\n\nA [[T1]] on 12 May 2026.\n")
    out, n = ds.strip_preamble(doc)
    assert n == 2 and out.startswith("## Decision summary")


def test_a_title_line_survives():
    doc = "# GLP-1 dossier\n\nrambling\n\n## Decision summary\n\nA.\n"
    out, n = ds.strip_preamble(doc)
    assert out.startswith("# GLP-1 dossier") and "rambling" not in out and n == 1


def test_a_clean_report_is_untouched():
    doc = "## Decision summary\n\nA.\n\n## What is moving\n\nB.\n"
    assert ds.strip_preamble(doc) == (doc, 0)


def test_a_report_without_any_mandatory_heading_is_left_alone():
    doc = "Some text without headings.\n"
    assert ds.strip_preamble(doc) == (doc, 0)


# --------------------------------------------------------------------------
# 10. R12 — die zwei Befunde aus jury_17, die Regeln sind
# --------------------------------------------------------------------------

_TWO = [{"id": "A1", "kind": "web", "rank": 2, "title": "Outlet A",
         "url": "https://a.example/1", "origin": "https://a.example/1",
         "outlet": "A", "date": "2026-08-05", "fetched": True},
        {"id": "B1", "kind": "web", "rank": 2, "title": "Outlet B",
         "url": "https://b.example/1", "origin": "https://b.example/1",
         "outlet": "B", "date": "2026-08-06", "fetched": True}]


def test_two_independent_secondary_sources_carry_a_summary_claim():
    """jury_17: die Regel drueckte die wahre, tragende Europa-These aus dem
    Text. Zwei unabhaengige Sekundaerquellen tragen sie jetzt — mit Marke."""
    doc = _doc("All fine [[A1]] on 12 May 2026.",
               decision="EU generics cannot enter before March 2031 "
                        "[[A1]], [[B1]].\n\nSecond claim [[A1]] 12 May 2026.")
    found = [e for e in ds.weak_source_claims(doc, _TWO, "en", "")
             if e["kind"] == "weakclaim" and e["section"] == "decision"]
    assert found and found[0]["corroborated"] is True
    out, n = ds.drop_unverified(doc, found)
    assert "March 2031" in out, "die Aussage darf nicht verschwinden"
    assert "(secondary source only)" in out


def test_one_weak_source_still_does_not_carry_the_summary():
    doc = _doc("All fine [[A1]] on 12 May 2026.",
               decision="EU generics cannot enter before March 2031 [[A1]].\n\n"
                        "Second claim [[A1]] 12 May 2026.")
    found = [e for e in ds.weak_source_claims(doc, _TWO, "en", "")
             if e["section"] == "decision"]
    assert found and found[0]["corroborated"] is False
    out, _n = ds.drop_unverified(doc, found)
    assert "March 2031" not in out


def _cal(rows: list[str]) -> str:
    head = ["| Date | Event | Source | Why it matters |", "|---|---|---|---|"]
    return _doc("x", options="") .replace(
        "## What happens next\n\n| Date | Event | Source | Why it matters |\n"
        "|---|---|---|---|\n",
        "## What happens next\n\n" + "\n".join(head + rows) + "\n")


def test_a_funding_programme_year_is_not_a_technology_date():
    """jury_17: 'drei themenfremde Horizon-Europe-Jahreszahlen', 'der Kalender
    enthaelt keinen einzigen GLP-1-Termin'."""
    rows = [f"| 203{i} | Horizon Europe programme phase {i} | [[A1]] | funding |"
            for i in range(5)]
    c = ds.calendar_rows(_cal(rows), "en", 2026, ("glp-1", "incretin"))
    assert c["ok"] == 0 and c["off_topic"] == 5
    txt = " ".join(ds.calendar_findings(_cal(rows), "en", 2026,
                                        ("glp-1", "incretin")))
    assert "nicht zum Thema" in txt


def test_a_topic_row_counts():
    rows = [f"| 203{i} | GLP-1 readout {i} | [[A1]] | matters |"
            for i in range(5)]
    c = ds.calendar_rows(_cal(rows), "en", 2026, ("glp-1", "incretin"))
    assert c["ok"] == 5 and c["off_topic"] == 0


def test_without_topic_terms_the_rule_is_off():
    rows = ["| 2030 | Anything at all | [[A1]] | matters |"]
    assert ds.calendar_rows(_cal(rows), "en", 2026)["ok"] == 1


# --------------------------------------------------------------------------
# Runde 13 (jury_17, 2026-09-07): die vier Befunde, die Regeln sind
# --------------------------------------------------------------------------
# jury_17 gab dem Dossier 5,7 gegen 6,9 und verteilte den Abstand auf drei
# Kriterien: Zeitliche Einordnung 3:7, Spezifitaet 5:8, Abdeckung 5:8. Der
# Lauf zeigt, warum: 16 von 61 Websuchen gingen an Scheinentitaeten
# ("Phase phase 3 trial results", "polypeptide court ruling generic"), und
# "polypeptide" nahm "tirzepatide" den Platz in der zweiten Welle.


class TestR13EntityHygiene:
    def test_class_words_are_not_substances(self):
        for w in ("polypeptide", "nonpeptide", "oligonucleotide", "agonist"):
            assert not cr._is_substance(w), w

    def test_real_inns_survive(self):
        for w in ("semaglutide", "tirzepatide", "retatrutide", "survodutide",
                  "petrelintide", "orforglipron"):
            assert cr._is_substance(w), w

    def test_the_full_company_name_wins_over_its_short_form(self):
        srcs = [{"title": "Novo Nordisk raises guidance", "snippet": "Novo Nordisk said"},
                {"title": "Novo Nordisk in court", "snippet": "Novo Nordisk lost"},
                {"title": "A ruling for Novo Nordisk", "snippet": "Novo Nordisk again"}]
        ents, _ = cr.harvest_entities(srcs, "obesity drugs")
        assert any(e.lower() == "novo nordisk" for e in ents)
        assert not any(e.lower() == "novo" for e in ents)

    def test_abstract_section_words_are_no_actors(self):
        srcs = [{"title": "METHODS Obesity trial", "snippet": "RESULTS Obesity Phase"},
                {"title": "METHODS Obesity study", "snippet": "RESULTS Obesity Phase"}]
        ents, _ = cr.harvest_entities(srcs, "obesity")
        low = {e.lower() for e in ents}
        assert not (low & {"methods", "results", "obesity", "phase"})

    def test_substances_are_harvested_from_the_read_page_text(self):
        """Die laufende Wirkstoffgeneration steht nicht in unseren Titeln."""
        page = ("Trial results for CagriSema and retatrutide were reported; "
                "survodutide followed. ") * 2
        srcs = [{"title": "Pipeline update", "snippet": "", "text": page},
                {"title": "Second page", "snippet": "", "text": page}]
        _, subs = cr.harvest_entities(srcs, "obesity drugs")
        assert "retatrutide" in subs and "survodutide" in subs


class TestR13CatalystSweep:
    def test_it_asks_per_topic_and_per_actor(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, count=6: seen.append(q) or [])
        added, record = cr.sweep_catalysts(
            "GLP-1 and incretin technology",
            ["semaglutide", "tirzepatide", "Novo Nordisk"],
            [], set(), [], [], 6)
        assert len(seen) == len(cr.CATALYST_PATTERNS) + 3 * len(
            cr.ENTITY_CATALYST_PATTERNS)
        assert any("catalysts calendar" in q for q in seen)
        assert any(q.startswith("tirzepatide") for q in seen)
        assert "CATALYST SWEEP RECORD" in record

    def test_the_actor_list_is_capped(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, count=6: seen.append(q) or [])
        cr.sweep_catalysts("topic", [f"e{i}" for i in range(20)],
                           [], set(), [], [], 6)
        assert len(seen) == len(cr.CATALYST_PATTERNS) + \
            cr.CAT_MAX_ENTITIES * len(cr.ENTITY_CATALYST_PATTERNS)


class TestR13CalendarCandidates:
    def test_a_future_date_is_normalised(self):
        assert cr._when_label("A decision is expected in Q4 2026.", 2026) == "Q4 2026"
        assert cr._when_label("The SPC expires on 19 March 2031.", 2026) == "19 March 2031"
        assert cr._when_label("Filing planned for H2 2027.", 2026) == "H2 2027"

    def test_a_past_date_is_not_a_calendar_entry(self):
        assert cr._when_label("The study ran from 2019 to 2021.", 2026) is None

    def test_the_earliest_future_date_wins(self):
        s = "Filed in 2019, the SPC expires in 2031 after review in 2027."
        assert cr._when_label(s, 2026) == "2027"

    def test_a_sentence_without_a_forward_marker_is_no_event(self):
        srcs = [{"id": "L1", "fetched": True,
                 "text": "GLP-1 sales reached a record in 2027 terms."}]
        assert cr.calendar_candidates([], srcs, ["glp-1"], [], 2026) == []

    def test_ledger_and_pages_both_feed_the_calendar(self):
        led = [{"date": "2026-12-01", "id": "M2",
                "statement": "FDA decision on CagriSema due December 2026"}]
        srcs = [{"id": "L4", "fetched": True,
                 "text": "A CHMP opinion on CagriSema is expected in Q1 2027."}]
        c = cr.calendar_candidates(led, srcs, ["glp-1"], ["cagrisema"], 2026)
        assert [x["id"] for x in c] == ["M2", "L4"]
        assert "[[M2]]" in cr.calendar_candidate_block(c)

    def test_off_topic_events_never_become_candidates(self):
        srcs = [{"id": "L9", "fetched": True,
                 "text": "The steel tariff review is expected in Q2 2027."}]
        assert cr.calendar_candidates([], srcs, ["glp-1"], ["semaglutide"],
                                      2026) == []

    def test_one_page_cannot_fill_the_whole_calendar(self):
        text = " ".join(f"A GLP-1 decision {i} is expected in Q1 202{i}."
                        for i in range(7, 10))
        text += " ".join(f"A GLP-1 readout {i} is expected in 203{i}."
                         for i in range(5))
        srcs = [{"id": "L1", "fetched": True, "text": text}]
        c = cr.calendar_candidates([], srcs, ["glp-1"], [], 2026)
        assert len(c) <= cr.CAL_MAX_PER_SOURCE

    def test_unread_pages_carry_nothing(self):
        srcs = [{"id": "L1", "fetched": False,
                 "text": "A GLP-1 decision is expected in Q1 2028."}]
        assert cr.calendar_candidates([], srcs, ["glp-1"], [], 2026) == []


class TestR13EffortAnchors:
    def test_a_grant_size_is_an_anchor(self):
        srcs = [{"id": "F3", "fetched": True,
                 "text": "The EIC Accelerator grant component is up to "
                         "EUR 2.5 million per company."}]
        a = cr.effort_anchors(srcs, ["glp-1"])
        assert a and a[0]["id"] == "F3"
        assert "[[F3]]" in cr.effort_anchor_block(a)

    def test_a_procedure_duration_is_an_anchor(self):
        srcs = [{"id": "L2", "fetched": True,
                 "text": "The EFSA health claim application procedure "
                         "typically takes 18 months from submission."}]
        assert cr.effort_anchors(srcs, ["glp-1"])

    def test_a_market_page_is_not_an_anchor(self):
        srcs = [{"id": "M7", "fetched": True,
                 "text": "The acquisition cost USD 10.2 billion in 2026."}]
        assert cr.effort_anchors(srcs, ["glp-1"]) == []


class TestR13ThinkingSwitch:
    def test_the_report_call_disables_thinking(self, monkeypatch):
        sent = {}

        class _R:
            @staticmethod
            def raise_for_status():
                return None

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": "x"}}]}

        class _C:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, json):
                sent.update(json)
                return _R()

        from pipeline import llamacpp_client as lc
        monkeypatch.setattr(lc.httpx, "Client", _C)
        lc.chat(model="m", prompt="p", enable_thinking=False)
        assert sent["chat_template_kwargs"] == {"enable_thinking": False}
        sent.clear()
        lc.chat(model="m", prompt="p")
        assert "chat_template_kwargs" not in sent


class TestR13Mending:
    def test_a_deleted_link_leaves_no_orphan_bracket(self):
        line = "**Trigger: ** Regulation, EC) 1924/2006, first opinions June 2012)"
        assert ds._mend_inline(line) == (
            "**Trigger:** Regulation, EC 1924/2006, first opinions June 2012")

    def test_a_correct_parenthesis_is_left_alone(self):
        line = "The claim (see the register) still stands."
        assert ds._mend_inline(line) == line

    def test_an_unsized_sentence_is_a_placeholder(self):
        for v in ("The effort cannot be sized from this evidence.",
                  "no primary source sizes this.",
                  "The evidence does not size it."):
            assert ds.is_placeholder(v), v

    def test_a_sized_effort_survives(self):
        assert not ds.is_placeholder("EUR 1-3m over 18 months [[F2]]")
        assert not ds.is_placeholder(
            "cannot be sized directly; a comparable EIC grant is EUR 2.5m [[F3]]")


class TestR13CalendarNoise:
    def test_a_year_inside_a_url_is_not_a_date(self):
        srcs = [{"id": "C1", "fetched": True,
                 "text": "The GLP-1 report is available at "
                         "example.com/state-of-glp1-regulation-2027 and is "
                         "planned to anchor the hub."}]
        assert cr.calendar_candidates([], srcs, ["glp-1"], [], 2026) == []

    def test_the_year_may_stand_before_the_half(self):
        srcs = [{"id": "C2", "fetched": True,
                 "text": "2026 H2 - Novo Nordisk CagriSema FDA decision is "
                         "expected for weight management."}]
        c = cr.calendar_candidates([], srcs, ["glp-1", "cagrisema"], [], 2026)
        assert c and c[0]["when"] == "H2 2026"
        assert not c[0]["statement"].startswith("-")


class TestR13DisavowedFigure:
    def test_a_figure_the_field_itself_rejects_is_no_figure(self):
        v = ("a GLP-1 pharma start-up raised $400 million in 2024, which is "
             "not transferable to a food-company P&L. The effort cannot be "
             "sized from this evidence.")
        assert ds.is_placeholder(v)

    def test_a_magnitude_after_the_disavowal_counts(self):
        v = ("a pharma round is not transferable; a comparable EIC grant is "
             "EUR 2.5m [[F3]]")
        assert not ds.is_placeholder(v)


def test_prefer_longest_survives_a_chain_of_names():
    """Regression: der Sammler strich einen Schluessel und griff ihn danach
    noch einmal ab (Lauf glp1-dr3, 2026-09-07: KeyError 't2dm applicant')."""
    df = {"a": {1, 2}, "a b": {1, 2}, "a b c": {1, 2}, "b c": {1, 2},
          "x y": {3}, "x": {3}}
    cr._prefer_longest(df)          # darf nicht werfen
    assert "a b c" in df and "a" not in df


class TestR13PastDatesInTheCurrentYear:
    """jury_18 (2026-09-07): „31.08.2026 — am Pruefdatum bereits vergangen,
    steht dennoch unter ,What happens next'"."""

    def test_a_passed_day_of_this_year_is_no_future(self):
        import datetime
        t = datetime.date(2026, 9, 7)
        assert cr._when_label("price rises on August 31, 2026", 2026, t) is None
        assert cr._when_label("filing 2026-09-01 planned", 2026, t) is None
        assert cr._when_label("readout 12 September 2026", 2026, t) == "12 September 2026"

    def test_a_finished_quarter_or_half_is_no_future(self):
        import datetime
        t = datetime.date(2026, 10, 2)
        assert cr._when_label("decision Q3 2026", 2026, t) is None
        assert cr._when_label("decision H1 2026", 2026, t) is None
        assert cr._when_label("decision Q4 2026", 2026, t) == "Q4 2026"

    def test_without_today_only_the_year_counts(self):
        assert cr._when_label("price rises on August 31, 2026", 2026) == "August 31, 2026"

    def test_one_source_carries_at_most_two_rows(self):
        assert cr.CAL_MAX_PER_SOURCE == 2


# --------------------------------------------------------------------------
# Runde 14 (jury_18, 2026-09-07): Streichung auf Absatzebene
# --------------------------------------------------------------------------


class TestR14SentenceSplit:
    def test_vs_is_not_a_sentence_end(self):
        t = "Fiber intake is 14.5 g/day vs. DRI 25-38 g/day. Calcium is low."
        assert ds.split_sentences(t) == [
            "Fiber intake is 14.5 g/day vs. DRI 25-38 g/day.", "Calcium is low."]

    def test_common_abbreviations_survive(self):
        t = "See Fig. 3 and Dr. Smith et al. for approx. 12 cases. Next one."
        assert len(ds.split_sentences(t)) == 2

    def test_split_claims_honours_the_same_rule(self):
        t = "A is 3 vs. B is 4. C follows."
        assert ds.split_claims(t) == ["A is 3 vs. B is 4.", "C follows."]

    def test_a_real_sentence_end_still_splits(self):
        assert len(ds.split_sentences("One ends here. Two ends here.")) == 2


class TestR14ParagraphMending:
    def test_an_orphaned_back_reference_falls_with_its_antecedent(self):
        orig = ("Sales rose 40% in 2025 [[M1]]. The two readings coexist. "
                "A closing sentence with enough words to stand on its own.")
        after = ("The two readings coexist. A closing sentence with enough "
                 "words to stand on its own.")
        out, n = ds._mend_paragraphs(after, orig)
        assert "two readings" not in out and "closing sentence" in out and n == 1

    def test_a_back_reference_that_opened_its_paragraph_stays(self):
        orig = "These are the facts. More follows here in detail."
        out, n = ds._mend_paragraphs(orig, orig)
        assert out == orig and n == 0

    def test_a_bare_label_is_removed(self):
        out, n = ds._mend_paragraphs("**Named actors and figures:**\n\nText stays here.",
                                     "**Named actors and figures:** x.\n\nText stays here.")
        assert out == "Text stays here." and n == 1

    def test_a_paragraph_reduced_to_a_stub_falls(self):
        orig = "First fact 1. Second fact 2. Third fact 3. Short tail."
        out, n = ds._mend_paragraphs("Short tail.", orig)
        assert out == "" and n == 1

    def test_drop_unverified_uses_it(self):
        doc = ("Sales rose 40% in 2025 [[M1]]. These are not directly "
               "comparable. A closing sentence with enough words to stand.")
        out, n = ds.drop_unverified(doc, [{"sentence": "Sales rose 40% in 2025 [[M1]].",
                                           "tokens": ["40%"]}])
        assert "not directly comparable" not in out and "closing sentence" in out


class TestR14FieldLineWithoutItsHead:
    def test_a_participle_tail_is_no_field(self):
        line = ("- Risk: positioning claims cost 2 million [[X]], spanning "
                "muscle preservation and gut health")
        assert ds._strip_clause(line, "2 million") is None

    def test_a_repairable_conjunction_tail_is_kept(self):
        line = "- Trigger: the take-off was 1990, and France reimburses from June 2026"
        out = ds._strip_clause(line, "1990")
        assert out and out.startswith("- Trigger: France")


class TestR14FragmentFindings:
    def test_bare_label_and_dangling_colon_are_findings(self):
        body = "**Named actors and figures:**\n\nKey figures:\n\n## H\n\nThese are orphans."
        f = ds.fragment_findings(body)
        assert any("label without content" in x for x in f)
        assert any("colon" in x for x in f)
        assert any("back-reference" in x for x in f)

    def test_clean_text_has_no_findings(self):
        body = "## Heading\n\nA proper sentence. Another proper one.\n\n- **Trigger:** x"
        assert ds.fragment_findings(body) == []


class TestR14ActorMap:
    def test_rows_come_from_the_ledger_first(self):
        led = [{"date": "2026-06-01", "statement": "Retatrutide cut weight 28.3% in TRIUMPH-1", "id": "M3"},
               {"date": "2025-01-01", "statement": "Retatrutide entered phase 3", "id": "M4"}]
        rows = cr.actor_map(led, [], ["retatrutide", "Novo Nordisk"], ["glp-1"])
        assert rows[0]["actor"] == "retatrutide" and rows[0]["id"] == "M3"
        assert len([r for r in rows if r["actor"] == "retatrutide"]) == 2

    def test_a_page_sentence_fills_in_when_the_ledger_is_silent(self):
        srcs = [{"id": "L7", "fetched": True,
                 "text": "Novo Nordisk booked GLP-1 sales of DKK 120 billion in 2025. Filler."}]
        rows = cr.actor_map([], srcs, ["Novo Nordisk"], ["glp-1"])
        assert rows and rows[0]["id"] == "L7" and "120 billion" in rows[0]["statement"]
        assert "[[L7]]" in cr.actor_map_block(rows)

    def test_an_actor_without_a_figure_gets_no_row(self):
        srcs = [{"id": "L8", "fetched": True,
                 "text": "Novo Nordisk is a company from Denmark active in GLP-1."}]
        assert cr.actor_map([], srcs, ["Novo Nordisk"], ["glp-1"]) == []


def _moving(rows):
    head = ["| Actor | What happened | Date | Source |", "|---|---|---|---|"]
    return ("## Decision summary\n\nx\n\n## What is moving\n\n"
            + "\n".join(head + rows) + "\n\n## Regulatory and IP status\n\ny\n")


class TestR14ActorRows:
    def test_complete_rows_are_counted_with_their_sources(self):
        rows = [f"| Actor {i} | GLP-1 result {i} 12% | 2026 | [[A{i}]] |" for i in range(5)]
        a = ds.actor_rows(_moving(rows), "en", ("glp-1",))
        assert a["ok"] == 5 and a["sources"] == 5
        assert ds.actor_findings(_moving(rows), "en", ("glp-1",)) == []

    def test_a_missing_table_is_a_finding(self):
        f = ds.actor_findings("## What is moving\n\nProse only.\n", "en")
        assert f and "no actor table" in f[0]

    def test_off_topic_and_figureless_rows_do_not_count(self):
        rows = ["| Steel Co | tariff 12% | 2026 | [[A1]] |",
                "| Novo | GLP-1 launch | — | [[A2]] |"]
        a = ds.actor_rows(_moving(rows), "en", ("glp-1",))
        assert a["ok"] == 0 and a["off_topic"] == 1 and a["no_figure"] == 1


def test_a_tail_without_its_head_is_a_finding():
    body = "**Named actors and figures:**\n\nin H2 2026 [[M4]].\n- **Lilly**: $16B."
    f = ds.fragment_findings(body)
    assert any("tail without its head" in x for x in f)


def test_us_abbreviation_does_not_split():
    t = "The pill launches outside the U.S. in H2 2026 [[M4]]. Next sentence."
    assert ds.split_sentences(t)[0].endswith("[[M4]].")


# --------------------------------------------------------------------------
# R14-3 Themenprofil / R14-4 Reparatur je Satz (Harness-Sichtung 2026-09-07)
# --------------------------------------------------------------------------


def _profile():
    return cr.TopicProfile(
        field="solid-state batteries",
        actor_types=["cell maker", "automaker"],
        regulators=["EU Battery Regulation", "UN 38.3 transport test"],
        event_types=["gigafactory commissioning", "pilot line start",
                     "A-sample delivery"],
        legal_questions=["battery passport requirements 2027"],
        market_questions=["automaker supply agreements volume"],
        perspectives=[cr.Perspective(role="automaker buyer",
                                     questions=["which cell makers ship A-samples",
                                                "cost per kWh target"])],
        actor_seeds=["QuantumScape", "Toyota"])


class TestR14TopicProfile:
    def test_without_a_profile_the_fixed_patterns_stay(self):
        pq = cr.profile_queries(None, "GLP-1 incretin", ["glp-1"])
        assert pq["regulatory"] == cr.REGULATORY_PATTERNS
        assert pq["catalyst"] == cr.CATALYST_PATTERNS and pq["perspective"] == ()

    def test_the_profile_shapes_every_direction(self):
        pq = cr.profile_queries(_profile(), "solid-state batteries", ["battery"])
        reg = [q.format(t="solid-state batteries") for q in pq["regulatory"]]
        assert any("EU Battery Regulation decision" in q for q in reg)
        assert any("patent expiry" in q for q in reg)          # Kern bleibt
        assert not any("EMA" in q or "EFSA" in q for q in reg)  # kein Pharma
        cat = [q.format(t="x") for q in pq["catalyst"]]
        assert any("gigafactory commissioning expected 2027" in q for q in cat)
        ent = [q.format(e="QuantumScape") for q in pq["entity_catalyst"]]
        assert any("QuantumScape gigafactory commissioning date" in q for q in ent)
        assert pq["perspective"][0].startswith("solid-state batteries which cell")

    def test_caps_hold(self):
        pq = cr.profile_queries(_profile(), "t", [])
        assert len(pq["regulatory"]) <= cr.PROFILE_MAX_REG
        assert len(pq["entity_legal"]) <= cr.PROFILE_MAX_ENT

    def test_a_question_that_already_names_the_topic_is_not_prefixed(self):
        assert cr._with_topic("battery passport rules", "battery", []) == "battery passport rules"
        assert cr._with_topic("passport rules", "battery", []) == "battery passport rules"

    def test_sweeps_accept_pattern_overrides(self, monkeypatch):
        seen = []
        monkeypatch.setattr(cr, "brave_search", lambda q, count=6: seen.append(q) or [])
        cr.sweep_regulatory("solid-state batteries", [], set(), [], [],
                            patterns=("{t} EU Battery Regulation decision",))
        cr.sweep_catalysts("solid-state batteries", ["QuantumScape"], [], set(), [], [], 6,
                           patterns=("{t} pilot line start expected 2027",),
                           entity_patterns=("{e} A-sample delivery date",))
        assert any("EU Battery Regulation" in q for q in seen)
        assert any(q == "QuantumScape A-sample delivery date" for q in seen)
        assert not any("PDUFA" in q or "CHMP" in q for q in seen)


class TestR14Repair:
    def _client(self, monkeypatch, answer):
        calls = []
        def fake_chat(model, prompt, system=None, **kw):
            calls.append(prompt)
            return answer
        monkeypatch.setattr(cr.llamacpp_client, "chat", fake_chat)
        return calls

    def test_a_repairable_sentence_is_rewritten_without_the_figure(self, monkeypatch):
        self._client(monkeypatch, "Sales rose sharply in 2025 [[M1]].")
        rep = "Intro. Sales rose 40% in 2025 [[M1]]. End."
        out, n = cr.repair_sentences(
            rep, [{"sentence": "Sales rose 40% in 2025 [[M1]].", "tokens": ["40%"],
                   "kind": "figure", "url": "https://x/1"}],
            [{"url": "https://x/1", "text": "Sales rose sharply in 2025."}])
        assert n == 1 and "40%" not in out and "[[M1]]" in out

    def test_drop_leaves_the_sentence_to_mechanical_deletion(self, monkeypatch):
        self._client(monkeypatch, "DROP")
        rep = "Sales rose 40% in 2025 [[M1]]."
        out, n = cr.repair_sentences(rep, [{"sentence": rep, "tokens": ["40%"],
                                            "kind": "figure", "url": ""}], [])
        assert n == 0 and out == rep

    def test_a_rewrite_that_keeps_the_figure_or_loses_the_marker_is_refused(self, monkeypatch):
        rep = "Sales rose 40% in 2025 [[M1]]."
        self._client(monkeypatch, "Sales rose 40% in 2025 [[M1]].")
        assert cr.repair_sentences(rep, [{"sentence": rep, "tokens": ["40%"],
                                          "kind": "figure", "url": ""}], [])[1] == 0
        self._client(monkeypatch, "Sales rose in 2025.")
        assert cr.repair_sentences(rep, [{"sentence": rep, "tokens": ["40%"],
                                          "kind": "figure", "url": ""}], [])[1] == 0

    def test_only_repairable_kinds_are_touched(self, monkeypatch):
        calls = self._client(monkeypatch, "x")
        rep = "A weak claim [[M1]]."
        cr.repair_sentences(rep, [{"sentence": rep, "tokens": ["A weak"],
                                   "kind": "weakclaim", "url": ""}], [])
        assert calls == []


def test_ledger_facts_carry_their_actor():
    f = cr.LedgerFact(date="2026", statement="Lilly booked $19.8B", actor="Eli Lilly")
    assert f.actor == "Eli Lilly"
    assert cr.LedgerFact(date="2026", statement="x").actor == ""


def test_actor_map_prefers_the_actor_field():
    led = [{"date": "2026-05-01", "statement": "Revenue $19.8B in Q1", "actor": "Eli Lilly", "id": "M1"}]
    rows = cr.actor_map(led, [], ["Eli Lilly"], ["glp-1"])
    assert rows and rows[0]["id"] == "M1"


def test_an_echo_of_the_board_question_is_no_search_direction():
    q = "Where does solid-state batteries stand today"
    question = ("Where does solid-state batteries stand today, and what should "
                "a mid-sized European company do about it?")
    assert cr._echoes_question(q, question)
    assert not cr._echoes_question("automaker supply agreements volume", question)
    prof = _profile()
    prof.market_questions = [q]
    pq = cr.profile_queries(prof, "solid-state batteries", [], question)
    assert not any("stand today" in x for x in pq["market"])


class TestR14ProfileHygiene:
    def test_generic_event_labels_are_dropped(self):
        prof = _profile()
        prof.event_types = ["investment", "research_publication", "gigafactory commissioning"]
        pq = cr.profile_queries(prof, "t", [])
        cat = " | ".join(pq["catalyst"])
        assert "gigafactory commissioning" in cat
        assert "investment expected" not in cat and "research publication" not in cat

    def test_underscores_become_words_and_dangling_words_fall(self):
        assert cr._short("research_publication of the") == "research publication"
        assert cr._short("How do shifts by entities like Plenty and") == \
            "How do shifts by entities like Plenty"

    def test_stem_based_topic_match(self):
        assert cr.mentions("a solid state battery pilot line", ["solid-state batteries"])
        assert cr.mentions("GLP-1 users", ["GLP-1"])
        assert not cr.mentions("steel tariffs", ["solid-state batteries"])

    def test_calendar_relevance_is_stem_based(self):
        srcs = [{"id": "C1", "fetched": True,
                 "text": "The solid state battery pilot line is expected to start in Q2 2027."}]
        c = cr.calendar_candidates([], srcs, ["solid-state batteries"], [], 2026)
        assert c and c[0]["when"] == "Q2 2027"


def test_none_regulators_never_become_queries():
    prof = _profile()
    prof.regulators = ["none", "n/a", "EU Battery Regulation"]
    pq = cr.profile_queries(prof, "t", [])
    reg = " | ".join(pq["regulatory"])
    assert "none decision" not in reg and "n/a" not in reg
    assert "EU Battery Regulation decision" in reg



class TestR14VerticalBackbone:
    def test_every_vertical_has_regulators_and_events(self):
        assert set(cr.VERTICALS) == {"HEALTH", "FOOD", "TECH", "ECO", "DESIGN",
                                     "FASHION", "BIZ", "LIFESTYLE"}
        for v, d in cr.VERTICAL_SETS.items():
            assert len(d["regulators"]) >= 4 and len(d["events"]) >= 4, v

    def test_the_backbone_shapes_the_queries_even_if_the_model_is_vague(self):
        prof = _profile()
        prof.regulators = ["none", "CES"]
        prof.event_types = ["investment", "ipo", "milestone"]
        pq = cr.profile_queries(prof, "solid-state batteries", [], vertical="ECO")
        reg = " | ".join(pq["regulatory"])
        assert "EU Battery Regulation 2023/1542 decision" in reg
        cat = " | ".join(pq["catalyst"])
        assert "gigafactory commissioning expected 2027" in cat
        assert "CES decision" in reg          # Profil ergaenzt, ersetzt nicht

    def test_a_health_topic_gets_the_pharma_backbone(self):
        pq = cr.profile_queries(_profile(), "GLP-1 incretin", [], vertical="HEALTH")
        assert any("EMA CHMP opinion" in q for q in pq["regulatory"])
        assert any("phase 3 readout" in q for q in pq["catalyst"])


def test_an_event_type_must_name_an_event():
    assert cr._generic_event("Technology Development")
    assert cr._generic_event("trade show")
    assert not cr._generic_event("Clinical Trial Results")
    assert not cr._generic_event("gigafactory commissioning")
    assert not cr._generic_event("EFSA opinion adoption")



class TestR14VerticalOfTopic:
    def test_the_neighbours_decide(self):
        nb = [{"vertical": "HEALTH"}] * 7 + [{"vertical": "BIZ"}] * 5
        assert cr.vertical_of_topic("GLP-1", nb) == "HEALTH"

    def test_keywords_decide_without_neighbours(self):
        assert cr.vertical_of_topic("solid-state batteries", []) == "ECO"
        assert cr.vertical_of_topic("vertical farming", []) == "FOOD"

    def test_a_known_vertical_brings_the_backbone_even_without_a_profile(self):
        pq = cr.profile_queries(None, "solid-state batteries", [], vertical="ECO")
        assert any("EU Battery Regulation" in q for q in pq["regulatory"])



class TestR14TwoVerticals:
    def test_keyword_vertical_joins_a_differing_corpus_vertical(self):
        nb = [{"vertical": "TECH"}] * 11 + [{"vertical": "ECO"}]
        assert cr.verticals_of_topic("solid-state batteries", nb) == ["TECH", "ECO"]
        assert cr.verticals_of_topic("GLP-1 and incretin technology",
                                     [{"vertical": "HEALTH"}] * 5) == ["HEALTH"]

    def test_both_backbones_are_merged(self):
        pq = cr.profile_queries(None, "solid-state batteries", [], vertical=["TECH", "ECO"])
        reg = " | ".join(pq["regulatory"])
        assert "CE marking" in reg and "EU Battery Regulation" in reg

    def test_refusals_are_filtered_everywhere(self):
        prof = _profile()
        prof.regulators = ["No company profile data provided", "EMA"]
        prof.actor_seeds = ["No company profile data provided", "Novo Nordisk"]
        prof.perspectives = [cr.Perspective(role="x", questions=["No company profile data provided"])]
        pq = cr.profile_queries(prof, "GLP-1", [], vertical="HEALTH")
        assert not any("provided" in q for q in pq["regulatory"] + pq["perspective"])
        assert prof.actor_seeds == ["Novo Nordisk"]

    def test_no_double_date(self):
        pq = cr.profile_queries(None, "t", [], vertical="HEALTH")
        assert not any(q.endswith("date date") for q in pq["entity_catalyst"])


def test_plural_event_nouns_count():
    for ev in ("Clinical trial phase completions", "Regulatory approvals and rejections",
               "Product launches and market entries", "Patent expirations and generic entry"):
        assert not cr._generic_event(ev), ev


def test_relative_dates_are_no_dates():
    assert cr._relative_date("Today") and cr._relative_date("Last month")
    assert not cr._relative_date("12 March 2026") and not cr._relative_date("Q1 2027")
    led = [{"date": "Today", "statement": "FDA approved a generic", "actor": "FDA", "id": "L1"}]
    rows = cr.actor_map(led, [], ["FDA"], ["glp-1"])
    assert rows and rows[0]["date"] == ""


def test_the_calendar_topic_check_reads_the_event_not_the_justification():
    row = ("| 2026 | EIC Accelerator Open programme (€414M) | [[F1]] | "
           "funds GLP-1 companion R&D |")
    c = ds.calendar_rows(_cal([row]), "en", 2026, ("glp-1", "incretin"))
    assert c["ok"] == 0 and c["off_topic"] == 1
    row2 = "| H2 2026 | CagriSema FDA decision | [[C1]] | matters |"
    c2 = ds.calendar_rows(_cal([row2]), "en", 2026, ("glp-1", "cagrisema"))
    assert c2["ok"] == 1


def test_a_paragraph_opening_with_a_preposition_is_a_normal_sentence():
    """LFP v3 (2026-09-12): 'In Europe and the United States, …' und 'On 30 July 2025,
    the Commission …' wurden als 'Schwanz ohne Kopf' gemeldet — es sind Satzanfaenge."""
    body = ("In Europe and the United States, LFP's share of EV sales remains below 10% [[W1]].\n\n"
            "On 30 July 2025, the European Commission published Regulation (EU) 2025/1561 [[W2]].")
    assert not [x for x in ds.fragment_findings(body) if "tail without its head" in x]


def test_a_conjunction_or_a_lowercase_preposition_still_is_a_tail():
    body = "and the rest followed in 2027 [[W1]].\n\nin H2 2026 [[M4]] the line opened."
    f = [x for x in ds.fragment_findings(body) if "tail without its head" in x]
    assert len(f) == 2


# --------------------------------------------------------------------------
# LFP v5 (2026-09-12): ungefetchte ids, Best-of-N-Bewertung, Einleitung vor Liste
# --------------------------------------------------------------------------

def test_uncitable_ids_are_marked_in_the_notes():
    note = "T900000006 | IEA report on LFP | https://x\n   snippet\nT900000060 | other | https://y"
    out = cr.mark_uncitable(note, {"T900000006"})
    assert out.startswith("T900000006 " + cr.UNCITABLE_MARK)
    assert "T900000060 " + cr.UNCITABLE_MARK not in out          # kein Praefix-Treffer
    assert cr.mark_uncitable(note, set()) == note


def test_draft_score_prefers_the_denser_cleaner_draft():
    src = [{"id": "W1", "kind": "web", "title": "10-Q", "rank": 0, "text": "revenue $4.1B in 2026",
            "url": "https://www.sec.gov/edgar/1", "origin": "", "outlet": "SEC", "date": "2026-08-01"}]
    dense = "## Decision summary\n\nOn 1 August 2026 the 10-Q reported revenue of $4.1B [[W1]].\n"
    thin = "## Decision summary\n\nRevenue grew strongly and the outlook is positive.\n"
    a = cr.draft_score(dense, src, "en", [], [], 2026, [])
    b = cr.draft_score(thin, src, "en", [], [], 2026, [])
    assert a["density"] > b["density"] and a["score"] > b["score"]


def test_an_intro_line_before_a_list_is_not_a_fragment():
    body = ("The following questions remain open:\n\n- **Capacity.** Not found.\n- **Price.** Not found.")
    assert not [x for x in ds.fragment_findings(body) if "colon" in x]
    alone = "The following questions remain open:\n\nSome prose that is not a list."
    assert [x for x in ds.fragment_findings(alone) if "colon" in x]


def test_harvest_reserves_seats_for_papers_and_funding(monkeypatch):
    """40 gelesene Webseiten duerfen die Paper nicht mehr verdraengen."""
    asked = []

    class _F:
        def __init__(self):
            self.facts = []

    monkeypatch.setattr(cr.llamacpp_client, "chat_structured",
                        lambda **kw: asked.append(kw["prompt"]) or _F())
    web = [{"id": f"W{i}", "kind": "web", "rank": 1, "title": f"page {i}", "url": f"https://a{i}.gov/x",
            "text": "x" * 5000} for i in range(40)]
    papers = [{"id": f"P{i}", "kind": "paper", "rank": 1, "title": f"paper {i}", "url": f"https://doi.org/{i}",
               "text": "abstract " * 60} for i in range(3)]
    funding = [{"id": "F0", "kind": "funding", "rank": 0, "title": "grant", "url": "https://ec.europa.eu/g",
                "text": "grant text " * 40}]
    cr.harvest_facts(web + papers + funding, "q", max_sources=10, dr=True)
    titles = " ".join(asked)
    assert all(f"paper {i}" in titles for i in range(3)) and "grant" in titles
    assert len(asked) == 10


# --------------------------------------------------------------------------
# Landschafts-Modus (2026-09-13)
# --------------------------------------------------------------------------

def test_landscape_question_asks_for_the_field_not_one_technology():
    q = cr.landscape_question("batteries")
    assert "Map the field of batteries" in q and "at least eight" in q and "skepticism" in q


def test_landscape_map_is_verified_and_thinned_by_corpus_counts(monkeypatch):
    items = [cr.LandscapeItem(name="sodium-ion cells", query="sodium-ion battery cell", why="Na instead of Li"),
             cr.LandscapeItem(name="unobtainium anodes", query="unobtainium", why="does not exist"),
             cr.LandscapeItem(name="Sodium-ion cells", query="dup", why="dup"),
             cr.LandscapeItem(name="solid-state electrolytes", query="solid-state electrolyte", why="no liquid")]
    monkeypatch.setattr(cr.llamacpp_client, "chat_structured", lambda **kw: cr.LandscapeMap(items=items))
    counts = {"sodium-ion cells": {"signals": 900, "patents": 40}, "unobtainium anodes": {"signals": 1, "patents": 0},
              "solid-state electrolytes": {"signals": 2500, "patents": 300}}
    monkeypatch.setattr(cr, "subfield_counts", lambda name, field="": counts.get(name, {"signals": 0, "patents": 0}))
    out = cr.build_landscape_map("batteries", ["Sodium-ion cells ship", "Solid-state pilot"])
    assert [r["name"] for r in out] == ["solid-state electrolytes", "sodium-ion cells"]
    note = cr.landscape_note(out, "batteries")
    assert "2500 signals" in note and "unobtainium" not in note
    app = cr.landscape_appendix(out, "batteries")
    assert "## Landscape map (auto-generated)" in app and "| sodium-ion cells | 900 | 40 |" in app


def test_subfield_terms_drop_field_and_generic_words():
    assert cr.subfield_terms("Sodium-ion battery cells", "batteries") == ["sodium-ion"]
    assert cr.subfield_terms("Second-life EV battery storage", "batteries") == ["second-life", "storage"]
    assert cr.subfield_terms("batteries", "batteries")                    # nichts uebrig → alle Woerter


def test_corpus_term_candidates_surface_recurring_compounds():
    titles = ["Advancements in Sodium-Ion Battery Technology", "Sodium-ion cells ship to Europe",
              "Solid-state battery negative electrode", "Solid-state batteries enter mass production",
              "Lithium metal battery anode study", "Lithium metal battery pilot", "Zinc battery startup raises"]
    c = dict(cr.corpus_term_candidates(titles, "batteries"))
    assert c["sodium-ion"] == 2 and c["solid-state"] == 2
    assert c["lithium metal"] == 2
    assert "battery" not in c


def test_fill_calendar_adds_dated_cited_on_topic_candidates_until_the_minimum():
    doc = ("## Decision summary\n\nx [[W1]].\n\n## What happens next\n\n"
           "| Date | Event | Source | Why it matters |\n|---|---|---|---|\n"
           "| 2027 | BYD solid-state pilot production | [[W1]] | matters |\n"
           "| Q2 2027 | Samsung SDI solid-state line | [[W2]] | matters |\n"
           "| 2027 | Geely pilot | [[W3]] | matters |\n\n## What the evidence does not support\n\n- y\n")
    cands = [{"when": "18 Feb 2027", "statement": "EU battery passport becomes mandatory", "id": "L4"},
             {"when": "2027", "statement": "BYD solid-state pilot production starts", "id": "W1"},   # schon drin
             {"when": "8 Oct 2026", "statement": "Horizon Europe battery call deadline", "id": "F2"},
             {"when": "2028", "statement": "Unrelated vanadium plant", "id": "M9"}]
    out, n = ds.fill_calendar(doc, cands, "en", 2026, ["battery", "solid-state"], min_rows=5)
    assert n == 2
    assert "| 18 Feb 2027 | EU battery passport becomes mandatory | [[L4]] | added from the dated-fact ledger (auto) |" in out
    assert "vanadium" not in out
    # 2 gueltige Zeilen + 2 ergaenzte = 4 (Geely-Zeile bleibt themenfremd); mehr
    # Kandidaten gibt es nicht — der Rest ist ehrlich ein Befund.
    assert ds.calendar_rows(out, "en", 2026, ["battery", "solid-state"])["ok"] == 4
    same, n0 = ds.fill_calendar(out, cands, "en", 2026, ["battery", "solid-state"], min_rows=5)
    assert n0 == 0 and same == out


# --------------------------------------------------------------------------
# Der Leser (2026-09-13)
# --------------------------------------------------------------------------

def test_reader_review_keeps_objections_but_drops_new_facts(monkeypatch):
    review = cr.ReaderReview(answers_question=False, overall="Reads like a funding brief.", findings=[
        cr.ReaderFinding(section="Decision summary", kind="summary", severity="major",
                         passage="The CEC awarded three grants", issue="Summarises grants, not the topic.",
                         suggestion="Lead with the topic's own dated milestones already in the body."),
        cr.ReaderFinding(section="What is moving", kind="missing", severity="major", passage="",
                         issue="No sub-field on zinc although the map lists it.",
                         suggestion="Add a paragraph on zinc from the gathered material."),
        cr.ReaderFinding(section="Options", kind="other", severity="minor", passage="x",
                         issue="Effort is vague.", suggestion="State the effort as roughly $45 million.")])
    monkeypatch.setattr(cr.llamacpp_client, "chat_structured", lambda **kw: review)
    out = cr.reader_review("## Decision summary\n\nThe CEC awarded three grants in 2025.\n", "q", "iron-air", None)
    assert out["answers_question"] is False
    assert [f["kind"] for f in out["findings"]] == ["summary", "missing"]      # $45 million = neuer Fakt → weg
    lines = cr.reader_lines(out)
    assert lines[0].startswith("READER: the dossier does not answer")
    assert any("ERGAENZEN" in l for l in lines) and any('passage: "The CEC awarded three grants"' in l for l in lines)
    assert cr.reader_lines(None) == []


def test_reader_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("DOSSIER_READER", "0")
    assert cr.reader_enabled() is False
    monkeypatch.delenv("DOSSIER_READER")
    assert cr.reader_enabled() is True


def test_field_anchor_forms_keep_the_narrow_field_word():
    assert cr.field_anchor_forms("quantum computing hardware") == ["quantum"]
    assert cr.field_anchor_forms("batteries") == ["batteries"]      # Postgres stemmt selbst
    assert cr.field_anchor_forms("energy storage")                      # nichts Enges → alle Formen


# --------------------------------------------------------------------------
# Abschnittsweises Schreiben + Landkarten-Pflicht (2026-09-14)
# --------------------------------------------------------------------------

def test_take_section_cuts_exactly_one_section():
    raw = ("Sure, here is the section.\n\n## What is moving\n\n| Actor | x |\n|---|---|\n| A | b |\n\n"
           "Prose [[T1]].\n\n## Regulatory and IP status\n\nleak\n")
    out = cr.take_section(raw, "What is moving")
    assert out.startswith("## What is moving\n") and "Prose [[T1]]." in out and "leak" not in out
    # Ueberschrift fehlt → Text wird unter die verlangte Ueberschrift gestellt
    out2 = cr.take_section("Some prose without heading [[T1]].", "Open questions and limits")
    assert out2.startswith("## Open questions and limits\n") and "[[T1]]" in out2


def test_write_sections_assembles_in_outline_order(monkeypatch):
    seen = []

    def chat(model, prompt, system=None, **kw):
        h = system.split('write ONLY the section "## ')[1].split('"')[0]
        seen.append(h)
        return f"## {h}\n\nBody of {h} [[T1]].\n"

    monkeypatch.setattr(cr.llamacpp_client, "chat", chat)
    out = cr.write_sections("SYS", "PROMPT", "en", {"temperature": 0.3})
    assert seen[0] == "What is moving" and seen[-1] == "Decision summary"
    heads = [l for l in out.splitlines() if l.startswith("## ")]
    assert heads[0] == "## What this is about" and heads[1] == "## Decision summary" and heads[2] == "## What is moving" and len(heads) == 8
    assert seen.index("What this is about") == len(seen) - 2


def test_landscape_findings_name_uncovered_subfields():
    body = "## What is moving\n\nSodium-ion cells ship [[T1]]. Solid-state pilots start [[T2]].\n"
    f = ds.landscape_findings(body, ["sodium-ion battery", "solid-state battery", "aqueous zinc battery"])
    assert len(f) == 1 and "1 of 3" in f[0] and "aqueous zinc battery" in f[0]
    assert ds.landscape_findings(body, []) == []
    assert not [x for x in ds.structure_findings(body, "en", landscape_items=["sodium-ion battery"]) if "Landscape" in x]


class TestCalendarFillGuards:
    """2026-09-18: was der Auffueller ohne Urteil eintraegt, muss primaer belegt
    und terminiert sein; Werbe-Anreisser sind keine Kandidaten."""

    BODY = ("## What happens next\n\n| Date | Event | Source | Why it matters |\n"
            "|---|---|---|---|\n"
            "| 11 October 2027 | vSphere 8 support ends [[S1]] | [[S1]] | hard date |\n\n"
            "## Open questions and limits\n\nx.\n")

    def _cands(self):
        return [
            {"id": "S2", "when": "2026", "statement": "Global data center investment is on track to approach $1 trillion in 2026."},
            {"id": "S3", "when": "2026", "statement": "It sets out how the EIC will allocate its funding for the year 2026."},
            {"id": "S4", "when": "Q2 2026", "statement": "Adoption of the EU data center rating scheme is scheduled for Q2 2026."},
            {"id": "S5", "when": "March 2027", "statement": "The data center rating regulation applies from March 2027."},
        ]

    def test_bare_year_and_rank2_are_not_filled(self):
        ranks = {"S2": 2, "S3": 0, "S4": 0, "S5": 2}
        out, n = ds.fill_calendar(self.BODY, self._cands(), "en", 2026,
                                  ("data center", "virtualization", "eic"), 3,
                                  rank_of=lambda cid: ranks[cid])
        assert n == 1
        assert "rating scheme" in out and "$1 trillion" not in out
        assert "EIC will allocate" not in out and "March 2027" not in out

    def test_without_rank_of_only_the_bare_year_rule_applies(self):
        out, n = ds.fill_calendar(self.BODY, self._cands(), "en", 2026,
                                  ("data center", "eic"), 5)
        assert n == 2 and "$1 trillion" not in out and "EIC will allocate" not in out

    def test_marketing_openers_are_no_candidates(self):
        led = [{"id": "F1", "date": "2026", "statement": "Discover the top data center events of 2026, where experts will unveil innovations."},
               {"id": "F2", "date": "Q4 2026", "statement": "The data center rating regulation is expected to be adopted in Q4 2026."}]
        c = cr.calendar_candidates(led, [], ["data center"], [], 2026)
        assert [x["id"] for x in c] == ["F2"]


class TestTableRowsAreOneClaim:
    """2026-09-18: eine Kalenderzeile zerfiel am Satzpunkt in Bruchstuecke; die
    Streichung nahm das Bruchstueck mit dem Datum und liess "|" stehen."""

    ROW = "| 12 September 2025 | The EU Data Act applies. | [Data Act](https://x.eu/a) | Defines the frame. |"
    BODY = ("## What happens next\n\n| Date | Event | Source | Why |\n|---|---|---|---|\n"
            + ROW + "\n| 2027 | Other. | [B](https://y.eu/b) | why |\n\n"
            "## Open questions and limits\n\nOne sentence. Another one.\n")

    def test_split_claims_keeps_rows_whole(self):
        claims = ds.split_claims(self.BODY)
        assert self.ROW in claims
        assert not any(c.strip() == "|" for c in claims)
        assert "One sentence." in claims and "Another one." in claims

    def test_drop_removes_the_whole_row(self):
        out, n = ds.drop_unverified(
            self.BODY, [{"sentence": self.ROW, "tokens": ["EU"], "kind": "subject",
                         "url": "https://x.eu/a", "section": "next"}], "en")
        assert n == 1
        assert "Data Act" not in out
        assert not any(ln.strip() == "|" for ln in out.splitlines())
        assert "| 2027 | Other." in out


class TestAboutSection:
    """Einstieg fuer Fachfremde (Owner 2026-09-18): Pflicht, Wortband, ohne Zahlen."""

    def test_missing_about_is_a_finding(self):
        md = _doc("Regip.")
        assert any("What this is about" in f for f in ds.structure_findings(md, "en"))

    def test_figures_and_short_text_are_findings(self):
        short = "## What this is about\n\nProxmox is a hypervisor. It matters.\n\n"
        f = ds.about_findings(ds.split_sections(short, "en")["about"], "en", ("proxmox",))
        assert any("Band" in x for x in f)
        with_fig = ("## What this is about\n\n" + " ".join(["Proxmox VE is a KVM-based hypervisor that hosts virtual machines on ordinary servers and replaces a licensed platform."] * 3)
                    + " It reached 1.5 million hosts in 2025.\n\n")
        f = ds.about_findings(ds.split_sections(with_fig, "en")["about"], "en", ("proxmox",))
        assert any("Zahlen/Daten" in x for x in f) and not any("Band" in x for x in f)

    def test_clean_about_passes_and_is_left_out_of_the_fact_quota(self):
        about = "## What this is about\n\n" + " ".join(["Proxmox VE is a KVM-based hypervisor that hosts virtual machines on ordinary servers and replaces a licensed platform; the question turns on licensing and compliance."] * 3) + "\n\n"
        assert ds.about_findings(ds.split_sections(about, "en")["about"], "en", ("proxmox",)) == []
        body = "## What is moving\n\nOn 12 May 2026 Proxmox shipped version 9 [[T1]].\n"
        d_with = ds.fact_density(about + body, _SRC, "en")
        d_without = ds.fact_density(body, _SRC, "en")
        assert d_with["words"] == d_without["words"] and d_with["per100"] == d_without["per100"]

