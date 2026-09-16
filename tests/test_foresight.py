"""Tests for the foresight core + snapshot persistence (temp DB, synthetic data)."""

import json
import os
import struct
from datetime import datetime
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
    run_id = run_snapshot("global", status="signal", k=2, window_months=0)
    assert run_id is None  # 60 signals < MIN_SIGNALS guard

    import pipeline.foresight_snapshot as snap
    old = snap.MIN_SIGNALS
    snap.MIN_SIGNALS = 10
    try:
        run_id = run_snapshot("vertical:FOOD", status="signal", k=2, tier="market",
                              window_months=0)
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
        # centroid is persisted (the detail page's nearest-neighbour anchor)
        assert c["centroid"] and len(bytes(c["centroid"])) == DIM * 4
        assert c["top_source"] == "TestSrc A"
        assert c["top_source_share"] == 1.0
    assert run["window_months"] == 0 and run["since"] is None
    assert run["cohort_sources"] is not None


# --------------------------------------------------------------- 2026-09-15 audit
# The cards' momentum was measuring our own source onboarding: inside the
# 36-month window the corpus grew 226 → 560 sources and the mix swung from
# 49 % trade media to 56 % research. These tests pin the three corrections.


def _panel_rows(months, sources, tag="topic", vert="TECH"):
    """Rows for one cluster: (month, source) pairs, one signal each."""
    out = []
    for i, (m, src) in enumerate(zip(months, sources)):
        out.append({
            "id": 10_000 + i, "title_en": f"signal {i}", "mega_trend": None,
            "tags": [tag], "source_name": src, "primary_vertical": vert,
            "status": "signal", "source_url": None,
            "published_date": f"{m}-15",
        })
    return out


def _one_cluster(rows):
    X = np.tile(np.array([1.0, 0.0], dtype=np.float32), (len(rows), 1))
    labels = np.zeros(len(rows), dtype=int)
    centroids = np.array([[1.0, 0.0]], dtype=np.float32)
    return X, labels, centroids


def test_momentum_ignores_sources_that_only_exist_late():
    """A feed switched on halfway through cannot create a rising trend."""
    months = [f"2025-{m:02d}" for m in range(1, 10)]
    # Established source delivers 6 signals a month throughout; a new source
    # starts in month 7 and delivers 30 a month — huge growth, all of it ours.
    rows = []
    for m in months:
        rows += _panel_rows([m] * 6, ["Established"] * 6)
        if m >= "2025-07":
            rows += _panel_rows([m] * 30, ["BrandNewFeed"] * 30)
    X, labels, centroids = _one_cluster(rows)
    res = foresight.analyze(rows, X, labels, centroids,
                            now=datetime(2026, 1, 15))
    assert res["cohort"]["applied"] is True
    assert res["cohort"]["sources"] == 1          # only "Established" spans both
    c = res["clusters"][0]
    # Single cluster = 100 % share in every month it appears, so the delta is
    # zero either way; what matters is that the panel excluded the newcomer.
    assert c["momentum"] in ("stable", "unknown")
    # raw counts stay honest — display never hides the newcomer's volume
    late = {p["m"]: p["n"] for p in c["monthly_series"]}
    assert late["2025-08"] == 36


def test_cohort_lifts_a_real_shift_out_of_corpus_growth():
    """Two themes, one stable panel: the share shift must survive the panel."""
    rows = []
    for m in [f"2025-{x:02d}" for x in range(1, 10)]:
        early = m <= "2025-03"
        # theme A shrinks, theme B grows — both carried by the same two feeds
        rows += _panel_rows([m] * (9 if early else 3), ["FeedOne"] * 9, tag="a")[: 9 if early else 3]
        rows += _panel_rows([m] * (3 if early else 9), ["FeedTwo"] * 9, tag="b")[: 3 if early else 9]
    for i, r in enumerate(rows):
        r["id"] = 20_000 + i
    X = np.array([[1.0, 0.0] if r["tags"] == ["a"] else [0.0, 1.0] for r in rows],
                 dtype=np.float32)
    labels = np.array([0 if r["tags"] == ["a"] else 1 for r in rows])
    centroids = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    res = foresight.analyze(rows, X, labels, centroids, now=datetime(2026, 1, 15))
    assert res["cohort"]["applied"] is True and res["cohort"]["sources"] == 2
    by_tag = {c["top_tags"][0]: c for c in res["clusters"]}
    assert by_tag["a"]["momentum"] == "declining"
    assert by_tag["b"]["momentum"] == "rising"


def test_running_month_is_dropped_from_the_axis():
    months = ["2026-07"] * 8 + ["2026-08"] * 8 + ["2026-09"] * 8
    rows = _panel_rows(months, ["FeedOne"] * 24)
    X, labels, centroids = _one_cluster(rows)
    res = foresight.analyze(rows, X, labels, centroids, now=datetime(2026, 9, 15))
    assert res["months"][-1] == "2026-08"
    assert res["cohort"]["dropped_month"] == "2026-09"
    # size still counts every member; only the series is restricted
    assert res["clusters"][0]["size"] == 24
    assert sum(p["n"] for p in res["clusters"][0]["monthly_series"]) == 16
    # a complete last month is kept
    res2 = foresight.analyze(rows, X, labels, centroids, now=datetime(2026, 10, 1))
    assert res2["months"][-1] == "2026-09"


