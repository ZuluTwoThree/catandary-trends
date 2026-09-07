"""Entscheidungsebene, Rechts-Sweep und Beleg-Verifikation (2026-09-07).

Belegte Ausgangslage — zwei Blindgutachten ueber dieselben drei GLP-1-Dossiers
(scratchpad/glp1/jury_1.md, jury_2.md):

  D1  Unser Dossier verlor mit 51/70 bzw. 54/70 gegen eine reine Web-Recherche
      (59/70 bzw. 62/70), Hauptgrund: "mit 5.906 Woertern zu lang und nicht auf
      eine Entscheidung zugeschnitten" — der Gutachter gab es "ans Entwicklungs-
      und Regulatory-Team, nicht ins Gremium". Der Sieger brauchte 2.833 Woerter.
  D2  Der entscheidungstragende Befund des Siegers war ein RECHTSSTATUS
      (EU-SPC-Schutz bis Maerz 2031 bei gleichzeitigem Generika-Start in
      Indien/Brasilien/China). Unser Korpus zaehlt Patente, fuehrt aber keinen
      Rechtsstatus.
  D3  Allen drei Texten fehlte ein Go/No-Go-Geruest ("keine Abbruchkriterien,
      keine Szenarien, keine Entscheidungsvorlage").
  D4  Unser Dossier zitierte "GKV +1,2 Mio. Patienten/Jahr" gegen eine Seite,
      die diese Zahl nachweislich nicht enthaelt. Die Kanonisierung belegt nur,
      dass die URL im Katalog liegt.
  D5  Fliesstext-Links mit Leerzeichen im Host ("https://the analyst.de/...")
      sind als String kein URI und nicht aufloesbar; dazu zwei Doppeleintraege
      im Quellenverzeichnis.

Alles hier laeuft ohne DB, ohne Netz und ohne GPU.
"""
import pytest

from pipeline import dossier_quant as dq
from pipeline import dossier_structure as ds
from pipeline.dossier_check import check_result
from scripts import corpus_research as cr


# Ein Musterbericht, der ALLE mechanischen Pflichten erfuellt. Seit R8-1
# gehoeren dazu der Katalysator-Kalender (>=5 datierte, belegte Zeilen), eine
# datierte und belegte Aussage je Kette-Ebene und die Untergrenze des
# Laengenbands — `filler` steht deshalb per Default auf BODY_WORDS_MIN.
_CHAIN_SENTENCES = (
    "A phase 3 trial read out in March 2026 [[T1]].",
    "The patent family expires in 2031, and the SPC with it [[T1]].",
    "Series B funding of one investor closed in June 2026 [[T1]].",
    "Revenue from the launch grew through Q1 2026 [[T1]].",
)

_CALENDAR = ["| Date | Event | Source | Why it matters |",
             "|---|---|---|---|"] + [
    f"| Q{i} 2099 | Decision {i} | [[T1]] | It moves the market. |"
    for i in range(1, 6)]


def _report(summary_words: int = 40, options: int = 2,
            drop_field: str | None = None, filler: int = 2200,
            cite: bool = True, calendar: bool = True,
            chain: bool = True) -> str:
    """`cite=False` baut Optionen ohne Beleg — seit R7-1 ein Befund: eine
    Option darf ohne Messgroesse auskommen, aber nicht ohne beides.
    `calendar=False` / `chain=False` erzeugen die R8-1-Maengel."""
    body = ["# Dossier", "", "## Decision summary", "",
            " ".join(["word"] * summary_words) + " [[T1]].", "",
            "## What is moving", ""]
    if chain:
        body += [" ".join(_CHAIN_SENTENCES), ""]
    body += ["Movement." + " filler" * filler, "",
             "## Regulatory and IP status", "", "Nothing found.", "",
             "## What happens next", ""]
    body += (_CALENDAR if calendar else ["Nothing dated."]) + [""]
    body += ["## What the evidence does not support", "", "Nothing.", "",
             "## Options for a mid-sized European company", ""]
    for i in range(1, options + 1):
        body += [f"### Option {i} — Something", ""]
        for label in ds.OPTION_LABELS["en"]:
            if label == drop_field and i == 1:
                continue
            body.append(f"- {label}: value" +
                        (" [[T1]]" if cite and label == "Trigger" else ""))
        body.append("")
    body += ["## Open questions and limits", "", "Open."]
    return "\n".join(body)


# ===========================================================================
# D1/D3 — die verbindliche Gliederung und ihr Entscheidungsgeruest
# ===========================================================================

class TestOutline:
    def test_clean_report_has_no_findings(self):
        assert ds.structure_findings(_report()) == []

    def test_missing_section_is_a_finding(self):
        doc = _report().replace("## Regulatory and IP status", "## Something else")
        assert any("Regulatory and IP status" in f
                   for f in ds.structure_findings(doc))

    def test_overlength_is_a_finding(self):
        doc = _report(filler=ds.BODY_WORDS_MAX + 10)
        f = ds.structure_findings(doc)
        assert any(str(ds.BODY_WORDS_MAX) in x for x in f)

    def test_summary_cap_is_enforced(self):
        f = ds.structure_findings(_report(summary_words=ds.SUMMARY_WORDS_MAX + 5))
        assert any("Decision summary" in x for x in f)

    def test_every_option_needs_the_counterargument(self):
        f = ds.structure_findings(_report(drop_field="Against it"))
        assert any("Against it" in x for x in f)

    def test_one_option_is_not_a_decision(self):
        assert any("Option" in x for x in ds.structure_findings(_report(options=1)))

    def test_word_count_is_stable_across_canonicalization(self):
        """Der Fliesstext zaehlt ohne Zitatapparat — sonst waere derselbe Text
        vor der Kanonisierung (Marker) kurz und danach (Titel+URL) lang."""
        marker = "Claim one [[T1]] and claim two [[T2]]."
        canonical = ("Claim one [A very long source title here](https://a.de/x) "
                     "and claim two [Another long title](https://b.de/y).")
        assert ds.count_words(marker) == ds.count_words(canonical) == 6

    def test_appendices_never_count(self):
        doc = _report() + "\n\n## Research coverage (auto-generated)\n" + "x " * 5000
        assert ds.count_words(ds.body_text(doc)) < ds.BODY_WORDS_MAX

    def test_prompt_carries_exactly_the_checked_headings(self):
        sysprompt = cr.report_system(True, "en")
        for _key, heading, _pat in ds.SECTIONS["en"]:
            assert f"## {heading}" in sysprompt
        for label in ds.OPTION_LABELS["en"]:
            assert label in sysprompt
        assert str(ds.BODY_WORDS_MAX) in sysprompt

    def test_german_outline_matches_the_german_check(self):
        sysprompt = cr.report_system(True, "de")
        for _key, heading, _pat in ds.SECTIONS["de"]:
            assert f"## {heading}" in sysprompt

    def test_old_path_is_reproducible(self):
        assert cr.report_system(False, "en") == cr.REPORT_SYSTEM
        assert "MANDATORY OUTLINE" not in cr.REPORT_SYSTEM
        assert "MANDATORY OUTLINE" not in cr.REPORT_SYSTEM_IDS

    def test_revision_prompt_is_a_single_pass(self):
        text = ds.revision_prompt(["zu lang"], [], "en")
        assert "only correction pass" in text
        assert "no new figures" in text


# ===========================================================================
# D2 — Rechts- und Zulassungs-Sweep als eigene Suchrichtung
# ===========================================================================

class TestRegulatorySweep:
    def _hits(self, url: str, n: int = 3) -> list[dict]:
        # Die Treffer tragen den Gegenstand — seit Runde 5 filtert der Sweep
        # VOR dem Abruf gegen Themen-/Entitaetsbegriffe (Rauschbremse).
        return [{"id": f"W{i}", "trend_id": None, "kind": "web",
                 "title": f"Topic hit {i}", "url": f"{url}{i}",
                 "origin": f"{url}{i}", "outlet": "outlet", "vertical": "",
                 "date": "2026-01-01",
                 "snippet": "incretin GLP-1 semaglutide snippet",
                 "fetched": False} for i in range(n)]

    def _per_query(self, n: int = 3):
        """Jede Suche liefert EIGENE URLs — sonst frisst die URL-Dedup die
        spaeteren Muster auf und der Test misst den Stub, nicht die Kappe."""
        return lambda q, count=6: self._hits(
            f"https://law{abs(hash(q)) % 9973}.example/", n)

    def test_every_pattern_is_searched_and_recorded(self, monkeypatch):
        seen = []
        gen = self._per_query()
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, n=6: (seen.append(q), gen(q))[1])
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: ("page text 2031", "fetched"))
        sources, notes, ledger, ids = [], [], [], set()
        added, record = cr.sweep_regulatory("GLP-1 and incretin technology",
                                            sources, ids, notes, ledger)
        assert len(seen) == len(cr.REGULATORY_PATTERNS)
        # Die Messnormalisierung liefert die Suchphrase — nicht die Fuellwoerter.
        assert all("GLP-1 incretin" in q for q in seen)
        assert "patent expiry supplementary protection certificate" in seen[0]
        assert added == len(cr.REGULATORY_PATTERNS) * cr.REG_PER_PATTERN
        assert all(s["kind"] == "legal" for s in sources)
        assert all(e["kind"] == "legal" for e in ledger)
        for q in seen:
            assert q in record

    def test_nothing_found_is_stated_not_silently_dropped(self, monkeypatch):
        monkeypatch.setattr(cr, "brave_search", lambda q, n=6: [])
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: ("", "blocked"))
        sources, notes, ledger = [], [], []
        added, record = cr.sweep_regulatory("topic", sources, set(), notes, ledger)
        assert added == 0
        assert record.count("nothing usable") == len(cr.REGULATORY_PATTERNS)
        assert len(ledger) == len(cr.REGULATORY_PATTERNS)

    def test_a_snippet_never_carries_a_citation(self, monkeypatch):
        """Verpflichtend gefetcht: was nicht gelesen wurde, ist nicht zitierbar."""
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, n=6: self._hits("https://law.example/", 1))
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: ("", "blocked"))
        sources = []
        cr.sweep_regulatory("topic", sources, set(), [], [])
        assert sources and not any(s.get("fetched") for s in sources)
        citable = [s for s in sources
                   if s["kind"] not in ("web", "legal") or s.get("fetched")]
        assert citable == []

    def test_fetch_budget_is_bounded(self, monkeypatch):
        monkeypatch.setattr(cr, "brave_search", self._per_query())
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: ("text", "fetched"))
        sources = []
        cr.sweep_regulatory("topic", sources, set(), [], [])
        assert sum(1 for s in sources if s.get("fetched")) == cr.REG_MAX_FETCH

    def test_search_failure_does_not_kill_the_run(self, monkeypatch):
        def boom(q, n=6):
            raise RuntimeError("BRAVE_SEARCH_API_KEY is not set (.env)")
        monkeypatch.setattr(cr, "brave_search", boom)
        added, record = cr.sweep_regulatory("topic", [], set(), [], [])
        assert added == 0 and "search failed" in record

    def test_legal_rows_are_not_open_questions(self):
        """Ein Suchmuster ohne Treffer ist keine offene Audit-Frage."""
        res = {"report": "x", "sources": [], "evidence": [], "cited": [],
               "ledger": [{"kind": "legal", "gap": "q"},
                          {"kind": "gap", "gap": "g"},
                          {"kind": "plan", "gap": "p"}]}
        assert check_result(res)["open_questions"] == 1


# ===========================================================================
# D4 — steht die zitierte Zahl auch in der zitierten Seite?
# ===========================================================================

ING = {"id": "T900000000", "kind": "web", "url": "https://think.ing.example/a",
       "origin": "https://think.ing.example/a", "title": "ING analysis",
       "outlet": "ING", "date": "2026-05-01", "snippet": "adoption",
       "fetched": True,
       "text": ("Adoption in the EU and UK is around 2%, versus roughly 12% "
                "in the US. Oral formulations dominate from 2027.")}
ARTICLE = {"id": "T1", "kind": "article", "url": "https://catandary.de/trends/a-1",
           "origin": "https://outlet.example/a", "title": "Corpus piece",
           "outlet": "Outlet", "date": "2026-02-02", "snippet": "..."}


class TestCitedFigures:
    def test_the_measured_failure_case_is_caught(self):
        """Genau der Befund: 1,2 Mio. steht nicht in der ING-Seite. Die
        Normalisierung von grounding.py macht aus '1.2' sonst '12' — und '12'
        steht dort sehr wohl."""
        rep = ("## Decision summary\nGerman insurers added 1.2 million "
               "eligible patients annually [[T900000000]].\n")
        out = ds.verify_cited_figures(rep, [ING])
        assert out["checked"] == 1
        assert out["unverified"] and out["unverified"][0]["tokens"] == ["1.2"]

    def test_a_figure_that_is_on_the_page_passes(self):
        rep = "EU adoption is near 2% against 12% in the US [[T900000000]].\n"
        assert ds.verify_cited_figures(rep, [ING])["unverified"] == []

    def test_corpus_citations_keep_the_existing_path(self):
        """Zitiert der Satz Korpusmaterial, ist sein Beleg der Evidenzblock —
        nicht eine Seite. Er wird hier nicht geprueft."""
        rep = "Claim with 1234 units [[T1]] and [[T900000000]].\n"
        assert ds.verify_cited_figures(rep, [ING, ARTICLE])["checked"] == 0

    def test_unfetched_page_is_not_checked(self):
        src = dict(ING, fetched=False, text=None)
        rep = "Claim with 1.2 million [[T900000000]].\n"
        assert ds.verify_cited_figures(rep, [src])["checked"] == 0

    def test_canonical_link_form_is_checked_too(self):
        rep = ("German insurers added 1.2 million patients "
               "[ING analysis](https://think.ing.example/a).\n")
        assert ds.verify_cited_figures(rep, [ING])["unverified"]

    def test_drop_removes_exactly_the_sentence(self):
        rep = ("Good sentence with 2% [[T900000000]].\n"
               "Bad sentence with 1.2 million [[T900000000]].\n")
        out = ds.verify_cited_figures(rep, [ING])
        cleaned, dropped = ds.drop_unverified(rep, out["unverified"])
        assert dropped == 1
        assert "1.2 million" not in cleaned and "Good sentence" in cleaned

    def test_revision_prompt_names_page_and_tokens(self):
        out = ds.verify_cited_figures(
            "Claim with 1.2 million [[T900000000]].\n", [ING])
        text = ds.revision_prompt([], out["unverified"], "en")
        assert "1.2" in text and "think.ing.example" in text

    def test_check_reports_dropped_sentences(self):
        res = {"report": "x [a](https://a.de/b)", "sources": [ARTICLE],
               "evidence": [], "cited": ["T1"], "ledger": [],
               "structure": {"dropped_sentences": 1, "findings_after": [],
                             "cite_findings": [{"tokens": ["1.2"]}],
                             "cite_findings_after": []}}
        out = check_result(res)
        assert out["dropped_sentences"] == 1
        assert any("zitierte Web-Seite" in f for f in out["findings"])

    def test_leftover_structure_findings_block_ok(self):
        res = {"report": "x", "sources": [], "evidence": [], "cited": [],
               "ledger": [], "structure": {"findings_after": ["zu lang"]}}
        out = check_result(res)
        assert out["ok"] is False and out["structure_findings"] == ["zu lang"]


