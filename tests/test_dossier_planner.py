"""Stufe 3 des Dossier-Agent-Plans (2026-09-19): VOI-Planer, Fast-Dubletten,
Anfrage-Schablonen (`dossier_query_stats`), Rechtstexte artikelweise, zwei
Seiten je Hersteller-Aussage, Leser-Urteil an den Pflichtpunkten.

Alles ohne DB (ausser SQLite in tmp), ohne Netz, ohne GPU.
"""
from __future__ import annotations

import importlib
import inspect
import random

import pytest

from pipeline import dossier_planner as dp
from pipeline import dossier_query_stats as qs
from pipeline import dossier_structure as ds
from pipeline import legal_text
from scripts import corpus_research as cr


# ==========================================================================
# 1. VOI-Planer
# ==========================================================================

def _planner(**kw):
    gaps = dp.make_gaps([("plan", "plan step one"), ("audit", "audit gap"),
                         ("must", "must-answer item"), ("pattern", "regulatory pattern")])
    return dp.Planner(gaps, phase="web", budget=kw.pop("budget", 20),
                      gain_floor=kw.pop("gain_floor", 0.15), **kw)


def test_argmax_takes_the_must_answer_item_first():
    p = _planner()
    d = p.next_action()
    assert d is not None and d.gap.kind == "must" and d.action == "search"
    # 3.0 · (1 − 0) · 0.5 / 1
    assert d.score == pytest.approx(1.5)
    assert p.trace[-1]["decision"] == "act" and p.trace[-1]["gap"] == "must:2"


def test_coverage_lowers_the_score_and_saturates_at_three():
    p = _planner()
    g = p.find("must:2")
    p.record(g, "search", admitted=2)
    assert g.coverage == pytest.approx(2 / 3)
    s, _a, _c = p.score(g, "search")
    assert s == pytest.approx(3.0 * (1 / 3) * 0.5)
    p.record(g, "search", admitted=5)
    assert g.coverage == 1.0 and g not in p.open_gaps()


def test_fetch_is_suggested_for_unread_hits_and_costs_two():
    p = _planner()
    g = p.find("audit:1")
    p.record(g, "search", admitted=1, unread_delta=1)
    s, action, cost = p.score(g)
    assert action == "fetch" and cost == 2.0
    assert s == pytest.approx(2.0 * (2 / 3) * dp.FETCH_P / 2.0)


def test_per_gap_budget_moves_the_planner_on():
    p = _planner()
    g = p.find("must:2")
    for _ in range(dp.PER_GAP_BUDGET):
        assert p.next_action().gap is g
        p.record(g, "search", admitted=0)          # nichts gefunden, Deckung bleibt 0
    d = p.next_action()
    assert d is not None and d.gap.kind == "audit"   # must ist ausgeschoepft


def test_stop_when_the_best_gain_falls_below_the_floor():
    p = _planner(gain_floor=0.6)
    order = []
    while (d := p.next_action()) is not None:
        order.append(d.gap.kind)
        p.record(d.gap, "search", admitted=3)      # jede Suche saettigt ihre Luecke
    # plan (0,5) und pattern (0,35) liegen unter 0,6 → nie dran; must 1,5 und audit 1,0 schon
    assert order == ["must", "audit"]
    assert p.trace[-1]["decision"] == "stop" and p.trace[-1]["reason"] == "gain below floor"


def test_stop_when_the_budget_is_exhausted():
    p = _planner(budget=2)
    assert p.next_action() is not None
    p.record(p.gaps[2], "search")
    assert p.next_action() is not None
    p.record(p.gaps[2], "search")
    assert p.should_stop() and p.next_action() is None
    assert p.trace[-1]["reason"] == "budget"


def test_finish_is_accepted_only_when_the_planner_agrees():
    p = _planner(budget=3)
    assert p.accept_finish() is False
    p.record(p.gaps[2], "finish", note="refused")
    assert p.gaps[2].declined == 1
    p.record(p.gaps[2], "search", admitted=3)
    p.record(p.gaps[1], "search", admitted=3)
    assert p.accept_finish() is True                 # Budget aus


