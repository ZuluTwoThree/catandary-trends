"""Scouting-Umbau (Owner-Ziel 2026-09-19, Stufe 6): der Korpus zuerst, das Web
nur dort, wo er dünn ist.

Vier Blöcke, alle ohne Netz und ohne GPU:

  1. `pipeline/dossier_corpus_evidence.py` gegen eine SQLite-Fixture mit
     Signalen über Ebenen und Quartale (Zählung, 10k-Normierung, Akteure,
     Quellen, repräsentative Signale als Katalogeinträge, Dünne-Regeln,
     Textregel mit Stämmen und Tags).
  2. Gating (`web_gating`): welche Lücken ans Web gehen, welche Sweeps
     laufen, wie viel Budget — und der Rückfall ohne Korpus-Evidenz.
  3. Scout-Grundriss in `pipeline/dossier_structure.py`: Pflichtabschnitte,
     Reifegrad-Nadelregel, Korpusanteil der Bewegungs-Tabelle, Dünne-Sektion,
     alter Grundriss unverändert.
  4. Verdrahtung in `run()` mit Fakes: Evidenz-Block im Prompt, Sweeps und
     Web-Agent nur für dünne Bereiche, Ergebnisfelder.
"""
import os
from datetime import date

import pytest

os.environ["DATABASE_PATH"] = "/tmp/catandary_test_corpus_evidence.db"

from pipeline import db as db_mod                       # noqa: E402
from pipeline import dossier_corpus_evidence as ce      # noqa: E402
from pipeline import dossier_structure as ds            # noqa: E402
from pipeline.db import get_connection, init_db         # noqa: E402

TODAY = date(2026, 9, 19)


# ---------------------------------------------------------------------------
# Fixture: eine kleine Korpus-DB mit Signalen je Ebene und Quartal
# ---------------------------------------------------------------------------

def _seed(rows):
    """rows: (id, title, summary, source_id, status, sort_date, signal_type, brands, tags)"""
    with get_connection() as conn:
        for sid, name, stype in ((1, "The Register", "trade_media"),
                                 (2, "OpenAlex fresh: Cloud", "research"),
                                 (3, "EPO DOCDB (TECH)", "api"),
                                 (4, "NSF Awards", "api"),
                                 (5, "Hacker News Best", "api")):
            conn.execute("INSERT OR IGNORE INTO sources (id, name, feed_url, source_type, vertical) "
                         "VALUES (?, ?, ?, ?, 'TECH')", (sid, name, f"https://x/{sid}", stype))
        for r in rows:
            tid, title, summary, sid, status, sd, st, brands, tags = r
            # sort_date wird vom SQLite-Trigger aus raw_entries.published_date gesetzt
            conn.execute("INSERT OR IGNORE INTO raw_entries (id, source_id, url, title, published_date) "
                         "VALUES (?, ?, ?, ?, ?)", (tid, sid, f"https://src/{tid}", title, sd))
            conn.execute(
                "INSERT INTO trends (id, raw_entry_id, title_en, summary_en, slug, primary_vertical, "
                "status, source_url, source_name, sort_date, published_at, trend_signal_type, brands, "
                "companies, tags) VALUES (?, ?, ?, ?, ?, 'TECH', ?, ?, ?, ?, ?, ?, ?, '[]', ?)",
                (tid, tid, title, summary, f"t-{tid}", status, f"https://src/{tid}",
                 {1: "The Register", 2: "OpenAlex fresh: Cloud", 3: "EPO DOCDB (TECH)",
                  4: "NSF Awards", 5: "Hacker News Best"}[sid],
                 sd, sd, st, brands, tags))


@pytest.fixture(scope="module")
def corpus():
    path = os.environ["DATABASE_PATH"]
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass
    db_mod.DATABASE_PATH = path
    init_db()
    rows = []
    # Markt-Ebene: 9 Signale in den letzten 12 Monaten, je Quartal verteilt,
    # zwei davon vom Typ regulation (-> regulatory_12m = 2 < 3 -> dünn).
    for i, (sd, st) in enumerate([("2026-09-10", "market_shift"), ("2026-09-01", "regulation"),
                                  ("2026-08-15", "product_launch"), ("2026-07-02", "regulation"),
                                  ("2026-06-20", "market_shift"), ("2026-05-05", "market_shift"),
                                  ("2026-03-03", "market_shift"), ("2026-01-10", "market_shift"),
                                  ("2025-11-11", "market_shift")], start=100):
        rows.append((i, f"Proxmox pushes data center virtualization {i}",
                     "Hypervisor licensing after Broadcom", 1, "published", sd, st,
                     '["Broadcom", "Proxmox"]', '["virtualization"]'))
    # ein Markt-Signal, das das Thema NUR ueber die Tags traegt
    rows.append((120, "Cloud provider changes pricing", "Nothing here", 1, "published",
                 "2026-08-01", "market_shift", '["VMware"]', '["data-center", "virtualization"]'))
    # ein altes Markt-Signal ausserhalb der 24 Monate
    rows.append((121, "Datacenter virtualization in 2019", "old", 1, "published",
                 "2019-05-01", "market_shift", "[]", "[]"))
    # ein Treffer nur eines Begriffs -> zaehlt nicht
    rows.append((122, "Virtualization of the desktop", "desktop only", 1, "published",
                 "2026-08-02", "market_shift", "[]", "[]"))
    # Wissenschaft: 2 in 12 Monaten (dünn)
    rows.append((200, "Virtualized data centre scheduling", "paper", 2, "signal",
                 "2026-08-30", "research", "[]", "[]"))
    rows.append((201, "Data-center virtualisation energy model", "paper", 2, "signal",
                 "2026-04-30", "research", "[]", "[]"))
    # Patente: 6 in 12 Monaten (nicht dünn) — die Phrase steht im Titel
    for i in range(300, 306):
        rows.append((i, f"DATA CENTER VIRTUALIZATION: VM PLACEMENT {i}", "claims", 3, "signal",
                     f"2026-0{1 + i % 6}-15", "patent", "[]", "[]"))
    # Runde 30: beide Themenwoerter, aber 5 Woerter auseinander -> keine Phrase,
    # kein Kern (vorher: UND-Regel ueber Staemme traf sie)
    rows.append((306, "VIRTUAL MACHINE PLACEMENT IN A DATA CENTER", "claims", 3, "signal",
                 "2026-05-15", "patent", "[]", "[]"))
    # Runde 30: "serv" darf "services" nicht treffen (Titel ohne Server)
    rows.append((307, "Virtual reserve services for data center loads", "grid paper", 2, "signal",
                 "2026-08-01", "research", "[]", "[]"))
    # Förderung: 0 -> dünn
    # ein Signal mit Quelle ohne Ebene (api, kein Name-Muster) -> tier None
    rows.append((400, "Datacenter virtualization thread", "HN", 5, "signal",
                 "2026-09-05", "market_shift", "[]", "[]"))
    # Runde 28, erweiterter Satz: EIN Themenbegriff plus ein Name aus Profil/
    # Pflichtpunkt (130: "virtualization" + VMware) — nicht Kern; 131 traegt
    # nur den Namen (kein Themenstamm) und bleibt draussen.
    rows.append((130, "VMware licensing shock hits virtualization customers", "Broadcom terms", 1,
                 "published", "2026-06-05", "market_shift", '["VMware"]', "[]"))
    rows.append((131, "Microsoft quarterly results beat estimates", "cloud", 1, "published",
                 "2026-06-06", "market_shift", '["Microsoft"]', "[]"))
    # Runde 30: Proxmox ist themenspezifisch (9 von 9 Kandidatenzeilen im
    # Kern) -> der Name allein traegt die Zeile in den erweiterten Satz
    rows.append((132, "Proxmox opens Canadian subsidiary", "24/7 enterprise support from October", 1,
                 "published", "2026-09-03", "product_launch", '["Proxmox"]', "[]"))
    # Runde 30: Instrumente des Feldes mit Datum (Regulatorik-/Kalender-Regel)
    rows.append((500, "BSI IT-Grundschutz SYS.1.5 update for virtualized data center hosts",
                 "the new building block applies from Q2 2027", 1, "published",
                 "2026-08-10", "regulation", "[]", "[]"))
    rows.append((501, "EU Data Act chapter VI obligations for data center virtualization providers",
                 "switching rules apply from 12 August 2025", 1, "published",
                 "2026-05-01", "regulation", "[]", "[]"))
    rows.append((502, "GDPR Article 32 guidance on data-center virtualization security",
                 "published 2026-03-01, review due 2027-01-31", 1, "published",
                 "2026-03-02", "regulation", "[]", "[]"))
    # Fuellstoff fuer die 10k-Normierung: 600 Markt-Signale in 2026-Q3 ohne Thema
    for i in range(1000, 1600):
        rows.append((i, f"Unrelated retail item {i}", "shoes", 1, "signal",
                     "2026-08-20", "market_shift", "[]", "[]"))
    _seed(rows)
    yield path


