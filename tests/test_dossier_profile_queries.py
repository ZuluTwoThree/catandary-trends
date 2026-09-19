"""Stufe 2 des Dossier-Agent-Plans (docs/plan_dossier_agent_2026-09-18.md):
Beschaffung aus dem Profil, Primärquellen je Feld.

Alles ohne Modell, Netz oder GPU: profile_queries ist rein, die Sweeps werden
mit einer falschen brave_search gefahren, die Erfahrungsbasis gegen eine
temporäre SQLite geprüft.
"""
from __future__ import annotations

import importlib
import re

import pytest

from scripts import corpus_research as cr


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------

def _virt_profile() -> cr.TopicProfile:
    return cr.TopicProfile(
        field="datacenter virtualization",
        actor_types=["hypervisor vendor", "enterprise IT operator"],
        regulators=["EU Data Act cloud switching", "GDPR Article 28 processor terms",
                    "BSI IT-Grundschutz SYS.1.5", "NIS2 directive"],
        event_types=["end of general support date", "major version release",
                     "licence renewal deadline"],
        legal_questions=["hypervisor licence audit rights"],
        market_questions=["hypervisor migration share Proxmox Nutanix"],
        perspectives=[cr.Perspective(role="CIO", questions=["total cost per host",
                                                            "migration tooling maturity"])],
        actor_seeds=["Broadcom", "Proxmox", "Nutanix"],
        source_classes=[
            cr.SourceClass(kind="vendor_documentation", name="Broadcom lifecycle pages",
                           hosts=["knowledge.broadcom.com"], why="support end dates"),
            cr.SourceClass(kind="vendor_documentation", name="Proxmox docs",
                           hosts=["pve.proxmox.com"], why="feature and release facts"),
            cr.SourceClass(kind="vulnerability_database", name="NVD", hosts=["nvd.nist.gov"],
                           why="CVE records"),
            cr.SourceClass(kind="register", name="EUR-Lex", hosts=[], why="legal text"),
        ])


def _pharma_profile() -> cr.TopicProfile:
    return cr.TopicProfile(
        field="incretin obesity drugs",
        actor_types=["drug developer"],
        regulators=["EMA CHMP opinion", "SPC supplementary protection certificate",
                    "FDA approval decision"],
        event_types=["phase 3 readout", "CHMP opinion", "PDUFA decision date"],
        legal_questions=["semaglutide patent expiry Europe"],
        market_questions=["reimbursement decision Germany obesity"],
        perspectives=[],
        actor_seeds=["Novo Nordisk", "Eli Lilly"],
        source_classes=[cr.SourceClass(kind="agency", name="EMA", hosts=["ema.europa.eu"],
                                       why="authorisations")])


def _all_queries(pq: dict) -> str:
    return " | ".join(q for k, v in pq.items() if k != "fallback" for q in v).lower()


OFF_FIELD = ("ai act", "spc", "reimbursement", "ce marking", "waste heat",
             "ema", "efsa", "pdufa", "horizon europe", "eic accelerator")