def test_gain_floor_from_env(monkeypatch):
    monkeypatch.setenv("DOSSIER_VOI_MIN_GAIN", "0.33")
    assert dp.min_gain() == pytest.approx(0.33)
    monkeypatch.setenv("DOSSIER_VOI_MIN_GAIN", "abc")
    assert dp.min_gain() == dp.DEFAULT_MIN_GAIN


def test_action_budget_from_brief_minutes():
    assert dp.action_budget("web", 14, None) == 14
    assert dp.action_budget("web", 14, 30) == 14
    assert dp.action_budget("web", 14, 60) == 28
    assert dp.action_budget("corpus", 6, 15) == 3
    assert dp.action_budget("web", 14, 1) == dp.MIN_ACTIONS
    assert dp.action_budget("web", 14, 1000) == dp.MAX_ACTIONS
    assert dp.action_budget("web", 14, "nonsense") == 14


def test_prior_hosts_raise_p_success_and_stats_feed_it():
    rows = {"must": [{"template": "{topic} {instrument} obligations", "n_used": 8, "n_admitted": 6}]}
    p = dp.Planner(dp.make_gaps([("must", "x")]), phase="web", budget=5, gain_floor=0.1,
                   stats=lambda kind: rows.get(kind, []), prior_hosts=["docs.example"])
    g = p.gaps[0]
    assert g.p_success == pytest.approx(7 / 10 + dp.PRIOR_HOST_BONUS)
    assert g.template == "{topic} {instrument} obligations"
    assert "worked before" in p.prompt_line(p.next_action())


def test_thompson_sampling_is_deterministic_with_a_seed_and_prefers_the_better_template():
    rows = [{"template": "good", "n_used": 20, "n_admitted": 16},
            {"template": "bad", "n_used": 20, "n_admitted": 2}]
    a = qs.p_success(rows, rng=random.Random(7))
    b = qs.p_success(rows, rng=random.Random(7))
    assert a == b
    wins = sum(1 for i in range(200) if qs.p_success(rows, rng=random.Random(i))[1] == "good")
    assert wins > 190
    # eine Zeile: Beta-Mittel, keine Ziehung
    assert qs.p_success(rows[:1]) == (pytest.approx(17 / 22), "good")
    assert qs.p_success([]) == (0.5, None)


def test_summary_carries_the_trace_for_result_voi():
    p = _planner(budget=2)
    d = p.next_action()
    p.record(d.gap, "search", admitted=1)
    s = p.summary()
    assert s["phase"] == "web" and s["used"] == 1 and s["budget"] == 2
    assert [t["decision"] for t in s["trace"]] == ["act", "result"]
    assert s["gaps"][2]["coverage"] == 0.33          # gerundet fuer das Protokoll


# ==========================================================================
# 2. Fast-Dubletten
# ==========================================================================

def test_jaccard_and_would_skip():
    assert dp.jaccard("proxmox subscription basic price", "proxmox basic subscription price") == 1.0
    assert dp.jaccard("a b c d e", "a b c d f") == pytest.approx(4 / 6)
    skipped = dp.would_skip_jaccard(["vsphere 8 end of general support",
                                     "vsphere 8 end of general support date",   # 5/6 = 0,83
                                     "proxmox subscription tiers pricing"])
    assert skipped == [1]


def test_dedup_jaccard_without_embedder():
    d = dp.QueryDedup(embed=None)
    assert d.check_and_add("EU Data Act cloud switching obligations", "web") is False
    assert d.check_and_add("EU Data Act cloud switching obligation", "web") is False   # 5/7 = 0,71
    assert d.check_and_add("obligations switching cloud Act Data EU", "web") is True   # gleiche Tokens
    assert d.summary()["skipped"] == 1 and d.summary()["skips"][0]["method"] == "jaccard"


def test_dedup_jaccard_threshold_is_0_8():
    d = dp.QueryDedup(embed=None)
    d.add("a b c d e f g h i j")
    dup, method, sim, _near = d.check("a b c d e f g h i k")      # 9/11 = 0,82
    assert dup and method == "jaccard" and sim >= 0.8
    dup, _m, sim, _n = d.check("a b c d e f g x y z")            # 7/13
    assert not dup


