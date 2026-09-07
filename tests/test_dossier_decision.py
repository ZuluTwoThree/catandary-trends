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


def _report(summary_words: int = 40, options: int = 2,
            drop_field: str | None = None, filler: int = 0) -> str:
    body = ["# Dossier", "", "## Decision summary", "",
            " ".join(["word"] * summary_words) + " [[T1]].", "",
            "## What is moving", "", "Movement." + " filler" * filler, "",
            "## Regulatory and IP status", "", "Nothing found.", "",
            "## What the evidence does not support", "", "Nothing.", "",
            "## Options for a mid-sized European company", ""]
    for i in range(1, options + 1):
        body += [f"### Option {i} — Something", ""]
        for label in ds.OPTION_LABELS["en"]:
            if label == drop_field and i == 1:
                continue
            body.append(f"- {label}: value")
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
            # lang genug, damit der Kurz-Guard (>= 300 Woerter) den Neuwurf
            # nicht als Abbruch verwirft
            return _report(filler=400)
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

    def test_short_report_is_advisory_not_a_rewrite(self):
        short = _report()
        assert ds.structure_findings(short) == []      # kein Neuwurf-Grund
        adv = ds.length_advisory(short)
        assert adv and str(ds.BODY_WORDS_MIN) in adv[0]
        long_enough = _report(filler=ds.BODY_WORDS_MIN)
        assert ds.length_advisory(long_enough) == []

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
        return lambda q, count=6: [
            {"id": f"W{i}", "trend_id": None, "kind": "web",
             "title": f"Topic hit {i}",
             "url": f"https://m{abs(hash(q)) % 9973}.example/{i}",
             "origin": "", "outlet": "o", "vertical": "", "date": "2026-01-01",
             "snippet": "incretin GLP-1 semaglutide", "fetched": False}
            for i in range(n)]

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
        assert cr.REG_MAX_FETCH == 12 and cr.MKT_MAX_FETCH == 12
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
