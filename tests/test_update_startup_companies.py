"""Tests für den inkrementellen Startup-Firmenstamm-Update-Pfad (#94 Teil 1).

Läuft komplett gegen SQLite (conftest erzwingt das) — startup_companies/
startup_events/startup_aliases/startup_press_rounds existieren dort nicht
über init_db() (die Postgres-DDL lebt in scripts/migrate_startup_explorer.py),
darum legt _create_startup_tables() eine SQLite-taugliche Teilkopie des
Schemas an, nur mit den hier gebrauchten Spalten.
"""
import os
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_update_startup_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db
from pipeline.company_norm import classify_new_company_exclusion, trigram_similarity

from scripts.update_startup_companies import (
    apply_match, apply_new, embed_match, load_candidate_groups,
    load_existing_anchors, load_existing_by_name, load_all_names,
    resolve, trigram_self_check,
)

STARTUP_SCHEMA = """
CREATE TABLE startup_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_norm TEXT NOT NULL,
    country TEXT, region TEXT, city TEXT,
    website TEXT,
    founded_date TEXT,
    sector TEXT,
    verticals TEXT DEFAULT '[]',
    cik TEXT, duns TEXT, pic TEXT, lei TEXT, ch_number TEXT,
    wikidata_qid TEXT,
    employees INTEGER,
    first_event_at TEXT, last_event_at TEXT,
    event_count INTEGER DEFAULT 0,
    total_funding_usd REAL,
    founders TEXT DEFAULT '[]',
    excluded TEXT
);
CREATE UNIQUE INDEX idx_sc_cik ON startup_companies (cik) WHERE cik IS NOT NULL;
CREATE UNIQUE INDEX idx_sc_pic ON startup_companies (pic) WHERE pic IS NOT NULL;
CREATE INDEX idx_sc_name_norm ON startup_companies (name_norm);

CREATE TABLE startup_aliases (
    company_id INTEGER NOT NULL,
    alias TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (company_id, alias, source)
);

CREATE TABLE startup_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_date TEXT NOT NULL,
    amount REAL,
    currency TEXT,
    round_label TEXT,
    investors TEXT DEFAULT '[]',
    meta TEXT DEFAULT '{}',
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    raw_entry_id INTEGER,
    UNIQUE (company_id, event_type, event_date, source_url)
);
CREATE INDEX idx_se_company ON startup_events (company_id, event_date);

CREATE TABLE startup_press_rounds (
    raw_entry_id INTEGER PRIMARY KEY,
    company TEXT,
    amount_value REAL,
    currency TEXT,
    amount_text TEXT,
    round_label TEXT,
    investors TEXT DEFAULT '[]',
    method TEXT,
    confidence REAL,
    model TEXT,
    extracted_at TEXT
);
"""


@pytest.fixture()
def seeded_db():
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    with get_connection() as c:
        c.executescript(STARTUP_SCHEMA)
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) "
                  "VALUES (1, 'SEC Form D (Test)', 'http://x', 'api', 'CROSS')")
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) "
                  "VALUES (2, 'SBIR/STTR Awards (US Startup R&D Funding)', 'http://y', 'api', 'CROSS')")
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) "
                  "VALUES (3, 'TechCrunch (Presse-Test)', 'http://z', 'trade_media', 'BIZ')")
        c.commit()
    yield
    pdb.DATABASE_PATH = old


def _formd_entry(conn, id_, cik, name, amount_label="$5.0M", industry="Other Technology",
                 city="AUSTIN", state="TEXAS", date="2026-08-25"):
    cik_padded = str(cik).zfill(10)
    url = (f"https://www.sec.gov/Archives/edgar/data/{cik_padded}/"
           f"00012345267{id_:02d}0001/xslFormDX01/primary_doc.xml")
    title = f"{name} raises {amount_label} private round ({industry})"
    excerpt = (f"[Funding · SEC Form D] {name} ({city}, {state}) filed a Reg-D "
               f"private offering. Industry: {industry}. Filed {date}.")
    conn.execute(
        "INSERT INTO raw_entries (id, source_id, url, title, excerpt, published_date) "
        "VALUES (?, 1, ?, ?, ?, ?)", (id_, url, title, excerpt, date))