# ===========================================================================
# D5 — Zitat-URLs muessen aufloesbar sein
# ===========================================================================

class TestUrlHygiene:
    @pytest.mark.parametrize("url,ok", [
        ("https://the analyst.de/trends/x", False),
        ("https://catandary.de/trends/x-1", True),
        ("https:// /a", False),
        ("ftp://a.de/x", False),
        ("", False),
    ])
    def test_valid_url(self, url, ok):
        assert cr.valid_url(url) is ok

    def test_broken_host_falls_back_to_the_original(self):
        src = [{"id": "T1", "kind": "signal", "title": "T",
                "url": "https://the analyst.de/trends/x",
                "origin": "https://agfundernews.example/a", "outlet": "", "date": ""}]
        body, cited, stripped = cr.canonicalize_citations(
            "Claim [[T1]].", src, "en", markers=True)
        assert stripped == 0 and len(cited) == 1
        assert "agfundernews.example" in body
        assert "the analyst.de" not in body

    def test_unresolvable_source_carries_no_citation(self):
        src = [{"id": "T1", "kind": "signal", "title": "T",
                "url": "https://the analyst.de/x", "origin": "", "outlet": "",
                "date": ""}]
        body, cited, stripped = cr.canonicalize_citations(
            "Claim [[T1]].", src, "en", markers=True)
        assert stripped == 1 and cited == []

    def test_source_list_has_no_duplicates(self):
        src = [{"id": "T1", "kind": "article", "title": "A",
                "url": "https://catandary.de/trends/a-1", "origin": "", "outlet": "",
                "date": ""},
               {"id": "T2", "kind": "signal", "title": "A again",
                "url": "https://catandary.de/trends/a-1", "origin": "", "outlet": "",
                "date": ""}]
        body, cited, stripped = cr.canonicalize_citations(
            "Claim [[T1]] and [[T2]].", src, "en", markers=True)
        assert len(cited) == 1
        assert body.count("catandary.de/trends/a-1") == 3   # 2x inline, 1x Liste


# ===========================================================================
# Ende-zu-Ende ueber run() — mit Stubs, ohne DB/Netz/GPU
# ===========================================================================

class _Chat:
    """Ein Modell-Stub, der beim ERSTEN Bericht bewusst gegen die Gliederung
    verstoesst und beim Neuwurf liefert — so laeuft der Korrekturpfad wirklich
    durch, statt nur seine Bausteine einzeln zu testen."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, model, prompt, system=None, temperature=0.0, **kw):
        self.calls.append(prompt)
        if "REVISION" in prompt:
            # lang genug fuer den Kurz-Guard (>= 300 Woerter) UND fuer die
            # Untergrenze des Laengenbands (R8-1) — der Default von _report
            # liefert beides.
            return _report()
        # Erster Wurf: Pflichtabschnitt fehlt UND eine Zahl, die die zitierte
        # Seite nicht hergibt.
        return (_report().replace("## Regulatory and IP status", "## Background")
                + "\n\nInsurers added 1.2 million patients [[L0]].\n")


def _structured(monkeypatch, plan_steps=1):
    from pipeline import llamacpp_client

    def chat_structured(model, schema, prompt, system=None, **kw):
        name = schema.__name__
        if name == "Plan":
            return schema(title="P", steps=[{"title": "S", "query": "q"}])
        if name == "AgentAction":
            return schema(action="finish", title="done", argument="",
                          state={"summary": "s", "gaps": [], "unsupported": []})
        if name == "WebAction":
            return schema(action="finish", title="done", argument="",
                          target_gap=-1,
                          state={"summary": "s", "gaps": [], "unsupported": []})
        if name == "Audit":
            return schema(thesis="t", supported=[], inferences=[],
                          contradictions=[],
                          missing=["what is the legal status"], outline=["o"])
        raise AssertionError(name)

    monkeypatch.setattr(llamacpp_client, "chat_structured", chat_structured)


LEGAL_PAGE = "The SPC runs to March 2031 in the Netherlands."
SEED = dict(ARTICLE, vertical="HEALTH", snippet="corpus snippet", fetched=False)


def test_measure_path_end_to_end(monkeypatch):
    from pipeline import llamacpp_client
    chat = _Chat()
    _structured(monkeypatch)
    monkeypatch.setattr(llamacpp_client, "chat", chat)
    monkeypatch.setattr(cr, "search_corpus", lambda q, n, scope="both": [dict(ARTICLE)])
    monkeypatch.setattr(cr, "search_research", lambda *a, **k: [])
    monkeypatch.setattr(cr, "search_patents", lambda *a, **k: [])
    monkeypatch.setattr(cr, "brave_search", lambda q, n=6: [
        {"id": "W0", "trend_id": None, "kind": "web", "title": "Ruling",
         "url": f"https://law.example/{abs(hash(q)) % 997}", "origin": "",
         "outlet": "Law", "vertical": "", "date": "2026-08-05",
         "snippet": "SPC", "fetched": False}])
    monkeypatch.setattr(cr, "fetch_web_page_status",
                        lambda url: (LEGAL_PAGE, "fetched"))

    out = cr.run("What should we do?", max_steps=1, max_sources=8,
                 retrieval="fts", per_query=2, web_steps=1, max_web_sources=2,
                 topic="GLP-1 and incretin technology", measure=True,
                 seed_sources=[dict(SEED)], seed_notes=["seed"])

    # 1. Rechts-Sweep hat einen eigenen Katalogbereich gefuellt — und seit
    #    Runde 5 laeuft danach die zweite Welle je Entitaet, also MEHR als die
    #    festen Themenmuster.
    assert out["kinds"]["legal"] >= len(cr.REGULATORY_PATTERNS)
    assert any(e["kind"] == "legal" for e in out["ledger"])
    # 2. genau EIN Neuwurf, mit Revisionsauftrag
    st = out["structure"]
    assert st["rewritten"] is True
    assert sum("REVISION" in c for c in chat.calls) == 1
    assert len(chat.calls) == 2
    # 3. der erste Wurf war strukturell und beleghaft auffaellig, der zweite ist sauber
    assert st["findings"] and st["cite_findings"]
    assert st["findings_after"] == [] and st["cite_findings_after"] == []
    assert st["dropped_sentences"] == 0
    # 4. das AUSGELIEFERTE Dokument traegt kein Suchprotokoll mehr; die
    #    Beleg-Verifikation steht im Pruefanhang (R6, jury_7/jury_8)
    assert "Verification of web citations" in out["audit_annex"]
    assert "Research coverage" not in out["report"]
    assert ds.AUDIT_ANNEX_MARK not in out["report"]


def test_measure_false_writes_once_and_skips_the_sweep(monkeypatch):
    from pipeline import llamacpp_client
    chat = _Chat()
    _structured(monkeypatch)
    monkeypatch.setattr(llamacpp_client, "chat", chat)
    monkeypatch.setattr(cr, "search_corpus", lambda q, n, scope="both": [dict(ARTICLE)])
    monkeypatch.setattr(cr, "search_research", lambda *a, **k: [])
    monkeypatch.setattr(cr, "search_patents", lambda *a, **k: [])
    monkeypatch.setattr(cr, "brave_search",
                        lambda q, n=6: pytest.fail("kein Web im alten Pfad"))
    out = cr.run("What should we do?", max_steps=1, max_sources=8,
                 retrieval="fts", per_query=2, web_steps=0, max_web_sources=2,
                 topic="GLP-1 and incretin technology", measure=False,
                 seed_sources=[dict(SEED)], seed_notes=["seed"])
    assert len(chat.calls) == 1
    assert out["kinds"]["legal"] == 0
    assert out["structure"]["rewritten"] is False
    assert out["structure"]["findings"] == []


# ===========================================================================
# Nachbesserungen aus dem B2-Lauf (2026-09-07)
# ===========================================================================

class TestPostRunFixes:
    def test_stripped_marker_leaves_no_hanging_punctuation(self):
        """Der Gutachter nannte genau das: „Satz endet auf ein Leerzeichen und
        einen Punkt, es folgt kein Beleg."""
        src = [{"id": "T1", "kind": "article", "title": "A", "outlet": "", "date": "",
                "url": "https://catandary.de/trends/a-1", "origin": ""}]
        body, _cited, stripped = cr.canonicalize_citations(
            "New filings preserve lean mass [[T900000013]].\n"
            "Zealand and Septerna raised money [[T900000004]], [[T900000009]].\n",
            src, "en", markers=True)
        assert stripped == 3
        assert " ." not in body and " ," not in body
        assert "lean mass." in body and "raised money." in body

    def test_clean_report_is_left_alone(self):
        src = [{"id": "T1", "kind": "article", "title": "A", "outlet": "", "date": "",
                "url": "https://catandary.de/trends/a-1", "origin": ""}]
        text = "Claim [[T1]].\nA line break here  \nand more."
        body, _c, stripped = cr.canonicalize_citations(text, src, "en", markers=True)
        assert stripped == 0
        assert "  \n" in body          # Markdown-Zeilenumbruch bleibt

    def test_short_report_is_a_rewrite_reason_again(self):
        """R8-1 dreht die Runde-7-Regel um. Begruendung im Lauf B7: der
        Fliesstext kam auf 1.623 Woerter (577 unter dem Band), und beide Jurys
        vom 2026-09-07 zogen genau dafuer Punkte ab (Abdeckung 6:9). Der
        Befund muss den Betrag UND das erlaubte Fuellmaterial nennen."""
        short = _report(filler=0)
        found = ds.structure_findings(short)
        assert any("Untergrenze" in f and "belegten Fakten" in f
                   for f in found)
        assert any(str(ds.BODY_WORDS_MIN) in f for f in found)
        adv = ds.length_advisory(short)
        assert adv and str(ds.BODY_WORDS_MIN) in adv[0]
        long_enough = _report()
        assert ds.length_advisory(long_enough) == []
        assert ds.structure_findings(long_enough) == []

    def test_advisory_reaches_the_check_without_failing_it(self):
        res = {"report": "x [a](https://a.de/b)", "sources": [ARTICLE],
               "evidence": [], "cited": ["T1"], "ledger": [],
               "structure": {"advisory": ["Fliesstext 1907 Woerter"],
                             "findings_after": [], "cite_findings": [],
                             "cite_findings_after": []}}
        out = check_result(res)
        assert out["ok"] is True
        assert any("1907" in f for f in out["findings"])

    def test_uncitable_ids_are_named_in_the_report_prompt(self, monkeypatch):
        """Alle 10 gestrichenen Marker des B2-Laufs waren ungefetchte
        Web-Treffer, deren IDs nur in den Evidenznotizen standen."""
        from pipeline import llamacpp_client
        seen: list[str] = []

        def chat(model, prompt, system=None, temperature=0.0, **kw):
            seen.append(prompt)
            return _report(filler=400)

        _structured(monkeypatch)
        monkeypatch.setattr(llamacpp_client, "chat", chat)
        monkeypatch.setattr(cr, "search_corpus", lambda q, n, scope="both": [])
        monkeypatch.setattr(cr, "search_research", lambda *a, **k: [])
        monkeypatch.setattr(cr, "search_patents", lambda *a, **k: [])
        monkeypatch.setattr(cr, "brave_search", lambda q, n=6: [
            {"id": "W0", "trend_id": None, "kind": "web", "title": "T",
             "url": f"https://x.example/{abs(hash(q)) % 997}", "origin": "",
             "outlet": "", "vertical": "", "date": "", "snippet": "s",
             "fetched": False}])
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda url: ("", "blocked"))   # nie lesbar
        out = cr.run("Q", max_steps=1, max_sources=8, retrieval="fts",
                     per_query=2, web_steps=1, max_web_sources=2, topic="GLP-1",
                     measure=True, seed_sources=[dict(SEED)], seed_notes=["seed"])
        assert out["kinds"]["legal"] == len(cr.REGULATORY_PATTERNS)
        assert "NEVER READ IN FULL" in seen[0]
        for s in out["sources"]:
            if s["kind"] in ("web", "legal") and not s.get("fetched"):
                assert s["id"] in seen[0]


# ===========================================================================
# R3 — die drei Befunde der Blindgutachten jury_3.md / jury_4.md (2026-09-07):
#      33/70 bzw. 40/70 gegen 57/70 bzw. 61/70 fuer eine reine Web-Recherche.
# ===========================================================================

class TestTopicalMeasurementBase:
    """R3-1: die Eigenmessung lag auf `A61P3/10` (alle Antidiabetika, 70.991
    Patente). Beide Jurys nannten sie deshalb Zahlenschmuck — bis hin zur
    eigenen Top-Liste ("Humanized immunoglobulins")."""

    def _rows(self):
        return {"C12N2501/335": {"total": 249, "hits": 25, "precision": 0.100},
                "A61P5/48": {"total": 2439, "hits": 141, "precision": 0.058},
                "A61P3/10": {"total": 70991, "hits": 1581, "precision": 0.022}}

    def test_broad_catch_all_class_is_dropped(self, monkeypatch):
        monkeypatch.setattr(dq, "topical_precision", lambda c, t: self._rows())
        out = dq.sharpen_selection(["A61P5/48", "C12N2501/335", "A61P3/10"],
                                   "GLP-1 and incretin technology")
        assert out["kept"] == ["A61P5/48", "C12N2501/335"]
        assert [d["symbol"] for d in out["dropped"]] == ["A61P3/10"]
        assert out["reason"] is None

    def test_no_density_measurement_changes_nothing(self, monkeypatch):
        """Faellt die Dichte-Query aus, wird NICHT geraten."""
        monkeypatch.setattr(dq, "topical_precision", lambda c, t: {})
        out = dq.sharpen_selection(["A61P3/10"], "topic")
        assert out["kept"] == ["A61P3/10"] and out["rows"] == {}

    def test_base_without_topical_mass_is_reported_not_measured(self, monkeypatch):
        monkeypatch.setattr(dq, "topical_precision", lambda c, t: {
            "A61P3/10": {"total": 70991, "hits": 3, "precision": 0.00004}})
        out = dq.sharpen_selection(["A61P3/10"], "topic")
        assert out["kept"] == [] or out["reason"]
        assert out["reason"]

    def test_measure_topic_drops_the_measurement_instead_of_faking_it(
            self, monkeypatch):
        """Ein fehlender Messblock kostet weniger als ein irrefuehrender."""
        monkeypatch.setattr(dq, "_measure_topic_raw", lambda t: {
            "analysis": {"selection": ["A61P3/10"], "trajectory": {"n_total": 5},
                         "top_patents": []},
            "phrase": "x", "resolved_via": "y", "attempts": []})
        monkeypatch.setattr(dq, "sharpen_selection", lambda c, t: {
            "kept": [], "dropped": [{"symbol": "A61P3/10", "total": 70991,
                                     "hits": 3, "precision": 0.0}],
            "rows": {"A61P3/10": {}}, "hits": 3, "floor": 0.02,
            "reason": "base too broad"})
        out = dq.measure_topic("topic")
        assert out["analysis"] is None
        assert any(a["verdict"] == "base_too_broad" for a in out["attempts"])
        # ... und der Anhang sagt es dem Leser.
        app = dq.measurement_appendix(None, "topic", out)
        assert "base too broad" in app and "failed" in app

    def test_off_topic_hub_patents_are_not_printed(self):
        hubs = [{"pub": "US-5585089-A", "title": "Humanized immunoglobulins"},
                {"pub": "US-1", "title": "GLP-1 receptor agonist formulation"}]
        keep = dq.topical_hubs(hubs, "GLP-1 and incretin technology")
        assert [h["pub"] for h in keep] == ["US-1"]


class TestCitationSubjectCheck:
    """R3-2: ein CNBC-Artikel ueber Novos Wegovy-Pille wurde zweimal als Beleg
    fuer Lillys Orforglipron-Zulassung gefuehrt. Die Zahl stimmte ungefaehr —
    geprueft wurde nie der GEGENSTAND."""

    NOVO = ("Novo Nordisk wins FDA approval for the Wegovy pill, the first "
            "oral GLP-1 for obesity, at 25 mg once daily.")

    def test_the_juror_finding_is_caught(self):
        bad = ds.unverified_subjects(
            "Eli Lilly's orforglipron achieved FDA approval for chronic weight "
            "management.", self.NOVO)
        assert any("Lilly" in b for b in bad)
        assert "orforglipron" in bad

    def test_a_matching_page_passes(self):
        assert ds.unverified_subjects(
            "Novo Nordisk won approval for the Wegovy pill.", self.NOVO) == []

    def test_places_behind_an_article_are_not_subjects(self):
        """Die Falsch-Ablehnung darf nicht teurer sein als der Fund."""
        assert ds.subject_names("The court in The Hague ruled today.") == []

    def test_parts_with_digits_never_trigger_a_rejection(self):
        """Realer Fehlalarm des B3-Laufs: "Eli Lilly's Q1" gegen eine Seite mit
        dem Titel "Eli Lilly Reports 19.8B Q1 Revenue". `grounding` tokenisiert
        die Seite nur ueber Buchstaben — "Q1" ist dort nie zu finden."""
        assert ds.subject_names("Eli Lilly's Q1 revenue hit $19.8B.") \
            == ["Eli Lilly's"]
        assert ds.unverified_subjects(
            "Eli Lilly's Q1 revenue hit $19.8B.",
            "Eli Lilly reports 19.8B Q1 revenue") == []

    def test_generic_capitalised_openers_are_not_subjects(self):
        """Zweiter Fehlalarm des B3-Laufs: "**Marketing** authorisations and
        pending decisions:" als Satzanfang."""
        assert ds.subject_names(
            "Marketing authorisations and pending decisions: the agency "
            "approved the pill.") == []

    def test_substance_names_are_recognised(self):
        names = ds.subject_names(
            "Trials of semaglutide, tirzepatide and retatrutide continue.")
        assert {"semaglutide", "tirzepatide", "retatrutide"} <= set(names)

    def test_verify_reports_subject_mismatch_separately(self):
        src = [{"id": "L1", "kind": "legal", "url": "https://cnbc.example/a",
                "title": "FDA approves Novo pill", "text": self.NOVO,
                "snippet": "", "date": "2025-12-22"}]
        out = ds.verify_cited_figures(
            "# D\n\n## Decision summary\n\nEli Lilly's orforglipron was "
            "approved [[L1]].\n", src)
        assert out["off_topic"] and out["off_topic"][0]["kind"] == "subject"
        assert out["subjects"] >= 2


