#!/usr/bin/env python3
"""Persist foresight cluster/trajectory artifacts for the frontend (issue #3).

Batch layer computes, frontend reads: this job clusters a scope of the signal
space (pipeline.foresight core) and writes one `foresight_runs` row plus its
`foresight_clusters` to the main DB. The Next.js API then serves the latest
run per scope — no clustering ever happens in a request path.

Scopes:
    global            all verticals            (mega altitude, k-range 16..30)
    vertical:FOOD     one primary_vertical     (macro altitude, k-range 8..16)

`--tier` stores a lead-time-tier label on the run/clusters (radar ring for the
frontend); combine with --source-like until the canonical tier→source mapping
lands (issue #2). Table creation is self-contained here — deliberately NOT
wired into db.init_db(), so the running pipeline is untouched.

    python -m pipeline.foresight_snapshot --scope global
    python -m pipeline.foresight_snapshot --scope vertical:FOOD
    python -m pipeline.foresight_snapshot --all-verticals
    python -m pipeline.foresight_snapshot --scope global --tier funding \
        --source-like "NSF,NIH,OpenAIRE,UKRI"
"""
from __future__ import annotations

import argparse
import json
import logging
import time

from pipeline.db import get_connection
from pipeline.foresight import analyze, build_matrix, cluster_signals, load_signals

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("foresight_snapshot")

VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]
MIN_SIGNALS = 200

DEFAULT_K_RANGE = {"global": (16, 30), "vertical": (8, 16)}


def migrate_foresight_tables() -> None:
    """Create the artifact tables. Idempotent, additive, standalone (not part of
    db.init_db so the live pipeline never touches this migration)."""
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS foresight_runs ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " scope TEXT NOT NULL,"            # 'global' | 'vertical:FOOD' | …
            " tier TEXT,"                      # lead-time tier label (radar ring), nullable
            " status_filter TEXT,"
            " k INTEGER, signals INTEGER,"
            " first_month TEXT, last_month TEXT,"
            " created_at TEXT DEFAULT (datetime('now')))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS foresight_clusters ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " run_id INTEGER NOT NULL REFERENCES foresight_runs(id),"
            " cluster_idx INTEGER,"
            " label TEXT,"
            " size INTEGER, cohesion REAL,"
            " mega_trend TEXT, mega_purity REAL,"
            " verticals TEXT, top_tags TEXT,"  # JSON arrays
            " n_sources INTEGER,"
            " momentum TEXT, sov_delta_pp REAL,"
            " tier TEXT,"                      # radar ring (copied from run)
            " rep_trend_ids TEXT, rep_titles TEXT,"  # JSON arrays
            " monthly_series TEXT)"            # JSON [{m,n,share},…]
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fclusters_run "
                     "ON foresight_clusters(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fruns_scope "
                     "ON foresight_runs(scope, created_at)")


def prune_old_runs(keep_per_scope: int = 1) -> int:
    """Keep only the newest `keep_per_scope` runs per scope (+ their clusters).
    Runs accumulate on every snapshot; the frontend only reads the latest."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, scope FROM foresight_runs ORDER BY scope, id DESC").fetchall()
        seen: dict[str, int] = {}
        stale: list[int] = []
        for r in rows:
            rid = r["id"] if isinstance(r, dict) else r[0]
            scope = r["scope"] if isinstance(r, dict) else r[1]
            seen[scope] = seen.get(scope, 0) + 1
            if seen[scope] > keep_per_scope:
                stale.append(rid)
        if stale:
            ph = ",".join("?" * len(stale))
            conn.execute(f"DELETE FROM foresight_clusters WHERE run_id IN ({ph})", stale)
            conn.execute(f"DELETE FROM foresight_runs WHERE id IN ({ph})", stale)
        return len(stale)


def run_snapshot(scope: str, status: str = "signal,published",
                 k: int | None = None, k_range: tuple[int, int] | None = None,
                 limit: int = 0, source_like: str | None = None,
                 tier: str | None = None) -> int | None:
    """Cluster one scope and persist the artifacts. Returns run_id or None."""
    vertical = scope.split(":", 1)[1] if scope.startswith("vertical:") else None
    if k_range is None:
        k_range = DEFAULT_K_RANGE["vertical" if vertical else "global"]

    t0 = time.time()
    rows = load_signals(status=status, vertical=vertical,
                        source_like=source_like, limit=limit)
    logger.info("[%s] %d signals with embedding (status=%s%s)", scope, len(rows),
                status, f", source_like={source_like}" if source_like else "")
    if len(rows) < MIN_SIGNALS:
        logger.warning("[%s] below MIN_SIGNALS=%d — skipping", scope, MIN_SIGNALS)
        return None

    X = build_matrix(rows)
    labels, centroids, k_used = cluster_signals(X, k=k, k_range=k_range)
    result = analyze(rows, X, labels, centroids)
    months = result["months"]

    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO foresight_runs (scope, tier, status_filter, k, signals,"
            " first_month, last_month) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (scope, tier, status, k_used, len(rows),
             months[0] if months else None, months[-1] if months else None))
        run_id = cur.lastrowid
        for c in result["clusters"]:
            conn.execute(
                "INSERT INTO foresight_clusters (run_id, cluster_idx, label, size,"
                " cohesion, mega_trend, mega_purity, verticals, top_tags, n_sources,"
                " momentum, sov_delta_pp, tier, rep_trend_ids, rep_titles,"
                " monthly_series) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, c["cluster_idx"], c["label"], c["size"], c["cohesion"],
                 c["mega_trend"], c["mega_purity"], json.dumps(c["verticals"]),
                 json.dumps(c["top_tags"]), c["n_sources"], c["momentum"],
                 c["sov_delta_pp"], tier, json.dumps(c["rep_trend_ids"]),
                 json.dumps(c["rep_titles"]), json.dumps(c["monthly_series"])))
    logger.info("[%s] run %d persisted: k=%d, %d clusters, %.0fs",
                scope, run_id, k_used, len(result["clusters"]), time.time() - t0)
    return run_id


def main() -> int:
    ap = argparse.ArgumentParser(description="Persist foresight cluster snapshots")
    ap.add_argument("--scope", default=None,
                    help="'global' or 'vertical:<V>' (e.g. vertical:FOOD)")
    ap.add_argument("--all-verticals", action="store_true",
                    help="run global + one snapshot per vertical")
    ap.add_argument("--status", default="signal,published")
    ap.add_argument("--k", type=int)
    ap.add_argument("--k-range", default=None, help="lo,hi override (e.g. 8,16)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--source-like", default=None,
                    help="comma substrings OR-matched on source_name (tier scoping)")
    ap.add_argument("--tier", default=None,
                    help="lead-time tier label stored on run+clusters (radar ring)")
    args = ap.parse_args()

    if not args.scope and not args.all_verticals:
        ap.error("need --scope or --all-verticals")
    k_range = tuple(int(x) for x in args.k_range.split(",")) if args.k_range else None

    migrate_foresight_tables()
    scopes = ([args.scope] if args.scope else []) + \
             (["global"] + [f"vertical:{v}" for v in VERTICALS]
              if args.all_verticals else [])
    done = 0
    for scope in scopes:
        rid = run_snapshot(scope, status=args.status, k=args.k, k_range=k_range,
                           limit=args.limit, source_like=args.source_like,
                           tier=args.tier)
        done += 1 if rid else 0
    pruned = prune_old_runs(keep_per_scope=1)
    print(f"{done}/{len(scopes)} snapshots persisted ({pruned} stale runs pruned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