def test_dedup_uses_the_embedder_when_available():
    vecs = {"first query": [1.0, 0.0, 0.0], "almost the same": [0.99, 0.14, 0.0],
            "something else": [0.0, 1.0, 0.0]}
    d = dp.QueryDedup(embed=lambda q: vecs[q])
    assert d.check_and_add("first query") is False
    assert d.check_and_add("almost the same") is True        # cos ≈ 0,99, Jaccard 0
    assert d.check_and_add("something else") is False
    assert d.skips[0]["method"] == "embedding" and d.skips[0]["similarity"] >= 0.9


def test_dedup_falls_back_to_jaccard_when_the_embedder_dies():
    def boom(q):
        raise RuntimeError("embedder down")
    d = dp.QueryDedup(embed=boom)
    assert d.check_and_add("proxmox subscription basic price") is False
    assert d.method == "jaccard" and d.embed is None
    assert d.check_and_add("proxmox basic subscription price") is True
    assert d.skips[0]["method"] == "jaccard"


# ==========================================================================
# 3. Schablonen und dossier_query_stats
# ==========================================================================

class TestTemplates:
    def test_docstring_example(self):
        t = qs.normalise_template("EU Data Act cloud switching obligations 2027",
                                  topic_terms=["cloud"], instruments=["EU Data Act"])
        assert t == "{instrument} {topic} switching obligation {year}"

    def test_entities_and_plural_and_repeated_placeholders(self):
        t = qs.normalise_template("Proxmox VE Broadcom VMware licensing changes 2024 2025",
                                  topic_terms=["virtualization", "VMware"],
                                  entities=["Proxmox VE", "Broadcom"])
        assert t == "{entity} {topic} licensing change {year}"

    def test_generalises_across_fields(self):
        a = qs.normalise_template("semaglutide EMA approval date", topic_terms=["semaglutide"],
                                  instruments=["EMA"])
        b = qs.normalise_template("Proxmox BSI approval date", topic_terms=["Proxmox"],
                                  instruments=["BSI"])
        assert a == b == "{topic} {instrument} approval date"

    def test_empty_and_numbers(self):
        assert qs.normalise_template("") == ""
        assert qs.normalise_template("16 cores per CPU minimum") == "{n} core per cpu minimum"


class TestQueryStatsDb:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
        monkeypatch.setenv("DATABASE_URL", "")
        from pipeline import db as db_mod
        importlib.reload(db_mod)
        importlib.reload(qs)
        from pipeline.db import get_connection
        with get_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS dossier_query_stats")
        qs.ensure_schema()
        yield

    def _result(self):
        return {
            "ledger": [{"gap": "must item", "kind": "must", "web_queries": ["EU Data Act cloud switching 2027"]},
                       {"gap": "audit gap", "kind": "gap", "web_queries": []}],
            "web": {"steps": [
                {"step": 1, "action": "search", "gap": 0, "argument": "EU Data Act cloud switching 2027",
                 "hits": 6, "new": 2},
                {"step": 2, "action": "fetch", "argument": "https://x/1", "ok": True},
                {"step": 3, "action": "search", "gap": 1, "argument": "proxmox pricing subscription",
                 "hits": 5, "new": 1},
                {"step": "auto", "action": "search", "gap": 1, "argument": "proxmox pricing subscription",
                 "hits": 5, "new": 0}]},
            "trace": [{"step": 1, "action": "search", "argument": "cloud hypervisor market", "hits": 6,
                       "new": 6, "kind": "plan"}],
            "sources": [
                {"id": "T900000000", "kind": "web", "url": "https://x/1", "gap": 0, "fetched": True,
                 "query": "EU Data Act cloud switching 2027"},
                {"id": "T900000001", "kind": "web", "url": "https://x/2", "gap": 0, "fetched": False},
                {"id": "T900000002", "kind": "web", "url": "https://x/3", "gap": 1, "fetched": True},
            ],
            "cited": ["T900000000"],
        }

    def test_run_query_stats_and_upsert(self):
        rows = qs.run_query_stats(self._result(), topic_terms=["cloud"], instruments=["EU Data Act"])
        must = rows[("must", "{instrument} {topic} switching {year}")]
        # n_admitted zaehlt LAEUFE mit >= 1 aufgenommener Quelle (2 aufgenommen → 1 Erfolg)
        assert must == {"n_used": 1, "n_hits": 6, "n_admitted": 1, "n_read": 1, "n_cited": 1}
        audit = rows[("audit", "proxmox pricing subscription")]
        # zweimal gelaufen (Agent + Coverage), Quelle x/3 ohne `query` → ueber den gap-Index
        assert audit["n_used"] == 2 and audit["n_admitted"] == 1 and audit["n_read"] == 1
        assert rows[("plan", "{topic} hypervisor market")]["n_admitted"] == 1
        assert qs.upsert(rows) == 3
        assert qs.upsert(rows) == 3                     # Addition, kein Fehler
        got = {r["template"]: r for r in qs.list_stats("must")}
        assert got["{instrument} {topic} switching {year}"]["n_used"] == 2
        assert qs.beta_mean(2, 1) == pytest.approx(2 / 4)   # (1+1)/(2+2)
        assert qs.templates_for("audit")[0]["template"] == "proxmox pricing subscription"

    def test_update_from_run_never_raises(self, monkeypatch):
        assert qs.update_from_run(self._result()) == 3
        monkeypatch.setattr(qs, "upsert", lambda rows: (_ for _ in ()).throw(RuntimeError("db gone")))
        assert qs.update_from_run(self._result()) == 0

    def test_backfill_over_stored_runs(self):
        runs = [{"id": 1, "slug": "a", "version": 1, "topic": "cloud virtualization",
                 "result": self._result()},
                {"id": 2, "slug": "b", "version": 1, "topic": "cloud virtualization",
                 "result": {**self._result(), "profile": {"regulators": ["EU Data Act"]}}}]
        out = qs.backfill(runs)
        assert out["runs"] == 2 and out["queries"] == 8
        assert out["kinds"]["must"] >= 1 and out["kinds"]["plan"] == 1


