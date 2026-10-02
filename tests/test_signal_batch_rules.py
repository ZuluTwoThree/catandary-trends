"""The signal path judges patents and funding by rule, press/research by the head (02.10.2026).

A patent with a LOW head score is kept (the head was trained on press verdicts and dropped
92-96 % signals among patents — docs/filter_audit_2026-10-02.md); a plant variety goes as
rule:plant_variety; a research paper with a low score is still dropped by the head;
--head-for-all restores the old behaviour."""
import os
import tempfile

import pytest

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_signal_rules_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pipeline.db as pdb                                   # noqa: E402
from pipeline.db import get_connection, init_db             # noqa: E402
from scripts import signal_batch as sb                      # noqa: E402


class _LowHead:
    meta = {"heads": ["relevance", "vertical"]}
    has_relevance_head = True
    def classify_batch(self, X):
        return [{"relevance": 0.05, "vertical_confidence": 0.9, "primary_vertical": "TECH",
                 "pestel": ["T"], "mega_trend": None} for _ in range(len(X))]


@pytest.fixture
def db(monkeypatch):
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    with get_connection() as c:
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) VALUES "
                  "(1, 'Google Patents (TECH)', 'http://p', 'api', 'TECH'), "
                  "(2, 'arXiv Preprints', 'http://a', 'research', 'TECH')")
        rows = [(1, 1, "US1", "METHOD FOR COMPRESSING VIDEO STREAMS"),
                (2, 1, "US2", "SOYBEAN CULTIVAR 01220205"),
                (3, 2, None, "A paper the head does not like")]
        for i, src, pub, title in rows:
            c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt, pub_number) "
                      "VALUES (?, ?, ?, ?, ?, ?)", (i, src, f"http://x/{i}", title, "text " * 40, pub))
        c.commit()
    from pipeline import distill
    monkeypatch.setattr(distill.DistillClassifier, "load", staticmethod(lambda: _LowHead()))
    monkeypatch.setattr(sb, "EMBED_BACKEND", "llamacpp")
    monkeypatch.setattr(sb, "get_recent_titles", lambda days: [])
    monkeypatch.setattr(sb, "get_recent_embeddings", lambda days: [])
    monkeypatch.setattr(sb, "embed_batch",
                        lambda texts: [[float(i == k) for k in range(8)] for i, _ in enumerate(texts)])
    yield
    pdb.DATABASE_PATH = old


def _rows():
    with get_connection() as c:
        return {r["id"]: dict(r) for r in c.execute(
            "SELECT id, processed, filtered_out, filter_reason FROM raw_entries").fetchall()}


def test_patents_by_rule_research_by_head(db):
    assert sb.run_distill(limit=0, execute=True, embed_chunk=8, include=[], exclude=[]) == 0
    r = _rows()
    assert r[1]["processed"] and not r[1]["filtered_out"]                 # kept despite 0.05
    assert r[2]["filtered_out"] and r[2]["filter_reason"] == "rule:plant_variety"
    assert r[3]["filtered_out"] and r[3]["filter_reason"].startswith("not_relevant_distill:")


def test_head_for_all_restores_the_old_gate(db):
    sb.run_distill(limit=0, execute=True, embed_chunk=8, include=[], exclude=[], head_for_all=True)
    r = _rows()
    assert all(r[i]["filter_reason"].startswith("not_relevant_distill:") for i in (1, 2, 3))