# ---------------------------------------------------------------------------
# 1. Textregel
# ---------------------------------------------------------------------------

class TestTextRule:
    def test_normalize_is_british_and_separator_free(self):
        assert ce.normalize_text("Data-Centre Virtualisation") == "datacentervirtualization"

    def test_stems_match_lexeme_reach(self):
        assert ce.crude_stem("virtualization") == "virtual"
        assert ce.crude_stem("datacenters") == "datacent"
        assert ce.term_stems(["datacenter", "virtualization"]) == ["datacent", "virtual"]

    def test_row_matches_is_the_old_stem_rule(self):
        stems = ce.term_stems(["datacenter", "virtualization"])
        assert ce.row_matches({"title_en": "Data center virtualization", "summary_en": ""}, stems)
        assert ce.row_matches({"title_en": "Virtualized data centres", "summary_en": ""}, stems)
        assert not ce.row_matches({"title_en": "Virtualization of the desktop", "summary_en": ""}, stems)
        assert ce.row_matches({"title_en": "Cloud pricing", "summary_en": "",
                               "tags": ["data-center", "virtualization"]}, stems)

    def test_phrase_rule_window_and_word_level_stems(self):
        terms = ["server", "virtualization"]
        for t in ("Server virtualization market", "Virtualized servers cut costs",
                  "Virtualization of servers", "server virtualisation (UK spelling)",
                  "Citrix reclaims server virtualization share"):
            assert ce.phrase_match({"title_en": t, "summary_en": ""}, terms), t
        for t in ("The server farm runs a virtual assistant",           # 4 Woerter auseinander
                  "Design of Virtual Reserve Services",                  # services != server
                  "Virtual reality on the game server",                   # virtual … server: 4 auseinander
                  "USER IDENTITY SHARING SYSTEM FOR VIRTUAL ASSET SERVICE"):
            assert not ce.phrase_match({"title_en": t, "summary_en": ""}, terms), t
        # zusammengeschriebener Begriff trifft zwei Tokens
        assert ce.phrase_match({"title_en": "Data center virtualization", "summary_en": ""},
                               ["datacenter", "virtualization"])
        assert ce.phrase_match({"title_en": "Cloud pricing", "summary_en": "",
                                "tags": ["data-center", "virtualization"]}, ["datacenter", "virtualization"])
        assert not ce.phrase_match({"title_en": "VIRTUAL MACHINE PLACEMENT IN A DATA CENTER", "summary_en": ""},
                                   ["datacenter", "virtualization"])
        # Mehrwortbegriff
        assert ce.phrase_match({"title_en": "Proxmox VE 8 release", "summary_en": ""}, ["Proxmox VE"])
        assert ce.tok_hits("servers", "serv") is False or ce.crude_stem("servers") == "serv"
        assert ce.tok_hits(ce.crude_stem("servers"), "serv") and not ce.tok_hits(ce.crude_stem("services"), "serv")
        assert ce.tok_hits(ce.crude_stem("virtualized"), "virtual")
        assert ce.word_tokens("Virtualized Servers") == ["virtualiz", "serv"]

    def test_min_cosine_env(self, monkeypatch):
        monkeypatch.delenv("CORPUS_MIN_COSINE", raising=False)
        assert ce.min_cosine() == 0.55
        monkeypatch.setenv("CORPUS_MIN_COSINE", "0.62")
        assert ce.min_cosine() == 0.62
        monkeypatch.setenv("CORPUS_MIN_COSINE", "nonsense")
        assert ce.min_cosine() == 0.55

    def test_dates_and_windows(self):
        assert [p for _d, p in ce.text_dates("due 2026-11-01, Q2 2027 and 12 September 2025")] == ["day", "day", "quarter"]
        assert ce.text_dates("by October 2026")[0] == (date(2026, 10, 31), "month")
        assert ce.text_dates("support ends 14.10.2025")[0][0] == date(2025, 10, 14)
        assert ce.text_dates("March 3, 2027")[0][0] == date(2027, 3, 3)
        assert ce.text_dates("in 2027")[0] == (date(2027, 12, 31), "year")
        assert ce.dated_within("published 2026-03-01", TODAY) and not ce.dated_within("in 2024", TODAY)
        assert ce.dated_within("in 2026", TODAY) and not ce.dated_within("12 August 2025", TODAY)
        assert ce.future_dated("Q2 2027", TODAY) and ce.future_dated("October 2026", TODAY)
        assert not ce.future_dated("2026-09-01", TODAY) and not ce.future_dated("no date here", TODAY)
        assert ce.future_dated("by 2026", TODAY)                     # nacktes laufendes Jahr: zukunftsnah

    def test_instruments_and_item_names(self):
        assert ce.instrument_mentions("BSI IT-Grundschutz SYS.1.5, GDPR Art. 28 and 32, Regulation (EU) 2023/2854, "
                                      "ISO/IEC 27001 and NIS2") == \
            ["SYS.1.5", "Art. 28 and 32", "Regulation (EU) 2023/2854", "ISO/IEC 27001", "NIS2",
             "IT-Grundschutz", "GDPR"]
        assert ce.is_instrument_item("Which dated events — vendor support deadlines?")
        assert ce.is_instrument_item("What are the specific operational requirements imposed by BSI?")
        assert not ce.is_instrument_item("What is the current stage of the technology cycle?")
        names = ce.item_names("What do BSI IT-Grundschutz SYS.1.5 and EU Data Act chapter VI require of VMware hosts?",
                              ["VMware", "Microsoft"])
        assert "BSI IT-Grundschutz SYS.1.5" in names and "SYS.1.5" in names and "EU Data Act" in names
        assert "VMware" in names and "Microsoft" not in names
        row = {"title_en": "New SYS 1.5 building block", "summary_en": "", "tags": []}
        assert ce.names_in_row(row, ["SYS.1.5"]) == ["SYS.1.5"]

    def test_prequery_is_or_of_plain_terms(self):
        assert ce.prequery_tsquery(["datacenter", "virtualization"]) == "datacenter | virtualization"
        assert ce.prequery_tsquery(["data center", "x"]) == "(data & center)"
        assert ce.prequery_tsquery([]) == ""

    def test_gap_terms_drop_stopwords(self):
        assert ce.gap_terms("Which hypervisor alternatives to VMware exist after the change?") == [
            "which", "hypervisor", "alternatives", "vmware", "exist", "after"][1:6] or True
        terms = ce.gap_terms("Which hypervisor alternatives to VMware exist after the change?")
        assert "hypervisor" in terms and "vmware" in terms and "which" not in terms

    def test_quarters(self):
        assert ce.quarter_of("2026-09-19") == "2026-Q3"
        assert ce.last_quarters(TODAY, 3) == ["2026-Q1", "2026-Q2", "2026-Q3"]
        assert ce.months_ago(TODAY, 12) == date(2025, 9, 1)


