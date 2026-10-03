#!/usr/bin/env python3
"""Persist emerging-nest runs for the frontend (second layer next to the clusters).

    python -m pipeline.emerging_snapshot --scope global
    python -m pipeline.emerging_snapshot --scope vertical:FOOD --window-days 120
    python -m pipeline.emerging_snapshot --all-verticals

    python -m pipeline.emerging_snapshot --scope tier:market
    python -m pipeline.emerging_snapshot --all-tiers

Detection runs on a recent slice; the history scan then walks the WHOLE archive
so each nest can be dated. Deliberately separate from `foresight_snapshot`: the
cluster layer answers "what is the room talking about", this one answers "what
is new". Both stay on the page at the same time (Owner 2026-09-15).

SCOPES. 'global' and 'vertical:<V>' cut the corpus by subject. 'tier:<t>' cuts
it by CONVERSATION — research, patents, funding, market. Owner 2026-09-15: a
science trend is not a market trend even when the topic is identical. The two
cannot be separated after the fact, because the embedding carries register as
well as topic: a query written in scientific language retrieves science. Over
400,000 recent documents, "perovskite tandem solar cells" matched 146 science
rows above cosine 0.75 and 2 market rows; the market conversation exists, it
just does not speak that way. Clustering each tier on its own is the only way a
market pocket gets found by market vocabulary.

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
from pipeline.emerging import (HIST_SIM_FLOOR, MAX_CELLS, describe_nests,
                               detect_nests, pick_cells, scan_history, score_nests)
from pipeline.foresight import build_matrix, load_signals
from pipeline.tiers import TIERS
from pipeline.foresight_snapshot import add_columns

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("emerging_snapshot")

VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]
DEFAULT_WINDOW_DAYS = 90
MIN_SIGNALS = 800           # below this a slice has no density to speak of
MAX_WINDOW_DAYS = 180       # thin verticals get a wider slice, once
OLD_TAG_WINDOW = (24, 36)   # months back: the vocabulary baseline
ACTOR_WINDOW = (6, 24)      # months back: "late" is the last 6, "early" ends at 24
# Below this a scope has effectively found nothing; the partition is then too
# coarse for how diffuse that corpus is, and one finer attempt is made. The
# market tier is the case that forced it: 41,563 trade-press documents gave 5
# pockets at 207 documents per cell and 46 at 69 (measured 2026-09-15). Trade
# press writes about everything, so its pockets are small.
MIN_NESTS_TARGET = 10
CELL_RETRY_FACTOR = 3


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
            "llm_label": "TEXT",        # model-written name, grounding-checked
            "llm_label_note": "TEXT",   # why it was refused, when it was
            "tiers": "TEXT",            # JSON: per lead-time tier, dated separately
            "tier_order": "TEXT",       # JSON: tiers in the order they started
            "science_to_market_months": "INTEGER",
            "actors_early": "INTEGER",  # distinct market companies/brands…
            "actors_late": "INTEGER",   # …early vs late window
            "group_id": "INTEGER",      # domain runs: sub-group (emerging.group_nests)
            "group_label": "TEXT",      # …and its name, shared by the group's nests
            "calendar": "TEXT",         # JSON: dated by research/patent calendar (calendar_dating)
        })
        add_columns(conn, "emerging_runs", {
            "params": "TEXT",           # JSON: how a run was made (domain service)
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


def name_nests_on_gpu(nests: list[dict], scope: str) -> None:
    """Let the local model name the pockets. Never fatal.

    One handover for all of them, exactly like Research Pulse: if llama-server
    already serves the naming model this is a no-op, otherwise the symlink is
    swapped and restored afterwards. Detection and dating stay CPU-only — this
    is the single GPU step, and a refused handover simply leaves the
    deterministic tag labels in place."""
    from pipeline.nest_naming import NAME_MODEL, name_nests
    try:
        from pipeline.gpu_handover import content_gen_on_llamacpp
        with content_gen_on_llamacpp(NAME_MODEL):
            summary = name_nests(
                nests, model=NAME_MODEL,
                progress=lambda i, n: logger.info("[%s] named %d/%d", scope, i, n))
    except Exception as exc:
        logger.warning("[%s] naming skipped (%s: %s) — tag labels kept",
                       scope, exc.__class__.__name__, exc)
        for n in nests:
            n.setdefault("llm_label", None)
            n.setdefault("llm_label_note", f"handover failed: {exc.__class__.__name__}")
        return
    logger.info("[%s] %d of %d pockets got a model-written name",
                scope, summary["named"], summary["total"])


def _tiers(batch: list[dict]) -> list[str]:
    from pipeline.domains import tiers_of_rows
    return tiers_of_rows(batch)


def trained_domains() -> list[str]:
    """Domains with a trained probe that are still defined in domains.yaml."""
    from pipeline.domains import load_definitions, migrate_domain_tables
    migrate_domain_tables()
    with get_connection() as c:
        trained = {r["key"] for r in c.execute("SELECT key FROM domain_probes").fetchall()}
    return [k for k in load_definitions() if k in trained]


def domain_of(scope: str) -> str | None:
    """'domain:wireless' -> 'wireless' (a freely defined domain, pipeline/domains.py)."""
    return scope.split(":", 1)[1] if scope.startswith("domain:") else None


def load_scope(scope: str, status: str, since: str, probe=None) -> list[dict]:
    """The recent slice of a scope. Vertical and tier scopes filter by label; a domain
    scope takes every signal and keeps the members of the domain's probe — membership
    from the embedding, not from the classifier's label (Owner 30.09.)."""
    vertical, tier = scope_parts(scope)
    rows = load_signals(status=status, vertical=vertical, tier=tier, dim1024=True, since=since)
    if probe is None or not rows:
        return rows
    from pipeline.domains import tiers_of_rows
    X = build_matrix(rows)                  # consumes each row's "_emb" bytes …
    keep = probe.member(X, tiers_of_rows(rows))
    out = []
    for i in np.flatnonzero(keep):
        rows[i]["_emb"] = X[i].tobytes()    # … so the members get theirs back
        out.append(rows[i])
    return out


