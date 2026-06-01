"""Routing tests for the qwen3:8b stages → llama.cpp backend.

Verifies that the STAGE_8B_BACKEND env switch sends Stage 2 / Stage 4 / Stage 8
calls to the correct client without invoking the other. No network IO — both
clients are mocked.
"""

import importlib

import pytest


@pytest.fixture
def reload_pipeline(monkeypatch):
    """Reload pipeline.config + pipeline.llm_processor + pipeline.reclassify
    after monkeypatching env so module-level STAGE_8B_BACKEND picks up the value."""
    def _reload(backend: str):
        monkeypatch.setenv("STAGE_8B_BACKEND", backend)
        monkeypatch.setenv("STAGE_8B_MODEL", "Qwen3-8B-UD-Q4_K_XL.gguf")
        import pipeline.config  # noqa: F401
        import pipeline.llm_processor
        import pipeline.reclassify
        importlib.reload(pipeline.config)
        importlib.reload(pipeline.llm_processor)
        importlib.reload(pipeline.reclassify)
        return pipeline.llm_processor, pipeline.reclassify
    return _reload


def _stub_relevance():
    from pipeline.models import RelevanceResult
    return RelevanceResult(is_relevant=True, confidence=0.9,
                           primary_vertical="TECH", reason="ok")


def _stub_classification():
    from pipeline.models import ClassificationResult
    return ClassificationResult(
        verticals=["TECH"], pestel=["T"], tags=["x"],
        trend_signal_type="research", regions=["Global"],
        mega_trend=None,
    )


def _stub_reclassify():
    from pipeline.reclassify import ReclassifyResult
    return ReclassifyResult(primary="TECH", secondaries=[])


def test_stage2_routes_to_ollama_by_default(reload_pipeline, monkeypatch):
    lm, _ = reload_pipeline("ollama")
    ollama_calls = []
    llama_calls = []
    monkeypatch.setattr(lm, "chat_structured",
                        lambda **kw: (ollama_calls.append(kw), _stub_relevance())[1])
    monkeypatch.setattr(lm.llamacpp_client, "chat_structured",
                        lambda **kw: (llama_calls.append(kw), _stub_relevance())[1])

    lm.step_relevance_filter("title", "excerpt", "TECH")
    assert len(ollama_calls) == 1
    assert len(llama_calls) == 0


def test_stage2_routes_to_llamacpp_when_enabled(reload_pipeline, monkeypatch):
    lm, _ = reload_pipeline("llamacpp")
    ollama_calls = []
    llama_calls = []
    monkeypatch.setattr(lm, "chat_structured",
                        lambda **kw: (ollama_calls.append(kw), _stub_relevance())[1])
    monkeypatch.setattr(lm.llamacpp_client, "chat_structured",
                        lambda **kw: (llama_calls.append(kw), _stub_relevance())[1])

    lm.step_relevance_filter("title", "excerpt", "TECH")
    assert len(ollama_calls) == 0
    assert len(llama_calls) == 1
    assert llama_calls[0]["model"] == "Qwen3-8B-UD-Q4_K_XL.gguf"


def test_stage4_classify_routes_to_llamacpp_when_enabled(reload_pipeline, monkeypatch):
    lm, _ = reload_pipeline("llamacpp")
    from pipeline.models import ExtractionResult
    llama_calls = []
    monkeypatch.setattr(lm, "chat_structured",
                        lambda **kw: pytest.fail("ollama should not be called"))
    monkeypatch.setattr(lm.llamacpp_client, "chat_structured",
                        lambda **kw: (llama_calls.append(kw), _stub_classification())[1])

    lm.step_classification("title", "excerpt", ExtractionResult())
    assert len(llama_calls) == 1
    assert llama_calls[0]["model"] == "Qwen3-8B-UD-Q4_K_XL.gguf"


def test_stage8_reclassify_routes_to_llamacpp_when_enabled(reload_pipeline, monkeypatch):
    _, rc = reload_pipeline("llamacpp")
    llama_calls = []
    monkeypatch.setattr(rc, "chat_structured",
                        lambda **kw: pytest.fail("ollama should not be called"))
    monkeypatch.setattr(rc.llamacpp_client, "chat_structured",
                        lambda **kw: (llama_calls.append(kw), _stub_reclassify())[1])

    result = rc._classify_one("title", "summary")
    assert result == {"primary": "TECH", "verticals": ["TECH"]}
    assert len(llama_calls) == 1


def test_stage8_reclassify_routes_to_ollama_by_default(reload_pipeline, monkeypatch):
    _, rc = reload_pipeline("ollama")
    ollama_calls = []
    monkeypatch.setattr(rc, "chat_structured",
                        lambda **kw: (ollama_calls.append(kw), _stub_reclassify())[1])
    monkeypatch.setattr(rc.llamacpp_client, "chat_structured",
                        lambda **kw: pytest.fail("llamacpp should not be called"))

    rc._classify_one("title", "summary")
    assert len(ollama_calls) == 1
