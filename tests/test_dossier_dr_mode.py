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
