#!/usr/bin/env python3
"""Persist emerging-nest runs for the frontend (second layer next to the clusters).

    python -m pipeline.emerging_snapshot --scope global
    python -m pipeline.emerging_snapshot --scope vertical:FOOD --window-days 120
    python -m pipeline.emerging_snapshot --all-verticals

Detection runs on a recent slice; the history scan then walks the WHOLE archive
so each nest can be dated. Deliberately separate from `foresight_snapshot`: the
cluster layer answers "what is the room talking about", this one answers "what
is new". Both stay on the page at the same time (Owner 2026-09-15).

CPU only, no GPU, no model. On-demand like every radar artifact — no cron.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timedelta

import numpy as np

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.emerging import (HIST_SIM_FLOOR, describe_nests, detect_nests,
                               pick_cells, scan_history, score_nests)
from pipeline.foresight import build_matrix, load_signals
from pipeline.foresight_snapshot import add_columns

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("emerging_snapshot")

VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]
DEFAULT_WINDOW_DAYS = 90
MIN_SIGNALS = 800           # below this a slice has no density to speak of
MAX_WINDOW_DAYS = 180       # thin verticals get a wider slice, once
OLD_TAG_WINDOW = (24, 36)   # months back: the vocabulary baseline


def migrate_emerging_tables() -> None:
    """Create the two artifact tables. Idempotent, additive, standalone."""
    pk = ("id SERIAL PRIMARY KEY" if db_mod.USE_POSTGRES
          else "id INTEGER PRIMARY KEY AUTOINCREMENT")
    created = ("created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if db_mod.USE_POSTGRES
               else "created_at TEXT DEFAULT (datetime('now'))")
    blob = "BYTEA" if db_mod.USE_POSTGRES else "BLOB"
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS emerging_runs ("
            f" {pk},"
            " scope TEXT NOT NULL,"
            " status_filter TEXT,"
            " since TEXT, window_days INTEGER,"
            " signals INTEGER, cells INTEGER, nests INTEGER,"
            " scanned INTEGER,"
            " first_month TEXT, last_month TEXT,"
            f" {created})"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS emerging_nests ("
            f" {pk},"
            " run_id INTEGER NOT NULL REFERENCES emerging_runs(id),"
            " label TEXT,"
            " size INTEGER, cohesion REAL,"
            " n_sources INTEGER, top_source TEXT, top_source_share REAL,"
            " tagged_share REAL,"
            " verticals TEXT, top_tags TEXT, new_terms TEXT,"
            " first_month TEXT, age_months INTEGER,"
            " hits_total INTEGER, hits_recent INTEGER,"
            " novelty_lift REAL, accel REAL,"
            " rep_trend_ids TEXT, rep_titles TEXT,"
            " history_months TEXT, history_hits TEXT,"
            f" centroid {blob}, threshold REAL)"
        )
        # Added after the first run (2026-09-15): how much of a nest ever passed
        # the classification stages. Additive, so an existing table gains it.
        add_columns(conn, "emerging_nests", {
            "tagged_share": "REAL",
            "established_share": "REAL",
        })
        conn.execute("CREATE INDEX IF NOT EXISTS idx_enests_run ON emerging_nests(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_eruns_scope "
                     "ON emerging_runs(scope, created_at)")


def prune_old_emerging_runs(keep_per_scope: int = 1) -> int:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, scope FROM emerging_runs ORDER BY scope, id DESC").fetchall()
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
            conn.execute(f"DELETE FROM emerging_nests WHERE run_id IN ({ph})", stale)
            conn.execute(f"DELETE FROM emerging_runs WHERE id IN ({ph})", stale)
        return len(stale)


def _month_back(n: int, now: datetime | None = None) -> str:
    d = (now or datetime.now()).replace(day=1)
    y, m = d.year, d.month - n
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def run_emerging(scope: str, status: str = "signal,published",
                 window_days: int = DEFAULT_WINDOW_DAYS, cells: int | None = None,
                 min_cohesion: float | None = None, history_since: str | None = None,
                 seed: int = 42, now: datetime | None = None) -> int | None:
    """Detect nests in the recent slice, date them against the archive, persist."""
    vertical = scope.split(":", 1)[1] if scope.startswith("vertical:") else None
    now = now or datetime.now()
    since = (now - timedelta(days=window_days)).strftime("%Y-%m-%d")

    t0 = time.time()
    rows = load_signals(status=status, vertical=vertical, dim1024=True, since=since)
    logger.info("[%s] %d signals in the last %d days (since %s)",
                scope, len(rows), window_days, since)
    if len(rows) < MIN_SIGNALS and window_days < MAX_WINDOW_DAYS:
        # DESIGN and FASHION produce ~1,000 documents in 90 days (first run
        # 2026-09-15) — widen the slice once rather than leave a vertical blind.
        window_days = MAX_WINDOW_DAYS
        since = (now - timedelta(days=window_days)).strftime("%Y-%m-%d")
        rows = load_signals(status=status, vertical=vertical, dim1024=True, since=since)
        logger.info("[%s] thin slice — widened to %d days: %d signals (since %s)",
                    scope, window_days, len(rows), since)
    if len(rows) < MIN_SIGNALS:
        logger.warning("[%s] below MIN_SIGNALS=%d — skipping", scope, MIN_SIGNALS)
        return None

    kwargs = {} if min_cohesion is None else {"min_cohesion": min_cohesion}

    def _detect(mat):
        kk = cells or pick_cells(mat.shape[0])
        found = detect_nests(mat, k=kk, seed=seed, **kwargs)
        logger.info("[%s] %d cells -> %d nests holding %.0f%% of the slice (%.0fs)",
                    scope, kk, len(found),
                    100 * sum(n["members"].size for n in found) / max(mat.shape[0], 1),
                    time.time() - t0)
        return kk, found

    X = build_matrix(rows)
    k, nests = _detect(X)
    if not nests and window_days < MAX_WINDOW_DAYS:
        # A thin vertical can be above MIN_SIGNALS and still have no pocket
        # dense enough in 90 days (DESIGN, 1,619 documents, 2026-09-15).
        # Widening is honest as long as the window is on the page.
        window_days = MAX_WINDOW_DAYS
        since = (now - timedelta(days=window_days)).strftime("%Y-%m-%d")
        del X
        rows = load_signals(status=status, vertical=vertical, dim1024=True, since=since)
        logger.info("[%s] nothing dense enough — widened to %d days: %d signals",
                    scope, window_days, len(rows))
        X = build_matrix(rows)
        k, nests = _detect(X)
    if not nests:
        logger.warning("[%s] no nest passed the quality gate — skipping", scope)
        return None
    describe_nests(nests, rows)

    centroids = np.vstack([n["centroid"] for n in nests])
    thresholds = np.array([max(HIST_SIM_FLOOR, n["radius_p25"]) for n in nests],
                          dtype=np.float32)
    del X, rows

    t1 = time.time()
    hist = scan_history(centroids, thresholds, status=status, vertical=vertical,
                        dim1024=True, since=history_since,
                        tag_windows=(_month_back(OLD_TAG_WINDOW[1], now),
                                     _month_back(OLD_TAG_WINDOW[0], now)),
                        progress=lambda n: logger.info("[%s] scanned %d …", scope, n))
    logger.info("[%s] history: %d documents over %d months (%.0fs)",
                scope, hist["scanned"], len(hist["months"]), time.time() - t1)
    score_nests(nests, hist, now=now)

    months = hist["months"]
    with get_connection() as conn:
        returning = " RETURNING id" if db_mod.USE_POSTGRES else ""
        cur = conn.execute(
            "INSERT INTO emerging_runs (scope, status_filter, since, window_days,"
            " signals, cells, nests, scanned, first_month, last_month)"
            f" VALUES (?,?,?,?,?,?,?,?,?,?){returning}",
            (scope, status, since, window_days, sum(n["size"] for n in nests), k,
             len(nests), hist["scanned"], months[0] if months else None,
             months[-1] if months else None))
        run_id = cur.lastrowid
        for n in nests:
            conn.execute(
                "INSERT INTO emerging_nests (run_id, label, size, cohesion, n_sources,"
                " top_source, top_source_share, tagged_share, established_share,"
                " verticals, top_tags, new_terms,"
                " first_month, age_months, hits_total, hits_recent, novelty_lift,"
                " accel, rep_trend_ids, rep_titles, history_months, history_hits,"
                " centroid, threshold) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, n["label"], n["size"], n["cohesion"], n["n_sources"],
                 n["top_source"], n["top_source_share"], n["tagged_share"],
                 n["established_share"], json.dumps(n["verticals"]),
                 json.dumps(n["top_tags"]), json.dumps(n["new_terms"]),
                 n["first_month"], n["age_months"], n["hits_total"], n["hits_recent"],
                 n["novelty_lift"], n["accel"], json.dumps(n["rep_trend_ids"]),
                 json.dumps(n["rep_titles"]), json.dumps(n["history_months"]),
                 json.dumps(n["history_hits"]),
                 n["centroid"].astype(np.float32).tobytes(),
                 float(max(HIST_SIM_FLOOR, n["radius_p25"]))))
    logger.info("[%s] run %d persisted: %d nests, %.0fs total",
                scope, run_id, len(nests), time.time() - t0)
    return run_id


def main() -> int:
    ap = argparse.ArgumentParser(description="Persist emerging-nest snapshots")
    ap.add_argument("--scope", default=None, help="'global' or 'vertical:<V>'")
    ap.add_argument("--all-verticals", action="store_true",
                    help="run global + one snapshot per vertical")
    ap.add_argument("--status", default="signal,published")
    ap.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
                    help=f"detection slice in days (default {DEFAULT_WINDOW_DAYS})")
    ap.add_argument("--cells", type=int, default=None, help="k for the fine partition")
    ap.add_argument("--min-cohesion", type=float, default=None,
                    help="quality gate for a cell to count as a nest")
    ap.add_argument("--history-since", default=None,
                    help="limit the dating scan (default: the whole archive)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--keep", type=int, default=1, help="runs to keep per scope")
    args = ap.parse_args()

    if not args.scope and not args.all_verticals:
        ap.error("need --scope or --all-verticals")
    migrate_emerging_tables()
    scopes = ([args.scope] if args.scope else []) + \
             (["global"] + [f"vertical:{v}" for v in VERTICALS] if args.all_verticals else [])
    ok = 0
    for scope in scopes:
        if run_emerging(scope, status=args.status, window_days=args.window_days,
                        cells=args.cells, min_cohesion=args.min_cohesion,
                        history_since=args.history_since, seed=args.seed) is not None:
            ok += 1
    pruned = prune_old_emerging_runs(keep_per_scope=args.keep)
    print(f"{ok}/{len(scopes)} emerging runs persisted ({pruned} stale runs pruned).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