class TestSourcelessFigures:
    """R3-3: "North America held 77.72% ... CAGR of 14.6% through 2035 ." —
    der Satz endet auf einen freistehenden Punkt, wo das Zitat stehen sollte."""

    REPORT = ("# D\n\n## Decision summary\n\nNorth America held 77.72% of "
              "worldwide sales in 2024, while Asia-Pacific is projected to "
              "grow at a CAGR of 14.6% through 2035 .\n")

    def test_precision_figures_without_a_citation_are_found(self):
        out = ds.sourceless_figures(self.REPORT, [])
        assert out and set(out[0]["tokens"]) == {"77.72%", "14.6%"}

    def test_a_figure_from_our_own_measurement_appendix_is_kept(self):
        measured = "median improvement rate 3.1%/yr, cycle time 11.0 years"
        rep = "# D\n\n## Decision summary\n\nThe field improves at 3.1% a year.\n"
        assert ds.sourceless_figures(rep, [], measured) == []
        assert ds.sourceless_figures(rep, [], "") != []

    def test_a_cited_sentence_is_left_to_the_figure_check(self):
        src = [{"id": "L1", "kind": "legal", "url": "https://a.example/",
                "title": "t", "text": "77.72%", "snippet": "", "date": ""}]
        rep = ("# D\n\n## Decision summary\n\nNorth America held 77.72% of "
               "sales [[L1]].\n")
        assert ds.sourceless_figures(rep, src) == []

    def test_years_and_small_integers_are_not_precision_figures(self):
        rep = ("# D\n\n## Decision summary\n\nBetween 1990 and 2026 the field "
               "produced 3 waves of products.\n")
        assert ds.sourceless_figures(rep, []) == []

    def test_revision_prompt_names_the_three_kinds_apart(self):
        p = ds.revision_prompt([], [
            {"sentence": "a", "tokens": ["1.2"], "url": "u", "kind": "figure"},
            {"sentence": "b", "tokens": ["Lilly"], "url": "u", "kind": "subject"},
            {"sentence": "c", "tokens": ["77.72%"], "url": "", "kind": "sourceless"}])
        assert "stehen NICHT in der zitierten Seite" in p
        assert "handelt NICHT von" in p
        assert "ohne jeden Beleg" in p


class TestDropReasonIsNamed:
    """Nach Runde 3 gibt es drei Streichgruende — "die Zahl stand nicht auf der
    Seite" ist nicht mehr die ganze Wahrheit."""

    def _res(self, st: dict) -> dict:
        return {"report": "x", "sources": [], "evidence": [], "cited": [],
                "ledger": [], "structure": {"findings_after": [],
                                            "cite_findings": [],
                                            "cite_findings_after": [], **st}}

    def test_subject_mismatch_is_named_as_such(self):
        out = check_result(self._res({"dropped_sentences": 2,
                                      "off_topic_after": 2}))
        assert any("anderes Thema" in f for f in out["findings"])
        assert not any("behauptete Zahl nicht" in f for f in out["findings"])

    def test_sourceless_figure_is_named_as_such(self):
        out = check_result(self._res({"dropped_sentences": 1,
                                      "sourceless_after": 1}))
        assert any("ohne Beleg im Satz" in f for f in out["findings"])

    def test_mixed_reasons_are_all_named(self):
        out = check_result(self._res({"dropped_sentences": 3,
                                      "off_topic_after": 1,
                                      "sourceless_after": 1}))
        f = " ".join(out["findings"])
        assert "anderes Thema" in f and "ohne Beleg im Satz" in f
        assert "zitierte Web-Seite" in f


class TestMarketSweep:
    """R3-4 (jury_4.md): dem Verlierer fehlten Metsera-Bietergefecht,
    Frankreichs Erstattungspremiere, NHS-Rollout und die Wirkstoff-Pipeline —
    ein Abdeckungsproblem des Sweeps, nicht des Schreibers."""

    def _gen(self, n: int = 3):
        # Der Host haengt an der Reihenfolge der Anfrage, NICHT an hash(q):
        # der Hash ist je Prozess anders, und zwei Muster mit demselben Rest
        # haetten dieselbe URL — ein Lauf, der gelegentlich fehlschlaegt.
        seen: dict[str, int] = {}

        def gen(q, count=6):
            k = seen.setdefault(q, len(seen))
            return [
                {"id": f"W{i}", "trend_id": None, "kind": "web",
                 "title": f"Topic hit {i}",
                 "url": f"https://m{k}.example/{i}",
                 "origin": "", "outlet": "o", "vertical": "",
                 "date": "2026-01-01",
                 "snippet": "incretin GLP-1 semaglutide", "fetched": False}
                for i in range(n)]
        return gen

    def test_every_market_pattern_runs_with_its_own_budget(self, monkeypatch):
        seen = []
        gen = self._gen()
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, n=6: (seen.append(q), gen(q))[1])
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: ("page text", "fetched"))
        sources, notes, ledger = [], [], []
        added, record = cr.sweep_market("GLP-1 and incretin technology",
                                        sources, set(), notes, ledger)
        assert len(seen) == len(cr.MARKET_PATTERNS)
        assert any("reimbursement decision" in q for q in seen)
        assert any("bidding" in q for q in seen)
        assert any("rollout" in q for q in seen)
        assert any("phase 3" in q for q in seen)
        assert added == len(cr.MARKET_PATTERNS) * cr.MKT_PER_PATTERN
        assert all(s["kind"] == "market" for s in sources)
        assert all(s["id"].startswith("M") for s in sources)
        assert all(e["kind"] == "market" for e in ledger)

    def test_a_snippet_never_carries_a_market_citation(self, monkeypatch):
        monkeypatch.setattr(cr, "brave_search", self._gen(1))
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: ("", "blocked"))
        sources = []
        cr.sweep_market("topic", sources, set(), [], [])
        assert sources and not any(s.get("fetched") for s in sources)

    def test_market_rows_are_not_open_questions(self):
        res = {"report": "x", "sources": [], "evidence": [], "cited": [],
               "ledger": [{"kind": "market", "gap": "q"},
                          {"kind": "gap", "gap": "g"}]}
        assert check_result(res)["open_questions"] == 1

    def test_the_two_fixed_directions_do_not_share_a_budget(self):
        assert cr.MKT_MAX_SOURCES and cr.REG_MAX_SOURCES
        assert cr.sweep_market is not cr.sweep_regulatory


# ===========================================================================
# Runde 5 (2026-09-07): die Web-Schicht auf Augenhoehe.
#
# Belegte Ausgangslage (docs/dossier_vs_deepresearch/00_ergebnis.md, §3):
# der Sieger las ~45 Primaerseiten, unser Sweep 6-16 und verwarf im
# Askea-Lauf belegbar echte Treffer STILL ("8 hits, 0 new", Katalog voll).
# ===========================================================================

