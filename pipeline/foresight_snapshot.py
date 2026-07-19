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

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.foresight import (analyze, build_lineage, build_matrix,
                                cluster_signals, load_signals)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("foresight_snapshot")

VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]
MIN_SIGNALS = 200

DEFAULT_K_RANGE = {"global": (16, 30), "vertical": (8, 16)}


def migrate_foresight_tables() -> None:
    """Create the artifact tables. Idempotent, additive, standalone (not part of
    db.init_db so the live pipeline never touches this migration)."""
    # Backend-specific bits: SERIAL vs AUTOINCREMENT, CURRENT_TIMESTAMP default.
    pk = ("id SERIAL PRIMARY KEY" if db_mod.USE_POSTGRES
          else "id INTEGER PRIMARY KEY AUTOINCREMENT")
    created = ("created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if db_mod.USE_POSTGRES
               else "created_at TEXT DEFAULT (datetime('now'))")
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS foresight_runs ("
            f" {pk},"
            " scope TEXT NOT NULL,"            # 'global' | 'vertical:FOOD' | …
            " tier TEXT,"                      # lead-time tier label (radar ring), nullable
            " status_filter TEXT,"
            " k INTEGER, signals INTEGER,"
            " first_month TEXT, last_month TEXT,"
            f" {created})"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS foresight_clusters ("
            f" {pk},"
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
        # Lineage artifacts (issue #2 phase 1): cross-window cluster evolution.
        blob = "BYTEA" if db_mod.USE_POSTGRES else "BLOB"
        conn.execute(
            "CREATE TABLE IF NOT EXISTS foresight_lineage_runs ("
            f" {pk},"
            " scope TEXT NOT NULL,"
            " status_filter TEXT,"
            " step_months INTEGER, span_months INTEGER,"
            " first_window TEXT, last_window TEXT,"
            " windows INTEGER, nodes INTEGER, edges INTEGER,"
            f" {created})"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS foresight_lineage_nodes ("
            f" {pk},"
            " run_id INTEGER NOT NULL REFERENCES foresight_lineage_runs(id),"
            " node_idx INTEGER,"              # index within the run (edge refs)
            " window_start TEXT, window_end TEXT,"
            " cluster_idx INTEGER,"
            " label TEXT, size INTEGER, sov_share REAL, cohesion REAL,"
            " top_tags TEXT, rep_trend_ids TEXT,"   # JSON arrays
            " status TEXT,"                   # '' | 'emerged' | 'declined'
            f" centroid {blob})"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS foresight_lineage_edges ("
            f" {pk},"
            " run_id INTEGER NOT NULL REFERENCES foresight_lineage_runs(id),"
            " from_node INTEGER, to_node INTEGER,"  # node_idx values within the run
            " sim REAL, drift REAL,"
            " relation TEXT)"                 # continue | split | merge | split_merge
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_flnodes_run "
                     "ON foresight_lineage_nodes(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fledges_run "
                     "ON foresight_lineage_edges(run_id)")


def prune_old_runs(keep_per_scope: int = 1) -> int:
    """Keep only the newest `keep_per_scope` runs per (scope, tier) (+ clusters).
    Tier-scoped radar runs all share scope='global' but different tiers, so the
    key must include tier — otherwise each tier run prunes the previous one."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, scope, tier FROM foresight_runs ORDER BY scope, tier, id DESC"
        ).fetchall()
        seen: dict[tuple, int] = {}
        stale: list[int] = []
        for r in rows:
            rid = r["id"] if isinstance(r, dict) else r[0]
            key = ((r["scope"] if isinstance(r, dict) else r[1]),
                   (r["tier"] if isinstance(r, dict) else r[2]))
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > keep_per_scope:
                stale.append(rid)
        if stale:
            ph = ",".join("?" * len(stale))
            conn.execute(f"DELETE FROM foresight_clusters WHERE run_id IN ({ph})", stale)
            conn.execute(f"DELETE FROM foresight_runs WHERE id IN ({ph})", stale)
        return len(stale)


def prune_old_lineage_runs(keep_per_scope: int = 1) -> int:
    """Same policy as prune_old_runs, for the lineage tables."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, scope FROM foresight_lineage_runs ORDER BY scope, id DESC"
        ).fetchall()
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
            conn.execute(f"DELETE FROM foresight_lineage_edges WHERE run_id IN ({ph})", stale)
            conn.execute(f"DELETE FROM foresight_lineage_nodes WHERE run_id IN ({ph})", stale)
            conn.execute(f"DELETE FROM foresight_lineage_runs WHERE id IN ({ph})", stale)
        return len(stale)


def run_lineage(scope: str, status: str = "signal,published",
                since: str = "2016-01-01", until: str | None = None,
                step_months: int = 3, span_months: int = 12,
                k_range: tuple[int, int] | None = None,
                dim1024: bool = False,
                min_signals: int | None = None) -> int | None:
    """Build and persist a cross-window lineage for one scope. Returns run_id."""
    vertical = scope.split(":", 1)[1] if scope.startswith("vertical:") else None
    if k_range is None:
        k_range = DEFAULT_K_RANGE["vertical" if vertical else "global"]

    t0 = time.time()
    kwargs = {} if min_signals is None else {"min_signals": min_signals}
    res = build_lineage(status=status, vertical=vertical, since=since, until=until,
                        step_months=step_months, span_months=span_months,
                        k_range=k_range, dim1024=dim1024,
                        progress=lambda m: logger.info("[%s] %s", scope, m),
                        **kwargs)
    computed = [w for w in res["windows"] if w["computed"]]
    if not computed:
        logger.warning("[%s] no window reached LINEAGE_MIN_SIGNALS — nothing persisted",
                       scope)
        return None

    with get_connection() as conn:
        returning = " RETURNING id" if db_mod.USE_POSTGRES else ""
        cur = conn.execute(
            "INSERT INTO foresight_lineage_runs (scope, status_filter, step_months,"
            " span_months, first_window, last_window, windows, nodes, edges)"
            f" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?){returning}",
            (scope, status, step_months, span_months,
             computed[0]["start"], computed[-1]["start"],
             len(computed), len(res["nodes"]), len(res["edges"])))
        run_id = cur.lastrowid
        for idx, n in enumerate(res["nodes"]):
            conn.execute(
                "INSERT INTO foresight_lineage_nodes (run_id, node_idx, window_start,"
                " window_end, cluster_idx, label, size, sov_share, cohesion, top_tags,"
                " rep_trend_ids, status, centroid) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, idx, n["window_start"], n["window_end"], n["cluster_idx"],
                 n["label"], n["size"], n["sov_share"], n["cohesion"],
                 json.dumps(n["top_tags"]), json.dumps(n["rep_trend_ids"]),
                 n["status"], n["centroid"]))
        for e in res["edges"]:
            conn.execute(
                "INSERT INTO foresight_lineage_edges (run_id, from_node, to_node,"
                " sim, drift, relation) VALUES (?,?,?,?,?,?)",
                (run_id, e["from_node"], e["to_node"], e["sim"], e["drift"],
                 e["relation"]))
    logger.info("[%s] lineage run %d persisted: %d windows, %d nodes, %d edges, %.0fs",
                scope, run_id, len(computed), len(res["nodes"]), len(res["edges"]),
                time.time() - t0)
    return run_id


def run_snapshot(scope: str, status: str = "signal,published",
                 k: int | None = None, k_range: tuple[int, int] | None = None,
                 limit: int = 0, source_like: str | None = None,
                 tier: str | None = None, dim1024: bool = False,
                 noise_weight: bool = False) -> int | None:
    """Cluster one scope and persist the artifacts. Returns run_id or None."""
    vertical = scope.split(":", 1)[1] if scope.startswith("vertical:") else None
    if k_range is None:
        k_range = DEFAULT_K_RANGE["vertical" if vertical else "global"]

    t0 = time.time()
    # Canonical tier scoping (TIER_FILTERS in the engine): a known tier label
    # scopes the load by itself; an explicit --source-like still overrides.
    from pipeline.foresight import TIER_FILTERS
    tier_scope = tier if (tier in TIER_FILTERS and not source_like) else None
    rows = load_signals(status=status, vertical=vertical,
                        source_like=source_like, limit=limit, dim1024=dim1024,
                        tier=tier_scope)
    logger.info("[%s] %d signals with embedding (status=%s%s%s)", scope, len(rows),
                status, f", source_like={source_like}" if source_like else "",
                f", tier={tier_scope}" if tier_scope else "")
    if len(rows) < MIN_SIGNALS:
        logger.warning("[%s] below MIN_SIGNALS=%d — skipping", scope, MIN_SIGNALS)
        return None

    X = build_matrix(rows)
    labels, centroids, k_used = cluster_signals(X, k=k, k_range=k_range)
    sw = None
    if noise_weight:
        from pipeline.foresight import source_weights_from_pass_rate
        sw = source_weights_from_pass_rate()
        logger.info("[%s] noise-weighting active: %d sources weighted", scope, len(sw))
    result = analyze(rows, X, labels, centroids, source_weights=sw)
    months = result["months"]

    with get_connection() as conn:
        # RETURNING id under PG (the wrapper's .lastrowid reads it); plain
        # lastrowid under SQLite.
        returning = " RETURNING id" if db_mod.USE_POSTGRES else ""
        cur = conn.execute(
            "INSERT INTO foresight_runs (scope, tier, status_filter, k, signals,"
            f" first_month, last_month) VALUES (?, ?, ?, ?, ?, ?, ?){returning}",
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
    ap.add_argument("--dim1024", action="store_true",
                    help="cluster on the Matryoshka 1024-dim column (full-space runs)")
    ap.add_argument("--lineage", action="store_true",
                    help="build a cross-window lineage instead of a single snapshot")
    ap.add_argument("--since", default="2016-01-01", help="lineage: first window start")
    ap.add_argument("--until", default=None, help="lineage: coverage end (default today)")
    ap.add_argument("--step", type=int, default=3, help="lineage: window step in months")
    ap.add_argument("--span", type=int, default=12, help="lineage: window span in months")
    ap.add_argument("--noise-weight", action="store_true",
                    help="down-weight low-pass-rate sources in share/momentum (#2)")
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
        if args.lineage:
            rid = run_lineage(scope, status=args.status, since=args.since,
                              until=args.until, step_months=args.step,
                              span_months=args.span, k_range=k_range,
                              dim1024=args.dim1024)
        else:
            rid = run_snapshot(scope, status=args.status, k=args.k, k_range=k_range,
                               limit=args.limit, source_like=args.source_like,
                               tier=args.tier, dim1024=args.dim1024,
                               noise_weight=args.noise_weight)
        done += 1 if rid else 0
    pruned = (prune_old_lineage_runs(keep_per_scope=1) if args.lineage
              else prune_old_runs(keep_per_scope=1))
    kind = "lineages" if args.lineage else "snapshots"
    print(f"{done}/{len(scopes)} {kind} persisted ({pruned} stale runs pruned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