class TestProfileDrivesTheSweeps:
    def test_a_virtualization_profile_never_asks_pharma_or_ai_act_questions(self):
        pq = cr.profile_queries(_virt_profile(), "datacenter virtualization",
                                ["virtualization"], "Which hypervisor?", vertical="TECH")
        joined = _all_queries(pq)
        for bad in OFF_FIELD:
            assert not re.search(r"\b" + re.escape(bad) + r"\b", joined), bad
        assert "eu data act cloud switching decision" in joined
        assert "end of general support date expected 2027" in joined
        assert "{e} eu data act cloud switching" in joined            # zweite Welle
        assert pq["fallback"] == ()

    def test_actor_types_shape_market_and_funding(self):
        pq = cr.profile_queries(_virt_profile(), "t", [])
        assert any("hypervisor vendor adoption demand pricing" in q for q in pq["market"])
        assert any("hypervisor vendor funding round raised" in q for q in pq["funding"])
        assert not any("Horizon Europe" in q for q in pq["funding"])
        assert any("public funding call deadline" in q for q in pq["funding"])

    def test_a_pharma_profile_still_yields_ema_and_spc_queries(self):
        pq = cr.profile_queries(_pharma_profile(), "GLP-1", [], vertical="HEALTH")
        joined = _all_queries(pq)
        assert "ema chmp opinion decision" in joined
        assert "spc supplementary protection certificate" in joined
        assert "phase 3 readout expected 2027" in joined
        assert "reimbursement decision germany obesity" in joined   # aus dem Profil
        assert "ce marking" not in joined and "ai act" not in joined

    def test_without_a_profile_the_fixed_lists_and_the_backbone_remain(self):
        pq = cr.profile_queries(None, "GLP-1 incretin", [])
        assert pq["regulatory"] == cr.REGULATORY_PATTERNS
        assert pq["funding"] == cr.FUNDING_PATTERNS
        assert pq["fallback"] == ("fixed",)
        pq2 = cr.profile_queries(None, "datacenter virtualization", [], vertical="TECH")
        assert any("EU AI Act" in q for q in pq2["regulatory"])   # Rueckfall ohne Profil
        assert set(pq2["fallback"]) == {"regulators", "events", "funding"}

    def test_a_thin_profile_field_falls_back_per_field(self):
        prof = _virt_profile()
        prof.event_types = ["investment", "funding", "milestone"]   # nichts Brauchbares
        pq = cr.profile_queries(prof, "t", [], vertical="TECH")
        assert pq["fallback"] == ("events",)
        assert any("standard ratification expected 2027" in q for q in pq["catalyst"])
        assert not any("AI Act" in q for q in pq["regulatory"])     # Regulatoren bleiben Profil

    def test_corpus_counts_order_the_instruments_without_dropping_any(self):
        prof = _virt_profile()
        counts = {"NIS2 directive": 9, "EU Data Act cloud switching": 3,
                  "GDPR Article 28 processor terms": 0, "BSI IT-Grundschutz SYS.1.5": 1}
        pq = cr.profile_queries(prof, "t", [], instrument_counts=counts)
        reg = [q for q in pq["regulatory"] if q.endswith(" decision")]
        assert reg[0] == "{t} NIS2 directive decision"
        assert reg[1] == "{t} EU Data Act cloud switching decision"
        assert any("GDPR Article 28" in q for q in reg)             # 0 Treffer, bleibt

    def test_count_instruments_and_unseen_marking(self):
        prof = _virt_profile()
        hits = {"datacenter virtualization NIS2 directive": [{"id": 1}, {"id": 2}]}
        counts = cr.count_instruments(prof, "datacenter virtualization",
                                      lambda q, n: hits.get(q, []))
        assert counts["NIS2 directive"] == 2
        assert counts["EU Data Act cloud switching"] == 0
        ledger = [{"kind": "legal", "gap": "datacenter virtualization EU Data Act cloud switching decision",
                   "web_sources": 2, "off_topic_dropped": 0, "budget_dropped": 0, "rejected": []},
                  {"kind": "legal", "gap": "datacenter virtualization GDPR Article 28 processor terms decision",
                   "web_sources": 0, "off_topic_dropped": 0, "budget_dropped": 0, "rejected": []}]
        notes: list[str] = []
        unseen = cr.mark_unseen_instruments(ledger, notes, counts)
        assert "GDPR Article 28 processor terms" in unseen
        assert "EU Data Act cloud switching" not in unseen           # Web-Treffer
        assert ledger[1].get("instrument_unseen") == "GDPR Article 28 processor terms"
        assert notes and notes[0].startswith("INSTRUMENT CHECK")

    def test_old_profiles_without_source_classes_still_validate(self):
        p = cr.coerce_profile({"field": "x", "actor_types": [], "regulators": ["a", "b"],
                               "event_types": ["a", "b", "c"], "legal_questions": [],
                               "market_questions": [], "perspectives": [], "actor_seeds": []})
        assert p is not None and p.source_classes == []

    def test_the_prompt_asks_for_source_classes(self):
        assert cr.PROFILE_SYSTEM.startswith("You prepare the search directions")
        assert "source classes" in cr.PROFILE_SYSTEM
        assert "not by medical-device or pharma rules" in cr.PROFILE_SYSTEM


# --------------------------------------------------------------------------
# Entity hygiene
# --------------------------------------------------------------------------

def _catalog() -> list[dict]:
    mk = lambda i, t, s: {"id": f"T{i}", "kind": "article", "title": t, "snippet": s}   # noqa: E731
    return [
        mk(1, "Broadcom raises VMware prices again", "However, Proxmox adoption grows. Security teams object."),
        mk(2, "Proxmox VE 9 released", "General availability announced. Broadcom customers migrate."),
        mk(3, "Nutanix courts VMware refugees", "Security and general support matter; however costs rise."),
        mk(4, "Zebra Systems pilots KVM", "Proxmox is used by Zebra."),
    ]


