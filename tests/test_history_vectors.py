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


def test_selection_is_checked_per_tier_and_window():
    from pipeline.db import get_connection
    hv.migrate_history_tables()
    with get_connection() as c:
        c.execute("DELETE FROM history_items")
        c.execute("INSERT INTO history_items (tier, ref, month, layer) VALUES ('patent', 'P1', ?, 'random')",
                  (1995 * 12 + 2,))
        assert hv.tier_has_items(c, "patent", "1990-01-01", "2023-01-01")
        assert not hv.tier_has_items(c, "science", "2010-01-01", "2023-01-01")   # died before science
        assert not hv.tier_has_items(c, "patent", "2023-01-01", "2026-07-01")    # another window
        c.execute("DELETE FROM history_items")
