"""Signal space, stage 3: the individual signals as one 3D point cloud (2026-09-27).

Stages 1 and 2 (/trends/foresight/map) show the emerging NESTS — 55-94
centroids. This module places the signals themselves: a deterministic sample of
the embedded corpus, projected to three dimensions with UMAP, with the nests of
the latest global emerging run placed in the same cloud and every point tagged
with the nest it belongs to.

    python -m pipeline.signal_space                 # compute + persist one run
    python -m pipeline.signal_space --dry-run       # only count the sample
    python -m pipeline.signal_space --per-month 300 --months 120
    python -m pipeline.signal_space --layouts style  # only the 27.09. layout

Design decisions, each with its reason:

* **Equal points per month** (default 600, the last 180 months). The corpus
  grew from a few hundred signals a month to over a hundred thousand; a
  proportional sample would draw our own intake ramp and leave fifteen years of
  history as a faint smudge. Density in the cloud therefore means COMPOSITION
  within a month, never volume — volume is what the measured-axes view is for.
* **Deterministic sample.** Within a month the rows with the smallest
  `(id * 2654435761) mod 2^32` win (Knuth's multiplicative hash: spread across
  ids, hence across sources and days, and identical on every run over the same
  data). No Math.random, no np.random.
* **One global projection, filtered in the browser.** Research, patents and the
  trade press are NOT projected separately: positions stay comparable when the
  owner filters. The cost is visible and stated on the page — the embedding
  encodes writing style, so research and trade press sit apart even on the same
  subject (docs/emerging_nests_2026-09-15.md).
* **Two layouts per run (since 28.09.), see LAYOUTS.** "topic" (default):
  subtract each tier's mean vector, then UMAP with cosine on all 1024 dims —
  topics come together across tiers. "style": L2 -> PCA(50) -> UMAP, the layout
  of 27.09., where the tiers form their own continents. Both are fitted on the
  same sample; every signal is loaded once and placed into both. Measured in
  docs/space_eval_2026-09-28.md (scripts/space_eval/eval_projection.py).
* **UMAP keeps neighbourhoods, not distances.** The
  run records how much of that it achieved (kept nearest neighbours @10 and
  sklearn's trustworthiness on a 3,000-point subsample, both against the
  1024-dim vectors), and the page prints it.
* **One row per run, points as one packed BYTEA.** ~108k points x 16 bytes is
  1.7 MB. A table with a row per point would need an index and cleanup for
  something that is only ever read whole; and nothing here ever writes to
  `trends` (HNSW bloat, see the 17.09. lesson).
* **Memory.** Keyset-free: pass 1 returns only the chosen ids (a window
  function does the per-month cut in the database), pass 2 fetches their
  vectors in chunks into ONE preallocated float32 matrix — the 26.09. retrain
  OOM was an np.vstack of chunks. ~0.5 GB for 108k x 1024.

No cron (radar rule: a document with a date and a button). The frontend
starts it through the detached snapshot worker (mode "space").
"""
from __future__ import annotations

import argparse
import json
import logging
import resource
import time
from datetime import date

import numpy as np

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.foresight_snapshot import VERTICALS, add_columns
from pipeline.history_vectors import HISTORY_ID_BASE, iter_history
from pipeline.history_vectors import available as history_available
from pipeline.history_vectors import mark_overlaps as mark_history_overlaps
from pipeline.history_vectors import unpack as unpack_history
from pipeline.tiers import TIERS, tier_of

try:  # the run log must never stop a run (pipeline/ops_events.py)
    from pipeline.ops_events import record as ops_record
except Exception:  # noqa: BLE001
    from contextlib import nullcontext as ops_record  # type: ignore

logger = logging.getLogger("signal_space")

DEFAULT_PER_MONTH = 600
DEFAULT_MONTHS = 180
PCA_DIMS = 50
UMAP_NEIGHBOURS = 30
UMAP_MIN_DIST = 0.1
SEED = 42
FRAME_QUANTILE = 0.92     # the cloud is framed on the bulk, like normaliseCoords
QUALITY_SAMPLE = 3000
QUALITY_K = 10
FETCH_CHUNK = 5000
KEEP_RUNS = 2
HASH_MUL = 2654435761
# Two layouts of the same signals (28.09., docs/space_eval_2026-09-28.md). The
# first is the default picture; the second is kept as a switch on the page.
#   topic  subtract each tier's mean vector (the writing style: research, patents,
#          funding and trade press sit on separate continents even for one topic),
#          then UMAP with cosine straight on the 1024-dim prefix. Measured against
#          the old layout: hits of one search term 0.21 -> 0.34 of their neighbours
#          (all 28 test terms better), research<->market gap 0.47 -> 0.20, CPC
#          purity 0.47 -> 0.55; ~4 min more per run.
#   style  the layout of 27.09.: PCA 50 -> UMAP euclidean. The continents are the
#          point there — they show how differently the tiers write.
LAYOUTS = {
    "topic": {"tier_center": True, "pca_dims": None, "metric": "cosine",
              "method": "tiercenter-cos1024-umap3"},
    "style": {"tier_center": False, "pca_dims": PCA_DIMS, "metric": "euclidean",
              "method": "pca50-umap3"},
}
DEFAULT_LAYOUTS = ("topic", "style")
HASH_MOD = 2 ** 32

