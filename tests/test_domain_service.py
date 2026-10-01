"""pipeline/domain_service.py + the domain additions to pipeline/emerging.py.

Pins what live discovery relies on: the in-memory copy answers like the database code
(background sample, membership), a free term with synonyms seeds every spelling, the
domain-relative density gate keeps only the domain's densest cells, duplicates are
merged on domain-centred cosine (and only then), pockets are grouped deterministically,
and the archive scan reads (X, rows) pairs as it reads the database."""
import numpy as np
from sklearn.linear_model import LogisticRegression

from pipeline import domain_service as S
from pipeline import domains as D
from pipeline import emerging as E


def _rows(n, start=1, dim=D.DIM, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        v = rng.normal(size=dim).astype(np.float32)
        out.append({"id": start + i, "_emb": v.tobytes(), "published_date": f"2026-0{1 + i % 9}-10",
                    "status": ["signal", "published", "draft"][i % 3],
                    "source_name": ["arXiv", "Google Patents US", "TechCrunch", "OpenAlex corpus: Food"][i % 4],
                    "source_type": ["research", "api", "trade_media", "research"][i % 4],
                    "trend_signal_type": None})
    return out


def _store(n=300):
    st = S.Store()
    st._append(_rows(n))
    return st


def test_the_copy_holds_unit_vectors_months_tiers_and_status():
    st = _store(30)
    assert st.n == 30 and np.allclose(np.linalg.norm(st.X[:30].astype(np.float32), axis=1), 1, atol=1e-2)
    assert S.month_str(int(st.month[0])) == "2026-01" and st.month[1] == st.month[0] + 1
    assert S.TIER_NAMES[st.tier[0]] == "science" and S.TIER_NAMES[st.tier[1]] == "patent"
    assert list(st.status[:3]) == [S.ST_SIGNAL, S.ST_PUBLISHED, S.ST_OTHER]
    assert list(st.index_of([1, 30, 31])) == [0, 29, -1]
    assert st.known([1, 2, 3, 99]) == {1, 2}            # 3 is a draft, 99 unknown


def test_growing_keeps_the_rows_already_there():
    st = _store(10)
    first = st.X[:10].copy()
    st._append(_rows(5, start=11, seed=9))
    assert st.n == 15 and np.array_equal(st.X[:10], first) and list(st.index_of([15])) == [14]


def test_background_follows_the_hash_rule_and_skips_drafts_and_exclusions():
    st = _store(600)
    got = st.background(50, exclude={1, 2})
    h = [(i * D.HASH_MUL) % D.HASH_MOD for i in got]
    assert h == sorted(h) and 1 not in got and 2 not in got
    assert all(st.status[st.index_of([i])[0]] <= S.ST_PUBLISHED for i in got)
    assert st.background(50, set()) == st.background(50, set())
    assert st.excluded([4, 8, 1]) == {4, 8}             # "OpenAlex corpus: …" rows


def test_membership_in_memory_equals_the_probe():
    st = _store(300)
    X, tiers = st.vectors([int(i) for i in st.ids[:st.n] if st.status[st.index_of([int(i)])[0]] <= 1])
    t = np.array(tiers)
    means = {k: X[t == k].mean(axis=0) for k in set(tiers)}
    probe = D.DomainProbe("toy", None, means, 0.5, {"science": 0.4, "market": 0.6})
    y = X[:, 0] > 0
    probe.clf = LogisticRegression(max_iter=2000).fit(probe.features(X, tiers), y)
    p, thr = st.probability(probe)
    idx = st.index_of(st.ids[:st.n])
    allX, allT = st.X[idx].astype(np.float32), [S.TIER_NAMES[k] for k in st.tier[idx]]
    assert np.allclose(p, probe.prob(allX, allT), atol=1e-4)
    assert np.allclose(thr, probe.thresholds_for(allT))


def test_a_free_term_seeds_each_spelling_and_keeps_the_key_of_the_term():
    d = D.adhoc_definition("  Solid-state  battery ", ["all-solid-state battery", "Solid-state battery", ""])
    assert d["key"] == "q_solid_state_battery" and d["name"] == "Solid-state battery"
    assert d["phrases"] == ['"Solid-state battery"', '"all-solid-state battery"']
    assert d["vector_queries"] == ["Solid-state battery", "all-solid-state battery"]


def _blobs(seed=0, per=60, dim=32, spread=0.08, centres=None):
    rng = np.random.default_rng(seed)
    base = rng.normal(size=dim)
    centres = centres if centres is not None else [base + rng.normal(size=dim) * 0.35 for _ in range(6)]
    X = np.vstack([c + rng.normal(size=(per, dim)) * spread * (1 + 2 * i)
                   for i, c in enumerate(centres)]).astype(np.float32)
    return X / np.linalg.norm(X, axis=1, keepdims=True)


def test_the_relative_gate_keeps_only_the_domains_densest_cells():
    X = _blobs()
    loose = E.detect_nests(X, k=6, min_cohesion=0.0, min_size=10)
    tight = E.detect_nests(X, k=6, min_cohesion=0.0, min_size=10, relative_quantile=0.75)
    assert len(tight) < len(loose)
    assert min(n["cohesion"] for n in tight) >= np.quantile([n["cohesion"] for n in loose], 0.5)


def test_inside_a_domain_only_true_duplicates_merge():
    rng = np.random.default_rng(4)
    dim = 32
    shared = rng.normal(size=dim) * 4                  # the domain's own direction
    a, b = rng.normal(size=dim), rng.normal(size=dim)
    twin = a + rng.normal(size=dim) * 0.15             # a duplicate of a
    X = _blobs(per=50, dim=dim, spread=0.05, centres=[shared + a, shared + twin, shared + b])
    center = X.mean(axis=0)
    plain = E.detect_nests(X, k=3, min_cohesion=0.0, min_size=5)
    merged = E.detect_nests(X, k=3, min_cohesion=0.0, min_size=5, center=center)
    assert len(plain) == 1 and len(merged) == 2       # raw cosine alone fuses the whole domain
    assert sorted(n["members"].size for n in merged) == [50, 100]


def test_groups_are_numbered_by_size_and_stable():
    rng = np.random.default_rng(2)
    dim = 16
    g1, g2 = np.eye(dim)[0] * 3, np.eye(dim)[1] * 3      # two unrelated sub-topics
    nests = []
    for i, (g, size) in enumerate([(g1, 10), (g2, 50), (g1, 12), (g2, 40)]):
        c = g + rng.normal(size=dim) * 0.1
        nests.append({"centroid": (c / np.linalg.norm(c)).astype(np.float32), "size": size})
    center = np.zeros(dim, np.float32)
    E.group_nests(nests, center)
    assert [n["group_id"] for n in nests] == [2, 1, 2, 1]
    one = [{"centroid": nests[0]["centroid"], "size": 3}]
    E.group_nests(one, center)
    assert one[0]["group_id"] == 1


def test_the_archive_scan_reads_given_batches_like_the_database():
    rng = np.random.default_rng(7)
    X = rng.normal(size=(6, 8)).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    rows = [{"published_date": f"2025-0{1 + i % 2}-01", "source_name": "s", "source_type": "research",
             "trend_signal_type": None, "tags": [], "brands": [], "companies": []} for i in range(6)]
    hist = E.scan_history(X[:1], np.array([-1.0], np.float32), batches=iter([(X[:4], rows[:4]), (X[4:], rows[4:])]))
    assert hist["months"] == ["2025-01", "2025-02"] and hist["totals"] == [3, 3]
    assert hist["scanned"] == 6 and int(hist["hits"].sum()) == 6


def test_nearest_ranks_by_cosine_and_ignores_spare_capacity(monkeypatch):
    st = _store(40)                                    # capacity > n after _reserve
    assert len(st.ids) > st.n
    target = st.X[7].astype(np.float32)
    monkeypatch.setattr(D, "embed_text", lambda text: target * 3)
    got = st.nearest("anything", 1)
    assert got == {int(st.ids[7])} or st.status[7] > S.ST_PUBLISHED


def test_the_term_counts_in_any_inflection_and_only_as_a_phrase():
    assert S.carries_term("New Battery chemistry", ["batteries"])
    assert S.carries_term("Solid-state batteries go to market", ["solid-state battery"])
    assert not S.carries_term("A solid approach to state battery policy", ["solid-state battery"])
    assert S.carries_term("precision fermentations scale up", ["precision fermentation"])
    assert not S.carries_term("glass making", ["gas"])


def test_each_conversation_keeps_its_own_densest_quarter():
    rng = np.random.default_rng(11)
    dim = 32
    tight = [rng.normal(size=dim) for _ in range(8)]        # "research": dense cells
    loose = [rng.normal(size=dim) for _ in range(8)]        # "market": looser cells
    X = np.vstack([c + rng.normal(size=(40, dim)) * 0.05 for c in tight]
                  + [c + rng.normal(size=(40, dim)) * 0.25 for c in loose]).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    tiers = np.array(["science"] * 320 + ["market"] * 320)
    pooled = E.detect_nests(X, k=16, min_cohesion=0.0, min_size=10, relative_quantile=0.75)
    split = E.detect_nests(X, k=16, min_cohesion=0.0, min_size=10, relative_quantile=0.75,
                           row_tiers=tiers)
    t_of = lambda n: tiers[n["members"][0]]
    assert {t_of(n) for n in pooled} == {"science"}
    assert {t_of(n) for n in split} == {"science", "market"}
