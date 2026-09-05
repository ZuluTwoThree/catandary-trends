"""Embedding-Fehlerpfad in signal_batch (#98 d, 2026-09-05).

Server-/Verbindungsfehler (Connection refused, 503, Timeout) dürfen Einträge
NICHT als filtered_out='embedding_error' markieren — am 05.09. wurden so 2.416
Signale für immer aussortiert, weil der Embedding-Server gekillt worden war.
Stattdessen: gleicher Chunk erneut, nach N Fehlern in Folge Abbruch mit
Exit 3, alles Unverarbeitete bleibt unprocessed. 'embedding_error' bleibt nur
für inhaltliche Fehler (der Server lehnt genau diesen Text ab).
"""
import os
import tempfile

import httpx
import pytest

TEST_DB = os.path.join(tempfile.gettempdir(), "catandary_embed_err_test.db")
os.environ["DATABASE_PATH"] = TEST_DB

import pipeline.db as pdb                                   # noqa: E402
from pipeline.db import get_connection, init_db             # noqa: E402
from pipeline.llamacpp_client import EmbeddingBackendError  # noqa: E402
from scripts import signal_batch as sb                      # noqa: E402
from scripts import reset_embedding_errors as rst           # noqa: E402


def _resp(status: int):
    req = httpx.Request("POST", "http://x/v1/embeddings")
    return httpx.Response(status, request=req, json={"error": "x"})


class TestEmbedBatch:
    def _client(self, monkeypatch, exc):
        class Client:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, url, json=None): raise exc
        monkeypatch.setattr(sb.httpx, "Client", Client)
        monkeypatch.setattr(sb, "EMBED_BACKEND", "llamacpp")

    def test_connection_refused_is_a_backend_error(self, monkeypatch):
        self._client(monkeypatch, httpx.ConnectError("Connection refused"))
        with pytest.raises(EmbeddingBackendError):
            sb.embed_batch(["a", "b"])

    def test_503_and_timeout_are_backend_errors(self, monkeypatch):
        self._client(monkeypatch, httpx.HTTPStatusError("503", request=_resp(503).request,
                                                        response=_resp(503)))
        with pytest.raises(EmbeddingBackendError):
            sb.embed_batch(["a"])
        self._client(monkeypatch, httpx.ReadTimeout("timeout"))
        with pytest.raises(EmbeddingBackendError):
            sb.embed_batch(["a"])

    def test_content_error_falls_back_per_item_to_none(self, monkeypatch):
        """4xx = dieser Text; der Server lebt → per-item, None bleibt ein Urteil."""
        self._client(monkeypatch, httpx.HTTPStatusError("400", request=_resp(400).request,
                                                        response=_resp(400)))
        monkeypatch.setattr(sb, "_embed_one", lambda t: None if t == "bad" else [1.0])
        assert sb.embed_batch(["bad", "ok"]) == [None, [1.0]]

    def test_per_item_strict_raises_on_backend_failure(self, monkeypatch):
        import pipeline.llamacpp_client as lc
        class Client:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, url, json=None): raise httpx.ConnectError("refused")
        monkeypatch.setattr(lc.httpx, "Client", Client)
        with pytest.raises(EmbeddingBackendError):
            lc.generate_embedding("t", strict=True)
        assert lc.generate_embedding("t") is None       # Altverhalten ohne strict


class TestResilientChunk:
    @pytest.fixture(autouse=True)
    def _fast(self, monkeypatch):
        monkeypatch.setattr(sb, "EMBED_MAX_CONSECUTIVE_ERRORS", 3)
        monkeypatch.setattr(sb, "EMBED_ERROR_SLEEP", 0)

    def test_same_chunk_is_retried_until_the_server_is_back(self, monkeypatch):
        attempts = []
        def eb(texts):
            attempts.append(list(texts))
            if len(attempts) < 3:
                raise EmbeddingBackendError("refused")
            return [[1.0] for _ in texts]
        monkeypatch.setattr(sb, "embed_batch", eb)
        state: dict = {}
        assert sb.embed_chunk_resilient(["a", "b"], state) == [[1.0], [1.0]]
        assert attempts == [["a", "b"]] * 3
        assert state["consecutive"] == 0 and state["total"] == 2

    def test_aborts_after_n_consecutive_failures(self, monkeypatch):
        monkeypatch.setattr(sb, "embed_batch",
                            lambda t: (_ for _ in ()).throw(EmbeddingBackendError("refused")))
        with pytest.raises(sb.EmbeddingAbort, match="3 embedding backend failures"):
            sb.embed_chunk_resilient(["a"], {})

    def test_success_resets_the_streak(self, monkeypatch):
        seq = iter([EmbeddingBackendError("x"), EmbeddingBackendError("x"), None,
                    EmbeddingBackendError("x"), EmbeddingBackendError("x"), None])
        def eb(texts):
            e = next(seq)
            if e: raise e
            return [[1.0]]
        monkeypatch.setattr(sb, "embed_batch", eb)
        state: dict = {}
        sb.embed_chunk_resilient(["a"], state)
        sb.embed_chunk_resilient(["a"], state)     # 2+2 Fehler, nie 3 in Folge
        assert state["total"] == 4


class _FakeClf:
    meta = {"heads": ["vertical"]}
    has_relevance_head = False
    def classify_batch(self, X):
        return [{"relevance": None, "vertical_confidence": 0.9, "primary_vertical": "TECH",
                 "pestel": ["T"], "mega_trend": None} for _ in range(len(X))]