NO_NEST = 0xFFFF
# Codes are stored WITH every run (column `codes`), so the browser decodes with
# the table that produced the blob instead of a second hardcoded copy.
TIER_CODES = {None: 0, **{t: i + 1 for i, t in enumerate(TIERS)}}
VERTICAL_CODES = {None: 0, **{v: i + 1 for i, v in enumerate(VERTICALS)}}

PACK_DTYPE = np.dtype([
    ("x", "<u2"), ("y", "<u2"), ("z", "<u2"),
    ("month", "<u2"),
    ("tier", "u1"), ("vertical", "u1"),
    ("nest", "<u2"),
    ("trend_id", "<u4"),
])
assert PACK_DTYPE.itemsize == 16


# --------------------------------------------------------------------- tables

def migrate_signal_space_tables() -> None:
    """Create the run table. Idempotent, additive, standalone."""
    pk = ("id SERIAL PRIMARY KEY" if db_mod.USE_POSTGRES
          else "id INTEGER PRIMARY KEY AUTOINCREMENT")
    created = ("created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if db_mod.USE_POSTGRES
               else "created_at TEXT DEFAULT (datetime('now'))")
    blob = "BYTEA" if db_mod.USE_POSTGRES else "BLOB"
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS signal_space_runs ("
            f" {pk},"
            " method TEXT, params TEXT,"
            " n_points INTEGER, per_month INTEGER,"
            " first_month TEXT, last_month TEXT, months TEXT,"
            " emerging_run_id INTEGER, nests TEXT, codes TEXT,"
            " coord_range REAL,"
            " pca_variance REAL, neighbour_keep REAL, trustworthiness REAL,"
            " duration_s REAL, peak_rss_gb REAL,"
            f" points {blob},"
            f" {created})"
        )
        # 27.09. (evening): every signal of the window placed into the cloud, so a
        # search can show all matches, not only the ~6 % that are in the sample.
        add_columns(conn, "signal_space_runs", {"all_points": blob, "n_all": "INTEGER"})
        # 28.09.: a second layout of the same points (LAYOUTS). The first layout
        # keeps the original columns; the second gets its own blobs, range, nest
        # positions and quality. `layout` names the first (NULL = runs before
        # 28.09., which were "style").
        add_columns(conn, "signal_space_runs", {
            "layout": "TEXT", "alt_layout": "TEXT",
            "alt_points": blob, "alt_all_points": blob, "alt_coord_range": "REAL",
            "alt_nests": "TEXT", "alt_pca_variance": "REAL",
            "alt_neighbour_keep": "REAL", "alt_trustworthiness": "REAL",
        })
        # 03.10.: the history sample (pipeline/history_vectors.py) joins the cloud;
        # flows = patent citations between nests (JSON), n_history = history points.
        add_columns(conn, "signal_space_runs", {"flows": "TEXT", "n_history": "INTEGER",
                                                "n_history_all": "INTEGER"})


# -------------------------------------------------------------------- months

def month_window(end: str, n: int) -> list[str]:
    """The n months ending with `end` ('YYYY-MM'), oldest first."""
    y, m = int(end[:4]), int(end[5:7])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out[::-1]


def _month_expr() -> str:
    # No literal '%' on Postgres: the ?->%s wrapper hands the SQL to psycopg2.
    return ("to_char(r.published_date, 'YYYY-MM')" if db_mod.USE_POSTGRES
            else "strftime('%Y-%m', r.published_date)")


def _hash_expr() -> str:
    return (f"mod(t.id::bigint * {HASH_MUL}, {HASH_MOD})" if db_mod.USE_POSTGRES
            else f"((t.id * {HASH_MUL}) % {HASH_MOD})")


def _emb_col() -> str:
    """embedding_1024 on Postgres. SQLite has no such column and keeps the raw
    vector bytes in `embedding` — the first 1024 floats ARE the prefix
    (db.insert_trend), so load_vectors slices and the result is the same."""
    return "t.embedding_1024" if db_mod.USE_POSTGRES else "t.embedding"


def _signal_filter() -> str:
    return (f"t.status IN ('signal','published') AND {_emb_col()} IS NOT NULL"
            " AND r.published_date IS NOT NULL AND r.published_date <= CURRENT_TIMESTAMP")


# -------------------------------------------------------------------- pass 1

def _history_month_expr() -> str:
    return ("to_char(make_date(h.month / 12, mod(h.month, 12) + 1, 1), 'YYYY-MM')"
            if db_mod.USE_POSTGRES else "printf('%04d-%02d', h.month / 12, h.month % 12 + 1)")


def _history_hash_expr() -> str:
    base = HISTORY_ID_BASE
    return (f"mod(({base}::bigint + h.id) * {HASH_MUL}, {HASH_MOD})" if db_mod.USE_POSTGRES
            else f"((({base} + h.id) * {HASH_MUL}) % {HASH_MOD})")