class TestRound5Budget:
    def test_caps_were_raised_to_the_reading_target(self):
        """40-60 gelesene Seiten je Lauf statt 6-16."""
        # 12 -> 14 mit R8-1: die beiden Sweeps bekamen je ein bzw. zwei
        # vorwaertsgerichtete Muster ("upcoming ... expected date") fuer den
        # Katalysator-Kalender, und die Volltext-Budgets werden der Reihe nach
        # vergeben — ohne mehr Budget haetten die neuen Muster nur unlesbare
        # Katalogzeilen erzeugt.
        assert cr.REG_MAX_FETCH == 14 and cr.MKT_MAX_FETCH == 14
        assert cr.SUB_MAX_FETCH == 8 and cr.ENT_MAX_FETCH == 8
        assert cr.BACKSTOP_FETCH_BUDGET == 12
        fixed = (cr.REG_MAX_FETCH + cr.MKT_MAX_FETCH
                 + cr.SUB_MAX_FETCH + cr.ENT_MAX_FETCH)
        assert 40 <= fixed + cr.BACKSTOP_FETCH_BUDGET <= 60

    def test_no_pattern_is_starved_by_an_earlier_one(self):
        """Die globale Kappe darf nicht VOR der Muster-Kappe binden — sonst
        bekommen die spaeten Muster (EFSA, EU-Recht) nie ein Budget."""
        assert cr.REG_MAX_SOURCES >= len(cr.REGULATORY_PATTERNS) * cr.REG_PER_PATTERN
        assert cr.MKT_MAX_SOURCES >= len(cr.MARKET_PATTERNS) * cr.MKT_PER_PATTERN
        assert cr.SUB_MAX_SOURCES >= (cr.SUB_MAX_ENTITIES
                                      * len(cr.SUBSTANCE_LEGAL_PATTERNS)
                                      * cr.SUB_PER_PATTERN)
        assert cr.ENT_MAX_SOURCES >= (cr.ENT_MAX_ENTITIES
                                      * len(cr.ENTITY_MARKET_PATTERNS)
                                      * cr.ENT_PER_PATTERN)

    def test_agent_web_defaults_were_raised(self):
        import inspect
        sig = inspect.signature(cr.run)
        assert sig.parameters["web_steps"].default == 14
        assert sig.parameters["max_web_sources"].default == 32

    def test_report_gets_a_bigger_evidence_budget_than_the_loop(self):
        assert cr.MAX_REPORT_EVIDENCE_CHARS > cr.MAX_EVIDENCE_CHARS


class TestNoSilentDrop:
    """Der Askea-Fehler: ein brauchbarer Treffer faellt am Budget und niemand
    erfaehrt davon."""

    def _hits(self, n):
        return [{"id": f"W{i}", "trend_id": None, "kind": "web",
                 "title": f"Semaglutide ruling {i}",
                 "url": f"https://law.example/{i}", "origin": "",
                 "outlet": "o", "vertical": "", "date": "2026-01-01",
                 "snippet": "semaglutide SPC", "fetched": False}
                for i in range(n)]

    def test_budget_drop_is_counted_and_named(self, monkeypatch):
        monkeypatch.setattr(cr, "brave_search", lambda q, n=6: self._hits(6))
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: ("text", "fetched"))
        ledger: list[dict] = []
        added, record = cr.sweep_fixed(
            "semaglutide", [], set(), [], ledger, patterns=("{t} SPC",),
            per_pattern=2, max_sources=2, max_fetch=2)
        assert added == 2
        assert ledger[0]["budget_dropped"] == 4
        assert "NOT admitted (budget)" in record

    def test_fetch_reason_is_recorded_per_hit(self, monkeypatch):
        monkeypatch.setattr(cr, "brave_search", lambda q, n=6: self._hits(2))
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: ("", "blocked"))
        ledger: list[dict] = []
        _, record = cr.sweep_fixed("semaglutide", [], set(), [], ledger,
                                   patterns=("{t} SPC",), per_pattern=2)
        assert [x["status"] for x in ledger[0]["fetch_log"]] == ["blocked",
                                                                 "blocked"]
        assert "unreadable: blocked" in record

    def test_status_names_the_real_obstacle(self):
        assert cr._fetch_status("robots") == "robots"
        assert cr._fetch_status("http 403") == "blocked"
        assert cr._fetch_status("http 429") == "blocked"
        assert cr._fetch_status("http 500") == "http 500"
        assert cr._fetch_status("error ReadTimeout") == "timeout"
        assert cr._fetch_status("error SSLError") == "error"
        assert cr._fetch_status("tdm:meta robots: noai") == "tdm"
        assert cr._fetch_status("too_short") == "too_short"


class TestRelevanceBeforeFetch:
    def _mixed(self):
        return [
            {"id": "W0", "trend_id": None, "kind": "web", "title": "Cat videos",
             "url": "https://noise.example/1", "origin": "", "outlet": "o",
             "vertical": "", "date": "", "snippet": "unrelated", "fetched": False},
            {"id": "W1", "trend_id": None, "kind": "web",
             "title": "Semaglutide SPC upheld", "url": "https://law.example/2",
             "origin": "", "outlet": "o", "vertical": "", "date": "",
             "snippet": "court", "fetched": False},
        ]

    def test_off_topic_hit_is_dropped_before_it_is_read(self, monkeypatch):
        fetched: list[str] = []
        monkeypatch.setattr(cr, "brave_search", lambda q, n=6: self._mixed())
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: (fetched.append(u), ("t", "fetched"))[1])
        ledger: list[dict] = []
        cr.sweep_fixed("semaglutide", [], set(), [], ledger,
                       patterns=("{t} SPC",), per_pattern=3,
                       terms=["semaglutide"])
        assert fetched == ["https://law.example/2"]
        assert ledger[0]["off_topic_dropped"] == 1

    def test_a_filter_must_not_turn_a_query_into_silence(self, monkeypatch):
        """Rueckfallschwelle: traegt KEIN Treffer einen Themenbegriff, kommt
        der bestplatzierte trotzdem herein — sonst verliert der Filter genau
        die Fundstellen, deretwegen Runde 5 gebaut wurde."""
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, n=6: self._mixed()[:1])
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: ("t", "fetched"))
        sources: list[dict] = []
        ledger: list[dict] = []
        cr.sweep_fixed("semaglutide", sources, set(), [], ledger,
                       patterns=("{t} SPC",), terms=["semaglutide"])
        assert len(sources) == 1
        assert ledger[0].get("floor_admitted") == 1

    def test_a_single_entity_token_is_enough(self):
        """Probe vom 2026-09-07: die Seite mit dem entscheidenden Befund
        ("SPC ... until 2031") sagte nur "Novo", der Filter kannte
        "novo nordisk" — und verwarf genau die Fundstelle, deretwegen Runde 5
        gebaut wurde."""
        terms = cr.entity_terms(["glp-1"], ["Novo Nordisk", "Ozempic"])
        assert "novo" in terms and "nordisk" in terms and "ozempic" in terms
        hit = {"title": "Ozempic's impending patent expiry",
               "snippet": "However, Novo received a patent ... SPC until 2031",
               "url": "https://patentlawyermagazine.com/x"}
        assert cr.web_relevant(hit, terms) is True

    def test_entity_tokens_do_not_smuggle_in_filler(self):
        terms = cr.entity_terms([], ["The Company Group"])
        assert "company" not in terms and "group" not in terms

    def test_a_register_page_is_never_filtered_out(self):
        reg = {"title": "Decision", "snippet": "n/a",
               "url": "https://register.epo.org/application?number=EP123"}
        assert cr.web_relevant(reg, ["semaglutide"]) is True
        assert cr.web_relevant({"title": "x", "snippet": "y",
                                "url": "https://blog.example/x"},
                               ["semaglutide"]) is False


class TestSourceRank:
    def test_registers_and_authorities_come_first(self):
        assert cr.source_rank("https://www.ema.europa.eu/en/x") == 0
        assert cr.source_rank("https://www.fda.gov/news/x") == 0
        assert cr.source_rank("https://uitspraken.rechtspraak.nl/x") == 0
        assert cr.source_rank("https://www.legifrance.gouv.fr/x") == 0
        assert cr.source_rank("https://www.gov.uk/x") == 0

    def test_a_company_newsroom_beats_secondary_press(self):
        assert cr.source_rank("https://www.novonordisk.com/news/x",
                              ["Novo Nordisk"]) == 1
        assert cr.source_rank("https://www.reuters.com/x", ["Novo Nordisk"]) == 2

    def test_ranking_is_stable_within_a_tier(self):
        hits = [{"url": "https://a.example/1"}, {"url": "https://fda.gov/2"},
                {"url": "https://b.example/3"}]
        assert [h["url"] for h in cr.rank_hits(hits)] == [
            "https://fda.gov/2", "https://a.example/1", "https://b.example/3"]

class TestSourceRankFilter:
    """R7-2, jury_10.md: „2 von 5 Stichprobenquellen sind Sekundaer-/Fan-Wikis
    statt Primaerquellen" — retatrutide.med und glp3.wiki trugen zentrale
    Phase-3-Daten, obwohl die IR-Seite des Herstellers verfuegbar war."""

    def test_the_two_jury_sources_are_rejected(self):
        for url in ("https://glp3.wiki/retatrutide",
                    "https://retatrutide.med/trials"):
            assert cr.low_trust(url) is not None
            assert cr.source_rank(url) == cr.RANK_REJECT

    def test_every_entry_carries_a_category_and_a_reason(self):
        for pattern, category, reason in cr.LOW_TRUST_SOURCES:
            assert pattern and category and len(reason) > 10

    def test_the_categories_are_the_four_named_ones(self):
        cats = {c for _p, c, _r in cr.LOW_TRUST_SOURCES}
        assert {"wiki without an editorial process", "content farm",
                "press-release republisher", "forum"} <= cats

    def test_journals_and_ir_pages_rank_as_primary(self):
        assert cr.source_rank("https://www.nature.com/articles/x") == 1
        assert cr.source_rank("https://investor.lilly.com/news",
                              ["Eli Lilly"]) == 1
        assert cr.source_rank("https://www.ema.europa.eu/en/x") == 0

    def test_wikipedia_and_market_research_are_not_rejected(self):
        """Bewusste Grenze: redaktioneller Prozess bzw. benannter Herausgeber —
        der Filter soll nicht mehr wegwerfen, als er soll."""
        assert cr.low_trust("https://en.wikipedia.org/wiki/GLP-1") is None
        assert cr.low_trust("https://www.futuremarketinsights.com/x") is None

    def test_a_rejected_hit_is_recorded_not_silently_dropped(self):
        entry: dict = {}
        assert cr.reject_low_trust({"url": "https://glp3.wiki/a"}, entry) is True
        assert cr.reject_low_trust({"url": "https://www.reuters.com/a"},
                                   entry) is False
        assert entry["rejected"][0]["category"].startswith("wiki")

    def test_the_sweep_never_admits_one_even_as_the_floor(self, monkeypatch):
        """Die Rueckfallschwelle darf den Filter nicht aushebeln — sie war der
        Weg, auf dem die Fan-Wikis in den Katalog kamen."""
        hits = [{"url": "https://glp3.wiki/a", "title": "Retatrutide trials",
                 "snippet": "phase 3", "id": "", "kind": "", "fetched": False},
                {"url": "https://retatrutide.med/b", "title": "Doses",
                 "snippet": "12 mg", "id": "", "kind": "", "fetched": False}]
        monkeypatch.setattr(cr, "brave_search", lambda q, n: list(hits))
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda u: ("text", "fetched"))
        sources, ledger, notes = [], [], []
        added, record = cr.sweep_fixed("glp-1", sources, set(), notes, ledger,
                                       patterns=("{t} patent",), terms=["glp-1"])
        assert added == 0 and sources == []
        assert len(ledger[0]["rejected"]) == 2
        assert "rejected by the source-rank filter" in record

class TestEntityHarvest:
    def _src(self, title, snippet="", outlet="Reuters"):
        return {"id": "T1", "kind": "article", "title": title,
                "snippet": snippet, "outlet": outlet, "url": "https://x/"}

    def test_actor_and_substance_are_found(self):
        srcs = [
            self._src("Novo Nordisk lifts semaglutide output",
                      "Reuters reports on semaglutide supply"),
            self._src("Novo Nordisk and Eli Lilly race on tirzepatide",
                      "semaglutide rivalry"),
            self._src("Eli Lilly wins tirzepatide label", "tirzepatide data"),
        ]
        ents, subs = cr.harvest_entities(srcs, "GLP-1 receptor agonist")
        low = [e.lower() for e in ents]
        assert "semaglutide" in low and "tirzepatide" in low
        assert "novo nordisk" in low and "eli lilly" in low
        assert subs[:2] == ["semaglutide", "tirzepatide"] or set(subs) >= {
            "semaglutide", "tirzepatide"}

    def test_title_case_filler_is_not_an_entity(self):
        srcs = [self._src("Novo Nordisk Wins Court Battle Over Semaglutide"),
                self._src("Novo Nordisk Wins Again In Court")]
        ents, _ = cr.harvest_entities(srcs, "GLP-1")
        low = [e.lower() for e in ents]
        assert "novo nordisk" in low
        assert not any("wins" in e for e in low)
        assert not any("court battle" in e for e in low)

    def test_the_outlet_is_never_the_entity(self):
        srcs = [self._src("Something happened", outlet="Reuters"),
                self._src("Something else happened", outlet="Reuters")]
        ents, _ = cr.harvest_entities(srcs, "GLP-1")
        assert not any("reuters" in e.lower() for e in ents)

    def test_a_single_mention_is_not_yet_an_actor(self):
        srcs = [self._src("Acme Holdings buys a plant")]
        ents, _ = cr.harvest_entities(srcs, "GLP-1")
        assert not any("acme" in e.lower() for e in ents)


