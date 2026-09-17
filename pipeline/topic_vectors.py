"""Fill and index `topic_vectors` — the topic engine's search table (2026-09-17).

One row per embedded trend: its lead-time tier (pipeline.tiers, via the SQL
twin `tier_case_sql`) and a copy of the 1024-dim vector. Four partial HNSW
indexes, one per tier, hang on it. Why a side table and not a column on trends
is explained at `db._migrate_topic_vectors`; the short version: an INSERT here
costs trends nothing, an UPDATE there would rebuild the 14 GB HNSW index entry
by entry.

The source type is joined BY NAME, not through raw_entries: every
trends.source_name exists in sources.name (0 misses on 2026-09-17), and the
join through the 22M-row raw_entries made one 50k batch take five minutes. One
name ('Science News') is registered twice with two types; MIN() makes that
deterministic ('research').

Three fills, all idempotent (ON CONFLICT DO NOTHING):
  backfill()  — the whole table in id-range batches, one commit each
  topup()     — rows above the highest trend_id (every topic query, ~ms)
  reconcile() — anti-join over all of trends for rows whose embedding arrived
                late (once a day, seconds)
"""
from __future__ import annotations

import logging
import time

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.tiers import TIERS, tier_case_sql

logger = logging.getLogger("topic_vectors")

BATCH = 100_000
INDEX_NAME = "idx_topic_vectors_{tier}"
#: One in-memory graph build per tier. 4 GB is a session setting (no superuser
#: needed); the server default of 64 MB would make pgvector fall back to its
#: multi-pass path and build for hours.
MAINTENANCE_WORK_MEM = "4GB"


def _insert_sql(extra_where: str) -> tuple[str, list]:
    expr, params = tier_case_sql(t="t2", s="s")
    sql = (
        "INSERT INTO topic_vectors (trend_id, tier, embedding_1024) "
        f"SELECT t2.id, {expr}, t2.embedding_1024 "
        "FROM trends t2 LEFT JOIN (SELECT name, MIN(source_type) AS source_type "
        "                         FROM sources GROUP BY name) s ON s.name = t2.source_name "
        f"WHERE t2.embedding_1024 IS NOT NULL {extra_where} "
        "ON CONFLICT (trend_id) DO NOTHING"
    )
    return sql, params


def _rowcount(cur) -> int:
    n = getattr(cur, "rowcount", None)
    if n is None and hasattr(cur, "_cur"):
        n = getattr(cur._cur, "rowcount", None)
    return max(int(n or 0), 0)


def backfill(batch: int = BATCH, progress=None) -> int:
    """Copy every embedded trend not yet in the table, in id ranges."""
    with get_connection() as conn:
        row = conn.execute("SELECT MIN(id) AS lo, MAX(id) AS hi FROM trends").fetchone()
        done = conn.execute("SELECT COALESCE(MAX(trend_id), 0) AS m FROM topic_vectors").fetchone()
    lo, hi = (row["lo"], row["hi"]) if row else (None, None)
    if lo is None:
        return 0
    start = max(lo - 1, done["m"] if done else 0)
    sql, params = _insert_sql("AND t2.id > ? AND t2.id <= ?")
    total = 0
    t0 = time.time()
    while start < hi:
        end = start + batch
        with get_connection() as conn:
            total += _rowcount(conn.execute(sql, [*params, start, end]))
        start = end
        if progress:
            progress(min(start, hi), hi, total, time.time() - t0)
    return total


def topup() -> int:
    """Rows inserted into trends since the last fill (pkey range scan)."""
    sql, params = _insert_sql("AND t2.id > (SELECT COALESCE(MAX(trend_id), 0) FROM topic_vectors)")
    with get_connection() as conn:
        return _rowcount(conn.execute(sql, params))


def reconcile() -> int:
    """Rows whose embedding arrived after the top-up passed their id."""
    sql, params = _insert_sql(
        "AND NOT EXISTS (SELECT 1 FROM topic_vectors v WHERE v.trend_id = t2.id)")
    with get_connection() as conn:
        return _rowcount(conn.execute(sql, params))


def counts() -> dict[str, int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT tier, COUNT(*) AS n FROM topic_vectors GROUP BY 1").fetchall()
    return {r["tier"]: r["n"] for r in rows}


def index_status() -> dict[str, bool]:
    """Which per-tier HNSW indexes exist (Postgres); all False elsewhere."""
    if not db_mod.USE_POSTGRES:
        return {t: False for t in TIERS}
    with get_connection() as conn:
        rows = conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'topic_vectors' "
                            "AND indexname LIKE ?", ["idx_topic_vectors_%"]).fetchall()
    have = {r["indexname"] for r in rows}
    return {t: INDEX_NAME.format(tier=t) in have for t in TIERS}


def build_indexes(tiers=TIERS, progress=None) -> dict[str, float]:
    """CREATE INDEX CONCURRENTLY, one HNSW per tier, outside any transaction.
    Idempotent (IF NOT EXISTS). Returns seconds per tier."""
    if not db_mod.USE_POSTGRES:
        raise RuntimeError("per-tier HNSW indexes exist only on Postgres")
    import psycopg2
    took: dict[str, float] = {}
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute(f"SET maintenance_work_mem = '{MAINTENANCE_WORK_MEM}'")
        for t in tiers:
            name = INDEX_NAME.format(tier=t)
            t0 = time.time()
            cur.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON topic_vectors "
                        f"USING hnsw (embedding_1024 vector_cosine_ops) WHERE tier = '{t}'")
            took[t] = time.time() - t0
            if progress:
                progress(t, took[t])
    finally:
        conn.close()
    return took


def drop_index(name: str) -> None:
    if not db_mod.USE_POSTGRES:
        return
    import psycopg2
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    conn.autocommit = True
    try:
        conn.cursor().execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
    finally:
        conn.close()
