"""Newsletter-Deep-Dive (#96 Phase 1) — Kontrakt ohne GPU/Modell.

Geprüft: deterministische Themenwahl (Anteils-Delta + Varianz-Regel), das
Ehrlichkeits-Gate über Audit/Endkontrolle, die Nachprüfung des Kondensats
(Links nur aus dem Katalog, Zahlen nur aus dem Dossier, Wortfenster),
Speichern/Decodieren von deep_dive auf SQLite (inkl. nachträglichem ALTER),
der /analysis-Draft (draft: true) und die Degradationspfade des Orchestrators.
"""
from contextlib import nullcontext
from datetime import date
import json
import os

import pytest

import pipeline.db as pdb
from pipeline import dossier_orders as orders_mod
from pipeline import newsletter_generator as ng
from pipeline.db import get_connection
import scripts.newsletter_deep_dive as dd

TEST_DB = "/tmp/catandary_test_deep_dive.db"

# 2026-W35 = 2026-08-24 … 2026-08-30; Vorwochen W31–W34 (ab 2026-07-27).
YEAR, WEEK = 2026, 35
_PRIOR = [date.fromisocalendar(YEAR, WEEK - 4 + w, 3).isoformat() for w in range(4)]


@pytest.fixture(autouse=True)
def own_db(monkeypatch, tmp_path):
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE trends (id INTEGER PRIMARY KEY, title_en TEXT, slug TEXT, "
            "status TEXT, mega_trend TEXT, created_at TEXT, trend_score REAL, "
            "source_name TEXT, source_url TEXT, summary_en TEXT)")
        # Tabelle im VOR-#96-Zustand (ohne deep_dive) → ensure_deep_dive_column
        # muss die Spalte nachziehen, so wie auf der Live-DB.
        conn.execute(
            "CREATE TABLE newsletter_editions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "year INTEGER NOT NULL, week INTEGER NOT NULL, editorial TEXT, "
            "vertical_summaries TEXT, mega_trend_radar TEXT, trend_refs TEXT, "
            "total_signals INTEGER DEFAULT 0, created_at TEXT, UNIQUE(year, week))")
    orders_mod.ensure_schema()
    monkeypatch.setattr(dd, "LAST_PATH", tmp_path / "last.json")
    monkeypatch.setattr(dd, "ANALYSES_DIR", tmp_path / "analyses")
    monkeypatch.setattr(dd, "_llama_unit_active", lambda: False)
    monkeypatch.setattr(dd.gpu_handover, "content_gen_on_llamacpp",
                        lambda *a, **k: nullcontext())
    monkeypatch.setattr(dd.gpu_handover, "_served_model", lambda: None)
    yield
    pdb.DATABASE_PATH = old


def _add_trends(rows):
    with get_connection() as conn:
        for i, (theme, created, title) in enumerate(rows, 1):
            conn.execute(
                "INSERT INTO trends (title_en, slug, status, mega_trend, created_at, "
                "trend_score, source_name, source_url) VALUES (?, ?, 'published', ?, ?, ?, "
                "'Outlet', ?)",
                (title, f"{title.lower().replace(' ', '-')}-{i}", theme, created,
                 100 - i, f"https://example.org/{i}"))


def _add_edition(year, week, deep_dive=None):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO newsletter_editions (year, week, editorial, total_signals) "
            "VALUES (?, ?, 'ed', 10)", (year, week))
    if deep_dive is not None:
        dd.ensure_deep_dive_column()
        with get_connection() as conn:
            conn.execute("UPDATE newsletter_editions SET deep_dive = ? WHERE year = ? AND week = ?",
                         (json.dumps(deep_dive), year, week))


# ---- Themenwahl -----------------------------------------------------------