def scope_parts(scope: str) -> tuple[str | None, str | None]:
    """('vertical:FOOD') -> ('FOOD', None); ('tier:market') -> (None, 'market')."""
    if scope.startswith("vertical:"):
        return scope.split(":", 1)[1], None
    if scope.startswith("tier:"):
        return None, scope.split(":", 1)[1]
    return None, None


def persist_run(scope: str, status: str, since: str, window_days: int, cells: int,
                nests: list[dict], hist: dict, params: dict | None = None) -> int:
    """Write one run and its nests; returns the run id."""
    migrate_emerging_tables()
    months = hist["months"]
    with get_connection() as conn:
        returning = " RETURNING id" if db_mod.USE_POSTGRES else ""
        cur = conn.execute(
            "INSERT INTO emerging_runs (scope, status_filter, since, window_days,"
            " signals, cells, nests, scanned, first_month, last_month, params)"
            f" VALUES (?,?,?,?,?,?,?,?,?,?,?){returning}",
            (scope, status, since, window_days, sum(n["size"] for n in nests), cells,
             len(nests), hist["scanned"], months[0] if months else None,
             months[-1] if months else None, json.dumps(params) if params else None))
        run_id = cur.lastrowid
        for n in nests:
            conn.execute(
                "INSERT INTO emerging_nests (run_id, label, size, cohesion, n_sources,"
                " top_source, top_source_share, tagged_share, established_share,"
                " llm_label, llm_label_note, tiers, tier_order,"
                " science_to_market_months, actors_early, actors_late,"
                " verticals, top_tags, new_terms,"
                " first_month, age_months, hits_total, hits_recent, novelty_lift,"
                " accel, rep_trend_ids, rep_titles, history_months, history_hits,"
                " centroid, threshold, group_id, group_label, calendar)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, n["label"], n["size"], n["cohesion"], n["n_sources"],
                 n["top_source"], n["top_source_share"], n["tagged_share"],
                 n["established_share"], n.get("llm_label"), n.get("llm_label_note"),
                 json.dumps(n.get("tiers") or {}), json.dumps(n.get("tier_order") or []),
                 n.get("science_to_market_months"), n.get("actors_early"),
                 n.get("actors_late"), json.dumps(n["verticals"]),
                 json.dumps(n["top_tags"]), json.dumps(n["new_terms"]),
                 n["first_month"], n["age_months"], n["hits_total"], n["hits_recent"],
                 n["novelty_lift"], n["accel"], json.dumps(n["rep_trend_ids"]),
                 json.dumps(n["rep_titles"]), json.dumps(n["history_months"]),
                 json.dumps(n["history_hits"]),
                 n["centroid"].astype(np.float32).tobytes(),
                 float(max(HIST_SIM_FLOOR, n["radius_p25"])),
                 n.get("group_id"), n.get("group_label"),
                 json.dumps(n["calendar"]) if n.get("calendar") else None))
    return run_id