@pytest.fixture
def seeded_db():
    old = pdb.DATABASE_PATH
    pdb.DATABASE_PATH = TEST_DB
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    init_db()
    with get_connection() as c:
        c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) "
                  "VALUES (1, 'arXiv', 'http://a', 'research', 'TECH')")
        for i in range(1, 5):
            c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt) "
                      f"VALUES ({i}, 1, 'http://a/{i}', 'Paper number {i} on topic {i}', 'abstract {i}')")
        c.commit()
    yield
    pdb.DATABASE_PATH = old


def _rows():
    with get_connection() as c:
        return {r["id"]: dict(r) for r in c.execute(
            "SELECT id, processed, filtered_out, filter_reason FROM raw_entries").fetchall()}


class TestRunDistill:
    @pytest.fixture(autouse=True)
    def _wire(self, monkeypatch):
        from pipeline import distill
        monkeypatch.setattr(distill.DistillClassifier, "load", staticmethod(lambda: _FakeClf()))
        monkeypatch.setattr(sb, "EMBED_BACKEND", "llamacpp")
        monkeypatch.setattr(sb, "get_recent_titles", lambda days: [])
        monkeypatch.setattr(sb, "get_recent_embeddings", lambda days: [])
        monkeypatch.setattr(sb, "EMBED_MAX_CONSECUTIVE_ERRORS", 2)
        monkeypatch.setattr(sb, "EMBED_ERROR_SLEEP", 0)

    def test_server_down_leaves_everything_unprocessed_and_exits_3(self, seeded_db, monkeypatch):
        monkeypatch.setattr(sb, "embed_batch",
                            lambda t: (_ for _ in ()).throw(EmbeddingBackendError("Connection refused")))
        rc = sb.run_distill(limit=0, execute=True, embed_chunk=2, include=[], exclude=[])
        assert rc == sb.EXIT_EMBED_BACKEND == 3
        for r in _rows().values():
            assert not r["processed"] and not r["filtered_out"] and r["filter_reason"] is None, r

    def test_server_dies_mid_run_keeps_earlier_chunks(self, seeded_db, monkeypatch):
        calls = {"n": 0}
        def eb(texts):
            calls["n"] += 1
            if calls["n"] == 1:
                return [[float(i == k) for k in range(8)] for i, _ in enumerate(texts)]
            raise EmbeddingBackendError("Connection refused")
        monkeypatch.setattr(sb, "embed_batch", eb)
        rc = sb.run_distill(limit=0, execute=True, embed_chunk=2, include=[], exclude=[])
        assert rc == 3
        rows = _rows()
        assert rows[1]["processed"] and rows[2]["processed"]          # Chunk 1 → Signale
        assert not rows[3]["processed"] and not rows[3]["filtered_out"]
        assert not rows[4]["processed"] and not rows[4]["filtered_out"]
        with get_connection() as c:
            assert c.execute("SELECT count(*) AS n FROM trends WHERE status='signal'").fetchone()["n"] == 2

    def test_content_failure_is_still_embedding_error(self, seeded_db, monkeypatch):
        """Ein einzelner Text, den der Server ablehnt (None), bleibt ein Urteil."""
        def eb(texts):
            return [None if t.startswith("Paper number 2") else
                    [float(i == k) for k in range(8)] for i, t in enumerate(texts)]
        monkeypatch.setattr(sb, "embed_batch", eb)
        rc = sb.run_distill(limit=0, execute=True, embed_chunk=4, include=[], exclude=[])
        assert rc == 0
        rows = _rows()
        assert rows[2]["filtered_out"] and rows[2]["filter_reason"] == "embedding_error"
        assert all(rows[i]["processed"] and not rows[i]["filtered_out"] for i in (1, 3, 4))


class TestResetScript:
    def test_dry_run_counts_and_apply_resets_only_embedding_errors(self, seeded_db, capsys):
        with get_connection() as c:
            c.execute("UPDATE raw_entries SET processed=TRUE, filtered_out=TRUE, "
                      "filter_reason='embedding_error' WHERE id IN (1, 2)")
            c.execute("UPDATE raw_entries SET processed=TRUE, filtered_out=TRUE, "
                      "filter_reason='not_relevant' WHERE id = 3")
            c.commit()
        assert rst.main([]) == 0
        out = capsys.readouterr().out
        assert "in scope: 2" in out and "DRY-RUN" in out and "arXiv" in out
        rows = _rows()
        assert rows[1]["filtered_out"] and rows[2]["filtered_out"]      # nichts geändert
        assert rst.main(["--apply"]) == 0
        assert "Reset 2 rows" in capsys.readouterr().out
        rows = _rows()
        for i in (1, 2):
            assert not rows[i]["processed"] and not rows[i]["filtered_out"] and rows[i]["filter_reason"] is None
        assert rows[3]["filtered_out"] and rows[3]["filter_reason"] == "not_relevant"
        assert rst.main(["--apply"]) == 0                                # idempotent
        assert "in scope: 0" in capsys.readouterr().out

    def test_scope_flags(self, seeded_db, capsys):
        with get_connection() as c:
            c.execute("UPDATE raw_entries SET processed=TRUE, filtered_out=TRUE, "
                      "filter_reason='embedding_error'")
            c.commit()
        assert rst.main(["--min-id", "2", "--apply"]) == 0
        assert "Reset 2 rows" in capsys.readouterr().out                # ids 3, 4
        assert rst.main(["--source-type", "api"]) == 0
        assert "in scope: 0" in capsys.readouterr().out
