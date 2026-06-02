"""Routing tests for Stage 5 (Embedding) → llama.cpp backend.

Verifies the EMBED_BACKEND env switch sends generate_embedding calls to the
correct client. No network IO — both clients are mocked.
"""

import importlib

import pytest


@pytest.fixture
def reload_pipeline(monkeypatch):
    """Reload pipeline.config + pipeline.llm_processor after monkeypatching env
    so module-level EMBED_BACKEND picks up the new value."""
    def _reload(backend: str):
        monkeypatch.setenv("EMBED_BACKEND", backend)
        monkeypatch.setenv("EMBED_MODEL", "Qwen3-Embedding-8B-Q4_K_M.gguf")
        import pipeline.config  # noqa: F401
        import pipeline.llm_processor
        importlib.reload(pipeline.config)
        importlib.reload(pipeline.llm_processor)
        return pipeline.llm_processor
    return _reload


def _stub_vec():
    return [0.0] * 4096


def test_step_dedup_check_routes_to_ollama_by_default(reload_pipeline, monkeypatch):
    lm = reload_pipeline("ollama")
    ollama_calls = []
    llama_calls = []
    monkeypatch.setattr(lm, "generate_embedding",
                        lambda model, text: (ollama_calls.append((model, text)), _stub_vec())[1])
    monkeypatch.setattr(lm.llamacpp_client, "generate_embedding",
                        lambda text, model=None: (llama_calls.append((text, model)), _stub_vec())[1])
    # Patch get_recent_embeddings to avoid DB hit
    monkeypatch.setattr(lm, "get_recent_embeddings", lambda days: [])

    lm.step_dedup_check("Some title", "Some excerpt long enough.")
    assert len(ollama_calls) == 1
    assert len(llama_calls) == 0


def test_step_dedup_check_routes_to_llamacpp_when_enabled(reload_pipeline, monkeypatch):
    lm = reload_pipeline("llamacpp")
    ollama_calls = []
    llama_calls = []
    monkeypatch.setattr(lm, "generate_embedding",
                        lambda model, text: (ollama_calls.append((model, text)), _stub_vec())[1])
    monkeypatch.setattr(lm.llamacpp_client, "generate_embedding",
                        lambda text, model=None: (llama_calls.append((text, model)), _stub_vec())[1])
    monkeypatch.setattr(lm, "get_recent_embeddings", lambda days: [])

    lm.step_dedup_check("Some title", "Some excerpt long enough.")
    assert len(ollama_calls) == 0
    assert len(llama_calls) == 1
    assert llama_calls[0][1] == "Qwen3-Embedding-8B-Q4_K_M.gguf"