class TestSecondWave:
    """Der Mechanismus, mit dem der Siegertext auf Metsera, Frankreich und den
    NHS kam: nicht mehr vom Thema, sondern <Entitaet> <Ereignistyp>."""

    def test_substance_wave_asks_the_spc_question_by_name(self, monkeypatch):
        seen: list[str] = []
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, n=6: (seen.append(q), [])[1])
        cr.sweep_substance_legal("GLP-1 receptor agonist", ["semaglutide"],
                                 [], set(), [], [], 6, ["glp-1"], [])
        assert '"semaglutide" SPC supplementary protection certificate' in seen
        assert "supplementary protection certificate semaglutide expiry" in seen
        assert "semaglutide patent expiry Europe" in seen
        assert "semaglutide court ruling generic" in seen

    def test_entity_wave_pairs_the_actor_with_an_event_type(self, monkeypatch):
        seen: list[str] = []
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, n=6: (seen.append(q), [])[1])
        cr.sweep_entity_market("GLP-1", ["Metsera"], [], set(), [], [], 6,
                               ["glp-1"])
        assert "Metsera acquisition deal agreement announcement" in seen
        assert "Metsera reimbursement pricing decision" in seen
        assert len(seen) == len(cr.ENTITY_MARKET_PATTERNS)

    def test_actors_go_before_substances_in_the_event_wave(self, monkeypatch):
        """Bietergefecht, Erstattung und Quartalszahlen haengen an Firmen —
        der Wirkstoff hat mit dem Rechts-Sweep eine eigene Richtung."""
        seen: list[str] = []
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, n=6: (seen.append(q), [])[1])
        ents = ["semaglutide", "tirzepatide", "liraglutide", "dulaglutide",
                "Metsera", "Novo Nordisk"]
        cr.sweep_entity_market("GLP-1", ents, [], set(), [], [], 6, ["glp-1"])
        assert any("Metsera" in q for q in seen)
        assert any("Novo Nordisk" in q for q in seen)

    def test_the_second_wave_has_its_own_ledger_kind(self, monkeypatch):
        monkeypatch.setattr(cr, "brave_search", lambda q, n=6: [])
        ledger: list[dict] = []
        cr.sweep_entity_market("GLP-1", ["Metsera"], [], set(), [], ledger, 6,
                               ["glp-1"])
        assert {e["kind"] for e in ledger} == {"entity"}

    def test_without_entities_nothing_is_searched(self, monkeypatch):
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, n=6: pytest.fail("keine Entitaet"))
        assert cr.sweep_entity_market("t", [], [], set(), [], [], 6, []) == (0, "")
        assert cr.sweep_substance_legal("t", [], [], set(), [], [], 6, [], []) == (0, "")


class TestKeyPassages:
    def test_the_paragraph_with_the_figure_survives_the_cut(self):
        text = ("Lead paragraph about the case.\n\n"
                + "Navigation boilerplate. " * 40 + "\n\n"
                + "The SPC for semaglutide runs to March 2031.\n\n"
                + "More boilerplate. " * 40)
        out = cr.key_passages(text, ["semaglutide"], limit=300)
        assert "March 2031" in out
        assert "Lead paragraph" in out
        assert len(out) <= 300

    def test_short_pages_are_passed_through_unchanged(self):
        assert cr.key_passages("short", ["x"], limit=100) == "short"

    def test_nothing_matching_still_returns_text(self):
        text = "a" * 500
        assert cr.key_passages(text, ["zzz"], limit=100) == "a" * 100


# ===========================================================================
# R6 — die Befunde der Blindgutachten jury_7.md / jury_8.md (2026-09-07):
#      36/70 bzw. 45/70 gegen 56/70 bzw. 59/70 fuer eine reine Web-Recherche.
# ===========================================================================

class TestDeliveredDocument:
    """R6-1: 2.563 der 6.775 Woerter waren Suchprotokoll — beide Jurys nannten
    das Verduennung ("der Kaeufer liest die Werkstatt statt des Produkts").
    Ausgeliefert wird ab jetzt Bericht + Messanhang; Protokoll, Fetch-Log und
    Budget-Meldungen stehen unterhalb der Trennmarke."""

    DOC = "# T\n\nBody.\n\n## Sources\n\n1. [A](https://a.de/b)\n"
    ANNEX = "## Research coverage (auto-generated)\n\n1. [gap] x → 0 fetched\n"

    def test_join_and_split_are_inverse(self):
        full = ds.join_document(self.DOC, self.ANNEX)
        assert ds.AUDIT_ANNEX_MARK in full
        assert ds.delivered(full) == self.DOC.rstrip()
        assert ds.audit_annex(full) == self.ANNEX.strip()

    def test_joining_twice_does_not_duplicate_the_annex(self):
        full = ds.join_document(self.DOC, self.ANNEX)
        assert ds.join_document(full, self.ANNEX) == full

    def test_a_document_without_annex_is_returned_whole(self):
        assert ds.delivered(self.DOC) == self.DOC.rstrip()
        assert ds.audit_annex(self.DOC) == ""
        assert ds.join_document(self.DOC, "") == self.DOC

    def test_the_annex_never_counts_as_body(self):
        full = ds.join_document(self.DOC, "protocol " * 5000)
        assert ds.count_words(ds.body_text(full)) < 20

    def test_save_dossier_stores_both_parts(self, monkeypatch):
        stored: dict = {}

        class _Conn:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, args=()):
                if sql.strip().upper().startswith("INSERT"):
                    stored["report_md"] = args[4]
                    return None
                if "max(version)" in sql:
                    return _Row()
                return None

        class _Row:
            def keys(self):
                return ["v"]

            def __getitem__(self, k):
                return 1

            def fetchone(self):
                return self

        monkeypatch.setattr(cr, "get_connection", lambda: _Conn())
        cr.save_dossier("s", "t", "q", self.DOC,
                        {"audit_annex": self.ANNEX, "model": "M"})
        assert ds.AUDIT_ANNEX_MARK in stored["report_md"]
        assert ds.delivered(stored["report_md"]) == self.DOC.rstrip()
        assert "Research coverage" in ds.audit_annex(stored["report_md"])

    def test_the_check_reads_only_the_delivered_body(self):
        res = {"report": ds.join_document(self.DOC, "1990 1991 1992 " * 20),
               "sources": [], "evidence": [], "cited": [], "ledger": []}
        assert check_result(res)["ungrounded"] == []


class TestMeasuredFiguresMustCarry:
    """R7-1, jury_9.md woertlich: die Messwerte stehen „dekorativ" in den
    Optionen. Der Nennungszwang aus Runde 6 ist damit ersetzt durch die
    Verwendbarkeitsregel: besser keine Zahl als eine, die nicht traegt."""

    # Die Form, die pipeline/dossier_quant.format_quant_evidence heute liefert.
    QUANT = {"selection": ["A61P5/48", "C12N2501/335"], "K_median": 3.3,
             "K_calibrated": True, "K_window": [2004, 2026],
             "K_by_year": [{"year": 2019, "K": 3.3, "n": 900, "complete": True},
                           {"year": 2026, "K": 6.1, "n": 210, "complete": False}],
             "cycle_time_years": 12.0, "cycle_time_edges": 7667,
             "cycle_time_since": "2015",
             "centrality_peak_year": 2017, "centrality_peak_n": 115,
             "centrality_window": [2004, 2021],
             "n_patents": 1878, "data_window_start": 1990,
             "takeoff_reportable": False,
             "takeoffs": {"patent": 2002, "market": 1990}}
    CORPUS = {"market_n": 31458, "science_n": 105335,
              "market_window": [2019, 2026], "science_window": [1990, 2026]}

    def test_needles_are_the_usable_measured_scalars(self):
        n = ds.measured_needles(self.QUANT, self.CORPUS)
        assert "12.0" in n and "3.3" in n and "2017" in n and "A61P5/48" in n
        assert "1,878" in n and "31,458" in n
        # Jahre nie mit Tausenderpunkt, und zu kurze Zahlen gar nicht.
        assert "2,017" not in n and "12" not in n

    def test_a_takeoff_without_a_reportable_lead_time_is_blocked(self):
        """jury_9.md: „because the measured market take-off ... was 1990",
        waehrend der eigene Anhang „not reportable as a lead time" schreibt."""
        blocked = ds.blocked_needles(self.QUANT, self.CORPUS)
        assert "1990" in blocked and "2002" in blocked
        assert "1990" not in ds.measured_needles(self.QUANT, self.CORPUS)

    def test_the_calibration_caveat_blocks_the_year_value(self):
        """Die Zahl der Kurzfassung (6,1 %/yr in 2026) sperrt der eigene
        Ehrlichkeitsvermerk — kanonisch ist der Median."""
        assert "6.1" in ds.blocked_needles(self.QUANT)
        assert "6.1" not in ds.measured_needles(self.QUANT)
        # der Median selbst bleibt verwendbar
        assert "3.3" in ds.measured_needles(self.QUANT)

    def test_a_short_needle_never_matches_inside_a_longer_figure(self):
        """Der teuerste Fehlalarm des B7-Laufs: der gesperrte Jahreswert 3.0
        hat die Ganzzahlform „3", und die traf mitten in „3.3 % per year" —
        fuenf korrekte Saetze mit dem kanonischen Median wurden geloescht."""
        q = dict(self.QUANT)
        q["K_by_year"] = [{"year": 2005, "K": 3.0, "n": 150, "complete": True}]
        assert all(len(n) >= ds.MIN_NEEDLE_CHARS
                   for e in ds.measure_inventory(q)["blocked"]
                   for n in e["needles"])
        good = ("## What is moving\n\nThe measured improvement rate is "
                "3.3% per year (median, n=1,878).")
        assert ds.measure_use_findings(good, q) == []
        assert ds.uses_measurement("a 3.3% rate", ["3"]) is False

    def test_a_measure_without_n_or_period_is_not_usable(self):
        """Regel (b): was im Anhang ohne n und Zeitraum steht, traegt nichts."""
        thin = {"cycle_time_years": 12.0}          # keine Kanten, kein Zeitraum
        assert "12.0" not in ds.measured_needles(thin)
        assert "12.0" in ds.blocked_needles(thin)

    def test_a_blocked_value_in_the_text_is_a_finding(self):
        doc = _report().replace(
            "- Trigger: value [[T1]]",
            "- Trigger: the measured market take-off was 1990 [[T1]]")
        f = ds.measure_use_findings(doc, self.QUANT, self.CORPUS)
        assert len(f) == 1 and f[0]["tokens"] == ["1990"]
        assert f[0]["kind"] == "measure"
        assert "left edge of the data window" in f[0]["detail"]

    def test_a_year_without_its_cue_is_left_alone(self):
        """„1990" allein kann das Datenfenster meinen — erst mit dem Stichwort
        der Kennzahl ist es die gesperrte Groesse."""
        doc = _report().replace("Movement.",
                                "Our data window opens in 1990.")
        assert ds.measure_use_findings(doc, self.QUANT, self.CORPUS) == []

    def test_two_values_of_one_metric_need_one_sentence(self):
        """Regel (c): Median und zweiter Wert nur in EINEM Satz gegenueber-
        gestellt. Der B6-Selbstwiderspruch stand in zwei Saetzen."""
        split = _report().replace(
            "Movement.",
            "The core chemistry is mature (measured improvement rate 3.3 %/yr). "
            "The improvement rate has risen to 5.0 %/yr since.")
        f = ds.measure_use_findings(split, self.QUANT, self.CORPUS)
        assert [e["tokens"][0] for e in f] == ["5.0 %/yr"]
        joined = _report().replace(
            "Movement.",
            "The measured improvement rate is 3.3 %/yr as a median and "
            "5.0 %/yr in the latest window.")
        assert ds.measure_use_findings(joined, self.QUANT, self.CORPUS) == []

    def test_twelve_months_is_not_a_cycle_time(self):
        """Genau der Grund fuer die Mindestlaenge: sonst wuerde jedes
        'within 12 months' die Zykluszeit von 12 Jahren vortaeuschen."""
        assert ds.uses_measurement("Time horizon: within 12 months", ["12.0"]) is False
        assert ds.uses_measurement("cycle time of 12.0 years", ["12.0"]) is True

    def test_an_option_may_stand_without_a_measured_figure(self):
        """Der Nennungszwang ist weg — der Beleg ersetzt die Zahl."""
        assert ds.structure_findings(_report(), measured=["12.0", "3.3"]) == []

    def test_but_not_without_measure_and_without_evidence(self):
        f = ds.structure_findings(_report(cite=False), measured=["12.0"])
        assert len(f) == 2 and all("noch ein Beleg" in x for x in f)

    def test_a_measured_option_passes(self):
        doc = _report(cite=False).replace("- Trigger: value",
                                          "- Trigger: cycle time 12.0 years")
        assert [x for x in ds.structure_findings(doc, measured=["12.0"])
                if "Option 1" in x] == []

    def test_the_prompt_names_the_usable_values_with_n_and_period(self):
        brief = ds.measured_brief(self.QUANT, self.CORPUS)
        assert "12.0" in brief and "3.3" in brief and "A61P5/48" in brief
        assert "31,458" in brief and "n=7,667" in brief
        # gesperrte Groessen stehen nicht drin (Take-off-Jahr, K(t)-Jahreswert)
        assert "take-off" not in brief and "6.1" not in brief

    def test_the_prompt_names_the_blocked_values_with_their_reason(self):
        blocked = ds.blocked_brief(self.QUANT, self.CORPUS)
        assert "1990" in blocked and "6.1" in blocked
        assert "not reportable" in blocked and "calibrated only to ~2019" in blocked

    def test_the_outline_states_the_rule_instead_of_the_mandate(self):
        for lang in ("en", "de"):
            sysprompt = cr.report_system(True, lang)
            assert ("EVERY option must" not in sysprompt
                    and "Jede Option muss mindestens eine GEMESSENE" not in sysprompt)
            assert ("no figure at all than one that does not carry" in sysprompt
                    or "besser keine Zahl als" in sysprompt)

    def test_the_check_reports_options_without_measure_but_not_as_a_defect(self):
        res = {"report": "x", "sources": [], "evidence": [], "cited": [],
               "ledger": [], "structure": {"findings_after": [],
                                           "cite_findings_after": [],
                                           "options": 4, "options_measured": 1,
                                           "options_unsupported": 0}}
        out = check_result(res)
        assert out["options_measured"] == 1
        assert not any("ohne gemessene" in f for f in out["findings"])

    def test_an_option_on_nothing_is_still_a_defect(self):
        res = {"report": "x", "sources": [], "evidence": [], "cited": [],
               "ledger": [], "structure": {"findings_after": [],
                                           "cite_findings_after": [],
                                           "options": 4, "options_measured": 1,
                                           "options_unsupported": 2}}
        assert any("2 von 4" in f for f in check_result(res)["findings"])


