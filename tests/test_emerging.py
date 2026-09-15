"""Emerging-nest detection and dating (synthetic vectors, no DB for the engine)."""

from datetime import datetime

import numpy as np
import pytest

from pipeline import emerging as E


def _unit(vec):
    v = np.asarray(vec, dtype=np.float32)
    return v / np.linalg.norm(v)


def _blob(center, n, spread, rng):
    """n points around `center` on the unit sphere."""
    pts = np.tile(np.asarray(center, dtype=np.float32), (n, 1))
    pts += rng.normal(0, spread, pts.shape).astype(np.float32)
    return pts / np.clip(np.linalg.norm(pts, axis=1, keepdims=True), 1e-9, None)


def _space(rng, dim=32):
    """Two tight pockets plus a broad diffuse cloud that must stay noise."""
    a = np.zeros(dim, dtype=np.float32); a[0] = 1.0
    b = np.zeros(dim, dtype=np.float32); b[1] = 1.0
    tight_a = _blob(a, 120, 0.02, rng)
    tight_b = _blob(b, 90, 0.02, rng)
    cloud = rng.normal(0, 1, (900, dim)).astype(np.float32)
    cloud /= np.clip(np.linalg.norm(cloud, axis=1, keepdims=True), 1e-9, None)
    X = np.vstack([tight_a, tight_b, cloud])
    truth = np.array([0] * 120 + [1] * 90 + [-1] * 900)
    return X, truth


def test_detect_nests_finds_the_pockets_and_leaves_the_cloud_as_noise():
    rng = np.random.default_rng(3)
    X, truth = _space(rng)
    nests = E.detect_nests(X, k=40, seed=42)
    assert 2 <= len(nests) <= 6                     # the two pockets, maybe cloud shards
    covered = sum(n["members"].size for n in nests)
    assert covered < 0.5 * len(X)                   # most of the space is NOT a nest
    # each true pocket is recovered by one nest with high purity
    for label, size in ((0, 120), (1, 90)):
        best = max(nests, key=lambda n: (truth[n["members"]] == label).sum())
        got = (truth[best["members"]] == label).sum()
        assert got >= 0.8 * size
        assert (truth[best["members"]] == -1).mean() < 0.2
        assert best["cohesion"] >= E.MIN_COHESION


def test_detect_nests_merges_a_pocket_that_the_partition_split():
    rng = np.random.default_rng(5)
    dim = 32
    a = np.zeros(dim, dtype=np.float32); a[0] = 1.0
    X = _blob(a, 400, 0.02, rng)                     # ONE pocket
    nests = E.detect_nests(X, k=12, seed=42)         # forced to cut it into 12
    assert len(nests) == 1                           # …and put back together
    assert nests[0]["members"].size == 400


def test_detect_nests_rejects_a_loose_cell():
    rng = np.random.default_rng(7)
    X = rng.normal(0, 1, (600, 32)).astype(np.float32)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    assert E.detect_nests(X, k=20, seed=42) == []


def _rows(months, sources, tags):
    return [{"id": 1000 + i, "title_en": f"t{i}", "mega_trend": None, "tags": list(tags),
             "source_name": sources[i % len(sources)], "primary_vertical": "TECH",
             "status": "signal", "source_url": None, "published_date": f"{m}-15"}
            for i, m in enumerate(months)]


def test_describe_nests_labels_and_picks_recent_reps_one_per_source():
    rng = np.random.default_rng(11)
    dim = 32
    a = np.zeros(dim, dtype=np.float32); a[0] = 1.0
    X = _blob(a, 60, 0.02, rng)
    months = ["2024-01"] * 55 + ["2026-08"] * 5
    rows = _rows(months, ["Old", "A", "B", "C", "D", "E"], ["solid state battery", "ai"])
    for i, r in enumerate(rows):
        r["source_name"] = "Old" if i < 55 else ["A", "B", "C", "D", "E"][i - 55]
    nests = E.detect_nests(X, k=4, seed=42)
    E.describe_nests(nests, rows)
    n = nests[0]
    assert n["label"]
    assert n["size"] == 60
    assert n["top_source"] == "Old" and n["top_source_share"] > 0.9
    picked = {r["id"] for r in rows if r["id"] in set(n["rep_trend_ids"])}
    dates = [r["published_date"] for r in rows if r["id"] in picked]
    assert all(d.startswith("2026") for d in dates)
    names = [r["source_name"] for r in rows if r["id"] in picked]
    assert len(set(names)) == len(names)


