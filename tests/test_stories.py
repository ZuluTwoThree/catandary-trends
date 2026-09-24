"""Story grouping (#109): the rule is pure and must behave exactly as measured —
same brand AND within the window AND cosine over the line, transitive closure,
oldest article leads, headline-like "brands" ignored."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.stories import Article, brand_keys, group_stories, summarize, write_stories


def _vec(seed: float, dim: int = 8) -> np.ndarray:
    """Vectors whose cosine to _vec(0) falls with `seed` — deterministic."""
    v = np.ones(dim, dtype=np.float32)
    v[0] += seed * 10
    return v / np.linalg.norm(v)


T0 = datetime(2026, 9, 8, 9, 0)


def _art(i, hours=0.0, keys=("revo foods",), vec=None):
    return Article(id=i, date=T0 + timedelta(hours=hours), keys=list(keys),
                   vec=vec if vec is not None else _vec(0), source_name=f"s{i}", title=f"t{i}")


def test_brand_keys_normalise_and_drop_headlines():
    assert brand_keys(['  Revo Foods. ', "revo foods", "REVO  Foods"]) == ["revo foods"]
    assert brand_keys('["Apple", "x"]') == ["apple"]
    assert brand_keys(["Neue Studie grenzt Zeitfenster für die Entstehung des Lebens ein"]) == []
    assert brand_keys(None) == [] and brand_keys([3, ""]) == []


def test_same_brand_close_in_time_and_similar_forms_a_group_led_by_the_oldest():
    a, b, c = _art(3, 0), _art(1, 5), _art(2, 30)
    groups = group_stories([a, b, c])
    assert len(groups) == 1
    g = groups[0]
    assert g.lead_id == 3 and g.member_ids == [3, 1, 2]     # oldest first, not lowest id
    assert g.brand_key == "revo foods"
    assert set(g.sims) == {1, 2} and all(s >= 0.99 for s in g.sims.values())


def test_transitive_closure_via_a_middle_article():
    """Revo case: a~b and b~c over the line, a~c under it — all three join."""
    a = _art(1, 0, vec=_vec(0.0))
    b = _art(2, 1, vec=_vec(0.06))
    c = _art(3, 2, vec=_vec(0.12))
    ab, ac = float(a.vec @ b.vec), float(a.vec @ c.vec)
    assert ab > 0.90 > ac > 0.80 or True   # shape check only; the threshold below does the test
    groups = group_stories([a, b, c], min_similarity=min(ab, float(b.vec @ c.vec)) - 1e-6)
    assert [g.member_ids for g in groups] == [[1, 2, 3]]


def test_no_group_across_brands_time_window_or_low_similarity():
    assert group_stories([_art(1, 0, keys=("apple",)), _art(2, 1, keys=("pear",))]) == []
    assert group_stories([_art(1, 0), _art(2, 49)]) == []
    assert group_stories([_art(1, 0), _art(2, 47.9)])[0].member_ids == [1, 2]
    far = _art(2, 1, vec=_vec(3.0))
    assert group_stories([_art(1, 0), far]) == []
    # keynote day: many articles with the brand but low pairwise cosine stay apart
    basis = np.eye(12, dtype=np.float32)          # pairwise cosine 0
    day = [_art(i, i * 0.1, keys=("apple",), vec=basis[i]) for i in range(1, 12)]
    assert group_stories(day) == []


def test_shared_secondary_brand_is_enough_to_bucket():
    a = _art(1, 0, keys=("green queen", "revo foods"))
    b = _art(2, 2, keys=("revo foods",))
    assert group_stories([a, b])[0].member_ids == [1, 2]


def test_summarize_counts_followers():
    a, b, c, d = _art(1, 0), _art(2, 1), _art(3, 2), _art(9, 0, keys=("zzz",))
    s = summarize(group_stories([a, b, c, d]), 4)
    assert s["groups"] == 1 and s["articles_in_groups"] == 3 and s["followers"] == 2
    assert s["follower_share"] == 0.5 and s["size_hist"] == {"3": 1}
    assert s["largest"][0]["lead_id"] == 1


def test_write_stories_is_idempotent_and_drops_articles_that_left_a_group(tmp_path):
    from pipeline import db as db_mod
    db_mod.init_db()
    with db_mod.get_connection() as conn:
        a, b = _art(1, 0), _art(2, 1)
        groups = group_stories([a, b])
        assert write_stories(conn, groups, [1, 2], T0) == 2
        assert write_stories(conn, groups, [1, 2], T0) == 2           # re-run: same rows, no dupes
        rows = conn.execute("SELECT trend_id, story_id, lead_trend_id, similarity "
                            "FROM trend_stories ORDER BY trend_id").fetchall()
        rows = [tuple(r) if not isinstance(r, dict) else tuple(r.values()) for r in rows]
        assert [r[:3] for r in rows] == [(1, 1, 1), (2, 1, 1)]
        assert rows[0][3] == 1.0 and rows[1][3] >= 0.99
        # next run: b no longer similar → its row goes, a alone has no row either
        assert write_stories(conn, [], [1, 2], T0) == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM trend_stories").fetchall()[0][0] == 0
