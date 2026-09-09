"""Modell-Identitäts-Check der llama.cpp-Stages (#98, 2026-09-05).

llama-server ignoriert das model-Feld im Request und antwortet mit dem
geladenen GGUF. Tauscht ein fremder Job den Server mitten in einer Stage
(05.09.: Embedding-Server statt Gemma), muss die Stage abbrechen statt
weiterzugenerieren — und ihre Einträge unverarbeitet lassen. Kein Netz:
GET /v1/models und POST /v1/chat/completions sind gemockt.
"""
import importlib
import os
import tempfile

import httpx
import pytest

import pipeline.llamacpp_client as lc
from pipeline.llamacpp_client import ModelMismatchError

GEMMA = "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
EMB = "Qwen3-Embedding-8B-Q4_K_M.gguf"


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(lc, "_model_check_last", {})


class TestModelMatches:
    def test_gguf_basename_in_served_path(self):
        assert lc.model_matches(GEMMA, f"/home/dirk/llama.cpp/models/{GEMMA}")
        assert lc.model_matches(GEMMA, GEMMA)

    def test_alias_equal(self):
        assert lc.model_matches("Qwen3.8-27B", "Qwen3.8-27B")

    def test_other_model_or_down(self):
        assert not lc.model_matches(GEMMA, EMB)
        assert not lc.model_matches(GEMMA, None)


class TestAssertServedModel:
    def test_mismatch_raises_with_clear_message(self, monkeypatch):
        monkeypatch.setattr(lc, "served_model_id", lambda: EMB)
        with pytest.raises(ModelMismatchError) as ei:
            lc.assert_served_model(GEMMA, stage="GeneratedContent")
        msg = str(ei.value)
        assert "GeneratedContent" in msg and EMB in msg and GEMMA in msg and "#98" in msg

    def test_match_is_cached_within_ttl(self, monkeypatch):
        calls = []
        monkeypatch.setattr(lc, "served_model_id", lambda: (calls.append(1), GEMMA)[1])
        lc.assert_served_model(GEMMA)
        lc.assert_served_model(GEMMA)
        assert len(calls) == 1
        lc.assert_served_model(GEMMA, force=True)      # Retry-Pfad prüft immer
        assert len(calls) == 2

    def test_unreachable_is_not_a_verdict_and_not_cached(self, monkeypatch, caplog):
        calls = []
        monkeypatch.setattr(lc, "served_model_id", lambda: (calls.append(1), None)[1])
        lc.assert_served_model(GEMMA)                    # kein Raise
        lc.assert_served_model(GEMMA)                    # erneut geprüft (nicht gecacht)
        assert len(calls) == 2
        assert "unreachable" in caplog.text

    def test_served_model_id_parses_openai_shape(self, monkeypatch):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"data": [{"id": f"/models/{GEMMA}"}]}
        monkeypatch.setattr(lc.httpx, "get", lambda *a, **k: R())
        assert lc.served_model_id() == f"/models/{GEMMA}"
        monkeypatch.setattr(lc.httpx, "get",
                            lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("refused")))
        assert lc.served_model_id() is None


class _Schema(lc.BaseModel):
    x: int


