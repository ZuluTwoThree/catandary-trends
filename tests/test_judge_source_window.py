"""The judge must read at least as much source as the writer did (2026-09-24).

Stage 2 extracts from 12.000 characters and Stage 6 writes with those fields in
hand, so a figure from the back of a long article legitimately reaches the
draft. The judge's prompt was capped at 4.000 characters, so it called exactly
those specifics invented. Sample of 25 held drafts: 5 of 10 source_mismatch
verdicts were wrong, the disputed item sitting at position 4.005, 4.012, 4.033,
5.111 and 7.021.
"""

import json
import os
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_judge_window_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pipeline.draft_judge as dj


def test_source_window_reaches_beyond_the_old_4000_cap():
    assert dj.JUDGE_SOURCE_MAX_CHARS >= 12000, (
        "the judge must see at least what the extraction read, else the back of a "
        "long article looks invented to it")


def test_extraction_block_carries_the_verbatim_evidence():
    e = {"brand_name": "Augustiner",
         "key_figures": ["51 Prozent: Anteil der Stiftung an der Brauerei"],
         "key_claims": ["Die Augustiner Festhalle umfasst etwa 6000 Innenplätze"]}
    block = dj._extraction_block(json.dumps(e, ensure_ascii=False))
    assert "FULL SOURCE" in block
    assert "51 Prozent" in block and "6000 Innenplätze" in block


def test_extraction_block_is_robust_and_switchable(monkeypatch):
    assert dj._extraction_block(None) == ""
    assert dj._extraction_block("") == ""
    assert dj._extraction_block("{}") == ""
    assert dj._extraction_block("not json at all") == ""
    monkeypatch.setattr(dj, "JUDGE_EXTRACTION_MAX_CHARS", 0)
    assert dj._extraction_block(json.dumps({"brand_name": "X"})) == ""


def test_prompt_contains_late_source_material(monkeypatch):
    """A figure at position 5.000 must reach the judge — it did not before."""
    seen = {}

    def fake_chat(**kw):
        seen["prompt"] = kw["prompt"]
        return None

    monkeypatch.setattr("pipeline.llamacpp_client.chat_structured", fake_chat)
    body = "x" * 5000 + " PAYLOAD-51-PERCENT " + "y" * 3000
    dj.judge_one({"re_title": "T", "raw_content": body, "excerpt": None,
                  "source_name": "S", "title_en": "Title", "body_en": "Body.",
                  "extraction_json": json.dumps({"key_figures": ["PAYLOAD-FROM-EXTRACTION"]})})
    assert "PAYLOAD-51-PERCENT" in seen["prompt"]
    assert "PAYLOAD-FROM-EXTRACTION" in seen["prompt"]


def test_judge_one_survives_a_row_without_extraction(monkeypatch):
    monkeypatch.setattr("pipeline.llamacpp_client.chat_structured", lambda **kw: None)
    dj.judge_one({"re_title": None, "raw_content": None, "excerpt": "teaser",
                  "source_name": None, "title_en": "T", "body_en": "B."})


def test_rejudge_flag_controls_the_judged_at_condition(monkeypatch):
    sqls = []

    class FakeConn:
        def execute(self, sql, params=None):
            sqls.append((sql, params))
            class R:
                def fetchall(self_inner): return []
            return R()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(dj, "get_connection", lambda: FakeConn())

    dj._fetch_candidates(30, 600)
    assert "t.judged_at IS NULL" in sqls[-1][0]
    assert "length(COALESCE" not in sqls[-1][0]

    dj._fetch_candidates(720, 2000, rejudge=True, min_source_chars=4000)
    sql, params = sqls[-1]
    assert "t.judged_at IS NULL" not in sql
    assert "length(COALESCE(re.raw_content, re.excerpt, '')) > ?" in sql
    assert params == (720, 4000, 2000)


def test_rejudge_writes_its_own_stats_file():
    """A backfill must not overwrite the file the morning mail reads."""
    assert dj.REJUDGE_STATS_PATH != dj.STATS_PATH


def test_backlog_pickup_takes_fresh_first_then_leftovers(monkeypatch):
    """Owner 09.10.: Liegengebliebene der letzten Tage nach den frischen Entwürfen mitnehmen."""
    sqls = []

    class FakeConn:
        def execute(self, sql, params=None):
            sqls.append((sql, params))

            class R:
                def fetchall(self_inner): return []
            return R()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(dj, "get_connection", lambda: FakeConn())
    dj._fetch_candidates(30, 900, backlog_days=7)
    sql, params = sqls[-1]
    assert "AS fresh" in sql and "ORDER BY fresh DESC, t.id" in sql
    assert params == (30, 168, 900)          # Frisch-Grenze, Fenster 7 Tage, Limit
    dj._fetch_candidates(720, 2000, rejudge=True, backlog_days=7)   # Nachbeurteilung: kein Rückstandsmodus
    assert "AS fresh" not in sqls[-1][0]
    assert dj.JUDGE_LIMIT >= 900 and dj.JUDGE_BACKLOG_DAYS == 7
