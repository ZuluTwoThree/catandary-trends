"""Tests for the foresight core + snapshot persistence (temp DB, synthetic data)."""

import json
import os
import struct
import tempfile

# Belt-and-braces: set env for the standalone case; the fixture below also
# patches pipeline.db.DATABASE_PATH directly, because in a full-suite run
# another test module may already have imported pipeline.config with its own
# temp path (env is only read at first import).
TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_foresight_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import numpy as np
import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db
from pipeline import foresight
from pipeline.foresight_snapshot import migrate_foresight_tables, run_snapshot

DIM = 8  # tiny embeddings — the code derives dim from blob length


def _emb(vec):
    return struct.pack(f"{len(vec)}f", *vec)


def _seed_db(n_per_cluster: int = 30):
    """Two well-separated clusters: axis-0 heavy (FOOD, tag fermentation, months
    2024-01..03) and axis-1 heavy (TECH, tag edge-ai, months 2024-04..06)."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    migrate_foresight_tables()
    rng = np.random.default_rng(7)
    with get_connection() as conn:
        conn.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical)"
                     " VALUES (1, 'TestSrc A', 'http://a', 'trade_media', 'FOOD')")
        conn.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical)"
                     " VALUES (2, 'TestSrc B', 'http://b', 'research', 'TECH')")
        rid = 0
        for c, (axis, vert, tag, months) in enumerate([
            (0, "FOOD", "fermentation", ["2024-01", "2024-02", "2024-03"]),
            (1, "TECH", "edge-ai", ["2024-04", "2024-05", "2024-06"]),
        ]):
            for i in range(n_per_cluster):
                rid += 1
                base = np.full(DIM, 0.05, dtype=np.float32)
                base[axis] = 1.0
                base += rng.normal(0, 0.02, DIM).astype(np.float32)
                month = months[i % len(months)]
                conn.execute(
                    "INSERT INTO raw_entries (id, source_id, url, title, published_date)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (rid, c + 1, f"http://x/{rid}", f"entry {rid}", f"{month}-15"))
                conn.execute(
                    "INSERT INTO trends (raw_entry_id, title_en, slug, primary_vertical,"
                    " verticals, tags, mega_trend, source_url, source_name, embedding,"
                    " status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, f"Signal {rid} {tag}", f"sig-{rid}", vert,
                     json.dumps([vert]), json.dumps([tag, "innovation"]),
                     "future_of_food_and_agriculture" if vert == "FOOD" else None,
                     f"http://x/{rid}", f"TestSrc {'A' if c == 0 else 'B'}",
                     _emb(base.tolist()), "signal"))


@pytest.fixture(scope="module", autouse=True)
def seeded():
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    try:
        _seed_db()
        yield
    finally:
        pdb.DATABASE_PATH = old


def test_load_signals_filters():
    assert len(foresight.load_signals(status="signal")) == 60
    assert len(foresight.load_signals(status="signal", vertical="FOOD")) == 30
    assert len(foresight.load_signals(status="published")) == 0
    assert len(foresight.load_signals(status="signal", source_like="TestSrc A")) == 30
    assert len(foresight.load_signals(status="signal", since="2024-04-01")) == 30


def test_cluster_and_analyze_recovers_structure():
    rows = foresight.load_signals(status="signal")
    X = foresight.build_matrix(rows)
    assert X.shape == (60, DIM)
    assert np.allclose(np.linalg.norm(X, axis=1), 1.0, atol=1e-5)
    labels, centroids, k = foresight.cluster_signals(X, k=2)
    result = foresight.analyze(rows, X, labels, centroids)
    assert len(result["clusters"]) == 2
    for c in result["clusters"]:
        assert c["size"] == 30
        assert c["cohesion"] > 0.9          # tight synthetic clusters
        assert c["n_sources"] == 1
        assert len(c["rep_titles"]) == 5
        # monthly series covers the global axis and sums to the cluster size
        assert sum(p["n"] for p in c["monthly_series"]) == 30
    # each cluster is pure in one vertical
    verts = sorted(c["verticals"][0] for c in result["clusters"])
    assert verts == ["FOOD", "TECH"]


def test_source_weights_backward_compatible():
    # source_weights=None must produce byte-identical output to omitting it
    rows = foresight.load_signals(status="signal")
    X = foresight.build_matrix(rows)
    labels, centroids, _ = foresight.cluster_signals(X, k=2)
    base = foresight.analyze(rows, X, labels, centroids)
    same = foresight.analyze(rows, X, labels, centroids, source_weights=None)
    assert json.dumps(base, sort_keys=True) == json.dumps(same, sort_keys=True)
    # a uniform weight of 1.0 for every source is also identical (shares invariant)
    uni = {"TestSrc A": 1.0, "TestSrc B": 1.0}
    same2 = foresight.analyze(rows, X, labels, centroids, source_weights=uni)
    assert json.dumps(base, sort_keys=True) == json.dumps(same2, sort_keys=True)


def test_source_weights_shift_share():
    # Co-temporal mixed sources: two clusters in the SAME month, one fed by a
    # noisy source. Down-weighting that source must lower its cluster's share
    # (and raise the clean cluster's), while raw sizes stay put.
    n = 20
    rows, embs = [], []
    for i in range(2 * n):
        clean = i < n
        base = np.array([1.0, 0.05] if clean else [0.05, 1.0], dtype=np.float32)
        base += np.random.default_rng(i).normal(0, 0.01, 2).astype(np.float32)
        embs.append(base)
        rows.append({
            "id": i, "title_en": f"t{i}", "mega_trend": None,
            "tags": ["clean" if clean else "noisy"],
            "source_name": "CleanSrc" if clean else "NoisySrc",
            "primary_vertical": "FOOD" if clean else "TECH",
            "status": "signal", "source_url": None,
            "published_date": "2024-03-15",  # all same month
        })
    X = np.array(embs, dtype=np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    labels = np.array([0] * n + [1] * n)
    centroids = np.array([[1.0, 0.05], [0.05, 1.0]], dtype=np.float32)

    base = foresight.analyze(rows, X, labels, centroids)
    weighted = foresight.analyze(rows, X, labels, centroids,
                                 source_weights={"NoisySrc": 0.2})

    def cluster_for(res, vert):
        return next(c for c in res["clusters"] if c["verticals"][0] == vert)

    # raw size unchanged (display honesty)
    assert cluster_for(base, "TECH")["size"] == cluster_for(weighted, "TECH")["size"]
    # noisy cluster loses share, clean cluster gains it
    assert cluster_for(weighted, "TECH")["monthly_series"][0]["share"] < \
        cluster_for(base, "TECH")["monthly_series"][0]["share"]
    assert cluster_for(weighted, "FOOD")["monthly_series"][0]["share"] > \
        cluster_for(base, "FOOD")["monthly_series"][0]["share"]


def test_derive_label_skips_generic_tags():
    assert foresight.derive_label(["innovation", "fermentation"]) == "Fermentation"
    assert foresight.derive_label(["precision_fermentation", "alt_protein"]) \
        == "Precision Fermentation · Alt Protein"
    assert foresight.derive_label([]) == "Unlabelled cluster"


def test_snapshot_roundtrip():
    run_id = run_snapshot("global", status="signal", k=2)
    assert run_id is None  # 60 signals < MIN_SIGNALS guard

    import pipeline.foresight_snapshot as snap
    old = snap.MIN_SIGNALS
    snap.MIN_SIGNALS = 10
    try:
        run_id = run_snapshot("vertical:FOOD", status="signal", k=2, tier="market")
    finally:
        snap.MIN_SIGNALS = old
    assert run_id is not None

    with get_connection() as conn:
        run = conn.execute("SELECT * FROM foresight_runs WHERE id = ?",
                           (run_id,)).fetchone()
        clusters = conn.execute(
            "SELECT * FROM foresight_clusters WHERE run_id = ?", (run_id,)).fetchall()
    assert run["scope"] == "vertical:FOOD"
    assert run["tier"] == "market"
    assert run["signals"] == 30
    assert run["first_month"] == "2024-01" and run["last_month"] == "2024-03"
    assert len(clusters) == 2
    for c in clusters:
        assert c["tier"] == "market"
        series = json.loads(c["monthly_series"])
        assert all(set(p) == {"m", "n", "share"} for p in series)
        assert json.loads(c["rep_trend_ids"])
        assert c["momentum"] in ("rising", "stable", "declining", "unknown")
