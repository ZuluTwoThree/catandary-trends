"""Tests for the CPC backbone (#28): definition parsing, top-k projection core,
and the signal_cpc table roundtrip (backend-agnostic SQL, so it runs on the
hermetic SQLite test harness)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES = Path(__file__).parent / "fixtures"


# --- parse_cpc.parse_definition ------------------------------------------------

def test_parse_definition_fixture():
    from scripts.parse_cpc import parse_definition

    rec = parse_definition(FIXTURES / "cpc-definition-A99Z.xml")
    assert rec is not None
    assert rec["symbol"] == "A99Z"
    # title keeps the caption but drops the parenthesised cross-ref part
    assert rec["title"] == "SYNTHETIC TEST FOODSTUFFS"
    # definition text embeds title + body paragraphs, whitespace-collapsed
    assert "This place covers:" in rec["definition"]
    assert "Marmalades and jams;" in rec["definition"]
    assert "  " not in rec["definition"]
    # every class-ref is collected exactly once, sorted
    assert rec["cross_refs"] == "A01J,A23B,A23L"


def test_parse_definition_malformed_xml(tmp_path):
    from scripts.parse_cpc import parse_definition

    bad = tmp_path / "cpc-definition-B00B.xml"
    bad.write_text("<definitions><unclosed>")
    assert parse_definition(bad) is None


def test_parse_definition_real_corpus_sample():
    """If the real CPC corpus is present (dev machine), parse a known subclass
    and sanity-check the semantics used for embedding."""
    root = Path(__file__).parent.parent / "pdf" / "cpc"
    files = list(root.rglob("cpc-definition-A23L.xml"))
    if not files:
        pytest.skip("CPC corpus not present")
    from scripts.parse_cpc import parse_definition

    rec = parse_definition(files[0])
    assert rec["symbol"] == "A23L"
    assert rec["title"].startswith("FOODS, FOODSTUFFS OR NON-ALCOHOLIC BEVERAGES")
    assert "This place covers:" in rec["definition"]
    assert len(rec["definition"]) > 500


# --- assign_cpc.top_k_indices ---------------------------------------------------

def test_top_k_indices_orders_best_first():
    from scripts.assign_cpc import top_k_indices

    sims = np.array([0.1, 0.9, 0.3, 0.7, 0.5])
    idx = top_k_indices(sims, k=3)
    assert idx.tolist() == [1, 3, 4]


def test_top_k_indices_batched():
    from scripts.assign_cpc import top_k_indices

    sims = np.array([[0.0, 1.0, 0.5], [0.9, 0.1, 0.8]])
    idx = top_k_indices(sims, k=2)
    assert idx.tolist() == [[1, 2], [0, 2]]


def test_top_k_indices_k_larger_than_n():
    from scripts.assign_cpc import top_k_indices

    sims = np.array([0.2, 0.8])
    idx = top_k_indices(sims, k=5)
    assert idx.tolist() == [1, 0]


# --- signal_cpc table roundtrip (plain SQL — works on the SQLite harness) -------

@pytest.fixture()
def temp_db():
    """Fresh signal_cpc state per test. DATABASE_PATH is pinned by conftest to a
    temp SQLite file (module-level env pattern, same as test_db.py); the table
    is (re)created and emptied here so tests never see each other's rows."""
    import pipeline.db as db_mod
    from scripts import assign_cpc as mod

    mod.migrate()
    with db_mod.get_connection() as conn:
        conn.execute("DELETE FROM signal_cpc")
    yield db_mod
    with db_mod.get_connection() as conn:
        conn.execute("DELETE FROM signal_cpc")


def test_signal_cpc_migrate_and_gate(temp_db):
    """migrate() creates the table; the confident-gate query semantics hold."""
    from scripts import assign_cpc as mod

    with temp_db.get_connection() as conn:
        conn.execute(
            "INSERT INTO signal_cpc (trend_id, cpc, dist) VALUES (?, ?, ?)",
            (1, "A23L", 0.31))
        conn.execute(
            "INSERT INTO signal_cpc (trend_id, cpc, dist) VALUES (?, ?, ?)",
            (1, "C12N", 0.48))
        conn.execute(
            "INSERT INTO signal_cpc (trend_id, cpc, dist) VALUES (?, ?, ?)",
            (1, "G06N", 0.81))
        conn.execute(
            "INSERT INTO signal_cpc (trend_id, cpc, dist) VALUES (?, ?, ?)",
            (2, "H02S", 0.72))

    with temp_db.get_connection() as conn:
        # top-1 per trend = MIN(dist)
        rows = conn.execute(
            "SELECT trend_id, cpc FROM signal_cpc s "
            "WHERE dist = (SELECT MIN(dist) FROM signal_cpc x WHERE x.trend_id = s.trend_id) "
            "ORDER BY trend_id").fetchall()
        top1 = {(r["trend_id"] if isinstance(r, dict) else r[0]):
                (r["cpc"] if isinstance(r, dict) else r[1]) for r in rows}
        assert top1 == {1: "A23L", 2: "H02S"}

        # confident gate keeps only close matches
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM signal_cpc WHERE dist < ?",
            (mod.CONFIDENT_DIST,)).fetchone()
        n = n["n"] if isinstance(n, dict) else n[0]
        assert n == 2

    # idempotent re-migrate must not fail
    mod.migrate()


def test_signal_cpc_pk_prevents_duplicates(temp_db):
    with temp_db.get_connection() as conn:
        conn.execute("INSERT INTO signal_cpc (trend_id, cpc, dist) VALUES (1,'A23L',0.3)")
        with pytest.raises(Exception):
            conn.execute("INSERT INTO signal_cpc (trend_id, cpc, dist) VALUES (1,'A23L',0.4)")