def _existing_anchors(conn):
    return load_existing_anchors(conn)


# ---------------------------------------------------------------- new company

def test_new_company_created(seeded_db):
    with get_connection() as c:
        _formd_entry(c, 1, cik=1234567, name="Acme Robotics Inc.")
        c.commit()

    groups = load_candidate_groups(since=None, limit=0)
    assert len(groups) == 1

    with get_connection() as c:
        by_cik, by_duns, by_pic = _existing_anchors(c)
        by_name = load_existing_by_name(c)
    res = resolve(groups, by_cik, by_duns, by_pic, by_name,
                  embed_enabled=False, embed_threshold=0.9)
    assert len(res["new"]) == 1
    assert not res["stage_a"] and not res["stage_b"] and not res["stage_c"]

    with get_connection() as c:
        cid = apply_new(c, res["new"][0][0])
        c.commit()

    with get_connection() as c:
        row = c.execute("select * from startup_companies where id = ?", (cid,)).fetchone()
        n_events = c.execute("select count(*) n from startup_events where company_id = ?",
                             (cid,)).fetchone()["n"]
    assert row["name"].startswith("Acme Robotics")
    assert row["cik"] == "1234567"
    assert row["country"] == "US"
    assert row["region"] == "TX"
    assert row["excluded"] is None
    assert n_events == 1


# ---------------------------------------------------------------- existing match

def test_existing_company_matched_not_duplicated(seeded_db):
    with get_connection() as c:
        c.execute(
            "INSERT INTO startup_companies (name, name_norm, country, region, cik, "
            "wikidata_qid, founded_date, employees) VALUES "
            "('Acme Robotics Inc.', 'acme robotics', 'US', 'TX', '1234567', "
            "'Q999999', '2010-01-01', 42)")
        c.commit()
        existing_id = c.execute("select id from startup_companies").fetchone()["id"]
        # Zweite Form-D-Filing derselben Firma (gleiche CIK, andere Stadt)
        _formd_entry(c, 1, cik=1234567, name="Acme Robotics Inc.",
                    amount_label="$2.0M", city="DALLAS", date="2026-08-26")
        c.commit()

    groups = load_candidate_groups(since=None, limit=0)
    assert len(groups) == 1

    with get_connection() as c:
        by_cik, by_duns, by_pic = _existing_anchors(c)
        by_name = load_existing_by_name(c)
    res = resolve(groups, by_cik, by_duns, by_pic, by_name,
                  embed_enabled=False, embed_threshold=0.9)
    assert len(res["stage_a"]) == 1
    assert res["stage_a"][0][1] == existing_id
    assert not res["new"]

    with get_connection() as c:
        n_new_events = apply_match(c, res["stage_a"][0][0], existing_id)
        c.commit()
    assert n_new_events == 1

    with get_connection() as c:
        n_companies = c.execute("select count(*) n from startup_companies").fetchone()["n"]
        row = c.execute("select * from startup_companies where id = ?", (existing_id,)).fetchone()
        n_events = c.execute("select count(*) n from startup_events where company_id = ?",
                             (existing_id,)).fetchone()["n"]
    assert n_companies == 1  # kein Duplikat
    assert n_events == 1