class TestThemeChoice:
    def test_ranks_by_share_delta_and_excludes_recent_themes(self):
        rows = []
        # Thema A: 20/Woche in den Vorwochen, 20 in der Woche → stabil
        for w in range(4):
            rows += [("a", f"{_PRIOR[w]}T10:00:00", f"A prior {w} {k}") for k in range(20)]
        rows += [("a", "2026-08-25T10:00:00", f"A week {k}") for k in range(20)]
        # Thema B: 5/Woche vorher, 20 in der Woche → stärkstes Delta
        for w in range(4):
            rows += [("b", f"{_PRIOR[w]}T10:00:00", f"B prior {w} {k}") for k in range(5)]
        rows += [("b", "2026-08-26T10:00:00", f"B week {k}") for k in range(20)]
        # Thema C: nur 3 Signale in der Woche → unter dem Mindestvolumen
        rows += [("c", "2026-08-27T10:00:00", f"C week {k}") for k in range(3)]
        _add_trends(rows)
        with get_connection() as conn:
            ranking = dd.theme_deltas(conn, YEAR, WEEK)
        # C hat keine Vorwochen-Basis → „emerging" ganz oben im Ranking, fällt
        # aber in pick_theme am Mindestvolumen; dann B (stärkstes Delta), dann A.
        assert [r["key"] for r in ranking] == ["c", "b", "a"]
        assert ranking[0]["emerging"] is True
        b = ranking[1]
        assert b["week_n"] == 20 and b["prior_n"] == 20 and b["prior_weekly_mean"] == 5.0
        assert b["rel_change"] > 0.5
        assert dd.pick_theme(ranking, excluded=[])["key"] == "b"
        # Varianz-Regel: B war schon dran → A
        assert dd.pick_theme(ranking, excluded=["b"])["key"] == "a"
        # C fällt am Mindestvolumen, nichts übrig → None
        assert dd.pick_theme(ranking, excluded=["a", "b"]) is None

    def test_recent_deep_dive_themes_reads_previous_editions_only(self):
        _add_edition(2026, 32, {"theme": "x", "dry_run": True})
        _add_edition(2026, 33, {"theme": "y", "dry_run": True})
        _add_edition(2026, 34, None)
        _add_edition(2026, 35, {"theme": "z"})          # die Ziel-Edition selbst
        _add_edition(2026, 36, {"theme": "later"})      # danach — zählt nicht
        with get_connection() as conn:
            assert dd.recent_deep_dive_themes(conn, 2026, 35) == ["y", "x"]

    def test_question_anchors_the_week(self):
        theme = {"key": "b", "name_en": "Theme B", "description": "about B", "week_n": 20}
        sig = [{"title_en": "Big launch", "source_name": "Outlet"}]
        q = dd.build_question(theme, sig, YEAR, WEEK)
        assert "Theme B" in q and "2026-08-24 to 2026-08-30" in q
        assert '"Big launch" (Outlet)' in q and "20 published signals" in q


# ---- Gate -----------------------------------------------------------------

def _result(supported=9, contradictions=1, links=2, stripped=0):
    srcs = [{"id": f"T{i}", "kind": "article", "title": f"Src {i}",
             "url": f"https://catandary.de/trends/src-{i}", "outlet": "O", "date": "2026-08-25",
             "snippet": "x"} for i in range(1, 4)]
    body = "# Report\n\nClaim one [Src 1](https://catandary.de/trends/src-1)."
    if links >= 2:
        body += " Claim two [Src 2](https://catandary.de/trends/src-2)."
    report = body + "\n\n---\n\n## Sources\n\n1. [Src 1](https://catandary.de/trends/src-1)\n" \
                    "\n---\n\n## Research coverage (auto-generated)\n\n1. gap → 3 paper(s)\n"
    return {
        "report": report, "sources": srcs, "cited": ["T1", "T2"][:max(links, 1)],
        "stripped_citations": stripped, "ledger": [{"gap": "g"}],
        "audit": {"supported": [{"claim": f"c{i}", "source_ids": ["T1"]} for i in range(supported)],
                  "inferences": [], "contradictions": ["x"] * contradictions, "missing": ["m"]},
        "kinds": {"article": 3, "signal": 0, "paper": 0, "patent": 0, "web": 0},
        "model": "Qwen3.8-27B", "finished_at": "2026-09-04T10:00:00+00:00",
    }


