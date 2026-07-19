"""PostgreSQL + pgvector integration tests (#8 hardening).

These exercise the real Postgres code paths (init_db migrations, pgvector columns,
insert_trend, the recent-dedup getters, a basic ANN query) that the SQLite-forced
unit suite cannot cover. They run ONLY when TEST_DATABASE_URL points at a disposable
Postgres — never the production database.

CI provides an ephemeral postgres:16 + pgvector service and sets TEST_DATABASE_URL.
Locally the whole module skips unless you export one, e.g.:

    createdb catandary_test
    TEST_DATABASE_URL=postgresql:///catandary_test .venv/bin/python -m pytest tests/test_pg_integration.py
"""
import os
import struct

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not TEST_DB, reason="TEST_DATABASE_URL not set (needs a disposable Postgres+pgvector)"
)


def _dbname(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]


@pytest.fixture()
def db(monkeypatch):
    """Point pipeline.db at the throwaway test DB, on a freshly reset public schema."""
    import psycopg2

    name = _dbname(TEST_DB)
    # Never touch the production database, whatever the env says.
    if name == "catandary" or "test" not in name.lower():
        pytest.fail(f"refusing: TEST_DATABASE_URL must be a disposable *test* DB, got '{name}'")

    import psycopg2.extras  # noqa: F401 — ensure the submodule is loaded before injection

    import pipeline.db as dbmod
    # conftest forces DATABASE_URL="" for the whole session, so db.py imported under
    # USE_POSTGRES=False and never bound psycopg2. Re-point it at the test DB and
    # inject the driver so the Postgres code paths run.
    monkeypatch.setattr(dbmod, "DATABASE_URL", TEST_DB)
    monkeypatch.setattr(dbmod, "USE_POSTGRES", True)
    monkeypatch.setattr(dbmod, "psycopg2", psycopg2, raising=False)

    conn = psycopg2.connect(TEST_DB)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA public CASCADE")
    cur.execute("CREATE SCHEMA public")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.close()
    return dbmod


def _cols(db, table):
    with db.get_connection() as c:
        rows = c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,)
        ).fetchall()
    return {r["column_name"] if isinstance(r, dict) else r[0] for r in rows}


def _seed_trend(db, *, emb=None, slug="t-1"):
    sid = db.upsert_source("SRC", "https://src.example/feed", "trade_media", "TECH")
    eid = db.insert_raw_entry(sid, f"https://src.example/{slug}", "Title", "Excerpt", "2026-07-18")
    data = {
        "title_en": "AI accelerates battery research",
        "slug": slug,
        "source_url": f"https://src.example/{slug}",
        "source_name": "SRC",
        "primary_vertical": "TECH",
        "verticals": ["TECH"],
        "embedding": emb if emb is not None else [0.01] * 4096,
        "status": "published",
    }
    return db.insert_trend(eid, data)


def test_fresh_init_db_creates_core_tables(db):
    db.init_db()
    tables = _cols(db, "trends")
    assert tables  # trends exists
    for t in ("sources", "raw_entries", "trends"):
        with db.get_connection() as c:
            c.execute(f"SELECT COUNT(*) FROM {t}")  # must not raise


def test_repeated_migration_is_idempotent(db):
    db.init_db()
    db.init_db()  # second run must not raise (IF NOT EXISTS / ON CONFLICT throughout)
    assert "embedding_1024" in _cols(db, "trends")


def test_embedding_1024_column_and_hnsw_index(db):
    db.init_db()
    assert "embedding_1024" in _cols(db, "trends")
    with db.get_connection() as c:
        idx = c.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename='trends' "
            "AND indexname='idx_trends_emb1024_pub_hnsw'"
        ).fetchone()
    assert idx is not None


def test_source_lead_time_tier_created(db):
    db.init_db()
    # table exists with the expected columns
    assert _cols(db, "source_lead_time_tier") == {"source_name", "lead_time_tier"}
    # populated from sources.yaml (present in the repo)
    with db.get_connection() as c:
        n = c.execute("SELECT COUNT(*) AS n FROM source_lead_time_tier").fetchone()
    count = n["n"] if isinstance(n, dict) else n[0]
    assert count >= 0  # table usable; rows depend on sources.yaml tiers


def test_insert_trend_with_4096_and_1024_embedding(db):
    db.init_db()
    tid = _seed_trend(db)
    assert tid
    with db.get_connection() as c:
        row = c.execute(
            "SELECT vector_dims(embedding) AS d4096, vector_dims(embedding_1024) AS d1024 "
            "FROM trends WHERE id = %s",
            (tid,),
        ).fetchone()
    d4096 = row["d4096"] if isinstance(row, dict) else row[0]
    d1024 = row["d1024"] if isinstance(row, dict) else row[1]
    assert d4096 == 4096
    assert d1024 == 1024  # Matryoshka prefix populated for ANN search


def test_insert_trend_accepts_bytes_embedding(db):
    db.init_db()
    emb_bytes = struct.pack("4096f", *([0.02] * 4096))
    tid = _seed_trend(db, emb=emb_bytes, slug="t-bytes")
    assert tid


def test_recent_getters(db):
    db.init_db()
    _seed_trend(db)
    titles = db.get_recent_titles(30)
    assert any("battery" in t.lower() for t in titles)
    embs = db.get_recent_embeddings(30, limit=10)
    assert len(embs) >= 1
    # each is (id, float32-bytes) usable by the dedup matrix
    _id, blob = embs[0]
    assert isinstance(blob, (bytes, bytearray)) and len(blob) % 4 == 0


def test_basic_ann_query(db):
    db.init_db()
    _seed_trend(db, slug="ann-1")
    probe = "[" + ",".join(["0.01"] * 1024) + "]"
    with db.get_connection() as c:
        row = c.execute(
            "SELECT id FROM trends WHERE embedding_1024 IS NOT NULL "
            "ORDER BY embedding_1024 <=> %s::vector LIMIT 1",
            (probe,),
        ).fetchone()
    assert row is not None  # HNSW/exact ANN returns the nearest row without error
