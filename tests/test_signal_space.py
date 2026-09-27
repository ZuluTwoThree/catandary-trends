"""Signal space, stage 3: the sampled signal cloud (pipeline/signal_space.py).

Pins the properties the page relies on:

  * the sample is deterministic and takes the same number of signals from every
    month (density = composition, never volume),
  * the loader reads the 1024-dim prefix and keeps rows aligned with their ids,
  * the packed blob has the byte layout the browser decodes (16 bytes, fixed
    offsets) and survives quantisation within one step,
  * a point belongs to a nest by exactly the archive-scan rule,
  * one real UMAP run keeps two separated groups apart and is reproducible.
"""
import os
import struct
import sys
import tempfile
from pathlib import Path

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_signal_space_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import signal_space as ss
from pipeline.db import get_connection, init_db


def _unit(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def _seed(per_month: dict[str, int], dim: int = 4096, seed: int = 3,
          extra: list[tuple[str, str]] | None = None):
    """Signals per 'YYYY-MM'. `extra`: (status, published_date) rows that the
    filter must reject. Returns {trend_id: vector}."""
    init_db()
    with get_connection() as c:
        for tbl in ("trends", "raw_entries", "sources"):
            c.execute(f"DELETE FROM {tbl}")
        c.execute("INSERT INTO sources (id,name,feed_url,source_type,vertical) "
                  "VALUES (1,'Trade','http://t','trade_media','FOOD')")
        c.execute("INSERT INTO sources (id,name,feed_url,source_type,vertical) "
                  "VALUES (2,'Journal','http://j','research','HEALTH')")
    rng = np.random.default_rng(seed)
    vecs = {}
    rows = []
    for month, n in per_month.items():
        for k in range(n):
            rows.append(("signal", f"{month}-{(k % 27) + 1:02d}T10:00:00"))
    rows += list(extra or [])
    with get_connection() as c:
        for i, (status, pub) in enumerate(rows):
            v = rng.normal(size=dim).astype(np.float32)
            c.execute("INSERT INTO raw_entries (id, source_id, url, title, published_date) "
                      "VALUES (?,?,?,?,?)",
                      (i + 1, 1 if i % 2 else 2, f"http://x/{i}", f"t{i}", pub))
            c.execute(
                "INSERT INTO trends (id, raw_entry_id, title_en, slug, source_url, "
                "primary_vertical, status, source_name, embedding) VALUES (?,?,?,?,?,?,?,?,?)",
                (i + 1, i + 1, f"T{i}", f"s{i}", "http://x", "TECH" if i % 2 else "FOOD",
                 status, "Trade" if i % 2 else "Journal", struct.pack(f"{dim}f", *v)))
            vecs[i + 1] = v
    return vecs


# ------------------------------------------------------------------ sampling

def test_month_window_counts_back_across_the_year():
    assert ss.month_window("2026-01", 3) == ["2025-11", "2025-12", "2026-01"]
    assert len(ss.month_window("2026-09", 180)) == 180


def test_sample_takes_the_quota_per_month_and_all_of_a_thin_month():
    _seed({"2026-01": 10, "2026-02": 3, "2026-03": 7})
    got = ss.sample_ids(["2026-01", "2026-02", "2026-03"], per_month=4)
    months = [m for _, m in got]
    assert months.count("2026-01") == 4
    assert months.count("2026-02") == 3          # fewer than the quota: all of them
    assert months.count("2026-03") == 4
    assert months == sorted(months)              # ordered by month


def test_sample_is_deterministic():
    _seed({"2026-01": 30, "2026-02": 30})
    a = ss.sample_ids(["2026-01", "2026-02"], per_month=7)
    b = ss.sample_ids(["2026-01", "2026-02"], per_month=7)
    assert a == b
    assert len({tid for tid, _ in a}) == 14


def test_sample_rejects_drafts_future_dates_and_other_months():
    _seed({"2026-01": 5}, extra=[("draft", "2026-01-05T10:00:00"),
                                  ("signal", "2999-01-01T10:00:00"),
                                  ("signal", "2025-06-01T10:00:00")])
    got = ss.sample_ids(["2026-01"], per_month=100)
    assert len(got) == 5


# ------------------------------------------------------------------- loading

def test_load_vectors_reads_the_prefix_in_id_order():
    vecs = _seed({"2026-01": 6})
    ids = [5, 2, 4]
    X, meta = ss.load_vectors(ids)
    assert X.shape == (3, 1024)
    for row, tid in zip(X, ids):
        np.testing.assert_allclose(row, vecs[tid][:1024], atol=1e-6)
    # row i = id - 1: even i -> research journal (science), odd i -> trade (market)
    assert meta[0]["tier"] == "science" and meta[0]["vertical"] == "FOOD"   # id 5
    assert meta[1]["tier"] == "market" and meta[1]["vertical"] == "TECH"    # id 2
    assert ss.load_vectors([3])[1][0]["tier"] == "science"


# ---------------------------------------------------------------------- pack

def test_pack_layout_is_the_one_the_browser_decodes():
    # frontend/src/lib/spaceCloud.ts reads these exact offsets
    assert ss.PACK_DTYPE.itemsize == 16
    offs = {name: ss.PACK_DTYPE.fields[name][1] for name in ss.PACK_DTYPE.names}
    assert offs == {"x": 0, "y": 2, "z": 4, "month": 6, "tier": 8, "vertical": 9,
                    "nest": 10, "trend_id": 12}


def test_pack_roundtrip_within_one_quantisation_step():
    rng = np.random.default_rng(1)
    Y = rng.uniform(-1.5, 1.5, size=(500, 3))
    blob = ss.pack(Y, np.arange(500) % 180, np.full(500, 4), np.full(500, 2),
                   np.full(500, ss.NO_NEST), np.arange(1000, 1500), rng=1.5)
    assert len(blob) == 500 * 16
    rec = ss.unpack(blob)
    back = np.stack([ss.dequantise(rec[a], 1.5) for a in ("x", "y", "z")], axis=1)
    assert np.abs(back - Y).max() <= 2 * 1.5 / 65535 + 1e-12
    assert rec["trend_id"].tolist() == list(range(1000, 1500))
    assert set(rec["nest"].tolist()) == {ss.NO_NEST}


# --------------------------------------------------------------------- nests

def test_nest_membership_follows_the_archive_scan_threshold():
    C = _unit(np.eye(3, 8, dtype=np.float32))
    thr = np.array([0.9, 0.9, 0.9], dtype=np.float32)
    below = _unit(np.array([[0.89, np.sqrt(1 - 0.89 ** 2), 0, 0, 0, 0, 0, 0]], np.float32))
    above = _unit(np.array([[0.95, np.sqrt(1 - 0.95 ** 2), 0, 0, 0, 0, 0, 0]], np.float32))
    got = ss.assign_nests(np.vstack([below, above]), C, thr)
    assert got.tolist() == [ss.NO_NEST, 0]


def test_the_closer_nest_wins_when_two_are_cleared():
    C = _unit(np.array([[1, 0.2, 0], [1, 0.0, 0]], np.float32))
    thr = np.array([0.5, 0.5], dtype=np.float32)
    p = _unit(np.array([[1, 0.01, 0]], np.float32))
    assert ss.assign_nests(p, C, thr).tolist() == [1]


def test_no_nests_means_no_membership():
    X = _unit(np.random.default_rng(2).normal(size=(4, 8)).astype(np.float32))
    assert ss.assign_nests(X, np.zeros((0, 8), np.float32), np.zeros(0)).tolist() == [ss.NO_NEST] * 4


# ------------------------------------------------------------------- measure

def test_neighbour_keep_is_one_for_an_isometry_and_drops_for_noise():
    rng = np.random.default_rng(4)
    A = rng.normal(size=(60, 5))
    assert ss.neighbour_keep(A, A * 3.0 + 1.0, 5) == pytest.approx(1.0)
    assert ss.neighbour_keep(A, rng.normal(size=(60, 3)), 5) < 0.5


def test_frame_is_one_factor_and_puts_the_bulk_inside_the_box():
    Y = np.array([[0, 0, 0], [1, 0, 0], [0, 2, 0], [0, 0, 1], [50, 0, 0]], float)
    F, N = ss.frame(Y, np.array([[1.0, 1.0, 1.0]]), quantile=0.75)
    ratio_before = np.linalg.norm(Y[1] - Y[0]) / np.linalg.norm(Y[2] - Y[0])
    ratio_after = np.linalg.norm(F[1] - F[0]) / np.linalg.norm(F[2] - F[0])
    assert ratio_after == pytest.approx(ratio_before)
    assert np.abs(F[:4]).max() <= 1.0 + 1e-9
    assert np.abs(F[4]).max() > 1.0                # the outlier leaves the frame
    assert N.shape == (1, 3)


# --------------------------------------------------------------- projection

def _two_groups(n=120, dim=64, seed=9):
    rng = np.random.default_rng(seed)
    a = rng.normal(size=dim)
    b = -a
    X = np.vstack([a + 0.15 * rng.normal(size=(n, dim)), b + 0.15 * rng.normal(size=(n, dim))])
    return _unit(X.astype(np.float32))


def test_umap_keeps_two_separated_groups_apart():
    X = _two_groups()
    Y, N, var = ss.project(X, np.zeros((0, X.shape[1]), np.float32), pca_dims=10)
    a, b = Y[:120], Y[120:]
    spread = max(np.linalg.norm(a - a.mean(0), axis=1).mean(),
                 np.linalg.norm(b - b.mean(0), axis=1).mean())
    assert np.linalg.norm(a.mean(0) - b.mean(0)) > 3 * spread
    assert 0 < var <= 1.0 and N.shape == (0, 3)


def test_run_persists_one_row_is_reproducible_and_keeps_two():
    _seed({"2026-01": 40, "2026-02": 40, "2026-03": 40}, dim=1024)
    ss.migrate_signal_space_tables()
    ss.migrate_signal_space_tables()                   # idempotent
    with get_connection() as c:
        c.execute("DELETE FROM signal_space_runs")
    ids = [ss.run(per_month=25, n_months=3, end_month="2026-03") for _ in range(3)]
    assert all(i is not None for i in ids)
    with get_connection() as c:
        rows = c.execute("SELECT id, n_points, points, codes, months FROM signal_space_runs "
                         "ORDER BY id").fetchall()
    assert [r["id"] for r in rows] == ids[-2:]        # KEEP_RUNS = 2
    r = rows[-1]
    assert r["n_points"] == 75
    rec = ss.unpack(bytes(r["points"]))
    assert len(rec) == 75
    assert set(rec["trend_id"].tolist()) <= set(range(1, 121))
    assert set(rec["month"].tolist()) == {0, 1, 2}
    assert bytes(rows[0]["points"]) == bytes(rows[1]["points"])  # deterministic


# ------------------------------------------------------------- place everything

def test_every_signal_of_the_window_is_placed_and_samples_stay_put():
    _seed({"2026-01": 40, "2026-02": 40, "2026-03": 40}, dim=1024,
          extra=[("signal", "2025-06-01T10:00:00")])      # outside the window
    ss.migrate_signal_space_tables()
    with get_connection() as c:
        c.execute("DELETE FROM signal_space_runs")
    rid = ss.run(per_month=25, n_months=3, end_month="2026-03")
    with get_connection() as c:
        r = c.execute("SELECT points, all_points, n_all FROM signal_space_runs WHERE id = ?",
                      (rid,)).fetchone()
    sample = ss.unpack(bytes(r["points"]))
    every = ss.unpack(bytes(r["all_points"]))
    assert r["n_all"] == 120 == len(every)                 # all of the window, nothing else
    ids = every["trend_id"].tolist()
    assert ids == sorted(ids)                               # the server binary-searches this
    assert 121 not in ids                                   # the 2025 row is outside the window
    at = {int(t): k for k, t in enumerate(every["trend_id"])}
    for rec in sample:                                      # fitted position == placed position
        other = every[at[int(rec["trend_id"])]]
        assert (rec["x"], rec["y"], rec["z"]) == (other["x"], other["y"], other["z"])
        assert rec["month"] == other["month"] and rec["nest"] == other["nest"]


def test_sample_only_leaves_the_placed_blob_empty():
    _seed({"2026-01": 30, "2026-02": 30}, dim=1024)
    ss.migrate_signal_space_tables()
    rid = ss.run(per_month=20, n_months=2, end_month="2026-02", place_everything=False)
    with get_connection() as c:
        r = c.execute("SELECT all_points, n_all FROM signal_space_runs WHERE id = ?", (rid,)).fetchone()
    assert r["all_points"] is None and r["n_all"] is None
