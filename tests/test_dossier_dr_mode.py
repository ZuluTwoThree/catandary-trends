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
    s = cr.dr_sampling("write", True)
    assert s["temperature"] == 0.7 and s["top_p"] == 0.80
    assert s["top_k"] == 20 and s["presence_penalty"] == 1.5


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
    assert first["top_k"] == 20 and first["presence_penalty"] == 1.5


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