class TestEntityHygiene:
    def test_sentence_initial_words_never_become_entities(self):
        ents, _ = cr.harvest_entities(_catalog(), "datacenter virtualization")
        low = {e.lower() for e in ents}
        for bad in ("however", "security", "general"):
            assert bad not in low, ents
        assert "proxmox" in low and "broadcom" in low

    def test_sweep_entities_keeps_names_seen_twice_or_seeded(self):
        prof = _virt_profile()
        out = cr.sweep_entities(["However", "Security", "General", "Proxmox", "Broadcom",
                                 "Zebra Systems", "Nutanix"], _catalog(), prof)
        assert out == ["Proxmox", "Broadcom", "Nutanix"]     # Zebra: nur einmal, keine Saat
        assert cr.sweep_entities(["Zebra Systems"], _catalog(), None) == []

    def test_cap_and_kind(self):
        many = [f"Vendor{i}" for i in range(10)]
        cat = [{"title": " ".join(many), "snippet": " ".join(many)}] * 2
        assert len(cr.sweep_entities(many, cat, None, cap=6)) == 6
        assert cr.entity_kind("semaglutide") == "substance"
        assert cr.entity_kind("Broadcom") == "org"

    def test_catalyst_sweep_only_asks_per_clean_entity(self, monkeypatch):
        seen: list[str] = []
        monkeypatch.setattr(cr, "brave_search", lambda q, count=6: seen.append(q) or [])
        clean = cr.sweep_entities(["However", "Proxmox", "Broadcom"], _catalog(), None)
        cr.sweep_catalysts("datacenter virtualization", clean, [], set(), [], [], 6,
                           patterns=("{t} key milestones expected 2027 timeline",),
                           entity_patterns=("{e} next milestone timeline",))
        assert "Proxmox next milestone timeline" in seen
        assert not any(q.startswith("However") for q in seen)


# --------------------------------------------------------------------------
# Rank by field
# --------------------------------------------------------------------------

class TestRankByField:
    def test_documentation_and_standards_hosts_are_primary(self):
        for u in ("https://learn.microsoft.com/en-us/windows-server/x",
                  "https://knowledge.broadcom.com/external/article/123",
                  "https://pve.proxmox.com/wiki/Roadmap",
                  "https://docs.openstack.org/nova/latest/",
                  "https://developer.hashicorp.com/vault/docs",
                  "https://support.hpe.com/hpesc/public/docDisplay",
                  "https://proxmoxer.readthedocs.io/en/latest/",
                  "https://www.iso.org/standard/27001",
                  "https://www.etsi.org/deliver/x",
                  "https://www.cve.org/CVERecord?id=CVE-2024-1"):
            assert cr.source_rank(u) == 1, u
        assert cr.source_rank("https://nvd.nist.gov/vuln/detail/CVE-2024-1") == 0   # .gov bleibt 0
        assert cr.source_rank("https://www.theregister.com/x") == 2
        assert cr.source_rank("https://support.fandom.com/x") == cr.RANK_REJECT     # Rangfilter zuerst
        assert cr.source_rank("https://docs.com/x") == 2                              # kein Subdomain-Praefix

    def test_profile_hosts_rank_primary_for_this_run_only(self):
        cr.set_run_primary_hosts(["knowledge.broadcom.com", "https://www.example-vendor.com/a"])
        try:
            assert cr.run_primary_hosts() == frozenset({"knowledge.broadcom.com", "example-vendor.com"})
            assert cr.source_rank("https://www.example-vendor.com/lifecycle") == 1
            assert cr.source_rank("https://blog.example-vendor.com/lifecycle") == 1
        finally:
            cr.set_run_primary_hosts(())
        assert cr.source_rank("https://www.example-vendor.com/lifecycle") == 2
        assert cr.source_rank("https://www.example-vendor.com/lifecycle",
                              extra_primary=["example-vendor.com"]) == 1

    def test_rank_hits_uses_the_run_set(self):
        hits = [{"url": "https://www.theregister.com/a"}, {"url": "https://www.example-vendor.com/b"}]
        cr.set_run_primary_hosts(["example-vendor.com"])
        try:
            assert cr.rank_hits(hits)[0]["url"].startswith("https://www.example-vendor")
        finally:
            cr.set_run_primary_hosts(())


