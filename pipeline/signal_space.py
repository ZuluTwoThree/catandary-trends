"""Signal space, stage 3: the individual signals as one 3D point cloud (2026-09-27).

Stages 1 and 2 (/trends/foresight/map) show the emerging NESTS — 55-94
centroids. This module places the signals themselves: a deterministic sample of
the embedded corpus, projected to three dimensions with UMAP, with the nests of
the latest global emerging run placed in the same cloud and every point tagged
with the nest it belongs to.

    python -m pipeline.signal_space                 # compute + persist one run
    python -m pipeline.signal_space --dry-run       # only count the sample
    python -m pipeline.signal_space --per-month 300 --months 120

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
* **L2 -> PCA(50) -> UMAP(3D).** UMAP keeps neighbourhoods, not distances. The
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
from pipeline.foresight_snapshot import VERTICALS
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

def sample_ids(months: list[str], per_month: int) -> list[tuple[int, str]]:
    """(trend_id, month) of the sample, ordered by month then hash.

    The per-month cut is a window function in the database, so only the chosen
    ids travel — not 1.8M (id, month) pairs.
    """
    if not months:
        return []
    mexpr = _month_expr()
    sql = (
        "SELECT id, m FROM ("
        f"  SELECT t.id AS id, {mexpr} AS m,"
        f"         row_number() OVER (PARTITION BY {mexpr}"
        f"                            ORDER BY {_hash_expr()}, t.id) AS rn,"
        f"         {_hash_expr()} AS h"
        "  FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id"
        f"  WHERE {_signal_filter()}"
        f"    AND {mexpr} >= ? AND {mexpr} <= ?"
        ") s WHERE rn <= ? ORDER BY m, h, id"
    )
    with get_connection() as c:
        rows = c.execute(sql, (months[0], months[-1], per_month)).fetchall()
    return [(int(r["id"]), str(r["m"])) for r in rows]


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
                      "tier": dominant})
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


# ----------------------------------------------------------------- projection

def frame(Y: np.ndarray, extra: np.ndarray | None = None,
          quantile: float = FRAME_QUANTILE) -> tuple[np.ndarray, np.ndarray | None]:
    """Centre on the median and scale by ONE factor so the bulk fills [-1, 1].

    Same rule as normaliseCoords in frontend/src/lib/clusterMap.ts: per-axis
    scaling would stretch the shape; framing on the maximum would let one
    outlier shrink everything else to a dot.
    """
    centre = np.median(Y, axis=0)
    Yc = Y - centre
    ext = np.max(np.abs(Yc), axis=1)
    ref = float(np.quantile(ext, quantile)) if ext.size else 1.0
    f = 1.0 / ref if ref > 0 else 1.0
    Ec = None if extra is None else (extra - centre) * f
    return Yc * f, Ec


def project(Xn: np.ndarray, C: np.ndarray, seed: int = SEED,
            n_neighbors: int = UMAP_NEIGHBOURS, pca_dims: int = PCA_DIMS):
    """(points (n,3), nest positions (k,3), PCA variance kept)."""
    from sklearn.decomposition import PCA
    import umap  # noqa: PLC0415 — heavy import (numba JIT), only when projecting

    dims = min(pca_dims, Xn.shape[1], max(2, Xn.shape[0] - 1))
    pca = PCA(n_components=dims, random_state=seed, svd_solver="randomized")
    Z = pca.fit_transform(Xn)
    reducer = umap.UMAP(n_components=3, n_neighbors=min(n_neighbors, Xn.shape[0] - 1),
                        min_dist=UMAP_MIN_DIST, metric="euclidean", random_state=seed,
                        # A seed forces UMAP single-threaded. That is the price of the
                        # same picture on every run, and it is paid on purpose.
                        n_jobs=1)
    Y = reducer.fit_transform(Z)
    N = reducer.transform(pca.transform(C)) if C.shape[0] else np.zeros((0, 3))
    return (np.asarray(Y, dtype=np.float64), np.asarray(N, dtype=np.float64),
            float(pca.explained_variance_ratio_.sum()))


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
        end_month: str | None = None, dry_run: bool = False) -> int | None:
    t0 = time.time()
    months = month_window(end_month or date.today().strftime("%Y-%m"), n_months)
    print(f"window {months[0]} .. {months[-1]}, {per_month} per month", flush=True)

    chosen = sample_ids(months, per_month)
    by_month: dict[str, int] = {}
    for _, m in chosen:
        by_month[m] = by_month.get(m, 0) + 1
    full = sum(1 for m in months if by_month.get(m, 0) >= per_month)
    print(f"sample: {len(chosen):,} signals, {full}/{len(months)} months at the quota "
          f"({time.time() - t0:.1f}s)", flush=True)
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
    nest_idx = assign_nests(Xn, C, thr)
    members = int((nest_idx != NO_NEST).sum())
    print(f"nests: {len(nests)} from emerging run {emerging_run}, "
          f"{members:,} points inside one", flush=True)

    t1 = time.time()
    Y, N, pca_var = project(Xn, C)
    print(f"projection: PCA {PCA_DIMS} keeps {pca_var:.1%} of the variance, "
          f"UMAP done ({time.time() - t1:.0f}s)", flush=True)
    keep, trust = quality(Xn, Y)
    print(f"quality: {keep:.1%} of the {QUALITY_K} nearest neighbours kept, "
          f"trustworthiness {trust:.3f}", flush=True)

    Yf, Nf = frame(Y, N)
    rng = float(max(np.abs(Yf).max(), np.abs(Nf).max() if Nf is not None and Nf.size else 0, 1.0))
    month_pos = {m: i for i, m in enumerate(months)}
    blob = pack(
        Yf,
        np.array([month_pos[m] for _, m in chosen]),
        np.array([TIER_CODES.get(x.get("tier"), 0) for x in meta]),
        np.array([VERTICAL_CODES.get(x.get("vertical"), 0) for x in meta]),
        nest_idx,
        np.array(ids),
        rng,
    )
    nest_json = [{**n, "x": round(float(p[0]), 5), "y": round(float(p[1]), 5),
                  "z": round(float(p[2]), 5),
                  "members": int((nest_idx == i).sum())}
                 for i, (n, p) in enumerate(zip(nests, Nf if Nf is not None else []))]
    codes = {
        "tier": {str(v): k for k, v in TIER_CODES.items() if k},
        "vertical": {str(v): k for k, v in VERTICAL_CODES.items() if k},
        "no_nest": NO_NEST,
        "layout": [list(f) for f in PACK_DTYPE.descr],
    }
    params = {"pca_dims": PCA_DIMS, "n_neighbors": UMAP_NEIGHBOURS,
              "min_dist": UMAP_MIN_DIST, "seed": SEED, "frame_quantile": FRAME_QUANTILE,
              "quality_sample": QUALITY_SAMPLE, "quality_k": QUALITY_K}
    duration = time.time() - t0
    peak = _peak_rss_gb()
    with get_connection() as c:
        row = c.execute(
            "INSERT INTO signal_space_runs (method, params, n_points, per_month,"
            " first_month, last_month, months, emerging_run_id, nests, codes,"
            " coord_range, pca_variance, neighbour_keep, trustworthiness,"
            " duration_s, peak_rss_gb, points)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
            ("pca50-umap3", json.dumps(params), len(ids), per_month, months[0], months[-1],
             json.dumps(months), emerging_run, json.dumps(nest_json), json.dumps(codes),
             rng, pca_var, keep, trust, round(duration, 1), round(peak, 2),
             blob)).fetchone()  # bytes -> BYTEA/BLOB on both backends
        run_id = int(row["id"])
        c.execute("DELETE FROM signal_space_runs WHERE id NOT IN "
                  "(SELECT id FROM signal_space_runs ORDER BY id DESC LIMIT ?)", (KEEP_RUNS,))
    print(f"signal space run {run_id}: {len(ids):,} points, {len(blob) / 1e6:.1f} MB, "
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
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    migrate_signal_space_tables()
    with ops_record("signal_space"):
        rid = run(args.per_month, args.months, args.end_month, args.dry_run)
    return 0 if (rid is not None or args.dry_run) else 1


if __name__ == "__main__":
    raise SystemExit(main())
