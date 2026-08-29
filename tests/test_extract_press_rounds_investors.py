"""Tests fuer die LLM-Investoren-Nachveredelung (#94 Teil 2).

Laeuft komplett gegen SQLite (conftest erzwingt das). startup_press_rounds
existiert dort nicht ueber init_db() (die Postgres-DDL lebt in
ensure_table()/migrate_press_investor_enrichment.py) — die Fixture legt eine
SQLite-taugliche Kopie mit den hier gebrauchten Spalten an, inklusive der
additiven investors_enriched_at-Migration (ein eigener Test prueft, dass die
Enrichment-Funktionen sauber scheitern, wenn diese Spalte fehlt).

Kein echter :8090-Server wird angesprochen — jede LLM-Stelle wird gemockt
(chat_structured / _model_identity_ok), wie von der Aufgabe verlangt.
"""
import os
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_press_investors_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db

import scripts.extract_press_rounds as epr
import scripts.migrate_press_investor_enrichment as migrate_mod

PRESS_ROUNDS_SCHEMA_WITH_MARKER = """
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
    extracted_at TEXT,
    investors_enriched_at TEXT
);
"""

PRESS_ROUNDS_SCHEMA_NO_MARKER = """
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


def _seed(schema: str):
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    with get_connection() as c:
        c.executescript(schema)
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) "
                  "VALUES (1, 'TechCrunch (Test)', 'http://x', 'trade_media', 'BIZ')")
        c.commit()
    return old


@pytest.fixture()
def seeded_db():
    old = _seed(PRESS_ROUNDS_SCHEMA_WITH_MARKER)
    yield
    pdb.DATABASE_PATH = old


@pytest.fixture()
def seeded_db_no_marker():
    old = _seed(PRESS_ROUNDS_SCHEMA_NO_MARKER)
    yield
    pdb.DATABASE_PATH = old


def _raw_entry(conn, id_, title, excerpt):
    conn.execute(
        "INSERT INTO raw_entries (id, source_id, url, title, excerpt, published_date) "
        "VALUES (?, 1, ?, ?, ?, '2026-08-20')",
        (id_, f"http://x/{id_}", title, excerpt))


def _press_row(conn, raw_entry_id, company="Acme", amount_value=None,
               round_label=None, investors="[]", method="llm",
               investors_enriched_at=None):
    conn.execute(
        "INSERT INTO startup_press_rounds "
        "(raw_entry_id, company, amount_value, round_label, investors, method, "
        " confidence, investors_enriched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 0.8, ?)",
        (raw_entry_id, company, amount_value, round_label, investors, method,
         investors_enriched_at))


# --------------------------------------------------------------- candidates

def test_candidate_selection_empty_vs_treated_vs_regex_raw(seeded_db):
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises $8M Series B", "Acme raises $8M led by Sequoia.")
        _raw_entry(c, 2, "Beta raises $5M", "Beta raises $5M led by Index Ventures.")
        _raw_entry(c, 3, "Gamma raises $2M", "Gamma raises $2M seed.")
        _raw_entry(c, 4, "Delta raises $3M", "Delta raises $3M from backers.")
        _raw_entry(c, 5, "Epsilon raises $1M", "Epsilon raises $1M.")
        _raw_entry(c, 6, "Zeta Capital raises $850M fund", "Zeta Capital closes new fund.")
        # 1: leer, unbehandelt, method=llm -> Kandidat
        _press_row(c, 1, company="Acme", investors="[]", method="llm")
        # 2: bereits mit echten Investoren gefuellt (aelterer LLM-Pfad) -> KEIN Kandidat
        _press_row(c, 2, company="Beta", investors='["Index Ventures"]', method="llm")
        # 3: bereits behandelt (Marker gesetzt) -> KEIN Kandidat
        _press_row(c, 3, company="Gamma", investors="[]", method="llm",
                   investors_enriched_at="2026-08-20 00:00:00")
        # 4: regex-roh (method=regex, investors zufaellig nicht '[]') -> Kandidat
        #    ueber die method='regex'-OR-Klausel, unabhaengig vom investors-Inhalt
        _press_row(c, 4, company="Delta", investors='["unparsed junk"]', method="regex")
        # 5: company fehlt -> KEIN Kandidat
        _press_row(c, 5, company=None, investors="[]", method="regex")
        # 6: vc_fund-Rauschen -> KEIN Kandidat
        _press_row(c, 6, company=None, investors="[]", method="regex",
                   round_label="vc_fund")
        c.commit()

    cand = epr.investor_candidates(limit=100, gate_on_hint=False)
    ids = {r["raw_entry_id"] for r in cand}
    assert ids == {1, 4}


def test_investor_hint_gate_filters_out_text_without_cue(seeded_db):
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises $8M", "Acme raises $8M led by Sequoia.")
        _raw_entry(c, 2, "Beta raises $5M", "Beta raises $5M for expansion.")
        _press_row(c, 1, company="Acme", investors="[]", method="llm")
        _press_row(c, 2, company="Beta", investors="[]", method="llm")
        c.commit()

    gated = {r["raw_entry_id"] for r in epr.investor_candidates(100, gate_on_hint=True)}
    ungated = {r["raw_entry_id"] for r in epr.investor_candidates(100, gate_on_hint=False)}
    assert gated == {1}
    assert ungated == {1, 2}


# --------------------------------------------------------------- write logic

def test_write_never_overwrites_nonnull_company_or_amount(seeded_db):
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises $8M Series B", "Acme raises $8M led by Sequoia.")
        _press_row(c, 1, company="Acme Robotics", amount_value=8_000_000.0,
                   round_label="Series B", investors="[]", method="llm")
        c.commit()

    with get_connection() as c:
        epr.write_investor_enrichment(c, 1, ["Sequoia Capital"], "Should Not Overwrite")
        c.commit()

    with get_connection() as c:
        row = dict(c.execute(
            "select * from startup_press_rounds where raw_entry_id = 1").fetchone())
    assert row["company"] == "Acme Robotics"          # untouched
    assert row["amount_value"] == 8_000_000.0           # untouched
    assert row["round_label"] == "Series B"             # untouched (was already set)
    assert row["investors"] == '["Sequoia Capital"]'
    assert row["investors_enriched_at"] is not None


def test_write_fills_round_label_only_when_null(seeded_db):
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises funding", "Acme raises funding led by Sequoia.")
        _press_row(c, 1, company="Acme", round_label=None, investors="[]", method="llm")
        c.commit()

    with get_connection() as c:
        epr.write_investor_enrichment(c, 1, ["Sequoia Capital"], "Seed")
        c.commit()

    with get_connection() as c:
        row = dict(c.execute(
            "select * from startup_press_rounds where raw_entry_id = 1").fetchone())
    assert row["round_label"] == "Seed"


def test_write_stamps_marker_even_with_empty_investors(seeded_db):
    """Grounding may legitimately find nothing to keep — the row must still be
    marked treated (idempotent), not left to retry the LLM forever."""
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises funding", "No investor named.")
        _press_row(c, 1, company="Acme", investors="[]", method="llm")
        c.commit()

    with get_connection() as c:
        epr.write_investor_enrichment(c, 1, [], None)
        c.commit()

    with get_connection() as c:
        row = dict(c.execute(
            "select * from startup_press_rounds where raw_entry_id = 1").fetchone())
    assert row["investors"] == "[]"
    assert row["investors_enriched_at"] is not None


# --------------------------------------------------------------- idempotency

def test_enriched_row_drops_out_of_candidates(seeded_db):
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises funding", "Acme raises funding led by Sequoia.")
        _press_row(c, 1, company="Acme", investors="[]", method="llm")
        c.commit()

    assert len(epr.investor_candidates(100, gate_on_hint=False)) == 1

    with get_connection() as c:
        epr.write_investor_enrichment(c, 1, ["Sequoia"], None)
        c.commit()

    assert len(epr.investor_candidates(100, gate_on_hint=False)) == 0


# --------------------------------------------------------------- schema / grounding

def test_llm_extract_investors_passes_through_mocked_response(monkeypatch):
    stub = epr.InvestorEnrichmentResult(
        investors=[epr.InvestorEntry(name="Sequoia Capital", role="lead")],
        round_type="Series B", amount_usd=8_000_000.0)
    calls = []
    monkeypatch.setattr(epr.llamacpp_client, "chat_structured",
                        lambda **kw: (calls.append(kw), stub)[1])

    res = epr.llm_extract_investors("Qwen3-8B-UD-Q4_K_XL.gguf", "title", "excerpt")

    assert res is stub
    assert len(calls) == 1
    assert calls[0]["schema"] is epr.InvestorEnrichmentResult
    assert calls[0]["temperature"] == 0.0
    assert calls[0]["require_all_fields"] is True


def test_llm_extract_investors_returns_none_on_exhausted_retries(monkeypatch):
    monkeypatch.setattr(epr.llamacpp_client, "chat_structured", lambda **kw: None)
    assert epr.llm_extract_investors("m", "t", "e") is None


def test_ground_investors_drops_unstated_names_and_orders_lead_first():
    investors = [
        epr.InvestorEntry(name="Acme Ventures", role="participant"),
        epr.InvestorEntry(name="Sequoia Capital", role="lead"),
        epr.InvestorEntry(name="Fabricated VC", role="participant"),  # not in text
    ]
    title = "Startup raises $8M Series B"
    excerpt = "led by Sequoia Capital, with participation from Acme Ventures."

    grounded = epr._ground_investors(investors, title, excerpt)

    assert grounded == ["Sequoia Capital", "Acme Ventures"]  # lead first, fake dropped


def test_ground_investors_case_insensitive_and_dedupes():
    investors = [
        epr.InvestorEntry(name="sequoia capital", role="participant"),
        epr.InvestorEntry(name="Sequoia Capital", role="lead"),
    ]
    excerpt = "led by Sequoia Capital."
    grounded = epr._ground_investors(investors, "title", excerpt)
    assert grounded == ["sequoia capital"]  # first occurrence kept, deduped by lowercase key


# --------------------------------------------------------------- model identity guard

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload=None, exc=None, **kw):
        self._payload = payload
        self._exc = exc

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, **kw):
        if self._exc:
            raise self._exc
        return _FakeResponse(self._payload)


def test_model_identity_ok_matches_expected_model(monkeypatch):
    payload = {"data": [{"id": "/models/Qwen3-8B-UD-Q4_K_XL.gguf"}]}
    monkeypatch.setattr(epr.httpx, "Client", lambda **kw: _FakeClient(payload=payload))
    ok, info = epr._model_identity_ok("http://x/v1", "Qwen3-8B-UD-Q4_K_XL.gguf")
    assert ok is True
    assert "Qwen3-8B" in info


def test_model_identity_ok_rejects_wrong_model(monkeypatch):
    payload = {"data": [{"id": "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"}]}
    monkeypatch.setattr(epr.httpx, "Client", lambda **kw: _FakeClient(payload=payload))
    ok, info = epr._model_identity_ok("http://x/v1", "Qwen3-8B-UD-Q4_K_XL.gguf")
    assert ok is False
    assert "Falsches Modell" in info


def test_model_identity_ok_handles_unreachable_server(monkeypatch):
    monkeypatch.setattr(epr.httpx, "Client",
                        lambda **kw: _FakeClient(exc=ConnectionError("refused")))
    ok, info = epr._model_identity_ok("http://x/v1", "Qwen3-8B-UD-Q4_K_XL.gguf")
    assert ok is False
    assert "nicht erreichbar" in info


# --------------------------------------------------------------- enrich_investors driver

def test_enrich_investors_dry_run_makes_no_llm_call(seeded_db, monkeypatch):
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises funding", "Acme raises funding led by Sequoia.")
        _press_row(c, 1, company="Acme", investors="[]", method="llm")
        c.commit()

    def _boom(*a, **kw):
        raise AssertionError("dry-run must not call the LLM")
    monkeypatch.setattr(epr, "llm_extract_investors", _boom)
    monkeypatch.setattr(epr, "_model_identity_ok", _boom)

    rc = epr.enrich_investors(limit=10, apply=False, gate_on_hint=False)

    assert rc == 0
    with get_connection() as c:
        row = dict(c.execute(
            "select * from startup_press_rounds where raw_entry_id = 1").fetchone())
    assert row["investors"] == "[]"
    assert row["investors_enriched_at"] is None


def test_enrich_investors_apply_writes_and_is_idempotent(seeded_db, monkeypatch):
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises $8M Series B",
                  "Acme raises $8M Series B led by Sequoia Capital.")
        _press_row(c, 1, company="Acme", amount_value=8_000_000.0,
                  round_label=None, investors="[]", method="llm")
        c.commit()

    monkeypatch.setattr(epr, "_model_identity_ok",
                        lambda base, model, timeout=5.0: (True, model))
    stub = epr.InvestorEnrichmentResult(
        investors=[epr.InvestorEntry(name="Sequoia Capital", role="lead")],
        round_type="Series B", amount_usd=8_000_000.0)
    monkeypatch.setattr(epr, "llm_extract_investors", lambda model, title, excerpt: stub)

    rc = epr.enrich_investors(limit=10, apply=True, gate_on_hint=False)
    assert rc == 0

    with get_connection() as c:
        row = dict(c.execute(
            "select * from startup_press_rounds where raw_entry_id = 1").fetchone())
    assert row["investors"] == '["Sequoia Capital"]'
    assert row["round_label"] == "Series B"           # filled (was NULL)
    assert row["amount_value"] == 8_000_000.0          # untouched
    assert row["company"] == "Acme"                    # untouched
    assert row["investors_enriched_at"] is not None

    # Idempotent: a second apply run finds no candidates left.
    assert epr.investor_candidates(100, gate_on_hint=False) == []
    rc2 = epr.enrich_investors(limit=10, apply=True, gate_on_hint=False)
    assert rc2 == 0


def test_enrich_investors_apply_aborts_on_model_mismatch(seeded_db, monkeypatch):
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises funding", "Acme raises funding led by Sequoia.")
        _press_row(c, 1, company="Acme", investors="[]", method="llm")
        c.commit()

    monkeypatch.setattr(epr, "_model_identity_ok",
                        lambda base, model, timeout=5.0: (False, "falsches Modell geladen"))

    def _boom(*a, **kw):
        raise AssertionError("must not call the LLM when the identity guard fails")
    monkeypatch.setattr(epr, "llm_extract_investors", _boom)

    rc = epr.enrich_investors(limit=10, apply=True, gate_on_hint=False)

    assert rc == 1
    with get_connection() as c:
        row = dict(c.execute(
            "select * from startup_press_rounds where raw_entry_id = 1").fetchone())
    assert row["investors_enriched_at"] is None


def test_enrich_investors_errored_row_not_stamped_and_retries(seeded_db, monkeypatch):
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises funding", "Acme raises funding led by Sequoia.")
        _press_row(c, 1, company="Acme", investors="[]", method="llm")
        c.commit()

    monkeypatch.setattr(epr, "_model_identity_ok",
                        lambda base, model, timeout=5.0: (True, model))
    monkeypatch.setattr(epr, "llm_extract_investors", lambda model, title, excerpt: None)

    rc = epr.enrich_investors(limit=10, apply=True, gate_on_hint=False)
    assert rc == 0

    with get_connection() as c:
        row = dict(c.execute(
            "select * from startup_press_rounds where raw_entry_id = 1").fetchone())
    assert row["investors_enriched_at"] is None  # not stamped -> retried next run
    assert len(epr.investor_candidates(100, gate_on_hint=False)) == 1


# --------------------------------------------------------------- missing marker column

def test_enrich_investors_fails_clearly_without_migration(seeded_db_no_marker):
    with get_connection() as c:
        _raw_entry(c, 1, "Acme raises funding", "Acme raises funding led by Sequoia.")
        c.execute(
            "INSERT INTO startup_press_rounds "
            "(raw_entry_id, company, investors, method, confidence) "
            "VALUES (1, 'Acme', '[]', 'llm', 0.8)")
        c.commit()

    assert epr._investor_marker_exists() is False
    rc = epr.enrich_investors(limit=10, apply=False, gate_on_hint=False)
    assert rc == 1


# --------------------------------------------------------------- migration script

def test_migration_adds_marker_column_idempotently(seeded_db_no_marker):
    assert migrate_mod.column_exists() is False
    migrate_mod.migrate()
    assert migrate_mod.column_exists() is True
    migrate_mod.migrate()  # second call: no-op, must not raise
    assert migrate_mod.column_exists() is True


def test_migration_report_runs_after_apply(seeded_db):
    # seeded_db already has the marker column (simulates a migrated DB)
    assert migrate_mod.column_exists() is True
    migrate_mod.report()  # must not raise
