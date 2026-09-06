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
        return [{"id": f"W{i}", "trend_id": None, "kind": "web",
                 "title": f"Hit {i}", "url": f"{url}{i}", "origin": f"{url}{i}",
                 "outlet": "outlet", "vertical": "", "date": "2026-01-01",
                 "snippet": "snippet", "fetched": False} for i in range(n)]

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
        monkeypatch.setattr(cr, "fetch_web_page", lambda u: "page text 2031")
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
        monkeypatch.setattr(cr, "fetch_web_page", lambda u: "")
        sources, notes, ledger = [], [], []
        added, record = cr.sweep_regulatory("topic", sources, set(), notes, ledger)
        assert added == 0
        assert record.count("nothing usable") == len(cr.REGULATORY_PATTERNS)
        assert len(ledger) == len(cr.REGULATORY_PATTERNS)

    def test_a_snippet_never_carries_a_citation(self, monkeypatch):
        """Verpflichtend gefetcht: was nicht gelesen wurde, ist nicht zitierbar."""
        monkeypatch.setattr(cr, "brave_search",
                            lambda q, n=6: self._hits("https://law.example/", 1))
        monkeypatch.setattr(cr, "fetch_web_page", lambda u: "")
        sources = []
        cr.sweep_regulatory("topic", sources, set(), [], [])
        assert sources and not any(s.get("fetched") for s in sources)
        citable = [s for s in sources
                   if s["kind"] not in ("web", "legal") or s.get("fetched")]
        assert citable == []

    def test_fetch_budget_is_bounded(self, monkeypatch):
        monkeypatch.setattr(cr, "brave_search", self._per_query())
        monkeypatch.setattr(cr, "fetch_web_page", lambda u: "text")
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
    monkeypatch.setattr(cr, "fetch_web_page", lambda url: LEGAL_PAGE)

    out = cr.run("What should we do?", max_steps=1, max_sources=8,
                 retrieval="fts", per_query=2, web_steps=1, max_web_sources=2,
                 topic="GLP-1 and incretin technology", measure=True,
                 seed_sources=[dict(SEED)], seed_notes=["seed"])

    # 1. Rechts-Sweep hat einen eigenen Katalogbereich gefuellt
    assert out["kinds"]["legal"] == len(cr.REGULATORY_PATTERNS)
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
    # 4. der Coverage-Anhang weist die Beleg-Verifikation aus
    assert "Verification of web citations" in out["report"]


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
        monkeypatch.setattr(cr, "fetch_web_page", lambda url: "")   # nie lesbar
        out = cr.run("Q", max_steps=1, max_sources=8, retrieval="fts",
                     per_query=2, web_steps=1, max_web_sources=2, topic="GLP-1",
                     measure=True, seed_sources=[dict(SEED)], seed_notes=["seed"])
        assert out["kinds"]["legal"] == len(cr.REGULATORY_PATTERNS)
        assert "NEVER READ IN FULL" in seen[0]
        for s in out["sources"]:
            if s["kind"] in ("web", "legal") and not s.get("fetched"):
                assert s["id"] in seen[0]