def sample_ids(months: list[str], per_month: int,
               history: bool = True) -> list[tuple[int, str]]:
    """(trend_id, month) of the sample, ordered by month then hash.

    The per-month cut is a window function in the database, so only the chosen
    ids travel — not 1.8M (id, month) pairs.

    history (03.10.): the random layer of the history sample (patents from 1990,
    research from 2010, both to 2026-06, pipeline/history_vectors.py) joins the pool the 600 a
    month are drawn from, under ids HISTORY_ID_BASE + item id. Before 2023 the
    pool then holds our thin own intake plus up to 2,000 per month and tier.
    """
    if not months:
        return []
    mexpr = _month_expr()
    pool = (f"  SELECT t.id AS id, {mexpr} AS m, {_hash_expr()} AS h"
            "  FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id"
            f"  WHERE {_signal_filter()}"
            f"    AND {mexpr} >= ? AND {mexpr} <= ?")
    params: list = [months[0], months[-1]]
    if history and history_available():
        pool += (f"  UNION ALL SELECT {HISTORY_ID_BASE} + h.id AS id, {_history_month_expr()} AS m,"
                 f"         {_history_hash_expr()} AS h"
                 "  FROM history_items h"
                 "  WHERE h.embedded_at IS NOT NULL AND h.layer = 'random'"
                 "    AND h.dup_of_trend IS NULL AND h.month >= ? AND h.month <= ?")
        params += [_mnum(months[0]), _mnum(months[-1])]
    sql = ("SELECT id, m FROM ("
           "  SELECT id, m, h, row_number() OVER (PARTITION BY m ORDER BY h, id) AS rn"
           f"  FROM ({pool}) pool"
           ") s WHERE rn <= ? ORDER BY m, h, id")
    with get_connection() as c:
        rows = c.execute(sql, (*params, per_month)).fetchall()
    return [(int(r["id"]), str(r["m"])) for r in rows]


def _mnum(m: str) -> int:
    return int(m[:4]) * 12 + int(m[5:7]) - 1


# -------------------------------------------------------------------- pass 2

def load_vectors(ids: list[int], dim: int = 1024) -> tuple[np.ndarray, list[dict]]:
    """Vectors + attributes for `ids`, in the given order, into one matrix.

    Rows whose vector cannot be parsed keep a zero row and are reported by the
    caller (never silently dropped: the blob and the id list must stay aligned).
    """
    X = np.zeros((len(ids), dim), dtype=np.float32)
    meta: list[dict] = [{} for _ in ids]
    pos = {tid: i for i, tid in enumerate(ids)}
    emb = f"{_emb_col()}::text" if db_mod.USE_POSTGRES else _emb_col()
    hist = [i for i in ids if i >= HISTORY_ID_BASE]
    trend_ids = [i for i in ids if i < HISTORY_ID_BASE]
    if hist:
        with get_connection() as c:
            for start in range(0, len(hist), FETCH_CHUNK):
                chunk = [i - HISTORY_ID_BASE for i in hist[start:start + FETCH_CHUNK]]
                q = ",".join("?" * len(chunk))
                for r in c.execute("SELECT h.id, h.tier, v.vec FROM history_items h "
                                   "JOIN history_vectors v ON v.item_id = h.id "
                                   f"WHERE h.id IN ({q})", tuple(chunk)).fetchall():
                    i = pos[HISTORY_ID_BASE + int(r["id"])]
                    v = unpack_history(r["vec"])
                    X[i, :min(dim, v.size)] = v[:dim]
                    meta[i] = {"tier": r["tier"], "vertical": None}
        print(f"  history vectors {len(hist):,}", flush=True)
    ids = trend_ids
    with get_connection() as c:
        for start in range(0, len(ids), FETCH_CHUNK):
            chunk = ids[start:start + FETCH_CHUNK]
            if db_mod.USE_POSTGRES:
                where, params = "t.id = ANY(?)", (chunk,)
            else:
                where, params = f"t.id IN ({','.join('?' * len(chunk))})", tuple(chunk)
            rows = c.execute(
                "SELECT t.id, t.source_name, t.trend_signal_type, t.primary_vertical,"
                f" s.source_type, {emb} AS emb"
                " FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id"
                " LEFT JOIN sources s ON r.source_id = s.id"
                f" WHERE {where}", params).fetchall()
            for r in rows:
                i = pos.get(int(r["id"]))
                if i is None:
                    continue
                raw = db_mod._vector_to_bytes(r["emb"])
                if raw:
                    v = np.frombuffer(raw, dtype=np.float32)
                    X[i, :min(dim, v.size)] = v[:dim]
                meta[i] = {
                    "tier": tier_of(r["source_name"], r["source_type"], r["trend_signal_type"]),
                    "vertical": r["primary_vertical"],
                }
            print(f"  vectors {min(start + FETCH_CHUNK, len(ids)):,}/{len(ids):,}", flush=True)
    return X, meta


