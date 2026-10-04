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


def test_dedupe_keeps_the_earliest_member_of_a_family_and_carries_the_cited_flag():
    from pipeline.db import get_connection
    hv.migrate_history_tables()
    with get_connection() as c:
        c.execute("CREATE TABLE IF NOT EXISTS patent_family (pub_number TEXT PRIMARY KEY, family_id INTEGER)")
        c.execute("DELETE FROM history_items")
        c.execute("DELETE FROM patent_family")
        for pub, fam in (("A1", 7), ("A2", 7), ("B1", 8)):
            c.execute("INSERT INTO patent_family (pub_number, family_id) VALUES (?, ?)", (pub, fam))
        c.executemany("INSERT INTO history_items (id, tier, ref, raw_entry_id, month, layer, cited) "
                      "VALUES (?, 'patent', ?, ?, ?, ?, ?)",
                      [(1, "A2", 12, 2024 * 12, "random", False),      # family 7, later member
                       (2, "A1", 11, 2021 * 12, "cited", False),       # family 7, earliest
                       (3, "B1", 13, 2020 * 12, "random", False),
                       (4, "C1", 14, 2019 * 12, "random", False)])    # no family: alone
        assert hv.dedupe_families(c) == 1
        got = {r["id"]: (r["layer"], bool(r["cited"])) for r in c.execute(
            "SELECT id, layer, cited FROM history_items").fetchall()}
        assert got[2] == ("cited", False) and got[1] == ("random:dupfamily", False)
        assert got[3] == ("random", False) and got[4] == ("random", False)
        assert hv.dedupe_families(c) == 0                             # idempotent
        c.execute("DELETE FROM history_items")