def test_enrichment_columns_untouched_on_match(seeded_db):
    """wikidata_qid/founded_date sind tabu; city war NULL und darf gefuellt
    werden, region war bereits gesetzt und darf NICHT ueberschrieben werden
    (die neue Filing-Zeile traegt DALLAS/TEXAS, region ist aber schon 'TX')."""
    with get_connection() as c:
        c.execute(
            "INSERT INTO startup_companies (name, name_norm, country, region, city, cik, "
            "wikidata_qid, founded_date) VALUES "
            "('Acme Robotics Inc.', 'acme robotics', 'US', 'TX', NULL, '1234567', "
            "'Q999999', '2010-01-01')")
        c.commit()
        existing_id = c.execute("select id from startup_companies").fetchone()["id"]
        _formd_entry(c, 1, cik=1234567, name="Acme Robotics Inc.",
                    city="DALLAS", date="2026-08-26")
        c.commit()

    groups = load_candidate_groups(since=None, limit=0)
    with get_connection() as c:
        by_cik, by_duns, by_pic = _existing_anchors(c)
        by_name = load_existing_by_name(c)
    res = resolve(groups, by_cik, by_duns, by_pic, by_name,
                  embed_enabled=False, embed_threshold=0.9)
    assert len(res["stage_a"]) == 1

    with get_connection() as c:
        apply_match(c, res["stage_a"][0][0], existing_id)
        c.commit()

    with get_connection() as c:
        row = c.execute("select * from startup_companies where id = ?", (existing_id,)).fetchone()
    assert row["wikidata_qid"] == "Q999999"   # Enrichment-Spalte: unangetastet
    assert row["founded_date"] == "2010-01-01"  # dito
    assert row["region"] == "TX"              # bereits gesetzt: NICHT ueberschrieben
    assert row["city"] == "Dallas"            # war NULL: darf gefuellt werden


# ---------------------------------------------------------------- excluded

def test_excluded_fund_vehicle_rule_fires(seeded_db):
    with get_connection() as c:
        _formd_entry(c, 1, cik=9999999, name="Sovereign Opportunity Fund IV, LLC",
                    industry="Commercial")
        c.commit()

    groups = load_candidate_groups(since=None, limit=0)
    with get_connection() as c:
        by_cik, by_duns, by_pic = _existing_anchors(c)
        by_name = load_existing_by_name(c)
    res = resolve(groups, by_cik, by_duns, by_pic, by_name,
                  embed_enabled=False, embed_threshold=0.9)
    assert len(res["new"]) == 1

    with get_connection() as c:
        cid = apply_new(c, res["new"][0][0])
        c.commit()
    with get_connection() as c:
        row = c.execute("select excluded from startup_companies where id = ?", (cid,)).fetchone()
    assert row["excluded"] == "fund_vehicle"


def test_excluded_press_name_artifact_rule_fires(seeded_db):
    headline = ("UPDATE: Another Really Long Headline Fragment That A Regex "
               "Grabbed Instead Of The Actual Company Name Here")
    with get_connection() as c:
        c.execute(
            "INSERT INTO raw_entries (id, source_id, url, title, published_date) "
            "VALUES (1, 3, 'http://z/1', 'irrelevant', '2026-08-25')")
        c.execute(
            "INSERT INTO startup_press_rounds (raw_entry_id, company, amount_value, "
            "currency, round_label) VALUES (1, ?, 5000000, 'USD', 'Seed')", (headline,))
        c.commit()

    groups = load_candidate_groups(since=None, limit=0)
    assert len(groups) == 1
    with get_connection() as c:
        by_cik, by_duns, by_pic = _existing_anchors(c)
        by_name = load_existing_by_name(c)
    res = resolve(groups, by_cik, by_duns, by_pic, by_name,
                  embed_enabled=False, embed_threshold=0.9)
    assert len(res["new"]) == 1
    with get_connection() as c:
        cid = apply_new(c, res["new"][0][0])
        c.commit()
    with get_connection() as c:
        row = c.execute("select excluded from startup_companies where id = ?", (cid,)).fetchone()
    assert row["excluded"] == "press_name_artifact"


# ---------------------------------------------------------------- idempotency

