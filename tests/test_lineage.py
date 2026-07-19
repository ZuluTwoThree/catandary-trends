"""Tests for the cross-window lineage engine (issue #2 phase 1).

Synthetic temp DB, same isolation pattern as test_foresight.py: two themes with
known evolution — theme A (axis 0) spans all windows (continue chain), theme B
(axis 1) only exists in the later windows (emergence)."""

import json
import os
import struct
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_lineage_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import numpy as np
import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db
from pipeline import foresight
from pipeline.foresight_snapshot import (migrate_foresight_tables, run_lineage,
                                         prune_old_lineage_runs)

DIM = 8
N = 25  # signals per theme per month


def _emb(vec):
    return struct.pack(f"{len(vec)}f", *vec)


def _seed_db():
    """Theme A (axis 0): every month 2022-01..2024-12 (spans all windows).
    Theme B (axis 1): only 2024-01..2024-12 — absent a full span before 2024,
    so it must be flagged 'emerged' once it appears as its own cluster."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    migrate_foresight_tables()
    rng = np.random.default_rng(11)
    months_a = [f"{y}-{m:02d}" for y in (2022, 2023, 2024) for m in range(1, 13)]
    months_b = [f"2024-{m:02d}" for m in range(1, 13)]
    with get_connection() as conn:
        conn.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical)"
                     " VALUES (1, 'Src', 'http://s', 'trade_media', 'TECH')")
        rid = 0
        for axis, tag, months in [(0, "fermentation", months_a),
                                  (1, "edge-ai", months_b)]:
            for month in months:
                for _ in range(N):
                    rid += 1
                    v = np.full(DIM, 0.05, dtype=np.float32)
                    v[axis] = 1.0
                    v += rng.normal(0, 0.02, DIM).astype(np.float32)
                    conn.execute(
                        "INSERT INTO raw_entries (id, source_id, url, title,"
                        " published_date) VALUES (?, ?, ?, ?, ?)",
                        (rid, 1, f"http://x/{rid}", f"e{rid}", f"{month}-10"))
                    conn.execute(
                        "INSERT INTO trends (raw_entry_id, title_en, slug,"
                        " primary_vertical, verticals, tags, source_url, source_name,"
                        " embedding, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (rid, f"Signal {rid} {tag}", f"sig-{rid}", "TECH",
                         json.dumps(["TECH"]), json.dumps([tag]),
                         f"http://x/{rid}", "Src", _emb(v.tolist()), "signal"))


@pytest.fixture(scope="module", autouse=True)
def seeded():
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    try:
        _seed_db()
        yield
    finally:
        pdb.DATABASE_PATH = old


def test_window_bounds_rolls_and_covers():
    wins = foresight.window_bounds("2024-01-01", "2024-12-31",
                                   step_months=3, span_months=6)
    assert wins[0] == ("2024-01-01", "2024-07-01")
    assert wins[1] == ("2024-04-01", "2024-10-01")
    assert wins[-1][1] >= "2024-12-31"
    # windows overlap by span - step months
    assert all(a[1] > b[0] for a, b in zip(wins, wins[1:]))


def test_lineage_continue_and_emergence():
    res = foresight.build_lineage(
        status="signal", since="2022-01-01", until="2024-12-31",
        step_months=6, span_months=12, k_range=(2, 3), min_signals=20)
    computed = [w for w in res["windows"] if w["computed"]]
    assert len(computed) >= 4
    assert res["nodes"] and res["edges"]

    # every edge carries sane fields
    for e in res["edges"]:
        assert 0.0 <= e["drift"] <= 1.0
        assert e["relation"] in ("continue", "split", "merge", "split_merge")
        assert e["sim"] >= foresight.MATCH_SIM

    # theme A (fermentation) forms an unbroken chain across all windows
    a_nodes = [i for i, n in enumerate(res["nodes"])
               if "fermentation" in " ".join(n["top_tags"]).lower()]
    a_windows = {res["nodes"][i]["window_idx"] for i in a_nodes}
    assert a_windows == {w_i for w_i, w in enumerate(res["windows"]) if w["computed"]}
    linked = {e["from_node"] for e in res["edges"]} | {e["to_node"] for e in res["edges"]}
    assert set(a_nodes) <= linked

    # theme B (edge-ai) is absent a full span before 2024 → flagged emerged when
    # it first appears as its own cluster (judged against the non-overlapping
    # window a full span earlier, not the overlapping neighbour)
    b_nodes = [n for n in res["nodes"]
               if "edge" in " ".join(n["top_tags"]).lower()]
    assert b_nodes
    assert any(n["status"] == "emerged" for n in b_nodes)
    # theme A, present throughout, is never flagged emerged
    assert all(res["nodes"][i]["status"] != "emerged" for i in a_nodes)

    # SoV shares within a window sum to ~1
    for wi in a_windows:
        s = sum(n["sov_share"] for n in res["nodes"] if n["window_idx"] == wi)
        assert 0.99 <= s <= 1.01


def test_gap_windows_break_chains():
    # every window below min_signals → all gaps, no nodes/edges
    res = foresight.build_lineage(
        status="signal", since="2022-01-01", until="2024-12-31",
        step_months=6, span_months=12, k_range=(2, 3), min_signals=10**6)
    assert all(not w["computed"] for w in res["windows"])
    assert res["nodes"] == [] and res["edges"] == []


def test_lineage_persistence_roundtrip():
    run_id = run_lineage("vertical:TECH", status="signal", since="2022-01-01",
                         until="2024-12-31", step_months=6, span_months=12,
                         k_range=(2, 3), min_signals=20)
    assert run_id is not None
    with get_connection() as conn:
        run = conn.execute("SELECT * FROM foresight_lineage_runs WHERE id = ?",
                           (run_id,)).fetchone()
        nodes = conn.execute("SELECT * FROM foresight_lineage_nodes WHERE run_id = ?"
                             " ORDER BY node_idx", (run_id,)).fetchall()
        edges = conn.execute("SELECT * FROM foresight_lineage_edges WHERE run_id = ?",
                             (run_id,)).fetchall()
    assert run["scope"] == "vertical:TECH"
    assert run["nodes"] == len(nodes) and run["edges"] == len(edges)
    assert len(nodes) > 0 and len(edges) > 0
    node_idx = {n["node_idx"] for n in nodes}
    for e in edges:
        assert e["from_node"] in node_idx and e["to_node"] in node_idx
    for n in nodes:
        assert json.loads(n["top_tags"]) is not None
        # centroid roundtrips as float32 bytes of the right dimension
        assert len(n["centroid"]) == DIM * 4

    # prune keeps exactly the newest run per scope
    run_id2 = run_lineage("vertical:TECH", status="signal", since="2022-01-01",
                          until="2024-12-31", step_months=6, span_months=12,
                          k_range=(2, 3), min_signals=20)
    assert prune_old_lineage_runs(keep_per_scope=1) == 1
    with get_connection() as conn:
        left = conn.execute("SELECT id FROM foresight_lineage_runs").fetchall()
    assert [r["id"] for r in left] == [run_id2]