def run_emerging(scope: str, status: str = "signal,published",
                 window_days: int = DEFAULT_WINDOW_DAYS, cells: int | None = None,
                 min_cohesion: float | None = None, history_since: str | None = None,
                 seed: int = 42, now: datetime | None = None,
                 llm_names: bool = True, history: bool = True) -> int | None:
    """Detect nests in the recent slice, date them against the archive, persist."""
    vertical, tier = scope_parts(scope)
    probe = None
    if domain_of(scope):
        from pipeline.domains import DomainProbe
        probe = DomainProbe.load(domain_of(scope))
    now = now or datetime.now()
    since = (now - timedelta(days=window_days)).strftime("%Y-%m-%d")

    t0 = time.time()
    rows = load_scope(scope, status, since, probe)
    logger.info("[%s] %d signals in the last %d days (since %s)",
                scope, len(rows), window_days, since)
    if len(rows) < MIN_SIGNALS and window_days < MAX_WINDOW_DAYS:
        # DESIGN and FASHION produce ~1,000 documents in 90 days (first run
        # 2026-09-15) — widen the slice once rather than leave a vertical blind.
        window_days = MAX_WINDOW_DAYS
        since = (now - timedelta(days=window_days)).strftime("%Y-%m-%d")
        rows = load_scope(scope, status, since, probe)
        logger.info("[%s] thin slice — widened to %d days: %d signals (since %s)",
                    scope, window_days, len(rows), since)
    if len(rows) < MIN_SIGNALS:
        logger.warning("[%s] below MIN_SIGNALS=%d — skipping", scope, MIN_SIGNALS)
        return None

    kwargs = {} if min_cohesion is None else {"min_cohesion": min_cohesion}

    def _detect(mat, force_k: int | None = None):
        kk = force_k or cells or pick_cells(mat.shape[0])
        found = detect_nests(mat, k=kk, seed=seed, **kwargs)
        logger.info("[%s] %d cells -> %d nests holding %.0f%% of the slice (%.0fs)",
                    scope, kk, len(found),
                    100 * sum(n["members"].size for n in found) / max(mat.shape[0], 1),
                    time.time() - t0)
        return kk, found

    X = build_matrix(rows)
    k, nests = _detect(X)
    if len(nests) < MIN_NESTS_TARGET and not cells:
        finer = min(MAX_CELLS, max(k * CELL_RETRY_FACTOR, 1), X.shape[0] // 20)
        if finer > k:
            logger.info("[%s] only %d pockets at %d documents per cell — retrying "
                        "with %d cells", scope, len(nests), X.shape[0] // max(k, 1), finer)
            k2, nests2 = _detect(X, force_k=finer)
            if len(nests2) > len(nests):
                k, nests = k2, nests2
    if not nests and window_days < MAX_WINDOW_DAYS:
        # A thin vertical can be above MIN_SIGNALS and still have no pocket
        # dense enough in 90 days (DESIGN, 1,619 documents, 2026-09-15).
        # Widening is honest as long as the window is on the page.
        window_days = MAX_WINDOW_DAYS
        since = (now - timedelta(days=window_days)).strftime("%Y-%m-%d")
        del X
        rows = load_scope(scope, status, since, probe)
        logger.info("[%s] nothing dense enough — widened to %d signals",
                    scope, window_days, len(rows))
        X = build_matrix(rows)
        k, nests = _detect(X)
    if not nests:
        logger.warning("[%s] no nest passed the quality gate — skipping", scope)
        return None
    describe_nests(nests, rows, X=X)
    if probe is not None:
        member_titles = [[rows[i].get("title_en") or "" for i in n["members"]] for n in nests]
        domain_titles = [r.get("title_en") or "" for r in rows]

    centroids = np.vstack([n["centroid"] for n in nests])
    thresholds = np.array([max(HIST_SIM_FLOOR, n["radius_p25"]) for n in nests],
                          dtype=np.float32)
    del X, rows

    t1 = time.time()
    # The dating scan stays UNSCOPED by tier on purpose: a market pocket should
    # be dated against everything, so its research prehistory shows up in its
    # tier profile instead of being hidden by the scope it was found in.
    if history:
        from pipeline.history_vectors import available, mark_overlaps
        if available():
            mark_overlaps()     # a document in trends and in the sample counts once
    hist = scan_history(centroids, thresholds, status=status, vertical=vertical,
                        dim1024=True, since=history_since, history=history,
                        tag_windows=(_month_back(OLD_TAG_WINDOW[1], now),
                                     _month_back(OLD_TAG_WINDOW[0], now)),
                        actor_windows=(_month_back(ACTOR_WINDOW[1], now),
                                       _month_back(ACTOR_WINDOW[0], now)),
                        progress=lambda n: logger.info("[%s] scanned %d …", scope, n),
                        member=(None if probe is None else
                                lambda X, batch: probe.member(X, _tiers(batch))))
    logger.info("[%s] history: %d documents + %d from the history sample over %d months, "
                "%d research rows dated 1 January left out (%.0fs)",
                scope, hist["scanned"], hist.get("history_scanned", 0), len(hist["months"]),
                hist.get("science_year_only", 0), time.time() - t1)
    score_nests(nests, hist, now=now)
    if probe is not None:
        # domains: date the pockets by the research and patent calendar (01.10.)
        from pipeline.calendar_dating import date_nests
        from pipeline.domains import load_definitions
        defn = load_definitions().get(domain_of(scope)) or {}
        anchor = [p.strip('"') for p in defn.get("phrases") or []][:8]
        date_nests(nests, member_titles, domain_titles, anchor)

    if llm_names:
        name_nests_on_gpu(nests, scope)

    run_id = persist_run(scope, status, since, window_days, k, nests, hist,
                         params={k: v for k, v in (
                             ("history_sample", hist.get("history_scanned", 0)),
                             ("science_year_only", hist.get("science_year_only", 0))) if v} or None)
    logger.info("[%s] run %d persisted: %d nests, %.0fs total",
                scope, run_id, len(nests), time.time() - t0)
    return run_id


def main() -> int:
    ap = argparse.ArgumentParser(description="Persist emerging-nest snapshots")
    ap.add_argument("--scope", default=None,
                    help="'global', 'vertical:<V>', 'tier:<t>' or 'domain:<key>' (domains.yaml)")
    ap.add_argument("--all-domains", action="store_true",
                    help="one snapshot per trained domain (pipeline.domains train <key>)")
    ap.add_argument("--all-verticals", action="store_true",
                    help="run global + one snapshot per vertical")
    ap.add_argument("--all-tiers", action="store_true",
                    help="one snapshot per lead-time tier (research, patents, "
                         "funding, market) — each conversation on its own")
    ap.add_argument("--status", default="signal,published")
    ap.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
                    help=f"detection slice in days (default {DEFAULT_WINDOW_DAYS})")
    ap.add_argument("--cells", type=int, default=None, help="k for the fine partition")
    ap.add_argument("--min-cohesion", type=float, default=None,
                    help="quality gate for a cell to count as a nest")
    ap.add_argument("--history-since", default=None,
                    help="limit the dating scan (default: the whole archive)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-history", action="store_true",
                    help="date against trends only, without the history sample of patents "
                         "1990 / research from 2010, up to 2026-06 (pipeline/history_vectors.py)")
    ap.add_argument("--no-llm-names", action="store_true",
                    help="skip the naming step (the only GPU step there is)")
    ap.add_argument("--keep", type=int, default=1, help="runs to keep per scope")
    args = ap.parse_args()

    if not args.scope and not args.all_verticals and not args.all_tiers and not args.all_domains:
        ap.error("need --scope, --all-verticals, --all-tiers or --all-domains")
    migrate_emerging_tables()
    scopes = ([args.scope] if args.scope else []) + \
             (["global"] + [f"vertical:{v}" for v in VERTICALS] if args.all_verticals else []) + \
             ([f"tier:{t}" for t in TIERS] if args.all_tiers else []) + \
             ([f"domain:{k}" for k in trained_domains()] if args.all_domains else [])
    ok = 0
    for scope in scopes:
        if run_emerging(scope, status=args.status, window_days=args.window_days,
                        cells=args.cells, min_cohesion=args.min_cohesion,
                        history_since=args.history_since, seed=args.seed,
                        llm_names=not args.no_llm_names,
                        history=not args.no_history) is not None:
            ok += 1
    pruned = prune_old_emerging_runs(keep_per_scope=args.keep)
    print(f"{ok}/{len(scopes)} emerging runs persisted ({pruned} stale runs pruned).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