def _history(months, corpus_per_month, nest_hits):
    """Hand-built history: nest_hits is a list per nest of per-month counts."""
    return {
        "months": list(months),
        "totals": [corpus_per_month] * len(months),
        "hits": np.array(nest_hits, dtype=np.int32),
        "old_tags": {},
        "recent_tags": {},
        "scanned": corpus_per_month * len(months),
    }


def test_score_nests_dates_the_first_appearance():
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    # nest 0 appears only from month 9; nest 1 has been there all along
    young = [0] * 8 + [10, 12, 15, 20]
    old = [10] * 12
    nests = [{"top_tags": []}, {"top_tags": []}]
    E.score_nests(nests, _history(months, 1000, [young, old]))
    assert nests[0]["first_month"] == "2025-09"
    assert nests[0]["age_months"] == 4
    assert nests[1]["first_month"] == "2025-01"
    assert nests[1]["age_months"] == 12


def test_novelty_lift_is_corpus_normalised():
    """A nest spread like the corpus scores 1; a young one scores far above."""
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    flat = [10] * 12
    young = [0] * 6 + [0, 0, 5, 20, 30, 40]
    nests = [{"top_tags": []}, {"top_tags": []}]
    E.score_nests(nests, _history(months, 1000, [flat, young]))
    assert nests[0]["novelty_lift"] == pytest.approx(1.0, abs=0.01)
    assert nests[1]["novelty_lift"] > 1.8


def test_novelty_lift_ignores_corpus_growth():
    """Our own intake tripling must not make every nest look new."""
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    hist = _history(months, 1000, [[10] * 6 + [30] * 6])
    hist["totals"] = [1000] * 6 + [3000] * 6       # corpus tripled, nest tracked it
    nests = [{"top_tags": []}]
    E.score_nests(nests, hist)
    assert nests[0]["novelty_lift"] == pytest.approx(1.0, abs=0.01)


def test_new_terms_need_a_vocabulary_that_did_not_exist_before():
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    hist = _history(months, 1000, [[5] * 12])
    hist["old_tags"] = {"ai": 500, "robotics": 400}
    hist["recent_tags"] = {"ai": 500, "robotics": 400, "agentic commerce": 300}
    nests = [{"top_tags": ["ai", "agentic commerce", "robotics"]}]
    E.score_nests(nests, hist)
    assert nests[0]["new_terms"] == ["agentic commerce"]


def test_score_nests_survives_an_empty_history():
    nests = [{"top_tags": ["x"]}]
    E.score_nests(nests, _history([], 0, np.zeros((1, 0), dtype=np.int32)))
    assert nests[0]["first_month"] is None and nests[0]["novelty_lift"] is None


def test_pick_cells_stays_inside_its_bounds():
    assert E.pick_cells(300_000) == 750
    assert E.pick_cells(50_000_000) == E.MAX_CELLS


def test_pick_cells_scales_its_floor_down_for_a_thin_vertical():
    """120 cells over 1,000 documents leaves 8 per cell — every one of them
    below the nest size gate, so the scope would find nothing at all."""
    assert E.pick_cells(1_000) == 25        # 40 documents per cell
    assert E.pick_cells(3_518) == 87        # the DESIGN case that found nothing
    assert E.pick_cells(60_000) == E.MIN_CELLS
    assert E.pick_cells(20_000) == E.MIN_CELLS
    assert E.pick_cells(120_000) == 300   # n // DOCS_PER_CELL once past the floor
    assert E.pick_cells(100) >= 8


