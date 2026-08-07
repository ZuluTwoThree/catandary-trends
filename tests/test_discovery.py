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


# ----------------------------------------------------------------- sampling
def test_mega_scope_selects_one_canonical_and_its_orphans():
    with get_connection() as c:
        c.execute("UPDATE trends SET mega_trend='clean_energy_transition' "
                  "WHERE primary_vertical='TECH'")
    try:
        assert len(discovery.load_scope("mega:clean_energy_transition", "signal")) == 40
        assert len(discovery.load_scope("mega:NULL", "signal")) == 40
        assert len(discovery.load_scope("mega:no_such_key", "signal")) == 0
    finally:
        with get_connection() as c:
            c.execute("UPDATE trends SET mega_trend=NULL")


def test_load_scope_meta_covers_the_same_scope_without_embeddings():
    meta = discovery.load_scope_meta("global", "signal")
    assert len(meta) == 80
    assert {m["_tier"] for m in meta} == {"market", "science"}
    assert all(m["id"] and m["source_name"] for m in meta)


def test_load_scope_by_ids_returns_exactly_those_rows():
    ids = [m["id"] for m in discovery.load_scope_meta("global", "signal")[:7]]
    rows = discovery.load_scope("global", "signal", ids=ids)
    assert sorted(r["id"] for r in rows) == sorted(ids)
    assert all(r["_emb"] for r in rows)


def _meta(spec):
    """{(tier, source): count} → meta rows with unique ids."""
    out, nid = [], 0
    for (tier, src), n in spec.items():
        for _ in range(n):
            nid += 1
            out.append({"id": nid, "source_name": src, "_tier": tier})
    return out


def test_plan_sample_balances_tiers_and_redistributes_thin_ones():
    meta = _meta({**{("market", f"m{i}"): 200 for i in range(10)},
                  **{("science", f"s{i}"): 50 for i in range(4)},
                  ("patent", "p0"): 30})
    ids, rep = discovery.plan_sample(meta, 300, strata="tier", source_cap=0)
    drawn = {t: c["drawn"] for t, c in rep["tiers"].items()}
    assert len(ids) == 300 == sum(drawn.values())
    assert drawn["patent"] == 30  # thin tier: take all it has
    # market holds 82 % of this corpus — balanced sampling must not hand it 82 %
    assert drawn["market"] / 300 < 0.6
    assert drawn["science"] > 30


def test_plan_sample_without_cap_stays_proportional():
    """source_cap=0 must mean 'draw the corpus as it is' — not 'equalise sources'.
    Equalising is a far stronger intervention and would silently rewrite what the
    'legacy/proportional' comparison run is supposed to show."""
    from collections import Counter
    meta = _meta({("market", "giant"): 8000, ("market", "small"): 2000})
    src_of = {m["id"]: m["source_name"] for m in meta}
    ids, _ = discovery.plan_sample(meta, 1000, strata="proportional", source_cap=0)
    counts = Counter(src_of[i] for i in ids)
    assert 750 <= counts["giant"] <= 850  # ≈ its 80 % share, not a 50/50 split


def test_plan_sample_caps_a_dominant_source():
    from collections import Counter
    meta = _meta({("market", "giant"): 5000,
                  **{("market", f"s{i}"): 100 for i in range(20)}})
    src_of = {m["id"]: m["source_name"] for m in meta}
    ids, rep = discovery.plan_sample(meta, 1000, strata="proportional", source_cap=0.05)
    counts = Counter(src_of[i] for i in ids)
    assert counts["giant"] <= 50  # 5 % of 1000, not the 96 % it holds in the pool
    capped = rep["sources_capped"]["giant [market]"]
    assert capped["available"] == 5000 and capped["drawn"] == counts["giant"]
    assert len(ids) == 1000  # the other 20 sources absorb what the cap took away


def test_plan_sample_is_deterministic_and_reports_a_binding_cap():
    meta = _meta({("market", "a"): 300, ("market", "b"): 300})
    a, _ = discovery.plan_sample(meta, 200, seed=7)
    b, _ = discovery.plan_sample(meta, 200, seed=7)
    c, _ = discovery.plan_sample(meta, 200, seed=8)
    assert a == b and a != c
    # only 2 sources, cap 5 % of 200 = 10 each → 20 drawn, and the run says so
    ids, rep = discovery.plan_sample(meta, 200, source_cap=0.05)
    assert rep["requested"] == 200 and rep["drawn"] == len(ids) == 20