# ==========================================================================
# 4. Rechtstexte artikelweise
# ==========================================================================

ACT = """REGULATION (EU) 2023/2854 on harmonised rules on fair access to and use of data

Article 1
Subject matter and scope
1. This Regulation lays down harmonised rules on making data available. It applies to everyone.

Article 2
Definitions
For the purposes of this Regulation, the following definitions apply:
(8) 'data processing service' means a digital service that enables ubiquitous and on-demand
network access to a shared pool of configurable, scalable and elastic computing resources.

Article 3
Obligation to make product data accessible
Products shall be designed so that data are accessible to the user by default.

Article 23
Removing obstacles to effective switching
Providers of data processing services shall take the measures to enable customers to switch
to a data processing service of another provider.

Article 29
Gradual withdrawal of switching charges
From 12 January 2027, providers of data processing services shall not impose any switching
charges on the customer for the switching process.

Article 31
Specific regime for certain data processing services
The obligations laid down in Article 23 shall not apply to data processing services the
majority of main features of which have been custom-built to accommodate the specific needs
of an individual customer.

Article 50
Entry into force and application
This Regulation shall apply from 12 September 2025.
"""


class TestLegalText:
    def test_hosts(self):
        assert legal_text.is_legal_host("https://eur-lex.europa.eu/eli/reg/2023/2854/oj")
        assert legal_text.is_legal_host("https://www.gesetze-im-internet.de/bdsg_2018/__64.html")
        assert legal_text.is_legal_host("https://www.legislation.gov.uk/ukpga/2018/12")
        assert not legal_text.is_legal_host("https://www.proxmox.com/en/pricing")
        assert not legal_text.is_legal_host("https://eur-lex.example/x")

    def test_split_finds_the_articles(self):
        arts = legal_text.split_articles(ACT)
        assert [a.label for a in arts] == ["Article 1", "Article 2", "Article 3", "Article 23",
                                           "Article 29", "Article 31", "Article 50"]
        assert arts[1].is_definitions and arts[1].title == "Definitions"
        assert arts[3].title == "Removing obstacles to effective switching"

    def test_slice_keeps_definitions_and_matching_articles_only(self):
        text, kept = legal_text.slice_articles(ACT, ["switching", "custom-built"])
        assert kept == ["Article 2 (Definitions)", "Article 23", "Article 29", "Article 31"]
        assert "custom-built" in text and "'data processing service' means" in text
        assert "Obligation to make product data accessible" not in text
        assert "Entry into force" not in text
        assert text.index("Article 2") < text.index("Article 23") < text.index("Article 31")

    def test_slice_respects_the_limit(self):
        text, kept = legal_text.slice_articles(ACT, ["switching"], limit=420)
        assert len(text) <= 420 and kept and kept[0].startswith("Article 2")

    def test_no_structure_means_the_opening(self):
        text, kept = legal_text.slice_articles("plain prose " * 50, ["x"], limit=100)
        assert kept == [] and len(text) == 100

    def test_fetcher_takes_max_chars(self):
        from pipeline import article_fetcher
        sig = inspect.signature(article_fetcher.fetch_fulltext_result)
        assert sig.parameters["max_chars"].default is None
        assert legal_text.LEGAL_KEEP_CHARS == article_fetcher.MAX_TEXT_CHARS

    def test_fetch_page_for_gap_reads_eur_lex_article_wise(self, monkeypatch, tmp_path):
        from pipeline import web_cache
        from pipeline.article_fetcher import FetchResult
        monkeypatch.setenv("WEB_CACHE_PATH", str(tmp_path / "c.sqlite"))
        monkeypatch.setattr(web_cache, "cache_get", lambda kind, key: None)
        monkeypatch.setattr(web_cache, "cache_put", lambda kind, key, value: True)
        seen = {}

        def fake_fetch(url, **kw):
            seen["max_chars"] = kw.get("max_chars")
            return FetchResult(ACT)
        monkeypatch.setattr(cr, "fetch_fulltext_result", fake_fetch)
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda url: pytest.fail("legal host must not use the 3.600-char path"))
        info: dict = {}
        text, status = cr.fetch_page_for_gap("https://eur-lex.europa.eu/eli/reg/2023/2854/oj",
                                             terms=["switching charges"], info=info)
        assert status == "fetched" and seen["max_chars"] == legal_text.LEGAL_FETCH_CHARS
        assert info["legal_articles"] == ["Article 2 (Definitions)", "Article 23", "Article 29"]
        assert "Article 31" not in text and "12 January 2027" in text

    def test_other_hosts_are_untouched(self, monkeypatch):
        monkeypatch.setattr(cr, "fetch_web_page_status", lambda url: ("body", "fetched"))
        assert cr.fetch_page_for_gap("https://www.proxmox.com/x", terms=["a"]) == ("body", "fetched")


