"""pipeline/domains.py — freely definable domains, membership from the embedding.

Pins what the two-stage pocket discovery relies on: definitions are read as written,
member thresholds keep the intended share of each tier's seeds, the tier centring takes
the writing style out before the probe decides, a stored probe decides exactly like the
trained one, and a domain-scoped archive scan counts members only (dating and
normalisation happen inside the domain)."""
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression

from pipeline import domains as D
from pipeline import emerging as E
from pipeline import emerging_snapshot as ES


def test_definitions_are_read_with_defaults(tmp_path):
    f = tmp_path / "domains.yaml"
    f.write_text("wireless:\n  name: Wireless\n  seeds:\n    cpc: [H04W]\n    phrases: ['\"5G\"']\n"
                 "bare: {}\n", encoding="utf-8")
    d = D.load_definitions(f)
    assert d["wireless"]["cpc"] == ["H04W"] and d["wireless"]["phrases"] == ['"5G"']
    assert d["wireless"]["target_recall"] == D.DEFAULT_TARGET_RECALL
    assert d["bare"]["name"] == "bare" and d["bare"]["openalex_topics"] == []


def test_threshold_keeps_the_target_share_of_seeds_but_never_goes_below_the_floor():
    p = np.linspace(0.0, 1.0, 101)
    t = D.threshold_for_recall(p, 0.3)
    assert t == pytest.approx(0.7, abs=0.01) and (p >= t).mean() == pytest.approx(0.3, abs=0.02)
    assert D.threshold_for_recall(p, 0.9) == D.MIN_THRESHOLD
    assert D.threshold_for_recall(np.array([]), 0.7) == 0.9


def _toy(seed=1, n=400, dim=D.DIM):
    """Two tiers that 'write' differently (a big offset per tier) and a small topic axis."""
    rng = np.random.default_rng(seed)
    tiers = np.array(["science"] * n + ["market"] * n)
    topic = rng.random(2 * n) < 0.3
    X = rng.normal(size=(2 * n, dim)).astype(np.float32) * 0.3
    X[tiers == "science", 0] += 6.0          # style
    X[tiers == "market", 1] += 6.0
    X[topic, 2] += 2.0                       # the domain
    return X, list(tiers), topic


def test_tier_centring_removes_the_style_axes():
    X, tiers, _ = _toy()
    Xn = X / np.linalg.norm(X, axis=1, keepdims=True)
    t = np.array(tiers)
    means = {k: Xn[t == k].mean(axis=0) for k in ("science", "market")}
    probe = D.DomainProbe("toy", None, means, 0.5)
    F = probe.features(X, tiers)
    assert abs(F[t == "science", 0].mean() - F[t == "market", 0].mean()) < 0.05


def test_a_stored_probe_decides_like_the_trained_one_with_per_tier_thresholds():
    X, tiers, y = _toy()
    Xn = X / np.linalg.norm(X, axis=1, keepdims=True)
    t = np.array(tiers)
    means = {k: Xn[t == k].mean(axis=0) for k in ("science", "market")}
    probe = D.DomainProbe("toy", None, means, 0.5, {"science": 0.6, "market": 0.8})
    probe.clf = LogisticRegression(max_iter=2000).fit(probe.features(X, tiers), y)
    again = D.DomainProbe.loads("toy", probe.dumps())
    assert np.allclose(probe.prob(X, tiers), again.prob(X, tiers))
    assert list(again.thresholds_for(["science", "market", "none"])) == [0.6, 0.8, 0.5]
    m = again.member(X, tiers)
    assert (m == (again.prob(X, tiers) >= again.thresholds_for(tiers))).all()
    assert m[y].mean() > 0.5 and m[~y].mean() < 0.1


def test_a_domain_scoped_history_scan_counts_members_only(monkeypatch):
    rng = np.random.default_rng(3)
    rows = []
    for i in range(10):
        v = rng.normal(size=8).astype(np.float32)
        rows.append({"_emb": v.tobytes(), "published_date": "2026-01-15", "source_name": f"s{i}",
                     "source_type": "research", "trend_signal_type": None, "tags": [],
                     "brands": [], "companies": [], "keep": i < 4})
    monkeypatch.setattr(E, "iter_signals", lambda **kw: iter([rows]))
    C = np.eye(8, dtype=np.float32)[:1]
    hist = E.scan_history(C, np.array([-1.0], np.float32),
                          member=lambda X, batch: np.array([r["keep"] for r in batch]))
    assert hist["totals"] == [4] and int(hist["hits"].sum()) == 4
    assert hist["scanned"] == 10


def test_scope_helpers_know_the_domain_scope():
    assert ES.domain_of("domain:wireless") == "wireless"
    assert ES.domain_of("vertical:TECH") is None
    assert ES.scope_parts("domain:wireless") == (None, None)


def test_a_domain_slice_keeps_the_members_vectors_for_the_partition(monkeypatch):
    rng = np.random.default_rng(5)
    rows = [{"_emb": rng.normal(size=16).astype(np.float32).tobytes(), "source_name": "s",
             "source_type": "research", "trend_signal_type": None, "i": i} for i in range(6)]
    monkeypatch.setattr(ES, "load_signals", lambda **kw: rows)

    class Probe:
        def member(self, X, tiers):
            return np.array([i % 2 == 0 for i in range(len(X))])

    got = ES.load_scope("domain:x", "signal,published", "2026-01-01", Probe())
    assert [r["i"] for r in got] == [0, 2, 4]
    X = ES.build_matrix(got)                     # the partition builds its matrix again
    assert X.shape == (3, 16) and np.allclose(np.linalg.norm(X, axis=1), 1.0)