class TestChatStructuredGate:
    def _client(self, monkeypatch, posts: list, fail_first: bool = False):
        class Resp:
            def raise_for_status(self): pass
            def json(self):
                return {"choices": [{"finish_reason": "stop",
                                     "message": {"content": '{"x": 1}'}}]}

        class Client:
            def __init__(self, *a, **k): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def post(self, url, json=None):
                posts.append(json)
                if fail_first and len(posts) == 1:
                    raise httpx.ConnectError("Connection refused")
                return Resp()
        monkeypatch.setattr(lc.httpx, "Client", Client)
        monkeypatch.setattr(lc.time, "sleep", lambda s: None)

    def test_mismatch_aborts_before_any_request_and_never_retries(self, monkeypatch):
        posts: list = []
        self._client(monkeypatch, posts)
        checks = []
        monkeypatch.setattr(lc, "served_model_id", lambda: (checks.append(1), EMB)[1])
        with pytest.raises(ModelMismatchError):
            lc.chat_structured(model=GEMMA, prompt="p", schema=_Schema, verify_model=True)
        assert posts == []            # nichts gegen das falsche Modell geschickt
        assert len(checks) == 1       # kein Retry-Zyklus

    def test_match_lets_the_request_through(self, monkeypatch):
        posts: list = []
        self._client(monkeypatch, posts)
        monkeypatch.setattr(lc, "served_model_id", lambda: GEMMA)
        r = lc.chat_structured(model=GEMMA, prompt="p", schema=_Schema, verify_model=True)
        assert r.x == 1 and len(posts) == 1

    def test_retry_rechecks_and_aborts_on_swapped_server(self, monkeypatch):
        """Der Vorfall in Kurzform: erster Request scheitert (Server wird
        gerade getauscht), beim Retry antwortet /v1/models mit dem
        Embedding-Modell → Abbruch statt Retry Nr. 2."""
        posts: list = []
        self._client(monkeypatch, posts, fail_first=True)
        served = iter([GEMMA, EMB, EMB])
        monkeypatch.setattr(lc, "served_model_id", lambda: next(served))
        with pytest.raises(ModelMismatchError):
            lc.chat_structured(model=GEMMA, prompt="p", schema=_Schema, verify_model=True)
        assert len(posts) == 1

    def test_default_is_unverified(self, monkeypatch):
        posts: list = []
        self._client(monkeypatch, posts)
        monkeypatch.setattr(lc, "served_model_id",
                            lambda: pytest.fail("no identity check without verify_model"))
        assert lc.chat_structured(model=GEMMA, prompt="p", schema=_Schema).x == 1


class TestStageRouting:
    """Die llama.cpp-Pfade der Stages 2/3/4/6/8 schalten den Check ein."""

    @pytest.fixture
    def lm(self, monkeypatch):
        monkeypatch.setenv("STAGE_8B_BACKEND", "llamacpp")
        monkeypatch.setenv("STAGE5_BACKEND", "llamacpp")
        monkeypatch.setenv("STAGE5_MODEL", GEMMA)
        import pipeline.config, pipeline.llm_processor, pipeline.reclassify
        importlib.reload(pipeline.config)
        importlib.reload(pipeline.llm_processor)
        importlib.reload(pipeline.reclassify)
        yield pipeline.llm_processor, pipeline.reclassify
        monkeypatch.delenv("STAGE_8B_BACKEND"); monkeypatch.delenv("STAGE5_BACKEND")
        monkeypatch.delenv("STAGE5_MODEL")
        importlib.reload(pipeline.config); importlib.reload(pipeline.llm_processor)
        importlib.reload(pipeline.reclassify)

    def test_every_llamacpp_stage_verifies(self, lm, monkeypatch):
        proc, rc = lm
        from pipeline.models import ExtractionResult, ClassificationResult
        seen = []
        def fake(**kw):
            seen.append((kw["schema"].__name__, kw.get("verify_model")))
            return None
        monkeypatch.setattr(proc.llamacpp_client, "chat_structured", fake)
        monkeypatch.setattr(rc.llamacpp_client, "chat_structured", fake)
        proc.step_relevance_filter("t", "e", "TECH")
        proc.step_extraction("t", "e")
        proc.step_classification("t", "e", ExtractionResult())
        proc.step_generate_content_en("t", "e", ExtractionResult(), ClassificationResult(
            verticals=["TECH"], pestel=["T"], tags=[], trend_signal_type="research",
            regions=["Global"], mega_trend=None), "http://x", "Src")
        rc._classify_one("t", "s")
        assert seen == [("RelevanceResult", True), ("ExtractionResult", True),
                        ("ClassificationResult", True), ("GeneratedContent", True),
                        ("ReclassifyResult", True)]


