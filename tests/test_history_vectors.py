"""History sample of the signal space (pipeline/history_vectors.py, 2026-10-03)."""
import numpy as np

from pipeline import history_vectors as hv


def test_pack_is_unit_1024_prefix_float16():
    rng = np.random.default_rng(1)
    v = rng.normal(size=4096).astype(np.float32)
    blob = hv.pack(v)
    assert len(blob) == 2048
    u = hv.unpack(blob)
    assert u.shape == (1024,)
    assert abs(float(np.linalg.norm(u)) - 1.0) < 1e-3
    ref = v[:1024] / np.linalg.norm(v[:1024])
    assert float(u @ ref) > 0.9999


def test_text_recipe_matches_signal_path():
    # scripts/signal_batch.py: f"{title}\n{(excerpt or '')[:500]}"
    body = "x" * 900
    assert hv.text_of("Title", body) == "Title\n" + body[:500]
    assert hv.text_of("Title", None) == "Title\n"


def test_migration_is_idempotent_on_sqlite():
    hv.migrate_history_tables()
    hv.migrate_history_tables()