def test_idempotent_second_run_is_a_no_op(seeded_db):
    with get_connection() as c:
        _formd_entry(c, 1, cik=1234567, name="Acme Robotics Inc.")
        c.commit()

    def _run_once():
        groups = load_candidate_groups(since=None, limit=0)
        with get_connection() as c:
            by_cik, by_duns, by_pic = _existing_anchors(c)
            by_name = load_existing_by_name(c)
        res = resolve(groups, by_cik, by_duns, by_pic, by_name,
                      embed_enabled=False, embed_threshold=0.9)
        with get_connection() as c:
            for g, cid, _ in res["stage_a"] + res["stage_b"] + res["stage_c"]:
                apply_match(c, g, cid)
            for g, _, _ in res["new"]:
                apply_new(c, g)
            c.commit()
        return res

    res1 = _run_once()
    assert len(res1["new"]) == 1

    with get_connection() as c:
        n_companies_after_1 = c.execute("select count(*) n from startup_companies").fetchone()["n"]
        n_events_after_1 = c.execute("select count(*) n from startup_events").fetchone()["n"]

    res2 = _run_once()
    assert len(res2["new"]) == 0
    assert len(res2["stage_a"]) == 0 and len(res2["stage_b"]) == 0

    with get_connection() as c:
        n_companies_after_2 = c.execute("select count(*) n from startup_companies").fetchone()["n"]
        n_events_after_2 = c.execute("select count(*) n from startup_events").fetchone()["n"]
    assert n_companies_after_2 == n_companies_after_1 == 1
    assert n_events_after_2 == n_events_after_1 == 1


# ---------------------------------------------------------------- Stage B (name+geo, no hard anchor)

def test_stage_b_name_geo_match_without_hard_anchor(seeded_db):
    """SBIR-Kandidat ohne DUNS-Treffer im CSV-Cache muss trotzdem per
    Name+Geo an eine bestehende Firma andocken."""
    with get_connection() as c:
        c.execute(
            "INSERT INTO startup_companies (name, name_norm, country, region) VALUES "
            "('Quantum Widgets Inc', 'quantum widgets', 'US', 'CA')")
        c.commit()
        existing_id = c.execute("select id from startup_companies").fetchone()["id"]
        c.execute(
            "INSERT INTO raw_entries (id, source_id, url, title, excerpt, published_date) "
            "VALUES (1, 2, 'http://sbir/1', "
            "'Quantum Widgets Inc wins $150k STTR Phase I award (National Science Foundation)', "
            "'[Funding · STTR Phase I · NSF · Palo Alto, CA · $150k] …', '2026-08-25')")
        c.commit()

    groups = load_candidate_groups(since=None, limit=0)
    with get_connection() as c:
        by_cik, by_duns, by_pic = _existing_anchors(c)
        by_name = load_existing_by_name(c)
    res = resolve(groups, by_cik, by_duns, by_pic, by_name,
                  embed_enabled=False, embed_threshold=0.9)
    assert len(res["stage_b"]) == 1
    assert res["stage_b"][0][1] == existing_id
    assert not res["new"]


# ---------------------------------------------------------------- Stage C degradation

def test_embed_match_reports_unavailable_when_server_unreachable(seeded_db):
    from pipeline.startup_resolution import Group, _event
    from datetime import date
    g = Group()
    g.names.append("Whatever Inc")
    g.events.append(_event("regd_offering", date(2026, 8, 1), "t", "u"))

    def failing_embed_fn(text):
        return None  # entspricht llamacpp_client.generate_embedding-Fehlerpfad

    cid, sim, status = embed_match(g, threshold=0.9, embed_fn=failing_embed_fn, search_fn=None)
    assert status == "unavailable" and cid is None


