"""Korpus-API/-Dienst, Entwürfe und Entwurfsblätter (Owner 2026-10-04,
docs/plan_field_research_2026-10-04.md). Ohne Postgres, ohne Netz, ohne GPU.

Was hier festgenagelt wird:
  * ein maschineller Entwurf erscheint nur im Entwurfsblatt (Wasserzeichen, *-ENTWURF,
    nie im Export) und trägt dort, dass er maschinell ist;
  * „status: rewritten" auf einem kaum geänderten Entwurf wird abgelehnt;
  * Modelltext wird escaped (kein rohes HTML, keine javascript:-Links ins PDF);
  * der Retriever für gpt-researcher liefert nie einen Treffer ohne Text
    (sonst kratzte gpt-researcher die Seite selbst);
  * der Korpus-Dienst verlangt das Token und weist Browser-Aufrufe ab.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from pipeline import corpus_api, corpus_service, field_drafts, field_research as fres
from pipeline import field_watch as fw
from pipeline import field_watch_render as fr

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------
def _sheet(reading: str = "", regulatory: str = "") -> dict:
    years = list(range(1990, 2027))
    ser = {t: [{"y": y, "n": 1, "per10k": None} for y in years] for t in fw.TIERS}
    return {"field": {"name": "Feld", "name_en": "Field", "slug": "feld", "terms": ["x"], "cpc": [],
                      "reading": reading, "regulatory": regulatory},
            "measured_on": "2026-10-04", "series": ser, "takeoff": {t: None for t in fw.TIERS},
            "first": {t: 1990 for t in fw.TIERS}, "totals": {t: 37 for t in fw.TIERS}, "science_from": 2010,
            "market_from": 2020, "patents_5y": 0, "patents_with_assignee_5y": 0, "assignees": [], "subclasses": [],
            "landmarks": [], "offices": [], "top_works": [], "quant": None}


def _week() -> dict:
    tiers = fw.TIERS
    qs = [f"{y}-Q{q}" for y in (2023, 2024, 2025, 2026) for q in (1, 2, 3, 4)][3:15]
    f = {"name": "Feld", "slug": "feld", "terms": ["x"], "cpc": [],
         "week": {t: {"n": 9 if t == "market" else 0, "median4": 3 if t == "market" else 0} for t in tiers},
         "weekly": {t: [1] * 8 for t in tiers}, "quarterly": {t: [{"q": q, "n": 1, "per10k": 1.0} for q in qs] for t in tiers},
         "top": {t: [] for t in tiers}, "actors": [], "actors_total": 0, "actors_new_week": 0, "sources_90d": 3,
         "signals_90d": 9, "patents_window": 0, "top_source": None, "nests": []}
    return {"week": "2026-W39", "week_start": "2026-09-21", "week_end": "2026-09-27", "measured_on": "2026-09-28",
            "weeks": [f"2026-W{w}" for w in range(32, 40)], "quarters": qs, "panel_size": {}, "fields": [f]}


MACHINE = """## Geltende Rechtsakte
- Die Verordnung (EU) 2015/2283 regelt neuartige Lebensmittel [VO 2015/2283](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32015R2283).
- Verordnung (EG) Nr. 1333/2008 [VO 1333/2008](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32011R1130).
<script>alert(1)</script> [klick](javascript:alert(1))"""
SOURCES = [{"url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32015R2283"},
           {"url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32011R1130"}]


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(field_drafts, "OUT_DIR", tmp_path)
    return tmp_path


def _save(out_dir, section="regulatory", body=MACHINE, week=None):
    return field_drafts.save_draft("kunde", "feld", section, body, {"model": "test-model"},
                                   {"sources": SOURCES}, week=week)


def _set_status(path: Path, status: str, body: str | None = None):
    raw = path.read_text(encoding="utf-8").replace("status: draft", f"status: {status}")
    if body is not None:
        head, _, _ = raw.partition("\n---\n")
        raw = head + "\n---\n\n" + body + "\n"
    path.write_text(raw, encoding="utf-8")


# ---------------------------------------------------------------------------
# Entwürfe
# ---------------------------------------------------------------------------
class TestDrafts:
    def test_roundtrip_and_sidecar(self, out_dir):
        p = _save(out_dir)
        d = field_drafts.parse(p)
        assert d["status"] == "draft" and d["section"] == "regulatory" and d["model"] == "test-model"
        assert d["sidecar"]["machine_text"].startswith("## Geltende")
        assert d["sidecar"]["retention_until"] > "2031"            # 1825-Tage-Regel
        assert _save(out_dir) != p                                  # nie überschreiben

    def test_draft_only_with_include_drafts(self, out_dir):
        _save(out_dir)
        assert field_drafts.load_section("kunde", "feld", "regulatory", include_drafts=False) is None
        assert field_drafts.load_section("kunde", "feld", "regulatory", include_drafts=True)["status"] == "draft"

    def test_rewritten_but_unchanged_is_refused(self, out_dir):
        p = _save(out_dir)
        _set_status(p, "rewritten")
        with pytest.raises(field_drafts.DraftNotRewritten):
            field_drafts.load_section("kunde", "feld", "regulatory", include_drafts=False)

    def test_really_rewritten_is_used(self, out_dir):
        p = _save(out_dir)
        _set_status(p, "rewritten", "## Rechtsrahmen\nFür das Feld gilt im Kern die Novel-Food-Verordnung; "
                                    "Zulassungen dauern in der Praxis länger als die Frist. Eigene Prüfung des Analysten.")
        d = field_drafts.load_section("kunde", "feld", "regulatory", include_drafts=False)
        assert d["status"] == "rewritten"

    def test_week_notes_are_week_specific(self, out_dir):
        _save(out_dir, "movers", "Notiz W39", week="2026-W39")
        assert field_drafts.load_section("kunde", "feld", "movers", True, week="2026-W39")["body"] == "Notiz W39"
        assert field_drafts.load_section("kunde", "feld", "movers", True, week="2026-W40") is None

    def test_review_hints_find_wrong_celex_and_foreign_links(self):
        hints = field_drafts.review_hints(MACHINE + "\n- x [y](https://elsewhere.example/z)", SOURCES)
        assert any("1333/2008" in h and "32011R1130" in h for h in hints)
        assert any("elsewhere.example" in h for h in hints)
        assert not any("32015R2283" in h for h in hints)

    def test_purge_respects_retention(self, out_dir):
        p = _save(out_dir)
        old = time.time() - (field_drafts.RETENTION_DAYS + 1) * 86400
        os.utime(p, (old, old))
        assert field_drafts.purge(apply=False) == [str(p)]
        assert p.exists()
        field_drafts.purge(apply=True)
        assert not p.exists() and p.with_suffix(".json").exists()

    def test_markdown_is_escaped(self):
        h = field_drafts.md_to_html(MACHINE)
        assert "<script>" not in h and "&lt;script&gt;" in h
        assert 'href="javascript' not in h
        assert '<a href="https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32015R2283">' in h
        assert "<h4>Geltende Rechtsakte</h4>" in h and "<ul>" in h


# ---------------------------------------------------------------------------
# Blätter
# ---------------------------------------------------------------------------
class TestSheets:
    def test_sheet_without_drafts_is_unchanged_in_kind(self):
        html = fr.render_sheet(_sheet(), None, "Kunde")
        assert "ENTWURF" not in html and "Anhang A" not in html and 'class="wm"' not in html
        assert "kein Sprachmodell beteiligt" in html

    def test_draft_sheet_is_marked_everywhere(self, out_dir):
        _save(out_dir)
        dr = field_drafts.load_section("kunde", "feld", "regulatory", include_drafts=True)
        html = fr.render_sheet(_sheet(), None, "Kunde", drafts={"regulatory": dr})
        assert 'class="wm"' in html and "nicht zur Auslieferung" in html
        assert "Entwurf · maschinell" in html and "Anhang A · Rechtsrahmen" in html and "Anhang B" in html
        assert "Anhang A ist ein maschineller ENTWURF" in html
        assert "32011R1130" in html and "passt nicht" in html     # Prüfhinweis im Anhang B
        assert "<script>" not in html

    def test_rewritten_sheet_says_who_wrote_it(self, out_dir):
        p = _save(out_dir)
        _set_status(p, "rewritten", "Eigener Text des Analysten mit [Quelle](https://eur-lex.europa.eu/x).")
        dr = field_drafts.load_section("kunde", "feld", "regulatory", include_drafts=False)
        html = fr.render_sheet(_sheet(), None, "Kunde", drafts={"regulatory": dr})
        assert 'class="wm"' not in html and "Anhang B" not in html
        assert "auf Grundlage eines maschinellen Rechercheentwurfs" in html
        assert "der Rechtsrahmen in Anhang A ist der einzige geschriebene Teil" in html

    def test_yaml_text_beats_draft_and_reads_as_analyst(self):
        html = fr.render_sheet(_sheet(reading="Absatz.", regulatory="## Recht\nText."), None, "Kunde")
        assert "Abschnitt 7 ist vom Analysten geschrieben und verantwortet." in html
        assert "Anhang A ist vom Analysten geschrieben und verantwortet." in html
        assert "geschriebene Teile sind die Einordnung in Abschnitt 7 und der Rechtsrahmen in Anhang A" in html

    def test_week_with_draft_note(self, out_dir):
        _save(out_dir, "movers", "Hinter dem Anstieg steht [eine Meldung](https://x.example/a).", week="2026-W39")
        n = field_drafts.load_section("kunde", "feld", "movers", True, week="2026-W39")
        html = fr.render_week(_week(), "Kunde", notes={"feld": n})
        assert "Was hinter der Bewegung steckt" in html and 'class="wm"' in html
        assert "maschinelle ENTWÜRFE" in html and "kein Sprachmodell hat Text erzeugt" not in html
        plain = fr.render_week(_week(), "Kunde")
        assert "kein Sprachmodell hat Text erzeugt" in plain and 'class="wm"' not in plain

    def test_export_skips_draft_files(self, tmp_path, monkeypatch):
        import scripts.field_watch as cli
        monkeypatch.setattr(cli, "OUT_DIR", tmp_path)
        d = tmp_path / "kunde"
        d.mkdir()
        (d / "2026-W39.pdf").write_bytes(b"%PDF final")
        (d / "sheet-feld-2026-10-04-ENTWURF.pdf").write_bytes(b"%PDF draft")
        site = cli.run_export({"slug": "kunde", "customer": "Kunde"})
        assert (site / "2026-W39.pdf").exists()
        assert not (site / "sheet-feld-2026-10-04-ENTWURF.pdf").exists()
        assert "ENTWURF" not in (site / "index.html").read_text()


# ---------------------------------------------------------------------------
# Aufträge (pure)
# ---------------------------------------------------------------------------
class TestSpecs:
    def test_movers_threshold(self):
        f = _week()["fields"][0]
        assert [m["tiers"] for m in fres.movers([f])] == [["market"]]
        f["week"]["market"] = {"n": 4, "median4": 0}
        assert fres.movers([f]) == []

    def test_regulatory_spec_is_web_only_with_legal_domains(self):
        f = fw.validate_customer({"customer": "K", "fields": [{"name": "F", "terms": ["a"], "regulatory_keywords": ["novel food"]}]})["fields"][0]
        s = fres.regulatory_spec(f, {"backend": "local"}, eurlex_block="EUR-Lex …")
        assert s["scope"] == "web" and "eur-lex.europa.eu" in s["domains"]
        assert s["context_word_budget"] == fres.LOCAL_CONTEXT_WORDS and "ENTWURF" in s["custom_prompt"]
        assert f["regulatory_keywords"] == ["novel food"]

    def test_parse_setup_tolerates_prose(self):
        d = fres.parse_setup('Here: {"terms": ["Oat Milk", "oat milk", "x"], "cpc_hints": ["A23C11/10"], "notes": "n"} done')
        assert d["terms"] == ["oat milk"] and d["cpc_hints"] == ["A23C11/10"]
        assert fres.parse_setup("no json")["terms"] == []

    def test_setup_yaml_comments_out_weak_terms(self):
        y = fres.setup_yaml("oat milk", [{"term": "oat milk", "market": 300, "science": 10, "patent": 5, "funding": 1},
                                         {"term": "oat drink", "market": 1, "science": 0, "patent": 0}], [])
        assert '- "oat milk"' in y and '# - "oat drink"' in y
        y = fres.setup_yaml("plant-based cheese", [{"term": "plant-based cheese", "market": 189, "science": 113, "patent": 76},
                                                   {"term": "coconut oil", "market": 8, "science": 5753, "patent": 2645}], [])
        assert '# - "coconut oil"   # ZU BREIT?' in y and '      - "plant-based cheese"' in y


# ---------------------------------------------------------------------------
# Korpus-API / -Dienst
# ---------------------------------------------------------------------------
class TestCorpusApi:
    def test_rrf_and_tsquery(self):
        assert [i for i, _ in corpus_api.rrf_merge([1, 2, 3], [3, 4])][:2] == [3, 1]
        assert "phraseto" in corpus_api.tsquery_sql("precision fermentation")
        assert "websearch" in corpus_api.tsquery_sql('"precision fermentation" OR whey')
        assert "websearch" in corpus_api.tsquery_sql("battery")

    @pytest.mark.parametrize("url", ["http://127.0.0.1:8090/v1/models", "http://localhost/x", "file:///etc/passwd",
                                     "http://10.1.2.3/", "http://100.94.255.57/", "ftp://example.org/"])
    def test_check_url_refuses_non_public(self, url):
        with pytest.raises(corpus_api.ToolError):
            corpus_api.check_url(url)

    def test_cellar_url_and_domains(self):
        assert corpus_api.cellar_url("https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32015R2283") \
            == "https://publications.europa.eu/resource/celex/32015R2283"
        assert corpus_api.cellar_url("https://example.org/?uri=CELEX:32015R2283") is None
        assert corpus_api.domain_matches("https://www.efsa.europa.eu/x", ["efsa.europa.eu"])
        assert not corpus_api.domain_matches("https://efsa.europa.eu.evil.com/x", ["efsa.europa.eu"])

    def test_dates_validated(self):
        assert corpus_api._date("2025", "since") == "2025-01-01"
        with pytest.raises(corpus_api.ToolError):
            corpus_api._date("2025; DROP TABLE trends", "since")

    def test_retriever_never_returns_items_without_text(self, monkeypatch):
        monkeypatch.setattr(corpus_api, "_corpus_documents", lambda *a: [{"url": "https://a", "raw_content": "x" * 300}])
        monkeypatch.setattr(corpus_api, "_web_documents", lambda *a: [{"url": "https://b", "raw_content": ""},
                                                                       {"url": "https://a", "raw_content": "dup"}])
        assert [d["url"] for d in corpus_api.gptr_retrieve("q", scope="both")] == ["https://a"]

    def test_call_tool_rejects_unknown_arguments_and_tools(self):
        with pytest.raises(corpus_api.ToolError, match="unknown argument"):
            corpus_service.call_tool("term_counts", {"terms": ["a"], "sql": "x"})
        with pytest.raises(corpus_api.ToolError, match="unknown tool"):
            corpus_service.call_tool("drop_everything", {})


@pytest.fixture
def service():
    corpus_service.Handler.token = "s" * 24
    srv = ThreadingHTTPServer(("127.0.0.1", 0), corpus_service.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


class TestCorpusService:
    def test_token_required(self, service):
        assert _get(service + "/health")[0] == 403
        assert _get(service + "/health", {"X-Corpus-Token": "wrong" * 5})[0] == 403
        code, body = _get(service + "/health", {"X-Corpus-Token": "s" * 24})
        assert code == 200 and "search_signals" in body["tools"]

    def test_browser_origin_is_refused_even_with_token(self, service):
        assert _get(service + "/health?token=" + "s" * 24, {"Origin": "https://evil.example"})[0] == 403

    def test_token_redacted_in_log(self, caplog):
        h = corpus_service.Handler.__new__(corpus_service.Handler)
        h.client_address = ("127.0.0.1", 1)
        with caplog.at_level("INFO", logger="corpus_service"):
            h.log_message('"%s" %s', "GET /gptr/retrieve?token=SECRET123&query=x", 200)
        assert "SECRET123" not in caplog.text and "token=***" in caplog.text


def test_research_venv_stays_out_of_the_cron_venv():
    """gpt-researcher/MCP gehören in ~/venvs/catandary-research, nie in requirements.txt (Cron-venv)."""
    req = (ROOT / "requirements.txt").read_text()
    assert "gpt-researcher" not in req and "\nmcp" not in req
    assert "gpt-researcher==" in (ROOT / "requirements-research.txt").read_text()


def test_reading_numbers_must_come_from_the_measurement():
    meas = "Patente: gesamt 500, Take-off 2017; K Median 3.6; Anmelder ARLA (62); 1.234 Werke"
    body = ("Patente: 500 seit 2017, K 3,6, ARLA 62, 1.234 Werke [Q](https://x.example/2025/99). "
            "Der Markt lag 2025 bei 7,4 Mrd. USD und wächst um 13 %.")
    assert field_drafts.ungrounded_numbers(body, meas) == ["13", "2025", "7.4"]
    hints = field_drafts.review_hints(body, [{"url": "https://x.example/2025/99"}], meas)
    assert any("nicht aus der Messung" in h and "7.4" in h for h in hints)


def test_pseudo_links_render_as_text_and_forecasts_are_flagged():
    h = field_drafts.md_to_html("Laut [Catandary-Messung](Catandary-Messung) stieg es.")
    assert "Laut Catandary-Messung stieg es." in h and "](" not in h
    hints = field_drafts.review_hints("Im Jahr 2026 wird erwartet, dass X wächst.", [])
    assert any("Prognose-Formulierung" in x for x in hints)