# ==========================================================================
# 5. Zwei Seiten je Hersteller-Aussage
# ==========================================================================

PRICING = {"id": "W1", "kind": "web", "url": "https://www.proxmox.com/en/proxmox-virtual-environment/pricing",
           "title": "Proxmox VE pricing", "fetched": True, "rank": 2, "host": "proxmox.com",
           "text": "Basic 370 EUR/year per socket. No-subscription use is for evaluation."}
FAQ = {"id": "W2", "kind": "web", "url": "https://pve.proxmox.com/wiki/FAQ", "title": "FAQ",
       "fetched": True, "rank": 1, "host": "pve.proxmox.com",
       "text": "Proxmox VE is licensed under the AGPLv3. The no-subscription repository is not "
               "recommended for production use."}
PRESS = {"id": "W3", "kind": "web", "url": "https://www.theregister.com/2025/x", "title": "Reg",
         "fetched": True, "rank": 2, "host": "theregister.com", "text": "…"}


def _doc(summary: str, moving: str = "") -> str:
    return ("# Dossier\n\n## What this is about\n\nBackground.\n\n## Decision summary\n\n"
            f"{summary}\n\n## What is moving\n\n{moving}\n\n## Regulatory and IP status\n\nx\n")


class TestMarketingOnly:
    def test_pricing_only_is_a_finding(self):
        rep = _doc("Proxmox VE without a subscription is meant for non-production use only [[W1]].")
        out = ds.marketing_only_claims(rep, [PRICING, FAQ, PRESS], "en", entities=["Proxmox"],
                                       is_doc_host=cr.is_doc_host)
        assert len(out) == 1 and out[0]["kind"] == "marketing"
        assert out[0]["host"] == "proxmox.com" and out[0]["section"] == "decision"
        assert "subscription" in out[0]["terms"]

    def test_faq_in_the_same_sentence_clears_it(self):
        rep = _doc("Proxmox VE without a subscription is meant for non-production use only [[W1]] [[W2]].")
        assert ds.marketing_only_claims(rep, [PRICING, FAQ], "en", entities=["Proxmox"],
                                        is_doc_host=cr.is_doc_host) == []

    def test_faq_in_the_same_paragraph_clears_it(self):
        rep = _doc("Proxmox VE without a subscription is meant for non-production use only [[W1]]. "
                   "The licence is AGPLv3 and the free repository is not recommended for production [[W2]].")
        assert ds.marketing_only_claims(rep, [PRICING, FAQ], "en", entities=["Proxmox"],
                                        is_doc_host=cr.is_doc_host) == []

    def test_faq_in_another_paragraph_does_not(self):
        rep = _doc("Proxmox VE without a subscription is meant for non-production use only [[W1]].\n\n"
                   "The licence is AGPLv3 [[W2]].")
        assert len(ds.marketing_only_claims(rep, [PRICING, FAQ], "en", entities=["Proxmox"],
                                            is_doc_host=cr.is_doc_host)) == 1

    def test_vendor_own_site_at_rank_2_counts_as_marketing(self):
        own = {**PRESS, "id": "W4", "url": "https://www.proxmox.com/en/about", "host": "proxmox.com"}
        rep = _doc("Proxmox VE ships with a built-in firewall for every host [[W4]].")
        assert len(ds.marketing_only_claims(rep, [own], "en", entities=["Proxmox VE"])) == 1
        # ohne Akteur-Bezug ist eine Rang-2-Seite nur Presse, kein Marketing
        assert ds.marketing_only_claims(rep, [own], "en", entities=["Broadcom"]) == []
        assert ds.marketing_only_claims(_doc("The register says something long enough here [[W3]]."),
                                        [PRESS], "en", entities=["Proxmox"]) == []

    def test_doc_search_query_and_add_citation(self):
        assert ds.doc_search_query("www.proxmox.com", ["subscription", "production"]) == \
            "site:proxmox.com (docs OR faq OR documentation) subscription production"
        assert ds.doc_search_query("pve.proxmox.com", ["a"]).startswith("site:proxmox.com ")
        s = "Claim here [[W1]]."
        assert ds.add_citation("x " + s, s, "[[W2]]") == "x Claim here [[W1]] [[W2]]."
        row = "| A | B | [[W1]] |"
        assert ds.add_citation(row, row, "[[W2]]") == "| A | B | [[W1]] [[W2]] |"
        assert ds.add_citation(s, s, "[[W1]]") == s

    def test_revision_prompt_names_the_rule(self):
        rep = _doc("Proxmox VE without a subscription is meant for non-production use only [[W1]].")
        f = ds.marketing_only_claims(rep, [PRICING], "en", entities=["Proxmox"])
        text = ds.revision_prompt([], f, "en")
        assert "MARKETINGSEITEN" in text and "FAQ" in text

    def test_support_verdict_uses_one_call_and_never_supports_on_failure(self):
        from pipeline import dossier_entailment as de
        calls = []

        def chat(model, schema, system, prompt, **kw):
            calls.append(prompt)
            return schema(verdicts=[{"sentence_index": 0, "verdict": "supported",
                                     "quote": "not recommended for production use"}])
        v, q = de.support_verdict("The free repo is not for production [[W1]].", FAQ,
                                  model="m", chat=chat)
        assert v == "supported" and "production" in q and len(calls) == 1
        assert de.support_verdict("x", FAQ, model="m",
                                  chat=lambda **kw: (_ for _ in ()).throw(RuntimeError("x"))) == ("unrelated", "")
        # Widerspruch ohne Zitatstelle ist kein Widerspruch
        assert de.support_verdict("x", FAQ, model="m", chat=lambda model, schema, system, prompt, **kw:
                                  schema(verdicts=[{"sentence_index": 0, "verdict": "contradicted", "quote": ""}]))[0] == "unrelated"