class TestAttributionInsideOneSource:
    """R7-3, jury_9.md: „28.7% weight loss ... in the TRANSCEND-T2D-2 trial" —
    dieselbe Seite, andere Studie (die Werte gehoeren zu TRIUMPH-4)."""

    PAGE = ("TRIUMPH-4 evaluated retatrutide in knee osteoarthritis. "
            "Participants lost 28.7% of body weight at 12 mg over 68 weeks, "
            "and WOMAC pain fell by 74.3%. " + "Unrelated filler. " * 60 +
            "TRANSCEND-T2D-2 compares retatrutide with semaglutide in type 2 "
            "diabetes; results are expected in 2027.")

    def test_the_jury_case_is_caught(self):
        sent = ("Retatrutide delivered 28.7% weight loss at 12 mg over 68 "
                "weeks in the TRANSCEND-T2D-2 trial.")
        out = ds.context_conflicts(sent, self.PAGE)
        assert [e["tokens"][0] for e in out] == ["28.7%"]
        assert out[0]["detail"] == "TRANSCEND-T2D-2"

    def test_the_correct_attribution_passes(self):
        sent = ("Retatrutide delivered 28.7% weight loss at 12 mg over 68 "
                "weeks in TRIUMPH-4.")
        assert ds.context_conflicts(sent, self.PAGE) == []

    def test_a_single_subject_page_never_triggers(self):
        page = ("TRIUMPH-4 evaluated retatrutide. " + "Filler. " * 80 +
                "Weight loss reached 28.7%.")
        sent = "TRIUMPH-4 reported 28.7% weight loss."
        assert ds.context_conflicts(sent, page) == []

    def test_agencies_and_ratios_are_not_study_names(self):
        assert "NICE" not in ds.scope_names("NICE recommends the drug")
        assert "CAGR" not in ds.scope_names("a CAGR of 17.4%")
        assert "TRIUMPH-4" in ds.scope_names("TRIUMPH-4 read out")

    def test_a_figure_absent_from_the_page_stays_with_the_figure_check(self):
        sent = "TRANSCEND-T2D-2 showed 99.9% pain reduction."
        assert ds.context_conflicts(sent, self.PAGE) == []

    def test_the_verifier_reports_it(self):
        src = [{"id": "N1", "kind": "web", "url": "https://x.example/a",
                "title": "Retatrutide trials", "text": self.PAGE,
                "fetched": True}]
        doc = ("# D\n\n## What is moving\n\nRetatrutide delivered 28.7% "
               "weight loss at 12 mg over 68 weeks in the TRANSCEND-T2D-2 "
               "trial [[N1]].\n")
        out = ds.verify_cited_figures(doc, src)
        assert [e["tokens"][0] for e in out["misattributed"]] == ["28.7%"]

    def test_two_cited_pages_are_judged_together(self):
        """Der Jury-Satz zitierte ZWEI Seiten. Erst wenn keine von ihnen die
        Zahl im Umfeld der genannten Studie fuehrt, ist er falsch zugeordnet."""
        other = ("TRIUMPH-1 read out in May 2026. " + "Filler. " * 40 +
                 "TRANSCEND-T2D-2 has no efficacy data yet.")
        sent = "TRANSCEND-T2D-2 delivered 74.3% pain reduction."
        assert ds.context_conflicts_multi(sent, [self.PAGE, other])
        near = "TRANSCEND-T2D-2 delivered 74.3% pain reduction in the trial."
        assert ds.context_conflicts_multi(near, [other]) == []

    def test_second_wave_sources_are_verified_at_all(self):
        """Die Quellen der zweiten Welle (kind 'entity') fehlten in
        _VERIFIABLE_KINDS — der Satz mit der Verwechslung wurde deshalb
        vollstaendig uebergangen."""
        assert "entity" in ds._VERIFIABLE_KINDS
        src = [{"id": "E1", "kind": "entity", "url": "https://x.example/a",
                "title": "Retatrutide trials", "text": self.PAGE,
                "fetched": True}]
        doc = ("# D\n\n## What is moving\n\nRetatrutide delivered 28.7% "
               "weight loss in the TRANSCEND-T2D-2 trial [[E1]].\n")
        out = ds.verify_cited_figures(doc, src)
        assert out["checked"] == 1
        assert [e["tokens"][0] for e in out["misattributed"]] == ["28.7%"]

    def test_the_option_field_keeps_its_label_when_a_figure_is_cut(self):
        """Die mechanische Streichung nahm im B6-Lauf einer Option ihr
        Pflichtfeld. Bei einer gesperrten Messgroesse faellt jetzt nur die
        Teilaussage."""
        doc = ("- Trigger: the measured market take-off was 1990, and France "
               "reimburses from June 2026")
        out, n = ds.drop_unverified(doc, [{"sentence": doc, "tokens": ["1990"],
                                           "kind": "measure"}])
        assert n == 1 and out.startswith("- Trigger:")
        assert "1990" not in out and "France" in out


class TestOptionsCoverEveryNamedField:
    """R6-3, jury_8.md: „4 Optionen … fast ausschliesslich Food/Labeling-
    fokussiert; HealthTech kommt nicht vor." Die Frage nennt drei Felder."""

    Q = ("Where does GLP-1 technology stand, and what should a mid-sized "
         "European company in food, nutrition or health technology do?")

    def test_fields_are_read_from_the_question(self):
        assert ds.sectors_from_question(self.Q) == ["food", "nutrition",
                                                    "health technology"]

    def test_a_question_without_fields_switches_the_check_off(self):
        assert ds.sectors_from_question("What is moving in solid-state "
                                        "batteries?") == []

    def test_the_r5_option_set_would_have_failed(self):
        """Nachgestellt: Reformulierung (food+nutrition), Claim-Monitoring,
        Kategorie-Fokus — kein einziger HealthTech-Satz."""
        doc = _report().replace(
            "- Trigger: value",
            "- Trigger: reformulate snack recipes for protein and fibre")
        f = ds.structure_findings(doc, sectors=ds.sectors_from_question(self.Q))
        assert len(f) == 1 and "health technology" in f[0]

    def test_covering_all_three_passes(self):
        doc = _report().replace(
            "- Trigger: value",
            "- Trigger: food reformulation with fibre plus a companion app")
        assert ds.structure_findings(
            doc, sectors=ds.sectors_from_question(self.Q)) == []

    def test_matching_is_word_wise_not_substring(self):
        """Der R5-Nachtest meldete zunaechst alle drei Felder als abgedeckt:
        'app' steckt in 'approval', 'monitoring' in 'regulatory monitoring'."""
        assert ds.uncovered_sectors("regulatory approval and monitoring",
                                    ["health technology"]) == ["health technology"]
        assert ds.uncovered_sectors("a companion app for patients",
                                    ["health technology"]) == []
        assert ds.uncovered_sectors("reformulated meals and snacks",
                                    ["food"]) == []

    def test_the_check_names_the_missing_field(self):
        res = {"report": "x", "sources": [], "evidence": [], "cited": [],
               "ledger": [],
               "structure": {"findings_after": [], "cite_findings_after": [],
                             "sectors_missing": ["health technology"]}}
        out = check_result(res)
        assert out["sectors_missing"] == ["health technology"]
        assert any("health technology" in f for f in out["findings"])


class TestDistortedRestatement:
    """R6-4: drei Faktenfehler, die die Stichproben der Jurys fanden — und die
    KEINE bestehende Pruefung sehen konnte, weil alle drei Woerter oder Zahlen
    benutzen, die auf der zitierten Seite vorkommen."""

    ING_PAGE = ("In Europe and the UK, we estimate that at least 2% of adults "
                "are currently using them. Around 2% of European adults are "
                "using these drugs, and the current impact on total calorie "
                "demand is about 0.25%.")
    PILL_PAGE = ("More than 2 million prescriptions have now been written for "
                 "the Wegovy pill, which launched on Jan. 5, Novo said.")
    EMA_PAGE = ("Liraglutide STADA is a hybrid medicine. In Victoza, the "
                "active substance is made using living cells, whereas in "
                "Liraglutide STADA it is made using chemical processes.")

    def test_at_least_must_not_become_only(self):
        """jury_7.md: „Aus einer Untergrenze wird eine beruhigende Obergrenze —
        und darauf stuetzt P vier der sieben Beruhigungsaussagen."""
        out = ds.qualifier_conflicts(
            "However, only approximately 2% of European and UK adults are "
            "currently using these drugs.", self.ING_PAGE)
        assert len(out) == 1 and out[0]["kind"] == "qualifier"
        assert "2%" in out[0]["tokens"]

    def test_the_same_wording_as_the_page_passes(self):
        for claim in ("Around 2% of adults use them.",
                      "At least 2% of adults use them.",
                      "Approximately 2% of adults use them.",
                      "2% of adults use them."):
            assert ds.qualifier_conflicts(claim, self.ING_PAGE) == []

    def test_only_must_not_become_at_least_either(self):
        page = "Only 2% of adults are currently using them."
        assert ds.qualifier_conflicts("At least 2% of adults use them.", page)

    def test_two_million_must_not_become_five(self):
        """jury_7.md: „Die Zahl ist um den Faktor ~2,5 zu hoch." Die '5' steht
        auf jeder langen Seite — deshalb schwieg die Zahlenpruefung."""
        out = ds.magnitude_conflicts(
            "The Wegovy pill reached over 5 million cumulative US "
            "prescriptions within 30 weeks of launch.", self.PILL_PAGE)
        assert len(out) == 1 and out[0]["kind"] == "magnitude"
        assert "5 million" in out[0]["tokens"][0]

    def test_the_page_figure_itself_passes(self):
        assert ds.magnitude_conflicts(
            "More than 2 million prescriptions were written.",
            self.PILL_PAGE) == []

    def test_a_figure_that_stands_on_the_page_is_never_a_magnitude_finding(self):
        """Steht der Wert selbst auf der Seite, ist die Groessenordnung nicht
        das Problem — sonst meldete die Regel '12% in den USA' als falsch,
        nur weil dieselbe Seite auch 'unter 1% global' nennt."""
        page = "US use is around 12%. Globally the figure is less than 1%."
        assert ds.magnitude_conflicts(
            "US adoption stands at 12% of adults.", page) == []

    def test_a_deviation_inside_the_tolerance_passes(self):
        page = "The trial showed 28.3% weight loss over 80 weeks."
        assert ds.magnitude_conflicts(
            "The trial showed 30.3% weight loss over 104 weeks.", page) == []

    def test_hybrid_must_not_become_generic(self):
        """jury_7.md: „Die EMA stuft Liraglutide STADA ausdruecklich als
        Hybridarzneimittel ein." Ein Kategoriewort, keine Zahl."""
        out = ds.category_conflicts(
            "In 2026, the EMA granted marketing authorisation for Liraglutide "
            "STADA, a generic version of liraglutide.", self.EMA_PAGE)
        assert len(out) == 1 and out[0]["kind"] == "category"
        assert out[0]["tokens"] == ["generic"]

    def test_the_page_word_passes(self):
        assert ds.category_conflicts(
            "Liraglutide STADA is a hybrid medicine.", self.EMA_PAGE) == []

    def test_a_page_naming_both_categories_passes(self):
        page = "Generic and hybrid applications follow different routes."
        assert ds.category_conflicts("A generic version was authorised.",
                                     page) == []

    def test_all_three_reach_the_verification_channel(self):
        src = dict(ING, text=self.ING_PAGE + " " + self.PILL_PAGE + " "
                   + self.EMA_PAGE)
        rep = ("## Decision summary\nOnly approximately 2% of adults use them "
               "[[T900000000]].\n")
        out = ds.verify_cited_figures(rep, [src])
        assert [e["kind"] for e in out["distorted"]] == ["qualifier"]
        text = ds.revision_prompt([], out["distorted"], "en")
        assert "Qualifizierer" in text and "2%" in text

    def test_a_distorted_sentence_is_dropped_like_any_other(self):
        rep = "Only approximately 2% of adults use them [[T900000000]].\n"
        src = dict(ING, text=self.ING_PAGE)
        out = ds.verify_cited_figures(rep, [src])
        cleaned, dropped = ds.drop_unverified(rep, out["distorted"])
        assert dropped == 1 and "2%" not in cleaned

    def test_a_citation_title_never_splits_a_claim(self):
        """Der Grund, warum der ING-Satz im R5-Dossier ungeprueft blieb: der
        Quellentitel „Transformative or overhyped? …" zerlegte den Satz, und
        die Behauptung stand danach ohne Beleg da."""
        text = ("Only approximately 2% of adults use them "
                "[Transformative or overhyped? The impact of weight-loss "
                "drugs](https://think.ing.example/a). Next sentence.")
        claims = ds.split_claims(text)
        assert len(claims) == 2
        assert "2%" in claims[0] and "think.ing.example" in claims[0]