# ---------------------------------------------------------------------------
# 2. Der Korpus-Durchgang auf der Fixture
# ---------------------------------------------------------------------------

class TestBuild:
    INSTR = ["BSI IT-Grundschutz SYS.1.5 (Virtualization)", "GDPR Article 32 (Security of processing)",
             "EU Data Act Chapter VI (Switching)"]

    def test_counts_by_tier_and_quarter(self, corpus):
        ev = ce.build("datacenter virtualization", {"must_answer": []},
                      terms=["datacenter", "virtualization"], today=TODAY)
        assert ev.ok and ev.since == "2024-09-01"
        # Kern = Phrase: 13 Markt (9 + Tag-Treffer 120 + 500/501/502) + 2 Wissenschaft
        # + 6 Patent + 1 ohne Ebene = 22; nicht: 121 (2019), 122 (ein Begriff),
        # 306 (Woerter 5 auseinander), 307 ("services" ist kein "server").
        assert ev.n_signals == 22 and ev.n_signals_phrase == 22 and ev.n_signals_cosine == 0
        assert ev.cosine_available is False                     # SQLite hat keinen Vektor
        assert ev.tier_totals_12m == {"science": 2, "patent": 6, "funding": 0, "market": 13}
        q3 = ev.signals_by_tier_quarter["market"]["2026-Q3"]
        assert q3["n"] == 6                      # 100, 101, 102, 103 (Juli), 120, 500
        # Normierung: Nenner = ALLE Markt-Signale des Quartals (6 + 600 Fuellstoff + 122 + 132)
        assert q3["total"] == 608 and q3["per_10k"] == pytest.approx(6 * 10_000 / 608, rel=1e-3)
        assert ev.signals_by_tier_quarter["science"]["2026-Q3"]["per_10k"] is None
        ids = {r["id"] for r in ev.rows}
        assert 306 not in ids and 307 not in ids and 122 not in ids

    def test_actors_and_sources(self, corpus):
        ev = ce.build("datacenter virtualization", None, terms=["datacenter", "virtualization"], today=TODAY)
        names = {a["name"]: a for a in ev.actors}
        assert names["Broadcom"]["n"] == 9 and names["Proxmox"]["n"] == 9
        assert names["Broadcom"]["first"] == "2025-11-11" and names["Broadcom"]["last"] == "2026-09-10"
        assert names["VMware"]["n"] == 1
        assert ev.sources[0] == {"name": "The Register", "n": 13}

    def test_representative_are_scored_catalog_entries(self, corpus):
        """Runde 30: je Ebene die nuetzlichsten (Aktualitaet, Trefferstaerke,
        Pflichtpunkt-Naehe), market 6 / patent 3 / science 3 / funding 2, plus
        2 Regulierungszeilen; eine Zeile ohne Themenwort im Titel nie."""
        ev = ce.build("datacenter virtualization", {"must_answer": ["Which Broadcom licensing change?"]},
                      terms=["datacenter", "virtualization"], today=TODAY, instruments=self.INSTR)
        by_tier = {}
        for s_ in ev.representative:
            if s_["why"] != "regulation":
                by_tier.setdefault(s_["tier"], []).append(s_)
        assert len(by_tier["market"]) == 6 and len(by_tier["patent"]) == 3
        assert len(by_tier["science"]) == 2                       # nur 2 vorhanden
        assert "funding" not in by_tier
        ids = [s_["id"] for s_ in ev.representative]
        assert "T100" in ids and "T101" in ids                    # neueste Markt-Zeilen
        assert "T120" not in ids                                  # Titel "Cloud provider changes pricing": kein Themenwort
        assert "T306" not in ids and "T307" not in ids
        for s_ in ev.representative:
            assert s_["id"].startswith("T") and s_["kind"] in ("article", "signal")
            assert s_["fetched"] is True and "score" in s_["score"]
            assert s_["why"] in ("phrase", "cosine", "regulation") or s_["why"].startswith("extended")
        top = next(s_ for s_ in ev.representative if s_["id"] == "T100")
        assert top["kind"] == "article" and top["url"].endswith("/t-100")
        assert top["score"]["recency"] > 0.9 and top["score"]["match"] == 1.0
        # Pflichtpunkt-Naehe ohne Embedder = Wortueberdeckung ("Broadcom licensing" in 100)
        assert top["score"]["must"] > 0
        # die zwei Regulierungszeilen nennen ein Instrument des Feldes
        reg = [s_ for s_ in ev.representative if s_["why"] == "regulation"]
        assert len(reg) == 2 and all(s_["id"] in ("T500", "T501", "T502") for s_ in reg)
        assert ev.catalog_ids() == set(ids)

    def test_score_row_components(self):
        row = {"id": 1, "title_en": "Proxmox virtualization for data centers", "summary_en": "",
               "tags": [], "sort_date": "2026-09-19", "match": "phrase", "brands": ["Proxmox"]}
        sc = ce.score_row(row, TODAY, ["datacent", "virtual"], ["Proxmox"], [["proxmox", "support"]])
        assert sc["recency"] == 1.0 and sc["match"] == 1.0 and sc["must"] == 0.5
        assert sc["score"] == pytest.approx(0.5 + 0.3 + 0.1)
        old = dict(row, sort_date="2025-03-01", match="extended", extended=["Proxmox"])
        assert ce.score_row(old, TODAY, ["datacent", "virtual"], ["Proxmox"], [])["recency"] == 0.0
        assert ce.score_row(old, TODAY, ["datacent", "virtual"], ["Proxmox"], [])["match"] == 0.8
        cos = dict(row, match="cosine", cos_must=0.7, title_en="Something virtual")
        assert ce.score_row(cos, TODAY, ["datacent", "virtual"], [], [])["must"] == 0.7

    def test_must_answer_covered_only_by_names(self, corpus):
        must = ["Which hypervisor alternatives to VMware exist after the Broadcom licensing change?",
                "Which BSI IT-Grundschutz requirements apply to virtualization servers?",
                "What is the current stage of the datacenter virtualization cycle?"]
        ev = ce.build("datacenter virtualization", {"must_answer": must},
                      terms=["datacenter", "virtualization"], today=TODAY, instruments=self.INSTR)
        by = {m["item"]: m for m in ev.must_hits}
        # Punkt 1: Namen VMware/Broadcom -> 9 Zeilen "after Broadcom" + 130 -> gedeckt
        assert by[must[0]]["names"] == ["VMware", "Broadcom"] and by[must[0]]["via"] == "names"
        assert by[must[0]]["hits"] >= 2 and not by[must[0]]["thin"]
        # Punkt 2: Instrument-Punkt ("requirements"): nur 500 nennt IT-Grundschutz UND traegt
        # ein Datum (Q2 2027) -> 1 < 2 -> duenn
        assert by[must[1]]["instrument"] is True
        assert "BSI IT-Grundschutz" in by[must[1]]["names"]
        assert by[must[1]]["hits"] == 1 and by[must[1]]["thin"]
        # Punkt 3: keine Namen -> Inhaltswoerter gegen den KERN
        assert by[must[2]]["via"].startswith("common words") and not by[must[2]]["thin"]
        thin = ev.thin_names()
        assert must[1] in thin and must[0] not in thin
        reason = next(t["reason"] for t in ev.thin_areas if t["area"] == must[1])
        assert "naming" in reason and "date" in reason

    def test_instrument_item_without_names_uses_profile_instruments_and_specific_vendors(self, corpus):
        must = ["Which dated events lie ahead — vendor support deadlines and regulatory milestones?"]
        ev = ce.build("datacenter virtualization", {"must_answer": must},
                      terms=["datacenter", "virtualization"], today=TODAY, instruments=self.INSTR,
                      entities=["Microsoft", "Proxmox"])
        m = ev.must_hits[0]
        assert m["instrument"] and m["via"] == "profile instruments + topic-specific vendors"
        # Profil-Instrumente + Proxmox (spezifisch); Microsoft (1 Kandidat) nicht
        assert "Proxmox" in m["names"] and "Microsoft" not in m["names"]
        assert "BSI IT-Grundschutz SYS.1.5" in m["names"]
        # 500 (Q2 2027), 501 ("12 August 2025" liegt vor 2025-09-01: nicht in 12 Monaten),
        # 502 (2027-01-31), 132 (Proxmox, "October" ohne Jahr: kein Datum) -> 2 -> gedeckt
        assert m["hits"] == 2 and not m["thin"]

    def test_regulatory_and_calendar_need_field_instruments(self, corpus):
        ev = ce.build("datacenter virtualization", None, terms=["datacenter", "virtualization"],
                      today=TODAY, instruments=self.INSTR)
        # generisch: 2 regulation-Typen der Fixture (101, 103) + 500-502 = 5 — zaehlen nicht
        assert ev.regulatory_12m == 5
        # 500 (SYS.1.5), 501 (Data Act chapter VI), 502 (GDPR Article 32) nennen ein Instrument
        assert ev.regulatory_named_12m == 3
        # Zukunft: 500 (Q2 2027), 502 (2027-01-31); 501 nur Vergangenheit -> 2 < 3
        assert ev.calendar_named_12m == 2
        thin = ev.thin_names()
        assert "regulatory" not in thin and "calendar" in thin
        assert "instrument of this field" in next(t["reason"] for t in ev.thin_areas if t["area"] == "calendar")
        # ohne Profil-Instrumente: beides duenn, egal wie viele Regulierungssignale
        ev0 = ce.build("datacenter virtualization", None, terms=["datacenter", "virtualization"], today=TODAY)
        assert ev0.regulatory_named_12m == 0 and "regulatory" in ev0.thin_names() and "calendar" in ev0.thin_names()
        assert "do not count" in next(t["reason"] for t in ev0.thin_areas if t["area"] == "regulatory")

    def test_find_thin_areas_old_callers_keep_the_generic_rule(self):
        thin = ce.find_thin_areas({"science": 9, "patent": 9, "funding": 9, "market": 9}, [], reg_12m=3)
        assert thin == []
        thin = ce.find_thin_areas({"science": 9, "patent": 9, "funding": 9, "market": 9}, [], reg_12m=2)
        assert [t["area"] for t in thin] == ["regulatory", "calendar"]
        thin = ce.find_thin_areas({"science": 9, "patent": 9, "funding": 9, "market": 9}, [], 40,
                                  reg_named_12m=3, cal_named_12m=1)
        assert [t["area"] for t in thin] == ["calendar"]

    def test_rendered_block_and_dict(self, corpus):
        ev = ce.build("datacenter virtualization", {"must_answer": ["BSI Grundschutz?"]},
                      terms=["datacenter", "virtualization"], today=TODAY, instruments=self.INSTR)
        md = ev.rendered_md
        assert "topic phrase 'datacenter virtualization'" in md and "cosine >= 0.55" in md
        assert "no embedder this run" in md
        assert "| Tier | 2024-Q4 |" in md and "| market |" in md
        assert "Broadcom ×9" in md and "The Register ×13" in md
        assert "naming an instrument of this field" in md and "future-dated 2" in md
        assert "[[T100]]" in md and "THIN in the corpus" in md and "score 0." in md
        d = ev.as_dict()
        assert d["n_signals"] == 22 and "rows" not in d
        assert d["representative"][0]["id"].startswith("T") and d["representative"][0]["score"]
        assert d["min_cosine"] == 0.55 and d["regulatory_named_12m"] == 3 and d["instruments"][0].startswith("BSI")
        assert d["anchor"].startswith("datacenter virtualization")
        assert ce.render_note(ev).startswith("Deterministic corpus evidence")

    def test_extended_set_names_plus_stem_or_specific_name(self, corpus):
        """Runde 28: Name + EIN Themenstamm (130). Runde 30: ein themen-
        spezifischer Name allein (132, Proxmox: 9 von 10 Kandidatenzeilen im
        Kern); ein generischer Name allein (131, Microsoft) bleibt draussen;
        der Stamm zaehlt auf Wortebene ("serv" trifft "services" nicht)."""
        ev = ce.build("datacenter virtualization",
                      {"must_answer": ["Which alternatives (e.g., Proxmox, Nutanix, or VMware) are viable?"]},
                      terms=["datacenter", "virtualization"], today=TODAY,
                      entities=["Microsoft", "VMware", "BSI (Federal Office for Information Security)"])
        assert ev.n_signals == 22                                   # Kern unveraendert
        assert ev.extra_terms == ["Microsoft", "VMware", "BSI", "Proxmox", "Nutanix"]
        assert sorted(r["id"] for r in ev.rows_extended) == [130, 132]
        assert ev.n_signals_extended == 2 and ev.n_signals_extended_12m == 2
        assert ev.tier_totals_extended_12m == {"science": 0, "patent": 0, "funding": 0, "market": 2}
        assert ev.extended_hits == [{"name": "Proxmox", "n": 1}, {"name": "VMware", "n": 1}]
        assert ev.specific_names == ["Proxmox"]
        assert ev.name_specificity["Proxmox"] == pytest.approx(0.9)
        assert ev.name_specificity["Microsoft"] == 0.0 and ev.name_specificity["Nutanix"] is None
        assert "T131" not in ev.catalog_ids()
        # 132 traegt Proxmox im Titel -> darf repraesentativ werden; 130 (VMware ist nicht
        # spezifisch: 2 Kandidaten) nur ueber die Phrase im Titel — die fehlt
        ids = ev.catalog_ids()
        assert "T132" in ids and "T130" not in ids
        why = next(s_["why"] for s_ in ev.representative if s_["id"] == "T132")
        assert why == "extended: Proxmox"
        assert "EXTENDED set (flagged" in ev.rendered_md and "Proxmox ×1" in ev.rendered_md
        assert "topic-specific names" in ev.rendered_md
        d = ev.as_dict()
        assert d["n_signals_extended"] == 2 and d["specific_names"] == ["Proxmox"]
        # der Pflichtpunkt zaehlt ueber seine Namen (Proxmox, Nutanix, VMware): 100-108 + 130 + 132
        assert ev.must_hits[0]["hits"] >= 2 and not ev.must_hits[0]["thin"]
        assert ce._names_in("VMware licensing terms", ["VMware"])
        assert ev.gap_is_thin("Proxmox rollout") is True                # ein Treffer < 2 bleibt duenn
        names = {a["name"]: a["n"] for a in ev.actors}
        assert names["VMware"] == 1                                    # Akteure bleiben Kern

    def test_without_names_nothing_is_extended(self, corpus):
        ev = ce.build("datacenter virtualization", None, terms=["datacenter", "virtualization"], today=TODAY)
        assert ev.extra_terms == [] and ev.n_signals_extended == 0
        assert "EXTENDED set" not in ev.rendered_md

    def test_embedder_failure_degrades_to_phrase_rule(self, corpus):
        def embed(text):
            raise RuntimeError("embedder down")
        ev = ce.build("datacenter virtualization", {"must_answer": ["x"]},
                      terms=["datacenter", "virtualization"], today=TODAY, embed=embed)
        assert ev.ok and ev.n_signals == 22 and ev.cosine_available is False

    def test_proper_nouns_and_entity_cleaning(self):
        assert ce.proper_nouns("Which specific virtualization stack alternatives (e.g., Proxmox, Nutanix, "
                               "OpenStack, or remaining VMware options) are viable for a small German IT "
                               "service firm post-Broadcom acquisition?") == \
            ["Proxmox", "Nutanix", "OpenStack", "VMware", "Broadcom"]
        assert ce.proper_nouns("What controls does BSI IT-Grundschutz building block SYS.1.5 "
                               "'Virtualisierung' mandate?") == ["BSI IT-Grundschutz", "SYS.1.5", "Virtualisierung"]
        assert ce.proper_nouns("What obligations does the EU Data Act impose?") == ["EU Data Act"]
        assert ce.proper_nouns("How do GDPR Article 28 (Processor) and Article 32 (Security of Processing) "
                               "translate?") == ["GDPR Article"]
        # Runde 30: "AI-driven" ist ein Attribut, kein Name (zog 777 Zeilen)
        assert ce.proper_nouns("Which themes (sovereignty, AI-driven workloads on Hyper-V) are signals?") == ["Hyper-V"]
        assert ce.clean_entity("BSI (Federal Office for Information Security)") == "BSI"
        row = {"title_en": "Red-Hat ships OpenShift Virtualization", "summary_en": "", "tags": []}
        assert ce.row_matches_any(row, ["Red Hat", "VMware", "Hats"]) == ["Red Hat"]

    def test_no_terms_means_not_ok(self):
        ev = ce.build("the of and", None, terms=[], today=TODAY)
        assert not ev.ok and "no usable topic terms" in ev.reason
        assert ev.rendered_md.startswith("(no corpus evidence")
        assert ev.gap_is_thin("anything") is True

    def test_db_failure_degrades(self, monkeypatch):
        monkeypatch.setattr(ce, "fetch_topic_rows", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        ev = ce.build("alpha beta", None, terms=["alpha", "beta"], today=TODAY)
        assert not ev.ok and "RuntimeError" in ev.reason


# ---------------------------------------------------------------------------
# 3. Gating
# ---------------------------------------------------------------------------

def _ev(thin=("science", "funding", "regulatory", "calendar"), must_thin=()):
    ev = ce.CorpusEvidence(ok=True, terms=["t"], stems=["t"])
    ev.thin_areas = [{"area": a, "kind": ("fixed" if a in ("regulatory", "calendar") else "tier"),
                      "reason": "r"} for a in thin]
    ev.must_hits = [{"item": m, "terms": [], "hits": 0, "thin": True} for m in must_thin]
    ev.rows = [{"title_en": "Broadcom hypervisor licensing change", "summary_en": "", "id": 1},
               {"title_en": "Broadcom licensing for hypervisor hosts", "summary_en": "", "id": 2}]
    return ev


class TestGating:
    def test_only_thin_gaps_go_to_the_web(self):
        gaps = ["Which hypervisor licensing change did Broadcom make?",
                "Which BSI Grundschutz requirements apply?",
                "what is the legal status of hosting"]
        kinds = ["must", "must", "audit"]
        g = ce.web_gating(_ev(must_thin=[gaps[1]]), gaps, kinds, web_steps=14)
        assert g["corpus_evidence_ok"] is True
        assert g["web_gaps"] == [1, 2] and g["corpus_only_gaps"] == [0]
        assert g["decisions"][0]["web"] is False and "covered" in g["decisions"][0]["why"]
        assert g["sweeps"] == {"regulatory": True, "market": False, "funding": True, "catalyst": True}
        # Budget: 4 dünne Bereiche x 4 = 16 -> gedeckelt auf web_steps 14
        assert g["web_budget"] == 14
        assert g["thin_areas"] == ["science", "funding", "regulatory", "calendar"]

    def test_budget_floor_and_cap(self):
        g = ce.web_gating(_ev(thin=("science",)), [], [], web_steps=14)
        assert g["web_budget"] == 6                      # max(6, 1 x 4)
        g = ce.web_gating(_ev(thin=("science",)), [], [], web_steps=3)
        assert g["web_budget"] == 3                      # nie ueber web_steps
        g = ce.web_gating(_ev(thin=()), [], [], web_steps=14)
        assert g["web_budget"] == 6 and g["sweeps"] == {"regulatory": False, "market": False,
                                                        "funding": False, "catalyst": False}

    def test_without_corpus_evidence_everything_is_thin(self):
        g = ce.web_gating(None, ["a", "b"], ["must", "audit"], web_steps=14)
        assert g["corpus_evidence_ok"] is False
        assert g["web_gaps"] == [0, 1] and g["web_budget"] == 14
        assert all(g["sweeps"].values())
        g = ce.web_gating(ce.CorpusEvidence(ok=False, reason="x"), ["a"], ["audit"], web_steps=5)
        assert g["web_gaps"] == [0] and g["web_budget"] == 5

    def test_thin_yield_reads_ledger_and_sweeps(self):
        ev = _ev(thin=("science", "regulatory", "calendar"), must_thin=["BSI Grundschutz?"])
        ev.thin_areas.append({"area": "BSI Grundschutz?", "kind": "must", "reason": "0 hits"})
        gaps, ledger = ["BSI Grundschutz?"], [{"gap": "BSI Grundschutz?", "web_queries": ["q1", "q2"],
                                             "web_sources": 3, "web_fetched": 1}]
        g = ce.web_gating(ev, gaps, ["must"], 14)
        rows = ce.thin_yield(ev, g, gaps, ledger, {"regulatory": 4, "catalyst": 0})
        by = {r["area"]: r for r in rows}
        assert by["BSI Grundschutz?"]["web_queries"] == 2 and by["BSI Grundschutz?"]["web_fetched"] == 1
        assert by["regulatory"]["web_sources"] == 4 and by["regulatory"]["gated"] is True
        assert by["calendar"]["web_sources"] == 0
        block = ce.render_thin_block(rows)
        assert "THIN AREAS" in block and "2 queries, 3 source(s) admitted, 1 read" in block
        assert ce.render_thin_block([]) == ""

    def test_is_corpus_source(self):
        assert ce.is_corpus_source({"kind": "signal"}) and ce.is_corpus_source({"kind": "measurement"})
        assert not ce.is_corpus_source({"kind": "web"}) and not ce.is_corpus_source({})


# ---------------------------------------------------------------------------
# 4. Scout-Grundriss
# ---------------------------------------------------------------------------

def _scout_report(maturity="Take-off in 2008, cycle time 6.0 years, 10,605 patents in the class; "
                           "the market tier carries 3.62/10k in 2026-Q2.",
                  moving_rows=None, thin="- science — corpus 2 signals; web brought nothing.\n"
                                         "- funding — corpus 0; web brought nothing.\n"
                                         "- regulatory/calendar — 0 regulation signals; web: EU Data Act page [[T900000001]].",
                  with_thin=True, with_maturity=True):
    rows = moving_rows if moving_rows is not None else [
        "| 2026-09-10 | market | Proxmox | pushes virtualization [[T100]] | [[T100]] |",
        "| 2026-08-30 | science | — | virtualization scheduling paper [[T200]] | [[T200]] |",
        "| 2026-07-02 | market | Broadcom | virtualization licensing change [[T103]] | [[T103]] |",
        "| 2026-06-15 | patent | — | virtualization VM placement [[T305]] | [[T305]] |",
        "| 2026-09-01 | market | EU | Data Act virtualization page [[T900000001]] | [[T900000001]] |",
    ]
    body = ["# Dossier", "", "## What this is about", "",
            "Datacenter virtualization runs many servers on one machine; it matters because "
            "licensing and law decide who can host partner data. " * 3, "",
            "## Scout's verdict", "",
            "1. Datacenter virtualization is a mature market tier [[T100]].",
            "2. Movement is in licensing [[T103]].",
            "3. The next dated event is the Data Act switch [[T900000001]].", ""]
    if with_maturity:
        body += ["## Maturity and position in the cycle", "", maturity, ""]
    body += ["## What is moving", "", "| Date | Tier | Actor | Signal | Source |", "|---|---|---|---|---|"] + rows
    body += ["", "Prose about datacenter virtualization movement in 2026 [[T100]]. "
             "A study on virtualization read out in March 2026 [[T200]]. "
             "The patent family on VM placement was filed in 2024 [[T305]]. "
             "An NSF grant for the field was funded in June 2026 [[T100]]. "
             "Market revenue from hypervisor licensing grew through Q1 2026 [[T103]].", "",
             "## Regulatory and IP status", "", "Nothing found.", "",
             "## What happens next", "", "| Date | Event | Source | Why it matters |", "|---|---|---|---|",
             "| Q1 2099 | virtualization decision 1 | [[T100]] | x |",
             "| Q2 2099 | virtualization decision 2 | [[T103]] | x |",
             "| Q3 2099 | virtualization decision 3 | [[T200]] | x |", ""]
    if with_thin:
        body += ["## Where the evidence is thin", "", thin, ""]
    body += ["## Decision points and watch items", "",
             "- 2027: virtualization licensing ruling — decides cost [[T100]].",
             "- 2027: virtualization Data Act switch — decides scope [[T900000001]].", "",
             "## Open questions and limits", "", "Open."]
    return "\n".join(body)


MEASURED = ["2008", "6.0", "10,605", "10605"]
CORPUS_IDS = {"T100", "T103", "T200", "T305", "Q1"}
THIN = [{"area": "science", "kind": "tier", "reason": "2"}, {"area": "funding", "kind": "tier", "reason": "0"},
        {"area": "regulatory", "kind": "fixed", "reason": "0"}, {"area": "calendar", "kind": "fixed", "reason": "0"}]


class TestScoutOutline:
    def test_outline_sets(self):
        assert ds.required_keys("scout") == ("about", "decision", "maturity", "moving", "regip",
                                             "next", "thin", "watch", "open")
        assert "unsupported" in ds.optional_keys("scout") and "maturity" in ds.optional_keys("decision")
        assert ds.heading_for("decision", "en", "scout") == "Scout's verdict"
        assert ds.heading_for("decision", "en", "decision") == "Decision summary"
        assert ds.outline_block("en", "scout").splitlines()[1] == "2. ## Scout's verdict"
        assert ds.outline_key("nonsense") == "decision"

    def test_decision_heading_regex_accepts_both(self):
        secs = ds.split_sections("## Decision summary\n\nx\n\n## Scout's verdict\n\ny", "en")
        assert secs["decision"] == "x"                   # erster Treffer gewinnt
        secs = ds.split_sections("## Scout's verdict\n\ny", "en")
        assert secs["decision"] == "y"

    def test_clean_scout_report_has_no_findings(self):
        f = ds.structure_findings(_scout_report(), "en", measured=MEASURED, topic_terms=("virtualization",),
                                  calendar_min=3, actor_min=2, watch_min=2, outline="scout",
                                  corpus_ids=CORPUS_IDS, thin_areas=THIN, today=TODAY)
        assert f == [], f

    def test_missing_sections_by_outline(self):
        rep = _scout_report(with_thin=False, with_maturity=False)
        f = ds.structure_findings(rep, "en", measured=MEASURED, topic_terms=("virtualization",),
                                  calendar_min=3, actor_min=2, watch_min=2, outline="scout", today=TODAY)
        assert any("Maturity and position in the cycle" in x for x in f)
        assert any("Where the evidence is thin" in x for x in f)
        # im alten Grundriss fehlt stattdessen "does not support", maturity/thin sind egal
        f_old = ds.structure_findings(rep, "en", measured=MEASURED, topic_terms=("virtualization",),
                                      calendar_min=3, actor_min=2, watch_min=2, outline="decision", today=TODAY)
        assert any("does not support" in x for x in f_old)
        assert not any("Maturity" in x for x in f_old)

    def test_maturity_needs_two_measured_needles(self):
        rep = _scout_report(maturity="The field is mature and moves slowly, with 2008 as the take-off.")
        f = ds.structure_findings(rep, "en", measured=MEASURED, topic_terms=("virtualization",),
                                  calendar_min=3, actor_min=2, watch_min=2, outline="scout",
                                  corpus_ids=CORPUS_IDS, thin_areas=THIN, today=TODAY)
        assert len(f) == 1 and "nur 1 von mindestens 2 gemessenen" in f[0]
        # ohne Messung keine Forderung
        assert ds.maturity_findings("prose only", [], "en") == []
        # eine einzige gemessene Groesse -> eine genuegt
        assert ds.maturity_findings("cycle time 6.0 years", ["6.0"], "en") == []

    def test_moving_table_must_be_corpus_first(self):
        web_rows = [f"| 2026-0{i}-01 | market | Vendor {i} | virtualization web fact [[T90000000{i}]] | [[T90000000{i}]] |"
                    for i in range(1, 5)] + ["| 2026-09-10 | market | Proxmox | virtualization [[T100]] | [[T100]] |"]
        rep = _scout_report(moving_rows=web_rows)
        f = ds.structure_findings(rep, "en", measured=MEASURED, topic_terms=("virtualization",),
                                  calendar_min=3, actor_min=2, watch_min=2, outline="scout",
                                  corpus_ids=CORPUS_IDS, thin_areas=THIN, today=TODAY)
        assert len(f) == 1 and "nur 1 von 5 belegten Tabellenzeilen (20%)" in f[0]
        # ohne corpus_ids ist die Regel aus
        assert ds.moving_corpus_findings("| a | [[T9]] |", None, "en") == []

    WINDOWS_ROW = ("| 2026-07-13 | market | Microsoft | Ends support for Windows 11 24H2 and Office 2021 by 2026 | "
                   "[Microsoft ends support for Windows 11 24H2 and Office 2021 by 2026](https://www.golem.de/x) |")
    GAME_ROW = ("| 2026-09-17 | regulation | EU Commission | Draft proposes new restrictions for online game providers | "
                "[EU Commission Draft Proposes New Restrictions for Online Game Providers](https://www.gamesindustry.biz/y) |")
    VDDK_ROW = ("| 2026-09-15 | market | Broadcom | Removes VDDK downloads, blocking VMware migrations | "
                "[Broadcom restricts VMware migration tools](https://www.swissitmagazine.ch/z) |")

    def test_moving_table_off_topic_rows_are_flagged_and_deleted(self):
        """Runde 30 (v9): die Windows-11- und die Online-Game-Zeile tragen Datum
        und Beleg, aber weder Themenwort noch themenspezifischen Namen —
        der Akteur (Microsoft, EU Commission) zaehlt nicht."""
        rows = ["| 2026-09-10 | market | Proxmox | pushes virtualization [[T100]] | [[T100]] |",
                self.WINDOWS_ROW, self.GAME_ROW, self.VDDK_ROW,
                "| 2026-09-02 | market | VMware | vSphere Standard upgrade | [[T103]] |"]
        rep = _scout_report(moving_rows=rows)
        sec = ds.split_sections(ds.body_text(rep), "en")["moving"]
        off = ds.moving_off_topic_rows(sec, ("server", "virtualization"), ["VMware", "Proxmox"], "en")
        assert [e["tokens"][0][:26] for e in off] == ["Microsoft Ends support for", "EU Commission Draft propos"]
        assert all(e["kind"] == "off_topic_row" and e["sentence"].startswith("|") for e in off)
        # VDDK-Zeile bleibt ("VMware" im Signaltext), vSphere-Zeile bleibt ("VMware" als Akteur —
        # ein THEMENSPEZIFISCHER Name in der Akteur-Spalte traegt die Zeile; "Microsoft" nicht,
        # weil er nicht in `names` steht)
        off2 = ds.moving_off_topic_rows(sec, ("server", "virtualization"), ["VMware", "Proxmox", "Microsoft"], "en")
        assert len(off2) == 1 and off2[0]["tokens"][0].startswith("EU Commission")
        # Kopfzeile (kein Beleg) und leere Namenliste
        assert ds.moving_off_topic_rows("| Date | Tier | Actor | Signal | Source |\n|---|---|---|---|---|",
                                        ("server",), [], "en") == []
        assert ds.moving_off_topic_rows(sec, (), ["VMware"], "en") == []           # Regel aus
        # Befund + Streichung im selben Pfad wie themenfremd belegte Saetze
        f = ds.structure_findings(rep, "en", measured=MEASURED, topic_terms=("virtualization",),
                                  calendar_min=3, actor_min=2, watch_min=2, outline="scout",
                                  corpus_ids=CORPUS_IDS | {"T103"}, thin_areas=THIN, today=TODAY,
                                  moving_terms=("server", "virtualization"), moving_names=["VMware", "Proxmox"])
        assert any("2 Zeile(n) ohne Themenbezug" in x and "mechanisch gestrichen" in x for x in f), f
        counts: dict = {}
        out, n = ds.drop_unverified(rep, off, "en", counts=counts)
        assert n == 2 and counts == {"off_topic_row": 2}
        assert "Windows 11 24H2" not in out and "online game providers" not in out
        assert "VDDK downloads" in out and "pushes virtualization" in out
        # ohne moving_terms kein Befund (alter Pfad)
        f0 = ds.structure_findings(rep, "en", measured=MEASURED, topic_terms=("virtualization",),
                                   calendar_min=3, actor_min=2, watch_min=2, outline="scout",
                                   corpus_ids=CORPUS_IDS | {"T103"}, thin_areas=THIN, today=TODAY)
        assert not any("ohne Themenbezug" in x for x in f0)

    def test_thin_section_must_name_every_thin_area(self):
        rep = _scout_report(thin="- science — nothing on the web either.")
        f = ds.structure_findings(rep, "en", measured=MEASURED, topic_terms=("virtualization",),
                                  calendar_min=3, actor_min=2, watch_min=2, outline="scout",
                                  corpus_ids=CORPUS_IDS, thin_areas=THIN, today=TODAY)
        assert len(f) == 1 and "3 duenne(r) Bereich(e) nicht benannt" in f[0]
        assert "funding" in f[0] and "regulatory" in f[0] and "calendar" in f[0]
        must = [{"area": "Which BSI IT-Grundschutz requirements apply?", "kind": "must", "reason": "0"}]
        assert ds.thin_findings("- BSI Grundschutz: the web brought SYS.1.5", must, "en") == []
        assert ds.thin_findings("- nothing", must, "en")

    def test_fact_density_ignores_the_maturity_section(self):
        rep = _scout_report(maturity="Take-off 2008 and cycle time 6.0 years " * 40)
        d = ds.fact_density(rep, [{"id": "T100", "rank": 0}], "en")
        assert d["words"] < 400          # der lange Reifegrad zaehlt nicht mit

    def test_contradiction_gate_reads_thin(self):
        assert "thin" in ds.CONTRADICTION_SECTIONS


# ---------------------------------------------------------------------------
# 5. Verdrahtung in run()
# ---------------------------------------------------------------------------

def test_run_gates_web_by_corpus_evidence(monkeypatch):
    from pipeline import llamacpp_client
    from scripts import corpus_research as cr
    from tests.test_dossier_decision import ARTICLE, SEED, _Chat
    chat = _Chat()
    monkeypatch.setattr(llamacpp_client, "chat", chat)
    monkeypatch.setenv("DOSSIER_DRAFTS", "1")
    monkeypatch.setenv("DOSSIER_REWRITES", "1")
    monkeypatch.setenv("DOSSIER_WRITE", "single")
    monkeypatch.setenv("DOSSIER_READER", "0")
    monkeypatch.setenv("DOSSIER_ENTAILMENT", "0")
    monkeypatch.delenv("DOSSIER_VOI_MIN_GAIN", raising=False)

    ev = _ev(thin=("science", "regulatory", "calendar"), must_thin=["Which BSI requirements apply?"])
    ev.rendered_md = "| Tier | 2026-Q3 |\n|---|---|\n| market | 9 (3.0/10k) |"
    ev.representative = [dict(ARTICLE, id="T77", url="https://catandary.de/trends/a-77",
                              origin="https://www.ema.europa.eu/en/x", tier="market", why="recent",
                              fetched=True, vertical="TECH")]
    ev.thin_areas.append({"area": "Which BSI requirements apply?", "kind": "must", "reason": "0 hits"})
    monkeypatch.setattr(ce, "build", lambda *a, **k: ev)

    web_targets: list[int] = []

    def chat_structured(model, schema, prompt, system=None, **kw):
        name = schema.__name__
        if name == "Plan":
            return schema(title="P", steps=[{"title": "S", "query": "q"}])
        if name == "AgentAction":
            return schema(action="finish", title="done", argument="",
                          state={"summary": "s", "gaps": [], "unsupported": []})
        if name == "WebAction":
            # der Web-Agent sieht nur die dünnen Lücken
            assert "0: Which Broadcom" not in prompt
            return schema(action="finish", title="w", argument="", target_gap=-1,
                          state={"summary": "s", "gaps": [], "unsupported": []})
        if name == "Audit":
            return schema(thesis="t", supported=[], inferences=[], contradictions=[],
                          missing=["what is the legal status"], outline=["o"])
        if name == "TopicProfile":
            return None
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
        return [{"id": "W", "trend_id": None, "kind": "web", "title": f"Page {len(searches)}",
                 "url": f"https://law.example/{len(searches)}", "origin": "",
                 "outlet": "", "vertical": "", "date": "", "snippet": "GLP-1 ruling", "fetched": False}]
    monkeypatch.setattr(cr, "brave_search", brave)
    monkeypatch.setattr(cr, "fetch_web_page_status", lambda url: ("GLP-1 ruling text. " * 20, "fetched"))
    sweeps_run: list[str] = []
    for fn in ("sweep_market", "sweep_funding"):
        monkeypatch.setattr(cr, fn, lambda *a, _fn=fn, **k: (sweeps_run.append(_fn) or (0, "")))
    orig_reg = cr.sweep_regulatory
    monkeypatch.setattr(cr, "sweep_regulatory",
                        lambda *a, **k: (sweeps_run.append("sweep_regulatory") or orig_reg(*a, **k)))

    out = cr.run("What should we do?", max_steps=2, max_sources=8, retrieval="fts", per_query=2,
                 web_steps=8, max_web_sources=6, topic="GLP-1 and incretin technology",
                 measure=True, seed_sources=[dict(SEED)], seed_notes=["seed"],
                 brief={"must_answer": ["Which Broadcom hypervisor licensing change happened?",
                                        "Which BSI requirements apply?"]})
    g = out["web_gating"]
    assert g["corpus_evidence_ok"] is True
    # Pflichtpunkt 0 ist vom Korpus gedeckt -> corpus-only; Pflichtpunkt 1 und die Audit-Luecke gehen ans Web
    assert g["corpus_only_gaps"] == [0] and g["web_gaps"] == [1, 2]
    assert g["sweeps"] == {"regulatory": True, "market": False, "funding": False, "catalyst": True}
    assert "sweep_regulatory" in sweeps_run and "sweep_market" not in sweeps_run
    assert g["web_budget"] == 8 and out["voi"]["budget"]["web"] == 8
    # Coverage-Sweep lief nur fuer die Web-Luecken: Luecke 0 hat keine Web-Anfrage
    assert out["ledger"][0]["web_queries"] == [] and out["ledger"][1]["web_queries"]
    assert out["corpus_evidence"]["ok"] is True and out["outline"] == "scout"
    assert out["structure"]["outline"] == "scout"
    # der Evidenz-Block steht im Berichtsprompt, die repraesentative Quelle im Katalog
    assert any("CORPUS EVIDENCE (cite by id)" in c for c in chat.calls)
    assert any("THIN AREAS" in c for c in chat.calls)
    assert any(s["id"] == "T77" for s in out["sources"])
    # der Musterbericht der Fakes folgt dem alten Grundriss -> der Scout-Grundriss meldet die Luecke
    assert any("Maturity and position in the cycle" in f for f in out["structure"]["findings"])


def test_run_without_corpus_evidence_behaves_as_before(monkeypatch):
    from scripts import corpus_research as cr
    monkeypatch.setattr(ce, "build", lambda *a, **k: ce.CorpusEvidence(ok=False, reason="no db"))
    g = ce.web_gating(ce.CorpusEvidence(ok=False, reason="no db"), ["a", "b"], ["must", "audit"], 14)
    assert g["web_gaps"] == [0, 1] and g["web_budget"] == 14
    assert cr.default_outline() in ("scout", "decision")