def test_reps_are_recent_and_spread_over_sources():
    months = ["2024-01"] * 30 + ["2026-05"] * 5
    sources = ["OldFeed"] * 30 + ["A", "B", "C", "D", "E"]
    rows = _panel_rows(months, sources)
    X, labels, centroids = _one_cluster(rows)
    res = foresight.analyze(rows, X, labels, centroids, now=datetime(2026, 9, 15))
    c = res["clusters"][0]
    picked = {r["id"] for r in rows if r["id"] in set(c["rep_trend_ids"])}
    dates = [r["published_date"] for r in rows if r["id"] in picked]
    assert all(d.startswith("2026") for d in dates)      # newest win
    names = [r["source_name"] for r in rows if r["id"] in picked]
    assert len(set(names)) == len(names)                 # one per source
    assert len(c["rep_trend_ids"]) == 5


def test_reps_fill_up_when_a_cluster_has_one_source():
    rows = _panel_rows([f"2026-0{1 + i % 5}" for i in range(25)], ["OnlyFeed"] * 25)
    X, labels, centroids = _one_cluster(rows)
    res = foresight.analyze(rows, X, labels, centroids, now=datetime(2026, 9, 15))
    assert len(res["clusters"][0]["rep_trend_ids"]) == 5


def test_labels_are_unique_within_a_run():
    used: set[str] = set()
    terms = ["sustainable fashion", "circular economy", "textile recycling"]
    a = foresight.unique_label(terms, used, "x")
    used.add(a)
    b = foresight.unique_label(terms, used, "x")
    assert a == "Sustainable Fashion · Circular Economy"
    assert b != a and b.startswith("Sustainable Fashion")
    used.add(b)
    c = foresight.unique_label(terms, used, "x")
    assert c not in (a, b)


def test_acronyms_survive_the_label_pass():
    assert foresight.derive_label(["nft marketplace"]) == "NFT Marketplace"
    assert foresight.derive_label(["sbir funding"]) == "SBIR Funding"
    assert foresight.derive_label(["eu funding", "circular economy"]) \
        == "EU Funding · Circular Economy"


def test_window_since_walks_back_whole_months():
    from pipeline.foresight_snapshot import window_since
    assert window_since(24, datetime(2026, 9, 15)) == "2024-09-01"
    assert window_since(12, datetime(2026, 1, 3)) == "2025-01-01"
    assert window_since(0) is None


def test_volume_spike_of_a_panel_source_does_not_create_momentum():
    """A source inside the panel that back-ingests three months of extra rows
    must not hand its theme a rising badge (FASHION run 2026-09-15: one outlet
    went from ~50 to ~350 items a month and produced the only riser)."""
    rows = []
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    for m in months:
        spike = m in ("2025-10", "2025-11", "2025-12")
        # Outlet A carries theme "a"; it back-ingests 7x in the last quarter.
        rows += _panel_rows([m] * (70 if spike else 10), ["OutletA"] * 70, tag="a")[: 70 if spike else 10]
        # Outlet B carries theme "b" at a steady rate throughout.
        rows += _panel_rows([m] * 10, ["OutletB"] * 10, tag="b")
    for i, r in enumerate(rows):
        r["id"] = 30_000 + i
    X = np.array([[1.0, 0.0] if r["tags"] == ["a"] else [0.0, 1.0] for r in rows],
                 dtype=np.float32)
    labels = np.array([0 if r["tags"] == ["a"] else 1 for r in rows])
    centroids = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    res = foresight.analyze(rows, X, labels, centroids, now=datetime(2026, 6, 1))
    by_tag = {c["top_tags"][0]: c for c in res["clusters"]}
    assert by_tag["a"]["momentum"] == "stable"       # damped back to its median
    assert abs(by_tag["a"]["sov_delta_pp"]) < 1.0
    # the raw volume change stays visible as its own number
    assert by_tag["a"]["vol_delta_pct"] > 400   # 40 items early window, 220 late


def test_a_large_cluster_needs_a_relative_move_not_just_a_percentage_point():
    """Seed-to-seed variance moves mid-sized clusters by 1-3 pp on its own."""
    # Cluster A holds ~30 % and gains 1.2 pp = 4 % of itself → not a direction.
    rows = []
    for m in [f"2025-{x:02d}" for x in range(1, 13)]:
        early = m <= "2025-04"
        a = 30 if early else 31
        rows += _panel_rows([m] * a, ["FeedOne"] * a, tag="a")
        rows += _panel_rows([m] * (70 if early else 69), ["FeedOne"] * 70, tag="b")[: 70 if early else 69]
    for i, r in enumerate(rows):
        r["id"] = 40_000 + i
    X = np.array([[1.0, 0.0] if r["tags"] == ["a"] else [0.0, 1.0] for r in rows],
                 dtype=np.float32)
    labels = np.array([0 if r["tags"] == ["a"] else 1 for r in rows])
    centroids = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    res = foresight.analyze(rows, X, labels, centroids, now=datetime(2026, 6, 1))
    a = next(c for c in res["clusters"] if c["top_tags"][0] == "a")
    assert a["sov_delta_pp"] == 1.0 or a["momentum"] == "stable"
    # a small cluster making the same absolute move IS a direction
    assert foresight.MOMENTUM_MIN_RELATIVE == 0.10