class TestStage6Abort:
    """Ein Mismatch mitten in Stage 6 stoppt die Generierung: der getroffene
    und alle folgenden Einträge bleiben unprocessed (nicht gefiltert, nicht
    markiert), die schon generierten laufen normal weiter, der Lauf endet mit
    Fehlerzähler > 0."""

    def test_remaining_entries_stay_unprocessed(self, monkeypatch, tmp_path):
        from contextlib import nullcontext
        db_path = str(tmp_path / "stage6.db")
        monkeypatch.setenv("DATABASE_PATH", db_path)
        monkeypatch.setenv("STAGE5_BACKEND", "llamacpp")
        monkeypatch.setenv("STAGE5_MODEL", GEMMA)
        monkeypatch.setenv("RSS_CLASSIFY_MODE", "llm")
        monkeypatch.setenv("STAGE_8B_BACKEND", "ollama")
        monkeypatch.setenv("EMBED_BACKEND", "ollama")
        import pipeline.config, pipeline.db as pdb, pipeline.llm_processor
        importlib.reload(pipeline.config)
        monkeypatch.setattr(pdb, "DATABASE_PATH", db_path)
        importlib.reload(pipeline.llm_processor)
        lm = pipeline.llm_processor
        from pipeline.db import get_connection, init_db
        from pipeline.models import (RelevanceResult, ExtractionResult,
                                     ClassificationResult, GeneratedContent)
        init_db()
        with get_connection() as c:
            c.execute("INSERT INTO sources (id, name, feed_url, source_type, vertical) "
                      "VALUES (1, 'Src', 'http://src', 'trade_media', 'TECH')")
            for i, t in enumerate(("Quantum error correction milestone",
                                   "Plant-based cheese scales in Europe",
                                   "Modular housing factory opens"), start=1):
                # >= MIN_SOURCE_TEXT_CHARS (80) — a bare title is filtered
                # before any LLM stage since 2026-09-09
                c.execute("INSERT INTO raw_entries (id, source_id, url, title, excerpt) "
                          f"VALUES ({i}, 1, 'http://s/{i}', '{t}', "
                          f"'Excerpt {i}: researchers describe the result in detail and "
                          f"give the figures behind it in the full report.')")
            c.commit()

        monkeypatch.setattr(lm, "step_relevance_filter", lambda *a, **k: RelevanceResult(
            is_relevant=True, confidence=0.9, primary_vertical="TECH", reason="ok"))
        monkeypatch.setattr(lm, "step_extraction", lambda *a, **k: ExtractionResult())
        monkeypatch.setattr(lm, "step_classification", lambda *a, **k: ClassificationResult(
            verticals=["TECH"], pestel=["T"], tags=[], trend_signal_type="research",
            regions=["Global"], mega_trend=None))
        monkeypatch.setattr(lm, "get_recent_titles", lambda days: [])
        monkeypatch.setattr(lm, "get_recent_embeddings", lambda days: [])
        n = {"i": 0}
        def emb(model, text):  # orthogonale Vektoren, sonst greift der Dedup
            n["i"] += 1
            v = [0.0] * 8; v[n["i"] % 8] = 1.0
            return v
        monkeypatch.setattr(lm, "generate_embedding", emb)
        gen = {"calls": 0}
        def content(*a, **k):
            gen["calls"] += 1
            if gen["calls"] == 1:
                return GeneratedContent(title="Article one", summary="s", body="b", source_attribution="a")
            raise ModelMismatchError("GeneratedContent: llama-server serves 'emb', expected 'gemma'")
        monkeypatch.setattr(lm, "step_generate_content_en", content)
        monkeypatch.setattr(lm.gpu_handover, "content_gen_on_llamacpp", lambda m: nullcontext())
        monkeypatch.setattr(lm, "reclassify_drafts", lambda: {"total": 0, "changed": 0})
        monkeypatch.setattr(lm, "gate_mega_trends", lambda: {"nulled": 0, "checked": 0})
        monkeypatch.setattr(lm, "auto_publish", lambda: {"published": 0, "skipped": 0})

        res = lm.run_pipeline_batch(limit=10)
        assert res["created"] == 1 and res["errors"] == 2
        assert gen["calls"] == 2                       # nach dem Mismatch kein weiterer Versuch
        with get_connection() as c:
            rows = {r["id"]: dict(r) for r in c.execute(
                "SELECT id, processed, filtered_out, filter_reason FROM raw_entries").fetchall()}
            trends = c.execute("SELECT raw_entry_id FROM trends").fetchall()
        assert bool(rows[1]["processed"]) is True
        for i in (2, 3):
            assert not rows[i]["processed"] and not rows[i]["filtered_out"], rows[i]
        assert [r["raw_entry_id"] for r in trends] == [1]
        monkeypatch.delenv("DATABASE_PATH"); monkeypatch.delenv("STAGE5_BACKEND")
        monkeypatch.delenv("STAGE5_MODEL"); monkeypatch.delenv("RSS_CLASSIFY_MODE")
        monkeypatch.delenv("STAGE_8B_BACKEND"); monkeypatch.delenv("EMBED_BACKEND")
        importlib.reload(pipeline.config); importlib.reload(pipeline.llm_processor)