def test_embed_match_skipped_entirely_without_postgres(seeded_db):
    """USE_POSTGRES ist unter den Tests immer False (SQLite) — Stufe C darf
    nie versuchen, embedding_1024/pgvector anzusprechen."""
    from pipeline.startup_resolution import Group, _event
    from datetime import date
    import pipeline.db as db_mod
    assert db_mod.USE_POSTGRES is False
    g = Group()
    g.names.append("Whatever Inc")
    g.events.append(_event("regd_offering", date(2026, 8, 1), "t", "u"))

    calls = []

    def spy_embed_fn(text):
        calls.append(text)
        return [0.1, 0.2]

    cid, sim, status = embed_match(g, threshold=0.9, embed_fn=spy_embed_fn, search_fn=None)
    assert status == "unavailable" and cid is None
    assert calls == []  # embed_fn wurde gar nicht erst aufgerufen


# ---------------------------------------------------------------- trigram self-check

def test_trigram_self_check_finds_near_miss():
    all_names = {1: "acme robotics inc", 2: "totally unrelated company"}
    from scripts.update_startup_companies import Group as G
    g = G()
    g.names.append("Acme Robotic Inc")  # fast identisch, aber ein neuer Kandidat
    findings = trigram_self_check([(g, None, None)], all_names, threshold=0.6)
    assert len(findings) == 1
    assert findings[0]["near_miss_id"] == 1


def test_trigram_self_check_no_finding_for_distinct_name():
    all_names = {1: "acme robotics inc"}
    from scripts.update_startup_companies import Group as G
    g = G()
    g.names.append("Zzyzx Quantum Dynamics")
    findings = trigram_self_check([(g, None, None)], all_names, threshold=0.6)
    assert findings == []


# ---------------------------------------------------------------- classify_new_company_exclusion

class TestClassifyExclusion:
    def test_fund_vehicle(self):
        assert classify_new_company_exclusion("Sovereign Fund IV, LLC") == "fund_vehicle"

    def test_press_artifact(self):
        assert classify_new_company_exclusion(
            "Another Super Angel Levels Up: Aydin Senkut's Felicis Ventures Closes $70M",
            {"press"}) == "press_name_artifact"

    def test_press_artifact_only_applies_to_press_source(self):
        # Gleicher Doppelpunkt-Name, aber NICHT aus Presse-Extraktion -> keine Regel
        assert classify_new_company_exclusion("Weird: Name Co", {"formd"}) is None

    def test_ordinary_name_not_excluded(self):
        assert classify_new_company_exclusion("Acme Robotics Inc", {"formd"}) is None


# ---------------------------------------------------------------- Regression: Rebuild-Import unveraendert

def test_build_startup_companies_still_importable_and_wired():
    """Import-Smoke fuer die Refaktorierung in pipeline/startup_resolution.py:
    scripts/build_startup_companies.py muss dieselben Namen weiter re-exportieren,
    ohne eigene Kopie."""
    import scripts.build_startup_companies as b
    import pipeline.startup_resolution as res_mod
    for name in ("Group", "merge", "load_formd", "load_sbir", "load_cordis",
                "load_press", "_geo_compatible", "_corroborates_regd", "_event",
                "parse_money", "_us_state"):
        assert getattr(b, name) is getattr(res_mod, name), (
            f"{name} ist in build_startup_companies.py keine Referenz auf "
            f"dieselbe Funktion aus pipeline.startup_resolution mehr")


def test_strip_possessive_prefix_cases():
    # Geo-Possessiv-Praefixe der Presse-Extraktion (#94-Dry-Run 2026-08-29)
    from pipeline.company_norm import strip_possessive_prefix as f
    assert f("Stockholm’s Pixelgen Technologies") == "Pixelgen Technologies"
    assert f("Canada’s Mid-Day Squares") == "Mid-Day Squares"
    assert f("Scotland's Singular Photonics") == "Singular Photonics"
    # bleibt unberuehrt: nichts nach dem Possessiv / Zwei-Token-Praefix / Kurzmarke
    assert f("McDonald's") == "McDonald's"
    assert f("Ninety One's Africa Credit Opportunities strategy").startswith("Ninety")
    assert f("Levi's Jeans Co") == "Levi's Jeans Co"
    assert f("") == ""