class TestGate:
    def test_passes_on_start_values(self):
        g = dd.evaluate_gates(_result(), {"ungrounded": [], "open_questions": 1, "words": 12})
        assert g["passed"] is True and g["reasons"] == []
        assert g["audit"]["supported"] == 9 and g["audit"]["canonical_rate"] == 1.0
        assert g["audit"]["links_in_body"] == 2      # Quellenliste/Anhang nicht mitgezählt

    def test_fails_below_supported_threshold(self):
        g = dd.evaluate_gates(_result(supported=7), {"ungrounded": []})
        assert g["gates"]["supported_claims"] is False and g["passed"] is False
        assert any("7 supported" in r for r in g["reasons"])

    def test_fails_on_contradictions_and_ungrounded(self):
        g = dd.evaluate_gates(_result(contradictions=3), {"ungrounded": ["42%"]})
        assert g["gates"]["contradictions"] is False
        assert g["gates"]["dossier_grounded"] is False
        assert g["audit"]["dossier_ungrounded"] == 1

    def test_non_canonical_link_in_body_fails(self):
        r = _result()
        r["report"] = r["report"].replace("https://catandary.de/trends/src-2",
                                          "https://invented.example/x")
        g = dd.evaluate_gates(r, {"ungrounded": []})
        assert g["gates"]["citations_canonical"] is False
        assert g["audit"]["canonical_rate"] == 0.5


# ---- Kondensat-Nachprüfung --------------------------------------------------