def l2(X: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(X, axis=1, keepdims=True)
    return X / np.clip(n, 1e-9, None)


# --------------------------------------------------------------------- nests

def latest_global_nests() -> tuple[int | None, list[dict], np.ndarray, np.ndarray]:
    """(run_id, nests, centroids (n,1024) L2-normalised, thresholds) of the
    latest global emerging run, or (None, [], empty, empty)."""
    try:
        with get_connection() as c:
            run = c.execute("SELECT id FROM emerging_runs WHERE scope = 'global' "
                            "ORDER BY id DESC LIMIT 1").fetchone()
            if not run:
                return None, [], np.zeros((0, 1024), np.float32), np.zeros(0, np.float32)
            rows = c.execute(
                "SELECT id, label, llm_label, tiers, centroid, threshold "
                "FROM emerging_nests WHERE run_id = ? ORDER BY id", (run["id"],)).fetchall()
    except Exception as exc:  # noqa: BLE001 — no emerging tables yet
        logger.warning("no emerging nests available: %s", exc)
        return None, [], np.zeros((0, 1024), np.float32), np.zeros(0, np.float32)
    nests, cents, thr = [], [], []
    for r in rows:
        raw = r["centroid"]
        if raw is None:
            continue
        v = np.frombuffer(bytes(raw), dtype=np.float32)
        if v.size != 1024:
            continue
        tiers = r["tiers"]
        if isinstance(tiers, str):
            try:
                tiers = json.loads(tiers)
            except ValueError:
                tiers = {}
        tiers = tiers or {}
        dominant = max(tiers, key=lambda t: (tiers[t] or {}).get("share_of_nest", 0),
                       default=None)
        nests.append({"id": int(r["id"]), "name": r["llm_label"] or r["label"] or "Nest",
                      "tier": dominant,
                      "tier_shares": {t: float((tiers[t] or {}).get("share_of_nest") or 0)
                                      for t in tiers}})
        cents.append(v)
        thr.append(float(r["threshold"] if r["threshold"] is not None else 1.0))
    C = l2(np.vstack(cents)) if cents else np.zeros((0, 1024), np.float32)
    return int(run["id"]), nests, C.astype(np.float32), np.asarray(thr, dtype=np.float32)


def assign_nests(Xn: np.ndarray, C: np.ndarray, thresholds: np.ndarray,
                 chunk: int = 20000) -> np.ndarray:
    """Index of the best nest a point clears the threshold of, else NO_NEST.

    The same rule as the archive scan (pipeline/emerging.py:scan_history): a
    signal is a lookalike of a nest when its cosine to the centroid reaches the
    nest's own threshold. Among several, the closest wins.
    """
    out = np.full(Xn.shape[0], NO_NEST, dtype=np.uint16)
    if C.shape[0] == 0:
        return out
    for s in range(0, Xn.shape[0], chunk):
        S = Xn[s:s + chunk] @ C.T
        ok = S >= thresholds[None, :]
        masked = np.where(ok, S, -np.inf)
        best = masked.argmax(axis=1)
        hit = ok[np.arange(S.shape[0]), best]
        out[s:s + chunk][hit] = best[hit].astype(np.uint16)
    return out


# ------------------------------------------------------------ tier centring

def tier_means(Xn: np.ndarray, codes: np.ndarray) -> np.ndarray:
    """(len(TIER_CODES), dim): mean vector of each tier code in the sample; a
    code without rows gets the sample mean (it then shifts nothing specific)."""
    g = Xn.mean(axis=0) if len(Xn) else np.zeros(Xn.shape[1], np.float32)
    M = np.tile(g, (len(TIER_CODES), 1)).astype(np.float32)
    for c in np.unique(codes):
        M[int(c)] = Xn[codes == c].mean(axis=0)
    return M


def center_tiers(X: np.ndarray, codes: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Subtract each row's tier mean and renormalise — the "topic" layout's input."""
    return l2(X - M[codes]).astype(np.float32)


def center_nests(C: np.ndarray, nests: list[dict], M: np.ndarray) -> np.ndarray:
    """Nest centroids mix tiers: subtract the mean weighted by the nest's own
    tier shares (from the archive scan), or the sample mean without shares."""
    if C.shape[0] == 0:
        return C
    g = M.mean(axis=0)
    out = np.empty_like(C)
    for i, n in enumerate(nests):
        sh = {t: w for t, w in (n.get("tier_shares") or {}).items() if w > 0 and t in TIER_CODES}
        tot = sum(sh.values())
        off = (sum(w * M[TIER_CODES[t]] for t, w in sh.items()) / tot) if tot else g
        out[i] = C[i] - off
    return l2(out).astype(np.float32)


# ----------------------------------------------------------------- projection

def frame(Y: np.ndarray, extra: np.ndarray | None = None,
          quantile: float = FRAME_QUANTILE) -> tuple[np.ndarray, np.ndarray | None]:
    """Centre on the median and scale by ONE factor so the bulk fills [-1, 1].

    Same rule as normaliseCoords in frontend/src/lib/clusterMap.ts: per-axis
    scaling would stretch the shape; framing on the maximum would let one
    outlier shrink everything else to a dot.
    """
    centre, f = frame_params(Y, quantile)
    Ec = None if extra is None else (extra - centre) * f
    return (Y - centre) * f, Ec


def frame_params(Y: np.ndarray, quantile: float = FRAME_QUANTILE) -> tuple[np.ndarray, float]:
    """(centre, factor) of `frame`, so points placed later get the SAME framing."""
    centre = np.median(Y, axis=0)
    ext = np.max(np.abs(Y - centre), axis=1)
    ref = float(np.quantile(ext, quantile)) if ext.size else 1.0
    return centre, (1.0 / ref if ref > 0 else 1.0)


def project(Xn: np.ndarray, C: np.ndarray, seed: int = SEED,
            n_neighbors: int = UMAP_NEIGHBOURS, pca_dims: int | None = PCA_DIMS,
            return_model: bool = False, metric: str = "euclidean"):
    """(points (n,3), nest positions (k,3), PCA variance kept or None[, (pca|None, reducer)]).

    `pca_dims=None` skips the PCA: UMAP then sees the full input (the "topic"
    layout, with cosine)."""
    from sklearn.decomposition import PCA
    import umap  # noqa: PLC0415 — heavy import (numba JIT), only when projecting

    pca, var = None, None
    Z = Xn
    if pca_dims:
        dims = min(pca_dims, Xn.shape[1], max(2, Xn.shape[0] - 1))
        pca = PCA(n_components=dims, random_state=seed, svd_solver="randomized")
        Z = pca.fit_transform(Xn)
        var = float(pca.explained_variance_ratio_.sum())
    reducer = umap.UMAP(n_components=3, n_neighbors=min(n_neighbors, Xn.shape[0] - 1),
                        min_dist=UMAP_MIN_DIST, metric=metric, random_state=seed,
                        # A seed forces UMAP single-threaded. That is the price of the
                        # same picture on every run, and it is paid on purpose.
                        n_jobs=1)
    Y = reducer.fit_transform(Z)
    N = (reducer.transform(pca.transform(C) if pca is not None else C) if C.shape[0]
         else np.zeros((0, 3)))
    out = (np.asarray(Y, dtype=np.float64), np.asarray(N, dtype=np.float64), var)
    return out + ((pca, reducer),) if return_model else out


def _next_month(m: str) -> str:
    y, mm = int(m[:4]), int(m[5:7]) + 1
    return f"{y + (mm > 12):04d}-{(mm - 1) % 12 + 1:02d}"


def place_all(months: list[str], layouts: list[dict], C: np.ndarray, thr: np.ndarray,
              chunk: int = 20_000, history: bool = True) -> dict:
    """Every embedded signal of the window, placed in the cloud of the sample.

    The sample defines the layout (600 per month, so the intake ramp does not);
    everything else is PLACED into it with the fitted PCA + UMAP (`transform`,
    ~6,750 points/s measured 27.09. after a one-off JIT compile). A signal that
    is part of the sample keeps its fitted position, so a search hit sits
    exactly where that point is drawn. Streams with the keyset loader of the
    archive scans — memory is one chunk, not the corpus.

    `layouts`: one dict per layout — "model" (pca or None, reducer), "means"
    (tier means to subtract, or None) and "fitted" ({trend_id: position}). Every
    chunk is read ONCE and placed into all layouts; loading is the larger half.

    history (03.10.): after the trends rows, every embedded history item of the
    window is placed too — the random layer AND the cited layer (the patents the
    signal space builds on), under ids HISTORY_ID_BASE + item id.

    Returns raw (unframed) coordinates per layout ("Y", a list in the order of
    `layouts`) plus the per-point attributes and "n_history".
    """
    from pipeline.foresight import build_matrix, iter_signals

    pos = {m: i for i, m in enumerate(months)}
    ids, month_idx, tiers, verts, nests = [], [], [], [], []
    coords: list[list[np.ndarray]] = [[] for _ in layouts]
    seen = placed = n_history = 0
    t0 = time.time()

    def source():
        for b in iter_signals(status="signal,published", dim1024=db_mod.USE_POSTGRES,
                              since=f"{months[0]}-01", until=f"{_next_month(months[-1])}-01",
                              chunk_size=chunk):
            M = build_matrix(b)
            if M.shape[1] > 1024:        # SQLite keeps the full vector; the prefix is the space
                M = l2(M[:, :1024])
            yield M, b
        if history:
            yield from iter_history(since=months[0], until=_next_month(months[-1]),
                                    layers=("random", "cited"), chunk_size=chunk)

    for X, batch in source():
        n_history += sum(1 for r in batch if r.get("status") == "history")
        keep = [i for i, r in enumerate(batch) if (r["published_date"] or "")[:7] in pos]
        if not keep:
            continue
        X = X[keep]
        rows = [batch[i] for i in keep]
        tcodes = np.array([TIER_CODES.get(tier_of(r.get("source_name"), r.get("source_type"),
                                                  r.get("trend_signal_type")), 0) for r in rows])
        for L, out in zip(layouts, coords):
            Y = np.empty((len(rows), 3), dtype=np.float64)
            todo = []
            for j, r in enumerate(rows):
                hit = L["fitted"].get(int(r["id"]))
                if hit is None:
                    todo.append(j)
                else:
                    Y[j] = hit
            if todo:
                Xt = X[todo] if L["means"] is None else center_tiers(X[todo], tcodes[todo], L["means"])
                pca, reducer = L["model"]
                Y[todo] = reducer.transform(pca.transform(Xt) if pca is not None else Xt)
            out.append(Y)
        placed += len(rows) - sum(1 for r in rows if int(r["id"]) in layouts[0]["fitted"])
        ids.append(np.array([int(r["id"]) for r in rows], dtype=np.int64))
        month_idx.append(np.array([pos[r["published_date"][:7]] for r in rows], dtype=np.int32))
        tiers.append(tcodes)
        verts.append(np.array([VERTICAL_CODES.get(r.get("primary_vertical"), 0) for r in rows]))
        nests.append(assign_nests(X, C, thr))
        seen += len(rows)
        print(f"  placed {seen:,} ({placed:,} by transform, {time.time() - t0:.0f}s)", flush=True)
    if not ids:
        return {"ids": np.zeros(0, np.int64), "Y": [np.zeros((0, 3)) for _ in layouts],
                "month": np.zeros(0, np.int32),
                "tier": np.zeros(0, np.int32), "vertical": np.zeros(0, np.int32),
                "nest": np.zeros(0, np.uint16), "transformed": 0, "n_history": 0}
    return {"ids": np.concatenate(ids), "Y": [np.vstack(c) for c in coords],
            "month": np.concatenate(month_idx),
            "tier": np.concatenate(tiers), "vertical": np.concatenate(verts),
            "nest": np.concatenate(nests), "transformed": placed, "n_history": n_history}


def citation_flows(ids: np.ndarray, nests: np.ndarray, top: int = 300) -> dict:
    """Patent citations between nests (03.10.): every placed patent that sits in a
    nest — trends signals and history items alike — is looked up in patent_links;
    a citation from a patent of nest A to a patent of nest B counts as one flow A -> B
    ("A builds on B"; A == B = within the nest). Indices are nest positions in the
    run's nest list. Postgres only (patent_links is not in the test schema)."""
    out = {"pairs": [], "edges": 0, "patents_in_nests": 0}
    if not db_mod.USE_POSTGRES or not len(ids):
        return out
    inside = nests != NO_NEST
    t_ids = [int(i) for i in ids[inside] if i < HISTORY_ID_BASE]
    h_ids = [int(i) - HISTORY_ID_BASE for i in ids[inside] if i >= HISTORY_ID_BASE]
    nest_of = {int(i): int(n) for i, n in zip(ids[inside], nests[inside])}
    pub_nest: dict[str, int] = {}
    with get_connection() as c:
        for s in range(0, len(t_ids), 50_000):
            for r in c.execute("SELECT t.id, r.pub_number FROM trends t JOIN raw_entries r "
                               "ON r.id = t.raw_entry_id WHERE t.id = ANY(?) "
                               "AND r.pub_number IS NOT NULL", (t_ids[s:s + 50_000],)).fetchall():
                pub_nest[r["pub_number"]] = nest_of[int(r["id"])]
        for s in range(0, len(h_ids), 50_000):
            for r in c.execute("SELECT id, ref FROM history_items WHERE id = ANY(?) "
                               "AND tier = 'patent'", (h_ids[s:s + 50_000],)).fetchall():
                pub_nest[r["ref"]] = nest_of[HISTORY_ID_BASE + int(r["id"])]
        pubs = list(pub_nest)
        pairs: dict[tuple[int, int], int] = {}
        edges = 0
        for s in range(0, len(pubs), 20_000):
            for r in c.execute("SELECT src_pub, dst_pub FROM patent_links WHERE link_type = 'cites' "
                               "AND src_pub = ANY(?)", (pubs[s:s + 20_000],)).fetchall():
                b = pub_nest.get(r["dst_pub"])
                if b is None:
                    continue
                k = (pub_nest[r["src_pub"]], b)
                pairs[k] = pairs.get(k, 0) + 1
                edges += 1
    ranked = sorted(pairs.items(), key=lambda kv: -kv[1])[:top]
    out.update(pairs=[[a, b, n] for (a, b), n in ranked], edges=edges,
               patents_in_nests=len(pub_nest))
    return out


def neighbour_keep(A: np.ndarray, B: np.ndarray, k: int) -> float:
    """Mean share of each point's k nearest neighbours in A that are still among
    its k nearest in B. Same definition as neighbourKeep in clusterMap.ts."""
    n = A.shape[0]
    if n <= 1:
        return 1.0
    k = min(k, n - 1)

    def knn(M: np.ndarray) -> np.ndarray:
        sq = (M * M).sum(1)
        D = sq[:, None] + sq[None, :] - 2 * M @ M.T
        np.fill_diagonal(D, np.inf)
        # ties broken by index, so the measure cannot depend on sort stability
        return np.lexsort((np.broadcast_to(np.arange(n), D.shape), D), axis=1)[:, :k]

    a, b = knn(A.astype(np.float64)), knn(B.astype(np.float64))
    return float(np.mean([len(set(a[i]) & set(b[i])) / k for i in range(n)]))


def quality(Xn: np.ndarray, Y: np.ndarray, sample: int = QUALITY_SAMPLE,
            k: int = QUALITY_K) -> tuple[float, float]:
    """(kept neighbours @k, trustworthiness) on an evenly spaced subsample."""
    from sklearn.manifold import trustworthiness

    n = Xn.shape[0]
    idx = np.linspace(0, n - 1, num=min(sample, n), dtype=int)
    A, B = Xn[idx], Y[idx]
    kk = min(k, max(1, len(idx) // 2 - 1))
    return neighbour_keep(A, B, kk), float(trustworthiness(A, B, n_neighbors=kk))


# ---------------------------------------------------------------------- pack

def quantise(v: np.ndarray, rng: float) -> np.ndarray:
    q = np.round((np.clip(v, -rng, rng) + rng) / (2 * rng) * 65535.0)
    return q.astype(np.uint16)


def dequantise(q: np.ndarray, rng: float) -> np.ndarray:
    return q.astype(np.float64) / 65535.0 * (2 * rng) - rng


def pack(Y: np.ndarray, month_idx: np.ndarray, tiers: np.ndarray, verticals: np.ndarray,
         nests: np.ndarray, trend_ids: np.ndarray, rng: float) -> bytes:
    rec = np.zeros(Y.shape[0], dtype=PACK_DTYPE)
    rec["x"], rec["y"], rec["z"] = (quantise(Y[:, i], rng) for i in range(3))
    rec["month"] = month_idx.astype(np.uint16)
    rec["tier"] = tiers.astype(np.uint8)
    rec["vertical"] = verticals.astype(np.uint8)
    rec["nest"] = nests.astype(np.uint16)
    rec["trend_id"] = trend_ids.astype(np.uint32)
    return rec.tobytes()


def unpack(buf: bytes) -> np.ndarray:
    return np.frombuffer(buf, dtype=PACK_DTYPE)


# ----------------------------------------------------------------------- run

def _peak_rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2


def run(per_month: int = DEFAULT_PER_MONTH, n_months: int = DEFAULT_MONTHS,
        end_month: str | None = None, dry_run: bool = False,
        place_everything: bool = True,
        layouts: tuple[str, ...] = DEFAULT_LAYOUTS, history: bool = True) -> int | None:
    t0 = time.time()
    months = month_window(end_month or date.today().strftime("%Y-%m"), n_months)
    print(f"window {months[0]} .. {months[-1]}, {per_month} per month", flush=True)
    history = history and history_available()
    if history and not dry_run:
        print(f"history sample: {mark_history_overlaps():,} new overlaps with trends marked",
              flush=True)

    chosen = sample_ids(months, per_month, history=history)
    n_hist_sample = sum(1 for tid, _ in chosen if tid >= HISTORY_ID_BASE)
    by_month: dict[str, int] = {}
    for _, m in chosen:
        by_month[m] = by_month.get(m, 0) + 1
    full = sum(1 for m in months if by_month.get(m, 0) >= per_month)
    print(f"sample: {len(chosen):,} signals ({n_hist_sample:,} from the history sample), "
          f"{full}/{len(months)} months at the quota ({time.time() - t0:.1f}s)", flush=True)
    if dry_run:
        years: dict[str, int] = {}
        for m, n in by_month.items():
            years[m[:4]] = years.get(m[:4], 0) + n
        for y in sorted(years):
            print(f"  {y}: {years[y]:,}", flush=True)
        return None
    if len(chosen) < 10:
        print("too few signals to project — nothing persisted", flush=True)
        return None

    ids = [tid for tid, _ in chosen]
    X, meta = load_vectors(ids)
    Xn = l2(X)
    blank = int((np.abs(X).sum(axis=1) == 0).sum())
    if blank:
        print(f"warning: {blank} rows without a parsable vector", flush=True)

    emerging_run, nests, C, thr = latest_global_nests()
    nest_idx = assign_nests(Xn, C, thr)          # membership lives in the ORIGINAL space
    members = int((nest_idx != NO_NEST).sum())
    print(f"nests: {len(nests)} from emerging run {emerging_run}, "
          f"{members:,} points inside one", flush=True)
    tcodes = np.array([TIER_CODES.get(x.get("tier"), 0) for x in meta])
    month_pos = {m: i for i, m in enumerate(months)}
    sample_month = np.array([month_pos[m] for _, m in chosen])
    sample_vert = np.array([VERTICAL_CODES.get(x.get("vertical"), 0) for x in meta])

    fits = []
    for name in layouts:
        spec = LAYOUTS[name]
        t1 = time.time()
        means = tier_means(Xn, tcodes) if spec["tier_center"] else None
        Xin = Xn if means is None else center_tiers(Xn, tcodes, means)
        Cin = C if means is None else center_nests(C, nests, means)
        Y, N, var, model = project(Xin, Cin, pca_dims=spec["pca_dims"], metric=spec["metric"],
                                   return_model=True)
        keep, trust = quality(Xn, Y)     # against the ORIGINAL space, for every layout
        centre, factor = frame_params(Y)
        fits.append({"name": name, "model": model, "means": means,
                     "fitted": {tid: Y[i] for i, tid in enumerate(ids)},
                     "Yf": (Y - centre) * factor, "Nf": (N - centre) * factor if N.size else N,
                     "centre": centre, "factor": factor,
                     "var": var, "keep": keep, "trust": trust})
        print(f"layout {name} ({spec['method']}): "
              + (f"PCA {spec['pca_dims']} keeps {var:.1%}, " if var is not None else "")
              + f"{keep:.1%} of the {QUALITY_K} nearest neighbours kept, "
              f"trustworthiness {trust:.3f} ({time.time() - t1:.0f}s)", flush=True)

    everything = None
    flows = None
    if place_everything:
        t2 = time.time()
        everything = place_all(months, fits, C, thr, history=history)
        for f, Y in zip(fits, everything["Y"]):
            f["all"] = (Y - f["centre"]) * f["factor"]
        print(f"placed all: {len(everything['ids']):,} signals, {everything['transformed']:,} "
              f"by transform, {len(fits)} layout(s) ({time.time() - t2:.0f}s)", flush=True)
        order = np.argsort(everything["ids"], kind="stable")   # the server binary-searches
        t3 = time.time()
        flows = citation_flows(everything["ids"], everything["nest"])
        print(f"citation flows: {flows['edges']:,} citations between {flows['patents_in_nests']:,} "
              f"patents in nests, {len(flows['pairs'])} nest pairs ({time.time() - t3:.0f}s)",
              flush=True)
    for f in fits:
        # One range per layout, wide enough for every placed point: the browser
        # decodes sample and search hits of a layout with the same coord_range.
        extents = [np.abs(f["Yf"]).max(), 1.0]
        if f["Nf"] is not None and f["Nf"].size:
            extents.append(np.abs(f["Nf"]).max())
        if everything is not None and len(everything["ids"]):
            extents.append(np.abs(f["all"]).max())
        f["rng"] = float(max(extents))
        f["blob"] = pack(f["Yf"], sample_month, tcodes, sample_vert, nest_idx, np.array(ids), f["rng"])
        f["all_blob"] = None
        if everything is not None:
            o = order
            f["all_blob"] = pack(f["all"][o], everything["month"][o], everything["tier"][o],
                                 everything["vertical"][o], everything["nest"][o],
                                 everything["ids"][o], f["rng"])
        f["nest_xyz"] = [[round(float(v), 5) for v in p] for p in (f["Nf"] if f["Nf"] is not None else [])]

    first = fits[0]
    alt = fits[1] if len(fits) > 1 else None
    nest_json = [{**{k: v for k, v in n.items() if k != "tier_shares"},
                  "x": xyz[0], "y": xyz[1], "z": xyz[2],
                  "members": int((nest_idx == i).sum())}
                 for i, (n, xyz) in enumerate(zip(nests, first["nest_xyz"]))]
    codes = {
        "tier": {str(v): k for k, v in TIER_CODES.items() if k},
        "vertical": {str(v): k for k, v in VERTICAL_CODES.items() if k},
        "no_nest": NO_NEST,
        "layout": [list(f) for f in PACK_DTYPE.descr],
    }
    params = {"layouts": {f["name"]: LAYOUTS[f["name"]] for f in fits},
              "n_neighbors": UMAP_NEIGHBOURS, "min_dist": UMAP_MIN_DIST, "seed": SEED,
              "frame_quantile": FRAME_QUANTILE,
              "quality_sample": QUALITY_SAMPLE, "quality_k": QUALITY_K}
    n_all = int(len(everything["ids"])) if everything is not None else None
    duration = time.time() - t0
    peak = _peak_rss_gb()
    with get_connection() as c:
        row = c.execute(
            "INSERT INTO signal_space_runs (method, params, n_points, per_month,"
            " first_month, last_month, months, emerging_run_id, nests, codes,"
            " coord_range, pca_variance, neighbour_keep, trustworthiness,"
            " duration_s, peak_rss_gb, points, all_points, n_all, layout,"
            " alt_layout, alt_points, alt_all_points, alt_coord_range, alt_nests,"
            " alt_pca_variance, alt_neighbour_keep, alt_trustworthiness,"
            " flows, n_history, n_history_all)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
            ("+".join(LAYOUTS[f["name"]]["method"] for f in fits), json.dumps(params),
             len(ids), per_month, months[0], months[-1],
             json.dumps(months), emerging_run, json.dumps(nest_json), json.dumps(codes),
             first["rng"], first["var"], first["keep"], first["trust"],
             round(duration, 1), round(peak, 2),
             first["blob"], first["all_blob"], n_all, first["name"],
             alt["name"] if alt else None, alt["blob"] if alt else None,
             alt["all_blob"] if alt else None, alt["rng"] if alt else None,
             json.dumps(alt["nest_xyz"]) if alt else None, alt["var"] if alt else None,
             alt["keep"] if alt else None, alt["trust"] if alt else None,
             json.dumps(flows) if flows else None, n_hist_sample,
             int(everything["n_history"]) if everything is not None else None,
             )).fetchone()  # bytes -> BYTEA/BLOB on both backends
        run_id = int(row["id"])
        c.execute("DELETE FROM signal_space_runs WHERE id NOT IN "
                  "(SELECT id FROM signal_space_runs ORDER BY id DESC LIMIT ?)", (KEEP_RUNS,))
    size = sum(len(f["blob"]) + len(f["all_blob"] or b"") for f in fits)
    print(f"signal space run {run_id}: {len(ids):,} points"
          + (f" + {n_all:,} placed" if n_all else "")
          + f", layouts {', '.join(f['name'] for f in fits)}, {size / 1e6:.1f} MB, "
          f"{duration:.0f}s, peak RSS {peak:.1f} GB", flush=True)
    return run_id


def main() -> int:
    ap = argparse.ArgumentParser(description="Project a sample of all signals into 3D (UMAP)")
    ap.add_argument("--per-month", type=int, default=DEFAULT_PER_MONTH,
                    help=f"signals drawn per month (default {DEFAULT_PER_MONTH})")
    ap.add_argument("--months", type=int, default=DEFAULT_MONTHS,
                    help=f"months back from the current one (default {DEFAULT_MONTHS})")
    ap.add_argument("--end-month", default=None, help="last month, YYYY-MM (default: now)")
    ap.add_argument("--dry-run", action="store_true", help="only count the sample")
    ap.add_argument("--layouts", default=",".join(DEFAULT_LAYOUTS),
                    help="layouts to compute, the first is the default picture "
                         f"(choices: {', '.join(LAYOUTS)}; default {','.join(DEFAULT_LAYOUTS)})")
    ap.add_argument("--no-history", action="store_true",
                    help="leave out the history sample (patents from 1990, research from 2010, to 2026-06)")
    ap.add_argument("--sample-only", action="store_true",
                    help="skip placing every other signal (search then covers only the sample)")
    args = ap.parse_args()
    layouts = tuple(x.strip() for x in args.layouts.split(",") if x.strip())
    if not layouts or any(x not in LAYOUTS for x in layouts) or len(layouts) > 2:
        ap.error(f"--layouts takes one or two of {', '.join(LAYOUTS)}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    migrate_signal_space_tables()
    with ops_record("signal_space"):
        rid = run(args.per_month, args.months, args.end_month, args.dry_run,
                  place_everything=not args.sample_only, layouts=layouts,
                  history=not args.no_history)
    return 0 if (rid is not None or args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
