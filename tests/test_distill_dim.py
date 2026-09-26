"""Heads on the 1024-dim Matryoshka prefix (2026-09-26, OOM-Fix).

The Sunday retrain died at 56 GB (1.83M x 4096 x 4 B matrix plus one sklearn
copy). Training moved to the 1024-dim prefix; inference keeps receiving the
full 4096-dim vector and every head is fed its own width. These tests pin the
two properties that make that safe:

  * slicing + normalising at inference == what the trainer loaded from
    trends.embedding_1024 (which IS trends.embedding[:1024]),
  * heads of DIFFERENT widths coexist in one classifier — production runs four
    1024-dim heads next to the 4096-dim signal_type head (#110).
"""
import os
import struct
import sys
import tempfile
from pathlib import Path

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_distill_dim_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pipeline.db import get_connection, init_db
from pipeline.distill import DistillClassifier, _HeadInput, _normalize

import train_distill_heads as tdh  # noqa: E402


def _unit(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True)


# --- inference: one input, several head widths ------------------------------

def test_head_input_prefix_equals_normalised_slice():
    rng = np.random.default_rng(7)
    X = rng.normal(size=(5, 4096)).astype(np.float32)

    class Narrow:
        n_features_in_ = 1024

    got = _HeadInput(X).for_head(Narrow())
    assert got.shape == (5, 1024)
    np.testing.assert_allclose(got, _unit(X[:, :1024]), atol=1e-6)


def test_head_input_full_width_is_unsliced():
    rng = np.random.default_rng(8)
    X = rng.normal(size=(3, 4096)).astype(np.float32)

    class Full:
        n_features_in_ = 4096

    np.testing.assert_allclose(_HeadInput(X).for_head(Full()), _normalize(X), atol=1e-6)


def test_head_input_caches_per_width():
    inp = _HeadInput(np.ones((2, 4096), dtype=np.float32))

    class Narrow:
        n_features_in_ = 1024

    assert inp.for_head(Narrow()) is inp.for_head(Narrow())


def test_head_input_rejects_input_narrower_than_head():
    class Wide:
        n_features_in_ = 4096

    with pytest.raises(ValueError, match="narrower"):
        _HeadInput(np.ones((1, 1024), dtype=np.float32)).for_head(Wide())


def test_head_without_n_features_in_uses_full_width():
    """Older pickles (or plain mocks) carry no n_features_in_ — do not slice."""
    class Legacy:
        pass

    X = np.ones((2, 4096), dtype=np.float32)
    assert _HeadInput(X).for_head(Legacy()).shape == (2, 4096)


def test_mixed_width_heads_classify_together():
    """Four 1024-dim heads plus the 4096-dim signal_type head — production shape."""
    from sklearn.linear_model import SGDClassifier
    from sklearn.multiclass import OneVsRestClassifier

    rng = np.random.default_rng(11)
    X = _unit(rng.normal(size=(60, 4096)).astype(np.float32))
    y = np.array(["TECH", "FOOD"] * 30)
    small = _unit(X[:, :1024])

    def head(Xtr, ytr):
        return SGDClassifier(loss="log_loss", max_iter=20, random_state=0).fit(Xtr, ytr)

    clf = DistillClassifier(
        vertical=head(small, y),
        mega=head(small, y),
        pestel=OneVsRestClassifier(
            SGDClassifier(loss="log_loss", max_iter=20, random_state=0)
        ).fit(small, np.tile([[1, 0, 0, 0, 0, 0]], (60, 1))),
        relevance=None,
        meta={"dim": 1024},
        signal_type=head(X, y),          # still the FULL width
    )
    out = clf.classify_batch(X[:4])
    assert len(out) == 4
    assert all(o["primary_vertical"] in {"TECH", "FOOD"} for o in out)
    assert all(o["signal_type"] in {"TECH", "FOOD"} for o in out)


# --- trainer: loader, sampling, preflight ----------------------------------

def _seed(n=24):
    # Explicitly empty the tables instead of removing the file: when the whole
    # suite runs, another module may have imported pipeline.db with ITS
    # DATABASE_PATH first, so removing this file would clear nothing and the
    # rows would accumulate across tests.
    init_db()
    with get_connection() as c:
        for tbl in ("trends", "raw_entries", "sources"):
            c.execute(f"DELETE FROM {tbl}")
    rng = np.random.default_rng(5)
    vecs = rng.normal(size=(n, tdh.DIM_FULL)).astype(np.float32)
    with get_connection() as c:
        c.execute("INSERT INTO sources (id,name,feed_url,source_type,vertical) "
                  "VALUES (1,'T','http://t','trade_media','FOOD')")
        for i in range(n):
            c.execute("INSERT INTO raw_entries (id, source_id, url, title) VALUES (?,?,?,?)",
                      (i + 1, 1, f"http://x/{i}", f"t{i}"))
            c.execute(
                "INSERT INTO trends (raw_entry_id, title_en, slug, source_url, "
                "primary_vertical, mega_trend, pestel, embedding) VALUES (?,?,?,?,?,?,?,?)",
                (i + 1, f"T{i}", f"s{i}", "http://x", "TECH" if i % 2 else "FOOD",
                 "artificial_intelligence_and_automation", '["T"]',
                 struct.pack(f"{tdh.DIM_FULL}f", *vecs[i])))
    return vecs


