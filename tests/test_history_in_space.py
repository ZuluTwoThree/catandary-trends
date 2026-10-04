"""The history sample inside the signal cloud and the archive scan (2026-10-03).

pipeline/history_vectors.py holds a weighted sample of the past (patents 1990-2022,
research 2010-2022). Pinned here:

  * the cloud's per-month draw takes from trends AND the embedded random layer,
    never from unembedded items or documents that also sit in trends,
  * history points carry ids >= HISTORY_ID_BASE and load from history_vectors,
  * a run places random and cited items and keeps the id order the server needs,
  * the archive scan counts history rows on their tier when asked, and only then.
"""
import os
import struct
import sys
import tempfile
from pathlib import Path

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_history_space_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import history_vectors as hv
from pipeline import signal_space as ss
from pipeline.db import get_connection, init_db
from pipeline.emerging import scan_history

BASE = hv.HISTORY_ID_BASE


def _seed(trend_months: dict[str, int], hist: list[tuple], dim: int = 1024, seed: int = 5):
    """trends per 'YYYY-MM' (source 'Journal', research) and history items
    (tier, 'YYYY-MM', layer, embedded, dup). Returns {id: vector} for both kinds."""
    init_db()
    hv.migrate_history_tables()
    with get_connection() as c:
        for tbl in ("history_vectors", "history_items", "trends", "raw_entries", "sources"):
            c.execute(f"DELETE FROM {tbl}")
        c.execute("INSERT INTO sources (id,name,feed_url,source_type,vertical) "
                  "VALUES (2,'Journal','http://j','research','HEALTH')")
    rng = np.random.default_rng(seed)
    vecs = {}
    with get_connection() as c:
        i = 0
        for month, n in trend_months.items():
            for k in range(n):
                i += 1
                v = rng.normal(size=dim).astype(np.float32)
                c.execute("INSERT INTO raw_entries (id, source_id, url, title, published_date) "
                          "VALUES (?,?,?,?,?)", (i, 2, f"http://x/{i}", f"t{i}", f"{month}-{k % 27 + 1:02d}"))
                c.execute("INSERT INTO trends (id, raw_entry_id, title_en, slug, source_url, "
                          "primary_vertical, status, source_name, embedding) VALUES (?,?,?,?,?,?,?,?,?)",
                          (i, i, f"T{i}", f"s{i}", "http://x", "HEALTH", "signal", "Journal",
                           struct.pack(f"{dim}f", *v)))
                vecs[i] = v
        for j, (tier, month, layer, embedded, dup) in enumerate(hist, start=1):
            m = int(month[:4]) * 12 + int(month[5:7]) - 1
            c.execute("INSERT INTO history_items (id, tier, ref, month, layer, cited, weight, "
                      "embedded_at, dup_of_trend) VALUES (?,?,?,?,?,?,?,?,?)",
                      (j, tier, f"R{j}", m, layer, layer == "cited", 3.0 if layer == "random" else None,
                       "2026-10-03" if embedded else None, 1 if dup else None))
            if embedded:
                v = rng.normal(size=dim).astype(np.float32)
                c.execute("INSERT INTO history_vectors (item_id, vec, device) VALUES (?,?,?)",
                          (j, hv.pack(v), "test"))
                vecs[BASE + j] = v
    return vecs


def test_the_draw_takes_trends_and_embedded_random_history_only():
    hist = [("science", "2020-01", "random", True, False)] * 10 + [
        ("science", "2020-01", "random", False, False),   # not embedded yet
        ("science", "2020-01", "random", True, True),     # also in trends
        ("patent", "2020-01", "cited", True, False)]      # cited layer: placed, never drawn
    _seed({"2020-01": 10}, hist)
    got = ss.sample_ids(["2020-01"], per_month=100)
    ids = [i for i, _ in got]
    assert len(ids) == 20
    assert sum(1 for i in ids if i >= BASE) == 10
    assert set(i - BASE for i in ids if i >= BASE) == set(range(1, 11))
    assert ss.sample_ids(["2020-01"], per_month=100, history=False) == \
        [(i, m) for i, m in got if i < BASE]


def test_the_draw_is_deterministic_and_mixes_both_pools():
    _seed({"2020-01": 40}, [("science", "2020-01", "random", True, False)] * 40)
    a = ss.sample_ids(["2020-01"], per_month=20)
    assert a == ss.sample_ids(["2020-01"], per_month=20)
    n_hist = sum(1 for i, _ in a if i >= BASE)
    assert 0 < n_hist < 20


def test_history_points_load_from_history_vectors():
    vecs = _seed({"2020-01": 2}, [("patent", "2020-01", "random", True, False)])
    X, meta = ss.load_vectors([1, BASE + 1, 2])
    ref = vecs[BASE + 1][:1024] / np.linalg.norm(vecs[BASE + 1][:1024])
    assert float(ss.l2(X[1:2])[0] @ ref) > 0.999
    assert meta[1] == {"tier": "patent", "vertical": None}
    assert meta[0]["tier"] == "science"


def test_iter_history_rows_look_like_signals_on_the_right_tier():
    _seed({}, [("patent", "1995-03", "random", True, False),
               ("science", "2012-07", "cited", True, False),
               ("science", "2012-07", "random", True, True)])
    rows = [r for _, b in hv.iter_history(layers=("random", "cited")) for r in b]
    assert [r["id"] for r in rows] == [BASE + 1, BASE + 2]
    from pipeline.tiers import tier_of
    assert [tier_of(r["source_name"], r["source_type"], None) for r in rows] == ["patent", "science"]
    assert rows[0]["published_date"] == "1995-03-01"
    assert [r["id"] for _, b in hv.iter_history(until="1996-01") for r in b] == [BASE + 1]


