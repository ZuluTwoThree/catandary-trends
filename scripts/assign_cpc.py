#!/usr/bin/env python3
"""Materialize the signal→CPC assignment (issue #28, last open backend item).

`nearest_cpcs` (tech_query) projects ONE query vector onto the CPC backbone
ad-hoc. This persists that projection for EVERY embedded signal into
`signal_cpc` (top-K nearest CPC subclasses + cosine distance), so cross-tier
fusion (#9), lead-time aggregation and the frontend can read a cheap indexed
table instead of re-scanning 1.1M vectors per question.

Patents in the corpus carry NATIVE CPC (patent_cpc) — `--verify` measures how
often the native subclass is recovered by the embedding projection, which is
the objective quality metric for the whole bridge idea.

    python scripts/assign_cpc.py                 # assign all missing (resumable)
    python scripts/assign_cpc.py --limit 1000    # first batch only (smoke test)
    python scripts/assign_cpc.py --verify        # native-CPC agreement metric
    python scripts/assign_cpc.py --stats         # coverage/distance distribution

GPU-free: pure SQL over stored embeddings (pgvector).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import USE_POSTGRES, get_connection

TOP_K = 3
# Same projection gate as cpc_leadtime/tech_query: cosine distance below this
# counts as a confident technology match; rows above it are stored anyway so
# consumers can pick their own gate.
CONFIDENT_DIST = 0.55
BATCH = 20_000


def top_k_indices(sims, k: int = TOP_K):
    """Indices of the k highest similarities, best first (numpy core, unit-tested)."""
    import numpy as np
    k = min(k, sims.shape[-1])
    idx = np.argpartition(-sims, k - 1, axis=-1)[..., :k]
    order = np.take_along_axis(sims, idx, axis=-1).argsort(axis=-1)[..., ::-1]
    return np.take_along_axis(idx, order, axis=-1)


def migrate() -> None:
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS signal_cpc ("
            " trend_id INTEGER NOT NULL,"
            " cpc TEXT NOT NULL,"
            " dist REAL NOT NULL,"
            " PRIMARY KEY (trend_id, cpc))")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_signal_cpc_cpc ON signal_cpc (cpc, dist)")


def assign_missing(limit: int | None = None) -> int:
    """Assign top-K CPCs to every embedded trend not yet in signal_cpc."""
    t0 = time.time()
    done = 0
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MIN(id) AS lo, MAX(id) AS hi FROM trends WHERE embedding_1024 IS NOT NULL"
        ).fetchone()
    lo, hi = (row["lo"], row["hi"]) if isinstance(row, dict) else (row[0], row[1])
    if lo is None:
        print("no embedded trends found")
        return 0
    for start in range(lo, hi + 1, BATCH):
        end = min(start + BATCH - 1, hi)
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO signal_cpc (trend_id, cpc, dist) "
                "SELECT t.id, d.symbol, d.dist FROM ("
                "  SELECT id, embedding_1024 FROM trends "
                "  WHERE id BETWEEN ? AND ? AND embedding_1024 IS NOT NULL "
                "    AND NOT EXISTS (SELECT 1 FROM signal_cpc sc WHERE sc.trend_id = trends.id)"
                ") t CROSS JOIN LATERAL ("
                "  SELECT symbol, (embedding_1024 <=> t.embedding_1024) AS dist "
                "  FROM cpc_definitions WHERE embedding_1024 IS NOT NULL "
                f"  ORDER BY embedding_1024 <=> t.embedding_1024 LIMIT {TOP_K}"
                ") d ON CONFLICT DO NOTHING",
                (start, end))
            # wrapper hides rowcount — read it off the raw psycopg2 cursor
            raw = getattr(cur, "_cursor", None)
            n = max(raw.rowcount, 0) if raw is not None else 0
        done += n
        if n:
            rate = done / max(time.time() - t0, 1e-9)
            print(f"  ids {start}–{end}: +{n:,} rows  ({done:,} total, {rate:,.0f} rows/s)",
                  flush=True)
        if limit and done >= limit * TOP_K:
            break
    print(f"assigned {done:,} (trend,cpc) rows in {time.time() - t0:,.0f}s")
    return done


def verify(sample: int = 20_000) -> None:
    """Objective bridge metric: for patent-derived trends (native CPC known),
    how often is the native subclass among the projected top-K?"""
    with get_connection() as conn:
        rows = conn.execute(
            "WITH pat AS ("
            "  SELECT t.id AS trend_id, r.pub_number FROM trends t "
            "  JOIN raw_entries r ON r.id = t.raw_entry_id "
            "  WHERE r.pub_number IS NOT NULL AND t.embedding_1024 IS NOT NULL "
            f"  ORDER BY random() LIMIT {int(sample)}) "
            "SELECT p.trend_id, "
            "       ARRAY(SELECT DISTINCT substr(pc.cpc,1,4) FROM patent_cpc pc "
            "             WHERE pc.pub_number = p.pub_number) AS native, "
            "       ARRAY(SELECT sc.cpc FROM signal_cpc sc WHERE sc.trend_id = p.trend_id "
            "             ORDER BY sc.dist) AS projected "
            "FROM pat p").fetchall()
    n = hit1 = hitk = have = 0
    for r in rows:
        native = set(r["native"] if isinstance(r, dict) else r[1] or [])
        proj = list(r["projected"] if isinstance(r, dict) else r[2] or [])
        if not native or not proj:
            continue
        have += 1
        if proj[0] in native:
            hit1 += 1
        if native & set(proj):
            hitk += 1
        n += 1
    if not n:
        print("no patent trends with both native CPC and projection found")
        return
    print(f"native-CPC recovery on {n:,} patent signals "
          f"(sampled {len(rows):,}, {have:,} usable):")
    print(f"  top-1 = native subclass:      {100 * hit1 / n:5.1f}%")
    print(f"  native ∈ projected top-{TOP_K}:    {100 * hitk / n:5.1f}%")


def stats() -> None:
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM trends WHERE embedding_1024 IS NOT NULL").fetchone()
        assigned = conn.execute(
            "SELECT COUNT(DISTINCT trend_id) FROM signal_cpc").fetchone()
        gated = conn.execute(
            "SELECT COUNT(DISTINCT trend_id) FROM signal_cpc WHERE dist < ?",
            (CONFIDENT_DIST,)).fetchone()
        dist = conn.execute(
            "SELECT percentile_cont(ARRAY[0.1,0.5,0.9]) WITHIN GROUP (ORDER BY dist) "
            "FROM (SELECT trend_id, MIN(dist) AS dist FROM signal_cpc GROUP BY trend_id) q"
        ).fetchone()
    g = lambda r: r[0] if not isinstance(r, dict) else list(r.values())[0]  # noqa: E731
    print(f"embedded trends:            {g(total):,}")
    print(f"with CPC assignment:        {g(assigned):,}")
    print(f"confident (<{CONFIDENT_DIST}):          {g(gated):,}")
    print(f"top-1 distance p10/p50/p90: {g(dist)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Persist signal→CPC projection (#28)")
    ap.add_argument("--limit", type=int, help="stop after ~N trends (smoke test)")
    ap.add_argument("--verify", action="store_true", help="native-CPC agreement metric")
    ap.add_argument("--stats", action="store_true", help="coverage/distance stats")
    args = ap.parse_args()
    if not USE_POSTGRES:
        print("signal_cpc targets Postgres (pgvector)")
        return 1
    migrate()
    if args.verify:
        verify()
        return 0
    if args.stats:
        stats()
        return 0
    assign_missing(limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