def test_title_terms_names_a_nest_that_has_no_tags():
    titles = [
        "E8-Cromwell Observer Field: Quantum Decoherence Through Root Vector Projection",
        "E8 Phi-Coupled Topological Vortex Lattice for Lossless Quantum Coherence",
        "E8-Phi Resonance Lattice for Golden-Ratio Gravitational Encoding",
        "Quantum synaptic distress and biosphere sensor networks",
    ]
    terms = E.title_terms(titles)
    assert "quantum" in terms
    assert all(t not in E.TITLE_STOPWORDS for t in terms)
    # stopwords and numbers never become a name
    assert E.title_terms(["The new study of the data", "A new study of the data"]) == []


def test_describe_nests_falls_back_to_titles_and_measures_tag_coverage():
    rng = np.random.default_rng(13)
    dim = 32
    a = np.zeros(dim, dtype=np.float32); a[0] = 1.0
    X = _blob(a, 60, 0.02, rng)
    rows = _rows(["2026-08"] * 60, ["S1", "S2"], [])
    for i, r in enumerate(rows):
        r["tags"] = []
        r["title_en"] = "Perovskite tandem module field degradation"
    nests = E.detect_nests(X, k=4, seed=42)
    E.describe_nests(nests, rows)
    assert "Perovskite" in nests[0]["label"]
    assert nests[0]["tagged_share"] == 0.0


def test_tagged_share_counts_members_that_passed_classification():
    rng = np.random.default_rng(17)
    dim = 32
    a = np.zeros(dim, dtype=np.float32); a[0] = 1.0
    X = _blob(a, 60, 0.02, rng)
    rows = _rows(["2026-08"] * 60, ["S1"], ["battery"])
    for r in rows[:15]:
        r["tags"] = []
    nests = E.detect_nests(X, k=4, seed=42)
    E.describe_nests(nests, rows)
    n = nests[0]
    untagged = sum(1 for i in n["members"] if not rows[i]["tags"])
    assert n["tagged_share"] == round(1 - untagged / n["members"].size, 4)
    assert 0.6 < n["tagged_share"] < 0.9


def test_established_share_separates_a_new_theme_from_a_new_subscription():
    """The first FOOD run filled its top ten with agronomy pockets 'first seen
    3 months ago' — from journal sweeps that started 3 months ago. Their age
    measured our subscriptions."""
    months = [f"20{y:02d}-{m:02d}" for y in range(24, 27) for m in range(1, 13)][:33]
    hist = _history(months, 1000, [[0] * 30 + [10, 12, 14], [0] * 30 + [10, 12, 14]])
    hist["source_first"] = {
        "OldJournal": "2015-01",       # read for years
        "BrandNewSweep": months[-3],   # started when the pocket appeared
    }
    nests = [
        {"top_tags": [], "source_counts": {"OldJournal": 40, "BrandNewSweep": 10}},
        {"top_tags": [], "source_counts": {"BrandNewSweep": 50}},
    ]
    E.score_nests(nests, hist)
    assert nests[0]["established_share"] == 0.8      # a real move in a read field
    assert nests[1]["established_share"] == 0.0      # nothing but a new feed
    # both look equally young on the raw dating
    assert nests[0]["first_month"] == nests[1]["first_month"]


def test_established_share_is_zero_when_nothing_is_known_about_the_sources():
    nests = [{"top_tags": [], "source_counts": {"X": 5}}]
    E.score_nests(nests, _history([f"2025-{m:02d}" for m in range(1, 13)], 100, [[5] * 12]))
    assert nests[0]["established_share"] == 0.0


def test_top_n_replaces_the_absolute_gate_with_a_relative_one():
    """The corpus of 2025 is diffuser than the corpus of 2026; an absolute bar
    then answers 'was our intake dense' instead of 'was the trend findable'."""
    rng = np.random.default_rng(23)
    dim = 32
    blobs = []
    for axis, spread in ((0, 0.02), (1, 0.05), (2, 0.12), (3, 0.2)):
        c = np.zeros(dim, dtype=np.float32); c[axis] = 1.0
        blobs.append(_blob(c, 80, spread, rng))
    X = np.vstack(blobs)
    strict = E.detect_nests(X, k=16, seed=42)                 # 0.75 bar
    loose = E.detect_nests(X, k=16, seed=42, top_n=4)
    assert len(loose) >= len(strict)
    assert len(loose) <= 4
    # the relative run still reports density, so the caller can re-apply the bar
    would_pass = [n for n in loose if n["cohesion"] >= E.MIN_COHESION]
    assert len(would_pass) == len(strict)
    assert all(n["members"].size >= E.MIN_NEST_SIZE for n in loose)