def test_a_run_places_random_and_cited_history_after_the_trends():
    _seed({"2020-01": 30, "2020-02": 30},
          [("science", "2020-01", "random", True, False)] * 20
          + [("patent", "2020-02", "cited", True, False)] * 5
          + [("patent", "2019-12", "random", True, False)])          # outside the window
    ss.migrate_signal_space_tables()
    with get_connection() as c:
        c.execute("DELETE FROM signal_space_runs")
    rid = ss.run(per_month=20, n_months=2, end_month="2020-02")
    with get_connection() as c:
        r = c.execute("SELECT all_points, n_all, n_history, n_history_all FROM signal_space_runs "
                      "WHERE id = ?", (rid,)).fetchone()
    every = ss.unpack(bytes(r["all_points"]))
    ids = every["trend_id"].tolist()
    assert ids == sorted(ids)
    assert r["n_all"] == 60 + 25
    assert r["n_history_all"] == 25
    assert sum(1 for i in ids if i >= BASE) == 25
    assert 0 < r["n_history"] <= 20


def test_the_archive_scan_counts_history_only_when_asked():
    vecs = _seed({"2024-01": 5}, [("science", "2015-06", "random", True, False)] * 3)
    C = np.vstack([vecs[BASE + k][:1024] / np.linalg.norm(vecs[BASE + k][:1024]) for k in (1, 2, 3)])
    thr = np.full(3, 0.99, np.float32)
    off = scan_history(C, thr, dim1024=False)
    assert "2015-06" not in off["months"] and off["history_scanned"] == 0
    on = scan_history(C, thr, dim1024=False, history=True)
    j = on["months"].index("2015-06")
    assert on["history_scanned"] == 3
    assert on["scanned"] == off["scanned"]      # trends rows only; the sample is not counted twice
    assert on["totals"][j] == 3
    assert on["tier_totals"]["science"][j] == 3
    assert on["hits"][:, j].tolist() == [1, 1, 1]
    vert = scan_history(C, thr, dim1024=False, history=True, vertical="FOOD")
    assert vert["history_scanned"] == 0


def test_openalex_research_dated_first_of_january_stays_out_of_the_monthly_scan():
    vecs = _seed({"2015-01": 1, "2015-03": 1}, [("science", "2015-01", "random", True, False)])
    # _seed dates trends rows to day k%27+1 -> the first row of 2015-01 is 2015-01-01
    with get_connection() as c:
        c.execute("UPDATE trends SET source_name = 'OpenAlex Science (TECH)'")
    C = np.vstack([v[:1024] / np.linalg.norm(v[:1024]) for v in vecs.values()])
    thr = np.full(len(C), 0.99, np.float32)
    h = scan_history(C, thr, dim1024=False, history=True)
    assert h["science_year_only"] == 1                   # the OpenAlex row of 1 January
    j = h["months"].index("2015-01")
    assert h["tier_totals"]["science"][j] == 1           # the history row of January still counts
    assert h["tier_totals"]["science"][h["months"].index("2015-03")] == 1


def test_a_journal_or_preprint_paper_of_first_of_january_still_counts():
    vecs = _seed({"2015-01": 1}, [])                     # source 'Journal' (research), 2015-01-01
    C = np.vstack([v[:1024] / np.linalg.norm(v[:1024]) for v in vecs.values()])
    h = scan_history(C, np.full(len(C), 0.99, np.float32), dim1024=False)
    assert h["science_year_only"] == 0
    assert h["tier_totals"]["science"][h["months"].index("2015-01")] == 1


def test_readers_add_columns_missing_on_an_older_history_table():
    init_db()
    with get_connection() as c:
        c.execute("DROP TABLE IF EXISTS history_vectors")
        c.execute("DROP TABLE IF EXISTS history_items")
        # the table as #118 created it: no dup_of_trend yet
        c.execute("""CREATE TABLE history_items (id INTEGER PRIMARY KEY AUTOINCREMENT, tier TEXT NOT NULL,
            ref TEXT NOT NULL, raw_entry_id INTEGER, month INTEGER NOT NULL, layer TEXT NOT NULL,
            cited INTEGER DEFAULT 0, weight REAL, claimed_by TEXT, claimed_at TIMESTAMP,
            embedded_at TIMESTAMP, UNIQUE(tier, ref))""")
        c.execute("CREATE TABLE history_vectors (item_id INTEGER PRIMARY KEY, vec BLOB NOT NULL, device TEXT)")
        c.execute("INSERT INTO history_items (id, tier, ref, month, layer, embedded_at) "
                  "VALUES (1, 'science', 'W1', ?, 'random', '2026-10-03')", (2015 * 12,))
        c.execute("INSERT INTO history_vectors (item_id, vec) VALUES (1, ?)", (hv.pack(np.ones(1024)),))
    hv._columns_checked = False
    assert hv.available()
    assert [r["id"] for _, b in hv.iter_history() for r in b] == [BASE + 1]
    with get_connection() as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(history_items)").fetchall()}
    assert "dup_of_trend" in cols