class TestSourcePriors:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
        monkeypatch.setenv("DATABASE_URL", "")
        from pipeline import db as db_mod
        importlib.reload(db_mod)
        from pipeline import dossier_priors
        importlib.reload(dossier_priors)
        from pipeline.db import get_connection
        with get_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS dossier_source_priors")
            conn.execute("DROP TABLE IF EXISTS dossiers")
        dossier_priors.ensure_schema()
        yield

    def _sources(self):
        return [
            {"id": "L1", "kind": "legal", "url": "https://knowledge.broadcom.com/a", "fetched": True, "rank": 1},
            {"id": "L2", "kind": "legal", "url": "https://knowledge.broadcom.com/b", "fetched": True, "rank": 1},
            {"id": "W1", "kind": "web", "url": "https://www.theregister.com/x", "fetched": True, "rank": 2},
            {"id": "W2", "kind": "web", "url": "https://www.theregister.com/y", "fetched": False, "rank": 2},
            {"id": "T1", "kind": "article", "origin": "https://pve.proxmox.com/wiki/z", "rank": 1},
            {"id": "P1", "kind": "paper", "url": "", "rank": 1},
        ]

    def test_run_host_stats(self):
        from pipeline import dossier_priors as dp
        st = dp.run_host_stats(self._sources(), ["L1", "L2", "W1", "T1"],
                               ["https://www.theregister.com/x"])
        assert st["knowledge.broadcom.com"] == {"n_read": 2, "n_cited": 2, "n_dropped": 0, "rank_seen": 1}
        assert st["theregister.com"] == {"n_read": 1, "n_cited": 1, "n_dropped": 1, "rank_seen": 2}
        assert st["pve.proxmox.com"]["n_cited"] == 1 and st["pve.proxmox.com"]["n_read"] == 0
        assert not any(h == "" for h in st)

    def test_upsert_adds_up_and_rank1_needs_two_citations_and_no_drop(self):
        from pipeline import dossier_priors as dp
        structure = {"cite_findings_after": [
            {"kind": "figure", "url": "https://www.theregister.com/x", "sentence": "s"},
            {"kind": "weaksource", "url": "https://knowledge.broadcom.com/a", "sentence": "t"}]}
        n = dp.update_from_run("Datacenter Virtualization", self._sources(), ["L1", "W1"], structure)
        assert n == 2                                   # pve.proxmox.com: weder gelesen noch zitiert
        assert dp.primary_hosts_for("datacenter virtualization") == []            # erst 1x zitiert
        dp.update_from_run("datacenter virtualization", self._sources(), ["L2", "W1"], structure)
        assert dp.primary_hosts_for("datacenter virtualization") == ["knowledge.broadcom.com"]
        assert dp.primary_hosts_for("other field") == []
        rows = {r["host"]: r for r in dp.list_priors("datacenter virtualization")}
        assert rows["knowledge.broadcom.com"]["n_read"] == 4
        assert rows["theregister.com"]["n_dropped"] == 2 and rows["theregister.com"]["n_cited"] == 2

    def test_backfill_rebuilds_from_runs_with_topic_as_field(self):
        from pipeline import dossier_priors as dp
        runs = [{"id": 1, "slug": "s", "version": 1, "topic": "Datacenter virtualization",
                 "result": {"sources": self._sources(), "cited": ["L1", "L2"], "structure": {}}},
                {"id": 2, "slug": "s", "version": 2, "topic": "Datacenter virtualization",
                 "result": {"sources": self._sources(), "cited": ["L1"],
                            "profile": {"field": "datacenter virtualization"}}}]
        out = dp.backfill(runs)
        assert out["runs"] == 2
        f = out["fields"]["datacenter virtualization"]
        assert f["runs"] == 2 and f["rank1_hosts"] == ["knowledge.broadcom.com"]
        out2 = dp.backfill(runs)                       # idempotent: loescht vorher
        assert out2["fields"]["datacenter virtualization"]["hosts"] == f["hosts"]
        assert dp.list_priors("datacenter virtualization")[0]["n_cited"] == 3

    def test_write_path_never_raises(self, monkeypatch):
        from pipeline import dossier_priors as dp
        monkeypatch.setattr(dp, "upsert", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db gone")))
        assert dp.update_from_run("f", self._sources(), [], None) == 0

    def test_missing_table_means_no_priors(self):
        from pipeline import dossier_priors as dp
        from pipeline.db import get_connection
        with get_connection() as conn:
            conn.execute("DROP TABLE dossier_source_priors")
        assert dp.primary_hosts_for("f") == []
        assert dp.update_from_run("f", self._sources(), ["L1"], None) == 0


# --------------------------------------------------------------------------
# Primary-first by usefulness
# --------------------------------------------------------------------------

def _src(i, url, title="", snippet=""):
    return {"id": i, "kind": "web", "url": url, "title": title, "snippet": snippet, "fetched": False}


class TestPrimaryFirstOrder:
    def test_rank_then_prior_then_must_terms_then_hit_order(self, monkeypatch):
        read: list[str] = []
        # Stufe 3: EUR-Lex laeuft artikelweise ueber fetch_fulltext_result —
        # hier ohne Netz gescheitert, dann faellt der Abruf auf den Stub zurueck.
        from pipeline.article_fetcher import FetchResult
        monkeypatch.setattr(cr, "fetch_fulltext_result", lambda url, **kw: FetchResult(None, "error"))
        monkeypatch.setattr(cr, "fetch_web_page_status",
                            lambda url: (read.append(url) or ("body 12 May 2026", "ok")))
        sources = [
            _src("W1", "https://docs.example.com/plain", "Plain docs page"),
            _src("W2", "https://docs.example.com/support", "End of support date for vSphere 8"),
            _src("W3", "https://knowledge.broadcom.com/lifecycle", "Lifecycle"),
            _src("W4", "https://www.theregister.com/x", "End of support vSphere"),    # Rang 2: nie
            _src("W5", "https://eur-lex.europa.eu/data-act", "Data Act text"),
        ]
        out = cr.read_primary_first(sources, [], [], ["vsphere"],
                                    must_terms=cr.must_answer_terms(
                                        ["When does vSphere 8 general support end?"]),
                                    prior_hosts=["knowledge.broadcom.com"])
        assert read == ["https://eur-lex.europa.eu/data-act",          # Rang 0
                        "https://knowledge.broadcom.com/lifecycle",     # Prior-Host
                        "https://docs.example.com/support",             # Pflichtpunkt-Begriffe
                        "https://docs.example.com/plain"]               # Trefferreihenfolge
        assert out["read"] == 4 and out["candidates"] == 4
        assert out["order"][0]["rank"] == 0 and out["order"][1]["prior"] == 1
        assert out["order"][2]["must_hits"] >= 1

    def test_budget_unchanged(self, monkeypatch):
        monkeypatch.setattr(cr, "fetch_web_page_status", lambda url: ("text " * 20, "ok"))
        sources = [_src(f"W{i}", f"https://www.fda.gov/p{i}") for i in range(10)]
        out = cr.read_primary_first(sources, [], [], ["x"], budget=3)
        assert out["read"] == 3 and cr.DR_READ_BUDGET == 28

    def test_must_answer_terms(self):
        t = cr.must_answer_terms(["Which hypervisor should we standardise on?",
                                  "What does the migration cost per host?"])
        assert "hypervisor" in t and "migration" in t and "should" not in t


# --------------------------------------------------------------------------
# Scope note: calendar rows off the profile
# --------------------------------------------------------------------------

def test_calendar_off_profile_names_the_foreign_instrument():
    report = ("## Decision summary\n\nx.\n\n## What happens next\n\n"
              "| Date | Event | Source |\n|---|---|---|\n"
              "| Q3 2026 | EU AI Act high-risk obligations apply | [[L1]] |\n"
              "| 2027 | EU Data Act switching charges end | [[L2]] |\n"
              "| 2027 | Proxmox VE 10 release | [[L3]] |\n")
    note = cr.calendar_off_profile(report, "en", _virt_profile())
    assert note["rows"] == 1 and note["instruments"] == ["ai act"]
    assert note["checked"] == 4                          # Kopfzeile zaehlt mit wie in calendar_rows
    assert "AI Act" in note["examples"][0]
    assert cr.calendar_off_profile(report, "en", None) is None
    prof = _virt_profile()
    prof.regulators.append("EU AI Act")
    assert cr.calendar_off_profile(report, "en", prof)["rows"] == 0