def _prose(n_words: int, links: list[str]) -> str:
    """n Wörter Prosa in 3 Absätzen, mit den Links verteilt."""
    words = ["word"] * n_words
    text = " ".join(words)
    paras = [text[: len(text) // 3], text[len(text) // 3: 2 * len(text) // 3],
             text[2 * len(text) // 3:]]
    for i, l in enumerate(links):
        paras[i % 3] += f" {l}."
    return "\n\n".join(paras)


class TestCondensateCheck:
    SRC = [{"id": f"T{i}", "kind": k, "title": f"Src {i}", "url": f"https://s.example/{i}",
            "origin": f"https://origin.example/{i}", "outlet": "O", "date": "", "snippet": ""}
           for i, k in enumerate(("article", "signal", "paper", "patent", "web"), 1)]
    MATERIAL = "The pilot line reached 84% retention after 350 cycles in 2025."

    def test_ok_text_passes(self):
        links = [f"[Src {i}](https://s.example/{i})" for i in range(1, 5)]
        text = _prose(320, links) + " Retention was 84% after 350 cycles."
        v = dd.verify_condensate(text, self.SRC, self.MATERIAL)
        assert v["ok"] is True, v["reasons"]
        assert {c["url"] for c in v["citations"]} == {f"https://s.example/{i}" for i in range(1, 5)}
        assert v["paragraphs"] == 3

    def test_origin_url_is_rewritten_to_canonical(self):
        links = ["[Src 2](https://origin.example/2)"] + \
                [f"[Src {i}](https://s.example/{i})" for i in (1, 3, 4)]
        v = dd.verify_condensate(_prose(320, links), self.SRC, self.MATERIAL)
        assert v["ok"] is True
        assert "https://origin.example/2" not in v["text"]
        assert "https://s.example/2" in v["text"]

    def test_unknown_link_is_stripped_and_fails(self):
        links = [f"[Src {i}](https://s.example/{i})" for i in range(1, 5)] + \
                ["[Made up](https://invented.example/page)"]
        v = dd.verify_condensate(_prose(320, links), self.SRC, self.MATERIAL)
        assert v["checks"]["links_in_catalog"] is False and v["ok"] is False
        assert v["unknown_links"] == ["https://invented.example/page"]
        assert "invented.example" not in v["text"] and "Made up" in v["text"]

    def test_figure_not_in_dossier_fails(self):
        links = [f"[Src {i}](https://s.example/{i})" for i in range(1, 5)]
        text = _prose(320, links) + " Output rose to 12,000 units."
        v = dd.verify_condensate(text, self.SRC, self.MATERIAL)
        assert v["checks"]["figures_in_dossier"] is False
        assert "12,000" in v["ungrounded"]

    def test_word_window_and_citation_count(self):
        v = dd.verify_condensate(_prose(120, ["[Src 1](https://s.example/1)"]),
                                 self.SRC, self.MATERIAL)
        assert v["checks"]["words_in_range"] is False
        assert v["checks"]["enough_citations"] is False
        assert v["ok"] is False

    def test_condense_retries_until_check_passes(self):
        good_links = [f"[Src {i}](https://s.example/{i})" for i in range(1, 5)]
        outputs = iter([_prose(120, good_links),                 # zu kurz
                        "## Title\n\n" + _prose(330, good_links)])  # Heading wird entfernt → ok
        calls = []

        def fake_chat(model, prompt, system=None, temperature=0.0, seed=None, max_tokens=None):
            calls.append(seed)
            return next(outputs)
        res = {"report": self.MATERIAL, "sources": self.SRC, "cited": [s["id"] for s in self.SRC]}
        theme = {"key": "t", "name_en": "T", "description": "", "week_n": 20}
        c = dd.condense(theme, YEAR, WEEK, [], res, chat=fake_chat, model="m")
        assert c["ok"] is True and c["attempt"] == 2
        assert calls == [dd.CONDENSE_SEED, dd.CONDENSE_SEED + 1]
        assert not c["text"].startswith("#")


# ---- Speichern / Draft ------------------------------------------------------

class TestStorage:
    def test_column_added_once_and_payload_roundtrips(self):
        assert dd.ensure_deep_dive_column() is True
        assert dd.ensure_deep_dive_column() is False
        _add_edition(YEAR, WEEK)
        dd.save_deep_dive(YEAR, WEEK, {"theme": "b", "dry_run": True, "gate_passed": False})
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM newsletter_editions WHERE week = ?", (WEEK,)).fetchone()
        ed = ng.decode_edition_row(row)
        assert ed["deep_dive"] == {"theme": "b", "dry_run": True, "gate_passed": False}

    def test_saving_requires_the_edition(self):
        dd.ensure_deep_dive_column()
        with pytest.raises(RuntimeError, match="does not exist"):
            dd.save_deep_dive(YEAR, 40, {"theme": "b"})

    def test_regenerating_the_edition_keeps_the_deep_dive(self):
        dd.ensure_deep_dive_column()
        _add_edition(YEAR, WEEK, {"theme": "b"})
        ng.save_newsletter_edition({"year": YEAR, "week": WEEK, "editorial": "new",
                                    "vertical_summaries": {}, "mega_trend_radar": [],
                                    "trend_refs": {}, "total_signals": 3})
        with get_connection() as conn:
            row = dict(conn.execute("SELECT editorial, deep_dive FROM newsletter_editions "
                                    "WHERE week = ?", (WEEK,)).fetchone())
        assert row["editorial"] == "new"
        assert json.loads(row["deep_dive"])["theme"] == "b"

    def test_analysis_draft_is_a_draft_with_frontmatter(self, tmp_path):
        payload = {"year": YEAR, "week": WEEK, "theme": "b", "theme_name": "Theme B",
                   "body_md": "First sentence [Src 1](https://s.example/1). Second.",
                   "dossier_slug": "newsletter-deepdive-2026-w35", "dossier_version": 1,
                   "generated_at": "2026-09-04T10:00:00+00:00", "corpus_asof": "2026-09-04",
                   "gate_passed": False, "dry_run": True,
                   "gates": {"supported_claims": True, "condensate": False},
                   "audit": {"supported": 9, "contradictions": 1, "cited": 5, "sources": 20,
                             "dossier_ungrounded": 0},
                   "models": {"research": "Qwen3.8-27B", "condense": "gemma"}}
        path = dd.write_analysis_draft(payload, {"report": "# Dossier\n\nBody."},
                                       root=tmp_path / "analyses")
        text = path.read_text()
        assert path.name == "newsletter-deepdive-2026-w35.md"
        head = text.split("---")[1]
        assert "draft: true" in head
        assert "slug: newsletter-deepdive-2026-w35" in head
        assert 'title: "Deep Dive — Theme B, week 35/2026"' in head
        assert "corpus_asof: 2026-09-04" in head
        assert "First sentence" in text and "# Dossier" in text
        assert "NOT REVIEWED" in text


# ---- Orchestrator (Degradation) ---------------------------------------------

def _seed_week_b():
    rows = []
    for w in range(4):
        rows += [("b", f"{_PRIOR[w]}T10:00:00", f"B prior {w} {k}") for k in range(5)]
    rows += [("b", "2026-08-26T10:00:00", f"B week {k}") for k in range(20)]
    _add_trends(rows)
    _add_edition(YEAR, WEEK)


class TestRun:
    def test_requires_the_edition(self):
        with pytest.raises(SystemExit, match="does not exist"):
            dd.run(YEAR, WEEK, research=lambda oid, b: None)

    def test_no_theme_leaves_edition_with_a_note(self):
        _add_edition(YEAR, WEEK)
        p = dd.run(YEAR, WEEK, research=lambda oid, b: pytest.fail("no research expected"))
        assert p["status"] == "no_theme" and p["gate_passed"] is False
        assert json.loads(dd.LAST_PATH.read_text())["status"] == "no_theme"

    def test_research_failure_degrades(self, monkeypatch):
        _seed_week_b()

        def failing(oid, budget):
            orders_mod.mark_running(oid)
            orders_mod.mark_failed(oid, "DeepDiveTimeout: time budget of 20 min exceeded")
            return {"rc": 2, "error": "DeepDiveTimeout: time budget of 20 min exceeded",
                    "status": "failed", "order": orders_mod.get_order(oid), "seconds": 1.0}
        called = []
        monkeypatch.setattr(dd, "condense", lambda *a, **k: called.append(1))
        p = dd.run(YEAR, WEEK, research=failing)
        assert p["status"] == "research_failed" and "time budget" in p["error"]
        assert p["dossier_slug"] == "newsletter-deepdive-2026-w35"
        assert called == []
        with get_connection() as conn:
            row = dict(conn.execute("SELECT deep_dive FROM newsletter_editions WHERE week = ?",
                                    (WEEK,)).fetchone())
        stored = json.loads(row["deep_dive"])
        assert stored["dry_run"] is True and stored["gate_passed"] is False
        assert stored["theme"] == "b" and stored["body_md"] is None
        # Auftrag im Desk sichtbar als failed
        assert orders_mod.get_order(p["order_id"])["status"] == "failed"
        # Draft trotzdem (mit Hinweis), Wächter-JSON
        assert (dd.ANALYSES_DIR / "newsletter-deepdive-2026-w35.md").exists()
        assert json.loads(dd.LAST_PATH.read_text())["status"] == "research_failed"

    def test_dry_run_end_to_end_with_fakes(self, monkeypatch):
        _seed_week_b()
        res = _result()

        def fake_research(oid, budget):
            orders_mod.mark_running(oid)
            o = orders_mod.get_order(oid)
            from scripts.corpus_research import save_dossier
            v = save_dossier(o["slug"], o["topic"], o["question"], res["report"], res)
            orders_mod.mark_review(oid, v, {"ok": True, "ungrounded": [], "findings": [],
                                            "stripped_citations": 0, "cited": 2, "sources": 3,
                                            "open_questions": 1, "words": 12, "seconds": 3.0})
            return {"rc": 0, "error": None, "status": "review",
                    "order": orders_mod.get_order(oid), "seconds": 3.0}

        links = [f"[Src {i}](https://catandary.de/trends/src-{i})" for i in (1, 2, 1, 2)]

        def fake_condense(theme, year, week, signals, result, chat=None, model=None, attempts=3):
            return dd.verify_condensate(_prose(320, links), dd.cited_sources(result),
                                        dd.grounding_material(result, signals)) | {"attempts": []}
        monkeypatch.setattr(dd.gpu_handover, "_served_model", lambda: "./models/gemma.gguf")
        p = dd.run(YEAR, WEEK, research=fake_research, condense_fn=fake_condense)
        assert p["dossier_gate"] is True
        # 2 distinkte Belege < MIN_CITATIONS → Kondensat-Check verfehlt → gate_failed
        assert p["gates"]["condensate"] is False and p["gate_passed"] is False
        assert p["status"] == "gate_failed" and p["dry_run"] is True
        assert p["models"] == {"research": "Qwen3.8-27B", "condense": "gemma.gguf"}
        assert p["dossier_version"] == 1 and p["corpus_asof"] == "2026-09-04"
        assert len(p["citations"]) == 2 and p["citations"][0]["kind"] == "article"
        with get_connection() as conn:
            row = dict(conn.execute("SELECT deep_dive FROM newsletter_editions WHERE week = ?",
                                    (WEEK,)).fetchone())
        stored = json.loads(row["deep_dive"])
        assert stored["body_md"].count("https://catandary.de/trends/src-1") == 2
        assert stored["theme_choice"]["ranking"][0]["key"] == "b"
        assert orders_mod.get_order(p["order_id"])["status"] == "review"
        assert (dd.ANALYSES_DIR / "newsletter-deepdive-2026-w35.md").read_text().count("draft: true") == 1

    def test_apply_skips_condensate_when_dossier_gate_fails(self, monkeypatch):
        _seed_week_b()
        res = _result(supported=3)

        def fake_research(oid, budget):
            orders_mod.mark_running(oid)
            o = orders_mod.get_order(oid)
            from scripts.corpus_research import save_dossier
            v = save_dossier(o["slug"], o["topic"], o["question"], res["report"], res)
            orders_mod.mark_review(oid, v, {"ok": True, "ungrounded": []})
            return {"rc": 0, "error": None, "status": "review",
                    "order": orders_mod.get_order(oid), "seconds": 1.0}
        p = dd.run(YEAR, WEEK, dry_run=False, research=fake_research,
                   condense_fn=lambda *a, **k: pytest.fail("condensate must be skipped"))
        assert p["status"] == "gate_failed" and p["dry_run"] is False
        assert p["body_md"] is None and p["gates"]["condensate"] is False


# ---- Morgen-Mail-Zeile (scripts/review_notify.py) ---------------------------

class TestMorningMailLine:
    def test_line_carries_gate_and_audit(self):
        from scripts import review_notify as rn
        d = {"year": 2026, "week": 35, "status": "gate_failed", "dry_run": True,
             "theme": "b", "theme_name": "Theme B", "words": 410,
             "audit": {"supported": 6, "contradictions": 1, "dossier_ungrounded": 0},
             "gates": {"supported_claims": False, "condensate": True},
             "gate_passed": False, "dossier_slug": "newsletter-deepdive-2026-w35",
             "dossier_version": 1}
        line = rn._deep_dive_line(d)
        assert line.startswith("Newsletter deep dive (dry-run) W35/2026: gate_failed — theme Theme B")
        assert "6 supported / 1 contradictions / 0 ungrounded" in line
        assert "gate failed: supported_claims" in line and "v1" in line

    def test_stats_reads_fresh_file_only(self, monkeypatch, tmp_path):
        from scripts import review_notify as rn
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data").mkdir()
        assert rn.deep_dive_stats() is None
        (tmp_path / "data" / "newsletter_deep_dive_last.json").write_text(
            json.dumps({"date": "2020-01-01T00:00:00+00:00", "status": "ok"}))
        assert rn.deep_dive_stats() is None          # zu alt
        from datetime import datetime, timezone
        (tmp_path / "data" / "newsletter_deep_dive_last.json").write_text(
            json.dumps({"date": datetime.now(timezone.utc).isoformat(), "status": "ok"}))
        assert rn.deep_dive_stats()["status"] == "ok"


# ---- Register: keine Beleglage-Meta-Rede (Owner 2026-09-04) -----------------

class TestMetaTalk:
    SRC = TestCondensateCheck.SRC
    MATERIAL = TestCondensateCheck.MATERIAL
    LINKS = [f"[Src {i}](https://s.example/{i})" for i in range(1, 5)]

    @pytest.mark.parametrize("sentence", [
        "Several signals regarding cybersecurity remain unverified.",
        "These claims lack validation from internal research or patent corpora.",
        "The corpus cannot provide details on algorithmic transparency audits.",
        "The timeline remains unknown.",
        "Attacks on solar parks are not covered by the evidence.",
        "There is no data in the corpus on this.",
        "The corpus does not resolve the discrepancy.",
        "Three open questions remain after the audit.",
        "Reports are single-source claims from external media with no corroborating evidence.",
    ])
    def test_meta_talk_is_rejected(self, sentence):
        text = _prose(320, self.LINKS) + " " + sentence
        v = dd.verify_condensate(text, self.SRC, self.MATERIAL)
        assert v["checks"]["no_meta_talk"] is False and v["ok"] is False
        assert v["meta_talk"] and any("meta-talk" in r for r in v["reasons"])

    def test_plain_reporting_passes(self):
        text = _prose(320, self.LINKS) + (
            " One report puts the settlement at 84% while another cites 350 cycles;"
            " both figures come from the sources cited.")
        v = dd.verify_condensate(text, self.SRC, self.MATERIAL)
        assert v["checks"]["no_meta_talk"] is True and v["ok"] is True

    def test_condense_retries_on_meta_talk_then_fails_gate(self):
        bad = _prose(320, self.LINKS) + " The corpus cannot confirm the attacks."
        outputs = iter([bad, bad, bad])
        calls = []

        def fake_chat(model, prompt, system=None, temperature=0.0, seed=None, max_tokens=None):
            calls.append(seed)
            return next(outputs)
        res = {"report": self.MATERIAL, "sources": self.SRC, "cited": [s["id"] for s in self.SRC],
               "audit": {"supported": [{"claim": "Retention was 84%.", "source_ids": ["T1"]}],
                         "contradictions": ["X vs Y"], "missing": ["gap one"]}}
        theme = {"key": "t", "name_en": "T", "description": "", "week_n": 20}
        c = dd.condense(theme, YEAR, WEEK, [], res, chat=fake_chat, model="m")
        assert len(calls) == dd.CONDENSE_ATTEMPTS == 3       # 1 Versuch + 2 Retries
        assert c["ok"] is False and c["checks"]["no_meta_talk"] is False


class TestPromptContext:
    def test_prompt_holds_supported_claims_and_catalog_only(self):
        src = TestCondensateCheck.SRC
        res = {"sources": src, "cited": [s["id"] for s in src],
               "report": "## Open questions\n\nThe corpus cannot answer the timeline.",
               "audit": {"supported": [{"claim": "Meta agreed to a $17 billion settlement.",
                                        "source_ids": ["T1", "T9"]}],
                         "contradictions": ["T1 says $17bn while T2 says $18bn — CONTRA-MARK"],
                         "missing": ["Historical timeline — MISSING-MARK"]}}
        theme = {"key": "t", "name_en": "Theme", "description": "d", "week_n": 20}
        claims = dd.supported_claims(res)
        assert [s["id"] for s in claims[0]["sources"]] == ["T1"]   # unbekannte IDs fallen weg
        prompt = dd.build_condense_prompt(theme, YEAR, WEEK, [], claims, dd.cited_sources(res))
        assert "Meta agreed to a $17 billion settlement." in prompt
        assert "[article] [Src 1](https://s.example/1)" in prompt
        assert "CONTRA-MARK" not in prompt and "MISSING-MARK" not in prompt
        assert "Open questions" not in prompt and "cannot answer" not in prompt
        assert "never pad" in prompt
        assert "unverified" in dd.CONDENSE_SYSTEM and "silence, not commentary" in dd.CONDENSE_SYSTEM


class TestFromDossier:
    def test_parse_ref(self):
        assert dd.parse_dossier_ref("newsletter-deepdive-2026-w35@3") == ("newsletter-deepdive-2026-w35", 3)
        with pytest.raises(SystemExit):
            dd.parse_dossier_ref("nope")

    def test_regenerates_without_research(self, monkeypatch):
        _seed_week_b()
        res = _result()
        from scripts.corpus_research import save_dossier
        oid = orders_mod.create_order("Theme B", slug="newsletter-deepdive-2026-w35")
        orders_mod.mark_running(oid)
        v = save_dossier("newsletter-deepdive-2026-w35", "Theme B", "q", res["report"], res)
        orders_mod.mark_review(oid, v, {"ok": False, "ungrounded": ["24531336"]})  # veraltete Endkontrolle
        dd.ensure_deep_dive_column()
        dd.save_deep_dive(YEAR, WEEK, {"theme": "b", "theme_name": "B", "dry_run": True,
                                       "body_md": "OLD TEXT", "web_steps": 0,
                                       "research_seconds": 200.0, "order_id": oid})
        links = [f"[Src {i}](https://catandary.de/trends/src-{i})" for i in (1, 2, 1, 2)]

        def fake_condense(theme, year, week, signals, result, chat=None, model=None, attempts=3):
            return dd.verify_condensate(_prose(320, links), dd.cited_sources(result),
                                        dd.grounding_material(result, signals)) | {"attempts": []}
        monkeypatch.setattr(dd.gpu_handover, "_served_model", lambda: "./models/gemma.gguf")
        research_called = []
        monkeypatch.setattr(dd, "run_research", lambda *a, **k: research_called.append(1))
        p = dd.run_from_dossier(YEAR, WEEK, "newsletter-deepdive-2026-w35", v,
                                condense_fn=fake_condense)
        assert research_called == []
        assert p["regenerated_from"] == f"newsletter-deepdive-2026-w35@{v}"
        assert p["order_id"] == oid and p["research_seconds"] == 200.0
        assert p["theme"] == "b" and p["dossier_version"] == v
        # Endkontrolle neu gerechnet: die veraltete Slug-ID-Meldung ist weg
        assert p["audit"]["dossier_ungrounded"] == 0 and p["gates"]["dossier_grounded"] is True
        with get_connection() as conn:
            row = dict(conn.execute("SELECT deep_dive FROM newsletter_editions WHERE week = ?",
                                    (WEEK,)).fetchone())
        stored = json.loads(row["deep_dive"])
        assert "OLD TEXT" not in stored["body_md"] and stored["dry_run"] is True
        assert stored["regenerated_from"].endswith(f"@{v}")
        assert dd.LAST_PATH.exists()

    def test_missing_dossier_is_a_clear_error(self):
        _add_edition(YEAR, WEEK)
        with pytest.raises(SystemExit, match="does not exist"):
            dd.run_from_dossier(YEAR, WEEK, "newsletter-deepdive-2026-w35", 9)