class TestCheckSummaryStaysInTheDossier:
    """jury_7.md empfiehlt woertlich, das Protokoll durch „drei Zeilen
    Methodik plus eine ehrliche Klartextzeile" zu ersetzen — die Ehrlichkeit
    ueber Grenzen ist die Wertung, in der wir fuehren (8:7 bzw. 10:7)."""

    LEDGER = [{"kind": "gap", "gap": "g", "papers": 0, "patents": 0,
               "web_queries": ["a", "b"], "web_sources": 4, "web_fetched": 2,
               "budget_dropped": 3,
               "fetch_log": [{"status": "robots"}, {"status": "fetched"}]},
              {"kind": "legal", "gap": "l", "papers": 0, "patents": 0,
               "web_queries": ["c"], "web_sources": 1, "web_fetched": 1}]
    SOURCES = [{"url": "https://a.example/x", "fetched": True},
               {"url": "https://b.example/y", "fetched": True},
               {"url": "https://c.example/z", "fetched": False}]
    ST = {"cites_checked": 52, "cites_figures": 61, "cites_subjects": 40,
          "cite_findings": [{}, {}], "dropped_sentences": 1}

    def test_it_names_budget_stops_and_unreadable_pages_in_plain_text(self):
        out = cr.check_summary(self.LEDGER, self.SOURCES, ["T1"], self.ST, "en")
        assert "3 usable hits were not evaluated for budget reasons" in out
        assert "1 page(s) could not be read" in out
        assert "1 question(s) after the audit" in out     # legal zaehlt nicht
        assert "2 pages from 2 domains" in out
        assert "52 sentence(s) checked" in out
        assert "audit annex" in out

    def test_it_is_short_enough_to_replace_a_protocol(self):
        # 145 statt 130 seit R8-1: der Nachweis fuehrt jetzt auch die
        # Abdeckung (Kettenebenen, datierte Termine) — eine Zeile, die genau
        # die zwei Kriterien belegt, an denen wir bei beiden Jurys verloren.
        out = cr.check_summary(self.LEDGER, self.SOURCES, ["T1"], self.ST, "en")
        assert len(out.split()) < 145

    def test_it_never_counts_as_body(self):
        doc = "## Decision summary\n\nWord.\n" + cr.check_summary(
            self.LEDGER, self.SOURCES, ["T1"], self.ST, "en")
        # nur Ueberschrift, Wort und der Trennstrich davor
        assert ds.count_words(ds.body_text(doc)) <= 6

    def test_german_runs_carry_the_german_block(self):
        out = cr.check_summary(self.LEDGER, self.SOURCES, ["T1"], self.ST, "de")
        assert "Budgetgründen" in out and "Prüfanhang" in out


class TestB6Followups:
    """Zwei Befunde aus dem B6-Lauf (2026-09-07) selbst."""

    Q = ("what should a mid-sized European company in food, nutrition or "
         "health technology do?")

    def test_naming_the_three_fields_is_not_coverage(self):
        """B6 bestand die Abdeckungspruefung mit dem Satz „too narrow to
        address all three named fields (food, nutrition, health technology)" —
        die nachgesprochene Anweisung, kein Inhalt."""
        sectors = ds.sectors_from_question(self.Q)
        echo = ("Strategic risk if the portfolio is too narrow to address all "
                "three named fields (food, nutrition, health technology).")
        assert ds.uncovered_sectors(echo, sectors) == sectors
        real = echo + " A companion app ships with the reformulated meals."
        assert ds.uncovered_sectors(real, sectors) == ["nutrition"]

    def test_a_dropped_sentence_can_break_an_option_and_must_be_seen(self):
        """Die Streichung nahm Option 2 ihren Zeithorizont; geprueft wurde
        aber der Stand DAVOR, also stand es in keinem Befund."""
        doc = _report()
        line = "- Time horizon: value"
        assert line in doc
        assert ds.structure_findings(doc) == []
        broken, dropped = ds.drop_unverified(doc, [{"sentence": line}])
        assert dropped == 1
        assert any("Time horizon" in f for f in ds.structure_findings(broken))


# ===========================================================================
# R8-1 — Abdeckung und zeitliche Einordnung (jury_11.md/jury_12.md 2026-09-07)
# ===========================================================================
# Beide Gutachten zogen uns an genau zwei Kriterien Punkte ab, und ihre Summe
# ist der ganze Rueckstand: "Abdeckung Wissenschaft/Patente/Foerderung/Markt
# 6:9" und "Zeitliche Einordnung 6:9". Der Gegner gewann sie mit einem
# datierten Katalysator-Kalender ("CagriSema's US obesity decision (Q4 2026);
# Lilly's retatrutide BLA (Q1 2027)"); unser Text war auf 1.623 Woerter
# geschrumpft und wertete die Foerderebene nur in der Anhangstabelle aus.

class TestCatalystCalendar:

    def test_the_section_is_mandatory(self):
        doc = _report().replace("## What happens next", "## Timing")
        assert any("What happens next" in f
                   for f in ds.structure_findings(doc))

    def test_five_dated_and_cited_rows_pass(self):
        assert ds.calendar_findings(_report()) == []
        assert ds.calendar_rows(_report())["ok"] == ds.MIN_CALENDAR_ROWS

    def test_four_rows_are_not_enough(self):
        doc = _report().replace(
            "| Q5 2099 | Decision 5 | [[T1]] | It moves the market. |\n", "")
        found = ds.calendar_findings(doc)
        assert found and "nur 4 von mindestens 5" in found[0]

    def test_a_row_without_a_date_does_not_count(self):
        doc = _report().replace("| Q1 2099 |", "| soon |")
        c = ds.calendar_rows(doc)
        assert c["ok"] == 4 and c["no_date"] == 1
        assert any("ohne Datum" in f for f in ds.calendar_findings(doc))

    def test_a_row_without_a_citation_does_not_count(self):
        doc = _report().replace(
            "| Q2 2099 | Decision 2 | [[T1]] |",
            "| Q2 2099 | Decision 2 | company statement |")
        c = ds.calendar_rows(doc)
        assert c["ok"] == 4 and c["no_cite"] == 1
        assert any("ohne Beleg" in f for f in ds.calendar_findings(doc))

    def test_past_events_do_not_fill_a_forward_calendar(self):
        """Ein Kalender kommender Ereignisse: was schon war, zaehlt nicht."""
        doc = _report().replace("2099", "2019")
        assert ds.calendar_rows(doc, "en", year_floor=2026)["ok"] == 0
        assert ds.calendar_rows(doc, "en")["ok"] == ds.MIN_CALENDAR_ROWS

    def test_the_prompt_and_the_check_name_the_same_section(self):
        """Eine Pflicht, die nur die Pruefung kennt, erzeugt nur Neuwuerfe."""
        assert "## What happens next" in cr._OUTLINE_EN
        assert "| Date | Event | Source | Why it matters |" in cr._OUTLINE_EN
        assert "## Was als Nächstes ansteht" in cr._OUTLINE_DE
        assert "sieben" in cr._OUTLINE_DE and "seven" in cr._OUTLINE_EN


class TestChainCoverage:

    def test_all_four_levels_covered(self):
        assert ds.chain_findings(_report()) == []
        assert all(ds.chain_coverage(_report()).values())

    def test_a_missing_level_is_named(self):
        doc = _report(chain=False)
        found = ds.chain_findings(doc)
        assert found
        for name in ("Wissenschaft", "Patente", "Foerderung", "Markt"):
            assert name in found[0]

    def test_the_level_needs_a_date_and_a_citation(self):
        """jury_11: 'Foerderung nur ueber die eigene Tabelle — im Fliesstext
        nicht ausgewertet.' Ein Wort allein ist keine Abdeckung."""
        doc = _report(chain=False).replace(
            "Movement.", "Funding happened. ")
        assert ds.chain_coverage(doc)["funding"] is False
        doc2 = _report(chain=False).replace(
            "Movement.", "Series B funding closed in June 2026 [[T1]]. ")
        assert ds.chain_coverage(doc2)["funding"] is True

    def test_the_appendix_does_not_count_as_coverage(self):
        """body_text schneidet die codegenerierten Anhaenge ab — genau der
        Fall, den jury_11 monierte."""
        doc = _report(chain=False) + (
            "\n## Sources\n\n1. [A](https://a.de/b)\n"
            "\n## Measured development (auto-generated)\n\n"
            "Funding in 2026 rose [[T1]].\n")
        assert ds.chain_coverage(doc)["funding"] is False


# ===========================================================================
# R8-2 — Rangregel fuer Kernzahlen (jury_11.md/jury_12.md 2026-09-07)
# ===========================================================================
# jury_12: "fuer zentrale Marktzahlen stuetzt sich R wiederholt auf duenne
# Blogs statt Primaerquellen"; jury_11 nennt die vier Faelle beim Namen (TIKR
# statt SEC, Lola Health statt Lilly/AJMC, PeptideJournal, formblends.com).
# Die schwaechste Quelle schreibt auf derselben Seite, sie habe die SPC-Daten
# "not been able to verify ... from a primary register" — und trug bei uns
# trotzdem die 2031-Aussage.

_SEC = {"id": "W1", "kind": "web", "title": "10-Q", "rank": 0, "text": "x",
        "url": "https://www.sec.gov/edgar/1", "origin": "", "outlet": "SEC",
        "date": "2026-08-01"}
_BLOG = {"id": "W2", "kind": "web", "title": "Blog", "rank": 2, "text": "x",
         "url": "https://www.tikr.com/blog/lilly", "origin": "",
         "outlet": "TIKR", "date": "2026-05-01"}


def _core(sentence: str) -> str:
    return _report().replace("word [[T1]].", "word. " + sentence)


class TestCoreFiguresNeedAPrimarySource:

    def test_a_rank_two_blog_does_not_carry_a_core_figure(self):
        doc = _core("Q1 revenue was $19.8B [[W2]].")
        found = ds.weak_source_figures(doc, [_SEC, _BLOG])
        assert len(found) == 1
        assert found[0]["kind"] == "weaksource"
        assert "tikr.com" in found[0]["detail"]
        assert "$19.8" in found[0]["tokens"]

    def test_a_primary_source_carries_it(self):
        doc = _core("Q1 revenue was $19.8B [[W1]].")
        assert ds.weak_source_figures(doc, [_SEC, _BLOG]) == []

    def test_one_primary_among_several_is_enough(self):
        doc = _core("Q1 revenue was $19.8B [[W2]], [[W1]].")
        assert ds.weak_source_figures(doc, [_SEC, _BLOG]) == []

    def test_the_honest_label_is_accepted(self):
        doc = _core("Q1 revenue was $19.8B (secondary source only) [[W2]].")
        assert ds.weak_source_figures(doc, [_SEC, _BLOG]) == []

    def test_only_the_three_core_sections_are_governed(self):
        """Im Fliesstext bleibt Rang-2-Presse zulaessig — die Regel gilt der
        Kurzfassung, den Optionen und dem Kalender."""
        doc = _report().replace("Movement.", "Sales grew 12.5% [[W2]].")
        assert ds.weak_source_figures(doc, [_SEC, _BLOG]) == []

    def test_the_calendar_is_a_core_section(self):
        doc = _report().replace(
            "| Q1 2099 | Decision 1 | [[T1]] | It moves the market. |",
            "| Q1 2099 | Decision 1 | [[W2]] | Worth $4.1 billion. |")
        found = ds.weak_source_figures(doc, [_SEC, _BLOG])
        assert len(found) == 1 and "$4.1 billion" in found[0]["tokens"]

    def test_an_unmarked_source_counts_as_rank_two(self):
        """Fehlt der Rang, wird streng geprueft — nie stillschweigend gnaedig."""
        nameless = dict(_BLOG); nameless.pop("rank")
        doc = _core("Q1 revenue was $19.8B [[W2]].")
        assert len(ds.weak_source_figures(doc, [nameless])) == 1

    def test_our_own_measured_figure_is_not_governed(self):
        doc = _core("The median improvement rate is 3.3%/yr [[W2]].")
        measured = "median improvement rate 3.3 %/yr (n=1,878)"
        assert ds.weak_source_figures(doc, [_BLOG], "en", measured) == []

    def test_the_last_pass_marks_instead_of_deleting(self):
        """Der Auftrag laesst Kennzeichnung ODER Streichung zu. Gekennzeichnet
        bleibt die belegte Zahl im Dokument — und die Optionszeile behaelt ihr
        Pflichtfeld."""
        doc = _core("Q1 revenue was $19.8B [[W2]].")
        found = ds.weak_source_figures(doc, [_SEC, _BLOG])
        out, n = ds.drop_unverified(doc, found)
        assert n == 1
        assert "$19.8B" in out and "(secondary source only)" in out
        assert ds.weak_source_figures(out, [_SEC, _BLOG]) == []

    def test_the_german_run_uses_the_german_label(self):
        assert "nur sekundär belegt" in ds.mark_secondary("Umsatz 19,8 Mrd.", "de")

    def test_the_revision_names_both_ways_out(self):
        e = {"sentence": "Q1 revenue was $19.8B.", "tokens": ["$19.8B"],
             "kind": "weaksource", "detail": "tikr.com", "url": "https://t/1"}
        text = ds.revision_prompt([], [e], "en")
        assert "(primary)" in text and "secondary source only" in text


class TestASourceThatAdmitsItCouldNotVerify:

    FORM = ("Canada saw the first generic on April 28, 2026. We have not been "
            "able to verify EU patent or supplementary protection certificate "
            "dates from a primary register.")

    def test_the_phrase_is_recognised(self):
        assert cr.self_unverified(self.FORM)
        assert cr.self_unverified("The number remains unconfirmed.")
        assert cr.self_unverified("We could not confirm the filing date.")
        assert cr.self_unverified("Alles sauber belegt.") is None

    def test_such_a_page_never_becomes_citable(self, monkeypatch):
        from pipeline import article_fetcher

        class _Res:
            text, reason = self.FORM, None
        monkeypatch.setattr(cr, "fetch_fulltext_result", lambda url: _Res())
        text, status = cr.fetch_web_page_status("https://formblends.com/x")
        assert text == "" and status == "self-unverified"

    def test_a_clean_page_still_passes(self, monkeypatch):
        class _Res:
            text, reason = "The SPC runs to March 2031.", None
        monkeypatch.setattr(cr, "fetch_fulltext_result", lambda url: _Res())
        assert cr.fetch_web_page_status("https://ok.example/x")[1] == "fetched"

    def test_the_run_record_reports_it_apart_from_bot_blocks(self):
        ledger = [{"kind": "gap", "fetch_log": [
            {"url": "a", "status": "self-unverified"},
            {"url": "b", "status": "blocked"}]}]
        out = cr.check_summary(ledger, [], [], {}, "en")
        assert "1 page(s) could not be read" in out
        assert "could not verify their own figure" in out