# ==========================================================================
# 6. Leser an den Pflichtpunkten
# ==========================================================================

class TestReader:
    def test_schema_defaults_keep_old_fakes_valid(self):
        r = cr.ReaderReview(answers_question=True, overall="fine", findings=[])
        assert r.answered_items == [] and r.unanswered_items == []
        assert "recommendation" in cr.READER_SYSTEM.lower() and "NOT expected" in cr.READER_SYSTEM
        from pipeline import dossier_brief
        assert "recommendation is NOT" in dossier_brief.must_answer_checklist(["a", "b"])

    def _fake(self, monkeypatch, answers, unanswered, kind="missing"):
        from pipeline import llamacpp_client

        def chat_structured(model, schema, prompt, system=None, **kw):
            assert schema is cr.ReaderReview
            return schema(answers_question=answers, overall="v",
                          findings=[{"section": "Decision summary", "kind": kind, "severity": "major",
                                     "passage": "", "issue": "i", "suggestion": "s"}] if kind else [],
                          answered_items=["Which stacks exist?"], unanswered_items=unanswered)
        monkeypatch.setattr(llamacpp_client, "chat_structured", chat_structured)

    def test_verdict_follows_the_must_answer_items(self, monkeypatch):
        self._fake(monkeypatch, answers=True, unanswered=["What does SYS.1.5 require?"])
        out = cr.reader_review(_doc("Long enough summary sentence with a claim [[T1]]."), "q", "t", None,
                               must_answer=["Which stacks exist?", "What does SYS.1.5 require?"])
        assert out["answers_question"] is False
        assert out["unanswered_items"] == ["What does SYS.1.5 require?"] and out["must_answer"] == 2
        lines = cr.reader_lines(out)
        assert lines[0].startswith("READER: these must-answer items") and "SYS.1.5" in lines[0]
        assert "does not answer the question asked" not in lines[0]

    def test_all_items_answered_is_a_yes(self, monkeypatch):
        self._fake(monkeypatch, answers=True, unanswered=[], kind=None)
        out = cr.reader_review(_doc("Long enough summary sentence with a claim [[T1]]."), "q", "t", None,
                               must_answer=["Which stacks exist?"])
        assert out["answers_question"] is True and out["answered_items"] == ["Which stacks exist?"]

    def test_coherence_finding_blocks_the_yes(self, monkeypatch):
        self._fake(monkeypatch, answers=True, unanswered=[], kind="coherence")
        out = cr.reader_review(_doc("Long enough summary sentence with a claim [[T1]]."), "q", "t", None,
                               must_answer=["Which stacks exist?"])
        assert out["answers_question"] is False

    def test_without_a_brief_the_old_verdict_stands(self, monkeypatch):
        self._fake(monkeypatch, answers=True, unanswered=["stray"], kind=None)
        out = cr.reader_review(_doc("Long enough summary sentence with a claim [[T1]]."), "q", "t", None)
        assert out["answers_question"] is True and out["must_answer"] == 0