def test_stream_trends_prefix_matches_full_vector():
    vecs = _seed()
    X_full, rows_full = tdh._stream_trends(0, tdh.DIM_FULL)
    X_pre, rows_pre = tdh._stream_trends(0, tdh.DIM_PREFIX)

    assert X_full.shape == (len(vecs), tdh.DIM_FULL)
    assert X_pre.shape == (len(vecs), tdh.DIM_PREFIX)
    # the prefix head sees exactly the normalised first 1024 components
    np.testing.assert_allclose(X_pre, _unit(vecs[:, :tdh.DIM_PREFIX]), atol=1e-5)
    # ... and that is what _HeadInput hands a 1024-dim head at inference time
    class Narrow:
        n_features_in_ = tdh.DIM_PREFIX

    np.testing.assert_allclose(_HeadInput(vecs).for_head(Narrow()), X_pre, atol=1e-5)
    # labels stay aligned with the rows
    assert [r["id"] for r in rows_pre] == [r["id"] for r in rows_full]
    assert all(r["pestel"] == ["T"] for r in rows_pre)


def test_stream_trends_rows_are_unit_length():
    _seed()
    X, _ = tdh._stream_trends(0, tdh.DIM_PREFIX)
    np.testing.assert_allclose(np.linalg.norm(X, axis=1), 1.0, atol=1e-5)


def test_sample_is_deterministic_across_runs():
    """--sample must hit the SAME rows twice, otherwise an A/B over the
    dimension compares two different corpora."""
    _seed(n=24)
    a, rows_a = tdh._stream_trends(6, tdh.DIM_PREFIX)
    b, rows_b = tdh._stream_trends(6, tdh.DIM_PREFIX)
    assert [r["id"] for r in rows_a] == [r["id"] for r in rows_b]
    assert 0 < len(rows_a) < 24
    np.testing.assert_allclose(a, b)


def test_preflight_refuses_instead_of_being_oom_killed(monkeypatch):
    """The real numbers of 2026-09-20: 1.83M rows at 4096 dim on this machine."""
    monkeypatch.setattr(tdh, "_mem_available_gb", lambda: 50.0)
    with pytest.raises(MemoryError, match="estimated peak"):
        tdh._preflight(1_827_351, tdh.DIM_FULL, "all")      # ~54 GB
    tdh._preflight(1_827_351, tdh.DIM_PREFIX, "all")        # ~14 GB — passes


def test_preflight_is_silent_without_meminfo(monkeypatch):
    """No MemAvailable (non-Linux, container) must not block the run."""
    monkeypatch.setattr(tdh, "_mem_available_gb", lambda: 0.0)
    tdh._preflight(50_000_000, tdh.DIM_FULL, "all")


def test_emb_column_is_backend_aware():
    assert tdh._emb_column(tdh.DIM_FULL) == "embedding"
    # SQLite has no prefix column — the blob is sliced while streaming
    assert tdh._emb_column(tdh.DIM_PREFIX) == "embedding"


# --- Abstain-Schwelle gehoert zum Head, nicht in eine Konstante -------------

def test_abstain_threshold_resolution_order():
    from pipeline.distill import MEGA_ABSTAIN_THRESHOLD, _mega_abstain_threshold as thr

    assert thr({"mega_abstain_threshold": -1.418}) == -1.418
    assert thr({"report": {"mega_trend": {"abstain_threshold": -1.35}}}) == -1.35
    # Heads von vor dem 26.09. tragen keine Schwelle -> die 4096er-Konstante gilt
    assert thr({}) == MEGA_ABSTAIN_THRESHOLD
    assert thr({"mega_abstain_threshold": None}) == MEGA_ABSTAIN_THRESHOLD


def _clf_with_threshold(meta):
    from sklearn.linear_model import SGDClassifier
    from sklearn.multiclass import OneVsRestClassifier

    rng = np.random.default_rng(3)
    X = _unit(rng.normal(size=(40, 1024)).astype(np.float32))
    y = np.array(["TECH", "FOOD"] * 20)
    head = lambda: SGDClassifier(loss="log_loss", max_iter=20, random_state=0).fit(X, y)
    return DistillClassifier(
        vertical=head(), mega=head(),
        pestel=OneVsRestClassifier(
            SGDClassifier(loss="log_loss", max_iter=20, random_state=0)
        ).fit(X, np.tile([[1, 0, 0, 0, 0, 0]], (40, 1))),
        relevance=None, meta=meta), X


def test_classify_uses_the_threshold_stored_with_the_model():
    """Eine unerreichbar hohe Schwelle muss JEDE Mega-Zuordnung unterdruecken,
    eine sehr tiefe keine — sonst haengt das Abstain weiter an der Konstante."""
    hoch, X = _clf_with_threshold({"mega_abstain_threshold": 999.0})
    assert all(o["mega_trend"] is None for o in hoch.classify_batch(X[:6]))
    tief, X = _clf_with_threshold({"mega_abstain_threshold": -999.0})
    assert all(o["mega_trend"] is not None for o in tief.classify_batch(X[:6]))
    # mega_top3 bleibt unabhaengig vom Abstain befuellt
    assert all(len(o["mega_top3"]) >= 1 for o in hoch.classify_batch(X[:6]))


# --- Cron-Defaults (der Sonntagslauf ruft ohne Argumente auf) --------------

def test_cron_defaults_are_balanced_and_1024():
    """`discovery_loop.retrain()` startet den Trainer OHNE Flags — die Defaults
    sind damit das produktive Verhalten und gehoeren gepinnt (Owner 26.09.)."""
    d = vars(tdh._parser().parse_args([]))
    assert d["dim"] == tdh.DIM_PREFIX
    assert d["mega_class_weight"] == "balanced"
    assert d["mega_abstain_rate"] == 0.072
    assert d["sample"] == 0
    assert d["relevance_only"] is False and d["mega_only"] is False