# --- lead-time tiers (Owner 2026-09-15) -------------------------------------
# "ein science trend ist nicht das selbe wie ein markttrend, selbst wenn
# thematisch deckungsgleich" — perovskite is researched, then patented, then
# funded, then argued about. One date per pocket is the earliest of four.

def _tier_history(months, per_tier, corpus=1000):
    """per_tier: {tier: [counts per month]} for a single nest."""
    total = np.sum([per_tier.get(t, [0] * len(months)) for t in ("science", "patent",
                                                                 "funding", "market")], axis=0)
    return {
        "months": list(months),
        "totals": [corpus] * len(months),
        "hits": np.array([total], dtype=np.int32),
        "tier_hits": {t: np.array([per_tier.get(t, [0] * len(months))], dtype=np.int32)
                      for t in ("science", "patent", "funding", "market")},
        "tier_totals": {t: [corpus // 4] * len(months) for t in
                        ("science", "patent", "funding", "market")},
        "actors": [{"early": 0, "late": 0}],
        "old_tags": {}, "recent_tags": {}, "source_first": {}, "scanned": 0,
    }


def test_each_tier_is_dated_separately():
    months = [f"2024-{m:02d}" for m in range(1, 13)] + [f"2025-{m:02d}" for m in range(1, 13)]
    hist = _tier_history(months, {
        "science": [5] * 24,                      # there from the start
        "patent":  [0] * 6 + [4] * 18,            # six months later
        "funding": [0] * 12 + [3] * 12,           # a year later
        "market":  [0] * 18 + [6] * 6,            # only in the last half year
    })
    nests = [{"top_tags": [], "source_counts": {}}]
    E.score_nests(nests, hist)
    t = nests[0]["tiers"]
    assert t["science"]["first_month"] == "2024-01"
    assert t["patent"]["first_month"] == "2024-07"
    assert t["funding"]["first_month"] == "2025-01"
    assert t["market"]["first_month"] == "2025-07"
    assert nests[0]["tier_order"] == ["science", "patent", "funding", "market"]
    assert nests[0]["science_to_market_months"] == 18


def test_a_pure_market_pocket_has_no_science_lead():
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    hist = _tier_history(months, {"market": [8] * 12})
    nests = [{"top_tags": [], "source_counts": {}}]
    E.score_nests(nests, hist)
    assert list(nests[0]["tiers"]) == ["market"]
    assert nests[0]["science_to_market_months"] is None
    assert nests[0]["tier_order"] == ["market"]


def test_a_single_stray_paper_does_not_start_a_tier():
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    hist = _tier_history(months, {"science": [1, 1, 0, 0, 5, 5, 5, 5, 5, 5, 5, 5]})
    nests = [{"top_tags": [], "source_counts": {}}]
    E.score_nests(nests, hist)
    assert nests[0]["tiers"]["science"]["first_month"] == "2025-05"


def test_actor_diffusion_is_reported_next_to_the_counts():
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    hist = _tier_history(months, {"market": [10] * 12})
    hist["actors"] = [{"early": 4, "late": 20}]
    nests = [{"top_tags": [], "source_counts": {}}]
    E.score_nests(nests, hist)
    assert nests[0]["actors_early"] == 4
    assert nests[0]["actors_late"] == 20
    assert nests[0]["actor_growth"] == 5.0


def test_scope_parts_reads_both_kinds_of_scope():
    from pipeline.emerging_snapshot import scope_parts
    assert scope_parts("global") == (None, None)
    assert scope_parts("vertical:FOOD") == ("FOOD", None)
    assert scope_parts("tier:market") == (None, "market")
    assert scope_parts("tier:science") == (None, "science")