# ==========================================================================
# 7. Verdrahtung in run(): Planer entscheidet, Dedup greift, Trace im Ergebnis
# ==========================================================================

def test_run_wires_planner_dedup_and_marketing_repair(monkeypatch):
    from pipeline import llamacpp_client
    from tests.test_dossier_decision import ARTICLE, SEED, _Chat
    chat = _Chat()
    monkeypatch.setattr(llamacpp_client, "chat", chat)
    monkeypatch.setenv("DOSSIER_DRAFTS", "1")
    monkeypatch.setenv("DOSSIER_REWRITES", "1")
    monkeypatch.setenv("DOSSIER_WRITE", "single")
    monkeypatch.setenv("DOSSIER_READER", "0")
    monkeypatch.setenv("DOSSIER_ENTAILMENT", "0")
    monkeypatch.delenv("DOSSIER_VOI_MIN_GAIN", raising=False)
    web_actions = iter([
        ("search", "proxmox subscription pricing tiers", 0),
        ("search", "proxmox pricing subscription tiers", 0),      # Jaccard 1,0 → uebersprungen
        ("finish", "", -1),
    ])

    def chat_structured(model, schema, prompt, system=None, **kw):
        name = schema.__name__
        if name == "Plan":
            return schema(title="P", steps=[{"title": "S", "query": "q"}])
        if name == "AgentAction":
            return schema(action="finish", title="done", argument="",
                          state={"summary": "s", "gaps": [], "unsupported": []})
        if name == "WebAction":
            a, arg, tg = next(web_actions, ("finish", "", -1))
            return schema(action=a, title="w", argument=arg, target_gap=tg,
                          state={"summary": "s", "gaps": [], "unsupported": []})
        if name == "Audit":
            return schema(thesis="t", supported=[], inferences=[], contradictions=[],
                          missing=["what is the legal status"], outline=["o"])
        if name == "TopicProfile":
            return None
        if name == "EntailmentReview":
            return schema(verdicts=[{"sentence_index": 0, "verdict": "supported",
                                     "quote": "not recommended for production"}])
        raise AssertionError(name)
    monkeypatch.setattr(llamacpp_client, "chat_structured", chat_structured)
    monkeypatch.setattr(cr, "search_corpus", lambda q, n, scope="both": [
        dict(ARTICLE, id=f"T{i}", url=f"https://catandary.de/trends/a-{i}", origin=o)
        for i, o in enumerate(("https://www.ema.europa.eu/en/x", "https://www.fda.gov/news/y",
                               "https://clinicaltrials.gov/study/z"), start=1)])
    monkeypatch.setattr(cr, "search_research", lambda *a, **k: [])
    monkeypatch.setattr(cr, "search_patents", lambda *a, **k: [])
    searches: list[str] = []

    def brave(q, n=6):
        searches.append(q)
        if q.startswith("site:"):
            return [{"id": "W", "trend_id": None, "kind": "web", "title": "FAQ",
                     "url": "https://pve.proxmox.com/wiki/FAQ", "origin": "https://pve.proxmox.com/wiki/FAQ",
                     "outlet": "", "vertical": "", "date": "", "snippet": "AGPL", "fetched": False}]
        return [{"id": "W", "trend_id": None, "kind": "web", "title": "Proxmox VE pricing",
                 "url": "https://www.proxmox.com/en/proxmox-virtual-environment/pricing",
                 "origin": "https://www.proxmox.com/en/proxmox-virtual-environment/pricing",
                 "outlet": "", "vertical": "", "date": "", "snippet": "GLP-1 pricing", "fetched": False}]
    monkeypatch.setattr(cr, "brave_search", brave)
    monkeypatch.setattr(cr, "fetch_web_page_status",
                        lambda url: ("Proxmox VE. The no-subscription repository is not recommended "
                                     "for production. GLP-1 mentioned. " * 8, "fetched"))
    out = cr.run("What should we do?", max_steps=2, max_sources=8, retrieval="fts", per_query=2,
                 web_steps=4, max_web_sources=6, topic="GLP-1 and incretin technology",
                 measure=True, seed_sources=[dict(SEED)], seed_notes=["seed"],
                 brief={"must_answer": ["What does the subscription cost?"]})
    voi = out["voi"]
    # Korpus: das Modell sagte zweimal „finish", der Planer lehnte beim ersten Mal ab
    assert voi["corpus"]["used"] == 2
    assert any(t.get("note") == "refused" for t in voi["corpus"]["trace"])
    assert any(t.get("action") == "finish" and t.get("result") == "refused" for t in out["trace"])
    # Pflichtpunkt steht vor der Audit-Luecke, mit Gewicht 3
    assert voi["web"]["gaps"][0]["kind"] == "must" and voi["web"]["gaps"][0]["weight"] == 3.0
    assert out["ledger"][0]["kind"] == "must" and out["ledger"][1]["kind"] == "gap"
    # Dedup: die zweite Anfrage lief nie
    assert voi["dedup"]["skipped"] == 1 and voi["dedup"]["skips"][0]["method"] == "jaccard"
    assert searches.count("proxmox pricing subscription tiers") == 0
    assert any(s.get("result") == "near-duplicate" for s in out["web"]["steps"])
    assert voi["budget"]["web"] == 4 and voi["budget"]["gain_floor"] == dp.DEFAULT_MIN_GAIN
    assert out["web"]["steps"][0].get("kind") == "must"
