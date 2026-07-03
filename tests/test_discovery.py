"""Tests for the two-layer discovery core (metrics + scope loading + clustering)."""

import json
import os
import struct
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_discovery_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import numpy as np
import pytest

import pipeline.db as pdb
from pipeline.db import get_connection, init_db
from pipeline import discovery

DIM = 8


def _emb(vec):
    return struct.pack(f"{len(vec)}f", *vec)


def _seed(n=40):
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    rng = np.random.default_rng(3)
    with get_connection() as c:
        c.execute("INSERT INTO sources (id,name,feed_url,source_type,vertical) "
                  "VALUES (1,'Trade','http://t','trade_media','FOOD')")
        c.execute("INSERT INTO sources (id,name,feed_url,source_type,vertical) "
                  "VALUES (2,'Res','http://r','research','TECH')")
        rid = 0
        # cluster A: axis0, FOOD+HEALTH (cross-vertical), market tier, 2024
        # cluster B: axis1, TECH single, science tier, 2022
        for c_i, (axis, verts, sid, mo) in enumerate([
            (0, ["FOOD", "HEALTH"], 1, "2024"),
            (1, ["TECH"], 2, "2022"),
        ]):
            for i in range(n):
                rid += 1
                v = np.full(DIM, 0.05, dtype=np.float32); v[axis] = 1.0
                v += rng.normal(0, 0.02, DIM).astype(np.float32)
                c.execute("INSERT INTO raw_entries (id,source_id,url,title,published_date) "
                          "VALUES (?,?,?,?,?)", (rid, sid, f"u{rid}", f"t{rid}", f"{mo}-06-01"))
                c.execute("INSERT INTO trends (raw_entry_id,title_en,slug,primary_vertical,"
                          "verticals,tags,mega_trend,source_url,source_name,embedding,status) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (rid, f"Signal {rid}", f"s{rid}", verts[0], json.dumps(verts),
                           json.dumps(["alpha" if axis == 0 else "beta"]), None,
                           f"u{rid}", "Trade" if sid == 1 else "Res", _emb(v.tolist()), "signal"))


@pytest.fixture(scope="module", autouse=True)
def seeded():
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    try:
        _seed()
        yield
    finally:
        pdb.DATABASE_PATH = old


def test_tier_of():
    assert discovery.tier_of("research", "Nature", None) == "science"
    assert discovery.tier_of("api", "NSF Awards", None) == "funding"
    assert discovery.tier_of("api", "arXiv Preprints", None) == "science"
    assert discovery.tier_of("api", "x", "US-123-B2") == "patent"  # pub_number wins
    assert discovery.tier_of("trade_media", "TechCrunch", None) == "market"


def test_scope_loading_and_cross_vertical():
    assert len(discovery.load_scope("global", "signal")) == 80
    assert len(discovery.load_scope("vertical:FOOD", "signal")) == 40
    assert len(discovery.load_scope("vertical:TECH", "signal")) == 40
    # cross-vertical pair: only the FOOD+HEALTH cluster carries both
    assert len(discovery.load_scope("pair:FOOD&HEALTH", "signal")) == 40
    assert len(discovery.load_scope("pair:FOOD&TECH", "signal")) == 0


def test_partition_recovers_structure_and_metrics():
    rows = discovery.load_scope("global", "signal")
    Xr = discovery.reduce_dims(discovery_build(rows), n_components=4)
    labels, _ = discovery.cluster_partition(Xr, k=2)
    res = discovery.characterize(rows, Xr, labels)
    assert res["n_clusters"] == 2
    labels_by = {c["verticals"][0]: c for c in res["clusters"]}
    # the FOOD+HEALTH cluster has 2 verticals → higher entropy than the TECH-only one
    food = labels_by["FOOD"]; tech = labels_by["TECH"]
    assert food["vertical_entropy"] > tech["vertical_entropy"]
    assert tech["vertical_entropy"] == 0.0  # single-vertical
    # maturity: FOOD cluster is market-tier, TECH cluster is science-tier
    assert food["tier_totals"]["market"] == 40
    assert tech["tier_totals"]["science"] == 40


def test_vertical_entropy_bounds():
    assert discovery.vertical_entropy([{"_verts": ["TECH"]}]) == 0.0
    two = discovery.vertical_entropy([{"_verts": ["FOOD", "HEALTH"]} for _ in range(10)])
    assert 0.0 < two <= 1.0


# helper: build matrix (foresight.build_matrix expects rows with _emb from load_scope)
def discovery_build(rows):
    from pipeline.foresight import build_matrix
    return build_matrix(rows)