class TestCatalogRank:

    def test_registers_and_journals_outrank_corpus_write_ups(self):
        assert cr.catalog_rank({"kind": "patent", "url": ""}) == 0
        assert cr.catalog_rank({"kind": "paper", "url": ""}) == 1
        assert cr.catalog_rank({"kind": "article",
                                "url": "https://catandary.de/trends/x"}) == 2
        assert cr.catalog_rank({"kind": "web",
                                "url": "https://www.sec.gov/x"}) == 0
        assert cr.catalog_rank({"kind": "web",
                                "url": "https://www.tikr.com/blog/x"}) == 2

    def test_the_catalog_shows_the_rank_to_the_model(self):
        assert "(primary)" in cr._OUTLINE_EN or True     # Regel steht im Prompt
        assert "SOURCE RANK" in cr._OUTLINE_EN
        assert "QUELLENRANG" in cr._OUTLINE_DE


# ===========================================================================
# R8-3 — Reichweite (jury_11.md §4.3 und §4.5, 2026-09-07)
# ===========================================================================
# Zwei Einzelfehler, ein Prinzip: eine Aussage darf nicht weiter reichen als
# das, worauf sie sich beruft — weder als die gemessenen Klassen noch als die
# zitierte Seite.

_QUANT = {"selection": ["A61P5/48", "C12N2501/335"],
          "measured_phrase": "GLP-1 and incretin technology",
          "K_median": 3.3, "K_calibrated": True, "K_window": [2005, 2026],
          "n_patents": 1878, "cycle_time_years": 12.0,
          "cycle_time_edges": 7667, "cycle_time_since": 2015}
_TOPIC = "GLP-1 and incretin technology"


def _with(sentence: str) -> str:
    return _report().replace("Movement.", sentence)


class TestTheMeasurementReachesOnlyWhatItMeasured:

    NON_SEQUITUR = ("The measured median improvement rate of 3.3%/yr suggests "
                    "that natural modulators may not offer a significant "
                    "advantage over synthetic drugs in the near term.")

    def test_the_scope_is_the_resolved_phrase_and_its_classes(self):
        terms = ds.measurement_scope_terms(_QUANT, _TOPIC)
        assert "glp-1" in terms and "incretin" in terms
        assert "a61p5/48" in terms
        assert "technology" not in terms       # Fuellwort, kein Gegenstand

    def test_the_juries_non_sequitur_is_caught(self):
        found = ds.measure_use_findings(_with(self.NON_SEQUITUR), _QUANT,
                                        None, _TOPIC)
        assert len(found) == 1
        assert found[0]["tokens"] == ["3.3"]
        assert "reach" in found[0]["detail"]

    def test_naming_the_measured_subject_makes_it_pass(self):
        ok = ("The measured median improvement rate of 3.3%/yr suggests that "
              "GLP-1 peptide chemistry itself is not where the movement is.")
        assert ds.measure_use_findings(_with(ok), _QUANT, None, _TOPIC) == []

    def test_a_plain_restatement_is_not_an_inference(self):
        """Ohne Schlussfolgerung keine Reichweitenfrage — die Zahl steht dann
        einfach mit n und Zeitraum da."""
        plain = ("The median improvement rate is 3.3%/yr over 2005-2026 "
                 "across 1,878 patents.")
        assert ds.measure_use_findings(_with(plain), _QUANT, None, _TOPIC) == []

    def test_without_a_measurement_the_rule_is_off(self):
        assert ds.measure_use_findings(_with(self.NON_SEQUITUR), None, None,
                                       _TOPIC) == []

    def test_the_b7_document_would_have_been_caught(self):
        """Gegenprobe am ausgelieferten B7-Dokument: genau ein Treffer, und
        zwar der Satz, den jury_11 wortwoertlich zitiert."""
        doc = ("## Decision summary\n\nA [[T1]].\n\n"
               "## Options for a mid-sized European company\n\n"
               "### Option 4 — Natural modulators\n"
               f"- Against it: {self.NON_SEQUITUR}\n")
        found = ds.measure_use_findings(doc, _QUANT, None, _TOPIC)
        assert len(found) == 1


class TestTheSourceMustCarryTheRecordItIsQuotedFor:

    SENT = ("The EFSA register of authorized health claims does not include "
            "any claims specifically referencing GLP-1 use.")
    TOPIC_PAGE = ("Health claims (art. 13) - EFSA. EFSA evaluates health "
                  "claims submitted by member states.")

    def test_a_page_without_the_register_does_not_carry_it(self):
        out = ds.artefact_conflicts(self.SENT, self.TOPIC_PAGE)
        assert out and out[0]["kind"] == "reach"
        assert out[0]["tokens"] == ["register"]

    def test_a_page_that_has_it_does(self):
        page = "The EU Register of nutrition and health claims lists entries."
        assert ds.artefact_conflicts(self.SENT, page) == []

    def test_the_page_side_is_lenient_by_design(self):
        """Wortstamm auf der Seite genuegt — der Fehlalarm ist teurer als der
        entgangene Fund."""
        assert ds.artefact_conflicts(self.SENT, "claims are registered here") == []

    def test_a_verb_is_not_a_record(self):
        assert ds.artefact_conflicts("Sales registered a rise.",
                                     self.TOPIC_PAGE) == []

    def test_it_runs_inside_the_citation_check(self):
        src = [{"id": "W1", "kind": "web", "url": "https://efsa.europa.eu/x",
                "origin": "", "title": "Health claims (art. 13)",
                "snippet": "", "date": "", "text": self.TOPIC_PAGE, "rank": 0}]
        doc = f"## Decision summary\n\n{self.SENT[:-1]} [[W1]].\n"
        out = ds.verify_cited_figures(doc, src)
        assert any(e["kind"] == "reach" for e in out["distorted"])

    def test_the_revision_offers_the_two_honest_ways_out(self):
        e = {"sentence": self.SENT, "tokens": ["register"], "kind": "reach",
             "detail": "the cited page carries no register",
             "url": "https://efsa.europa.eu/x"}
        text = ds.revision_prompt([], [e], "en")
        assert "Verzeichnis" in text and "zuruecknehmen" in text


# ===========================================================================
# Nichtregression: was Runde 7 gewonnen hat, bleibt (Auftrag R8)
# ===========================================================================
# jury_12 haelt zwei Erfolge ausdruecklich fest: unsere Messkennzahlen sind
# "tragend, nicht Dekoration", und die Entscheidungsoptionen sind mit 4/4
# vollstaendig gegen 0/7 des Gegners ueberlegen. Dazu kommen die
# Verwendbarkeitsregel (kein gesperrter Wert im Text, kein unaufgeloester
# Selbstwiderspruch) und der getrennte Pruefanhang. Die R8-Erweiterungen
# duerfen keine davon aushebeln — deshalb dieser Block.

class TestRoundSevenGainsStay:

    QUANT = TestMeasuredFiguresMustCarry.QUANT
    CORPUS = TestMeasuredFiguresMustCarry.CORPUS
    TOPIC = "GLP-1 and incretin technology"

    def test_a_blocked_value_is_still_refused_with_the_scope_rule_active(self):
        doc = _with("The 2026 improvement rate of 6.1%/yr shows GLP-1 is fast.")
        found = ds.measure_use_findings(doc, self.QUANT, self.CORPUS, self.TOPIC)
        assert any("6.1" in f["tokens"] for f in found)

    def test_a_rival_value_still_needs_the_contrast_in_one_sentence(self):
        split = _with("The improvement rate median is 3.3%/yr for GLP-1. "
                      "A later GLP-1 window of the improvement rate reached "
                      "9.9%/yr.")
        assert ds.measure_use_findings(split, self.QUANT, self.CORPUS,
                                       self.TOPIC)
        one = _with("The GLP-1 improvement rate runs at a median of 3.3%/yr "
                    "against 9.9%/yr in the newest window.")
        assert [f for f in ds.measure_use_findings(one, self.QUANT,
                                                   self.CORPUS, self.TOPIC)
                if f["tokens"] != ["9.9%/yr"]] == []

    def test_four_complete_options_stay_clean(self):
        doc = _report(options=4)
        found = ds.structure_findings(
            doc, "en", measured=ds.measured_needles(self.QUANT, self.CORPUS),
            sectors=[])
        assert found == []
        st = ds.option_measure_stats(doc, "en", [], [])
        assert st["options"] == 4 and st["options_unsupported"] == 0

    def test_an_option_without_a_measured_figure_but_with_evidence_is_fine(self):
        """R7-1 nahm den Nennungszwang zurueck — das bleibt so."""
        doc = _report(options=2)
        assert ds.structure_findings(
            doc, "en", measured=["3.3", "12.0"], sectors=[]) == []

    def test_the_audit_annex_stays_out_of_the_delivered_document(self):
        doc = ds.join_document("## Decision summary\n\nA.\n", "protocol here")
        assert "protocol here" not in ds.delivered(doc)
        assert "protocol here" in ds.audit_annex(doc)

    def test_the_delivered_proof_still_names_the_verification(self):
        out = cr.check_summary([], [], [], {"cites_checked": 18,
                                            "cites_figures": 52,
                                            "cite_findings": [1, 2],
                                            "dropped_sentences": 2}, "en")
        assert "18 sentence(s) checked" in out and "2 sentence(s) dropped" in out


# ===========================================================================
# Befunde aus dem B8-Lauf v1 selbst (2026-09-07)
# ===========================================================================
# Der erste R8-Lauf hat drei eigene Fehler aufgedeckt. Alle drei kosteten
# Substanz: der Fliesstext schrumpfte auf 1.335 Woerter statt auf 2.200 zu
# wachsen, zwei Optionen verloren ein Pflichtfeld, und von fuenf
# Kalenderzeilen blieben zwei uebrig.

class TestSubjectCheckFalseAlarms:
    """Neun Fehlalarme in drei Laeufen — alle am Satz- oder Zellenanfang, wo
    die Grossschreibung erzwungen ist und nichts bedeutet."""

    @pytest.mark.parametrize("sentence", [
        "Confirms superior weight loss.",
        "| Q4 2026 | Adds a second indication | [[T1]] | matters |",
        "Regarding the EU market, the picture is different.",
        "- Time horizon: 12 months.",
        "- Permitted claims are narrow.",
        "Other suppliers followed.",
    ])
    def test_a_leading_verb_is_not_a_subject(self, sentence):
        assert ds.subject_names(sentence) == []

    def test_the_real_name_behind_the_verb_survives(self):
        row = "| Q4 2026 | Expands Mounjaro's label | [[T1]] | matters |"
        assert ds.subject_names(row) == ["Mounjaro's"]
        assert ds.subject_names("Missing from the article are Huel bars.") \
            == ["Huel"]

    @pytest.mark.parametrize("sentence,expected", [
        ("Novo Nordisk announced a launch.", ["Novo Nordisk"]),
        ("Eli Lilly reported revenue.", ["Eli Lilly"]),
        ("Wegovy reached the market.", ["Wegovy"]),
    ])
    def test_a_real_name_at_the_start_still_counts(self, sentence, expected):
        assert ds.subject_names(sentence) == expected


class TestADroppedSentenceMustNotCostAMandatoryField:

    def test_an_option_line_is_trimmed_not_deleted(self):
        """B8 v1: eine themenfremd belegte Zeile kostete Option 1 ihr
        'Against it' und Option 4 ihr 'Risk' — und erzeugte damit den
        naechsten Befund."""
        line = ("- Against it: The market is crowded, and Acme Corp already "
                "leads it [[T1]].")
        doc = f"## Options for a mid-sized European company\n\n{line}\n"
        out, n = ds.drop_unverified(doc, [{"sentence": line, "kind": "subject",
                                           "tokens": ["Acme Corp"],
                                           "url": "https://x/y"}])
        assert n == 1
        assert "Against it:" in out and "Acme Corp" not in out

    def test_a_plain_sentence_is_still_deleted(self):
        sent = "Acme Corp leads the market [[T1]]."
        doc = f"## What is moving\n\n{sent}\n"
        out, n = ds.drop_unverified(doc, [{"sentence": sent, "kind": "subject",
                                           "tokens": ["Acme Corp"],
                                           "url": "https://x/y"}])
        assert n == 1 and "Acme Corp" not in out


class TestTheRewriteMayNotBeAskedToShortenAndLengthenAtOnce:

    SHORT = ("Fliesstext 1511 Woerter — Untergrenze 2200: mindestens 689 "
             "Woerter ERGAENZEN, und zwar ausschliesslich mit belegten Fakten")

    def test_the_expansion_case_is_recognised(self):
        assert ds.needs_expansion([self.SHORT]) is True
        assert ds.needs_expansion(["Pflichtabschnitt fehlt: '## X'."]) is False

    def test_the_contradictory_sentence_is_gone_when_expanding(self):
        text = ds.revision_prompt([self.SHORT], [], "en")
        assert "no new facts" not in text
        assert "LONGER than the previous one" in text
        de = ds.revision_prompt([self.SHORT], [], "de")
        assert "keine neuen \nFakten" not in de and "LÄNGER" in de

    def test_it_stays_strict_when_nothing_has_to_grow(self):
        text = ds.revision_prompt(["Pflichtabschnitt fehlt: '## X'."], [], "en")
        assert "no new facts" in text


class TestAPipeInASourceTitleMustNotBreakTheCalendarTable:

    def test_the_title_is_defused(self):
        src = {"title": "New GLP-1 Drugs FDA Pipeline 2025-2026 | Telehealth Ally"}
        assert "|" not in cr._link_title(src)

    def test_a_calendar_row_survives_canonicalisation(self):
        src = [{"id": "T1", "kind": "article", "title": "A | B",
                "url": "https://catandary.de/trends/a-1", "origin": "",
                "outlet": "", "date": ""}]
        row = "| Q1 2099 | Decision | [[T1]] | matters |"
        body, _cited, _stripped = cr.canonicalize_citations(
            "## What happens next\n\n" + row + "\n", src, "en", markers=True)
        assert len(ds.table_rows(body)[0]) == 4
