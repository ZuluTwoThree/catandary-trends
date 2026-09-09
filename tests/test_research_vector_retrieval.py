"""Vektorsuche des Korpus-Rechercheurs (#97, 2026-09-09).

Warum ein eigener Endpunkt: während ein Dossier läuft, hält :8090 den
27B-Rechercheur. Ein Embedding-Request dorthin wird vom **Chatmodell**
beantwortet — der Query-Vektor käme aus einem anderen Raum als die
gespeicherten, und die ANN-Suche wäre nicht ungenau, sondern Unsinn.
Deshalb `RESEARCH_EMBED_HOST` (CPU-Server auf :8091) plus ein harter
Dimensions-Check.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import scripts.corpus_research as cr
from pipeline import llamacpp_client


class TestEmbedQuery:
    def test_uses_the_dedicated_host_when_configured(self, monkeypatch):
        seen = {}
        monkeypatch.setattr("pipeline.config.RESEARCH_EMBED_HOST", "http://127.0.0.1:8091")
        monkeypatch.setattr(llamacpp_client, "generate_embedding",
                            lambda text, **kw: seen.update(kw) or [0.0] * 4096)
        cr.embed_query("frage")
        assert seen.get("host") == "http://127.0.0.1:8091"

    def test_falls_back_to_the_default_backend_without_the_variable(self, monkeypatch):
        seen = {}
        monkeypatch.setattr("pipeline.config.RESEARCH_EMBED_HOST", "")
        monkeypatch.setattr("pipeline.config.EMBED_BACKEND", "llamacpp")
        monkeypatch.setattr(llamacpp_client, "generate_embedding",
                            lambda text, **kw: seen.update(kw) or [0.0] * 4096)
        cr.embed_query("frage")
        assert "host" not in seen

    def test_short_vector_is_refused(self, monkeypatch):
        """768 Dimensionen = ein anderes Modell hat geantwortet."""
        monkeypatch.setattr("pipeline.config.RESEARCH_EMBED_HOST", "http://127.0.0.1:8091")
        monkeypatch.setattr(llamacpp_client, "generate_embedding", lambda text, **kw: [0.1] * 768)
        with pytest.raises(RuntimeError, match="768 dimensions"):
            cr.embed_query("frage")

    def test_empty_answer_names_the_configured_host(self, monkeypatch):
        monkeypatch.setattr("pipeline.config.RESEARCH_EMBED_HOST", "http://127.0.0.1:9999")
        monkeypatch.setattr(llamacpp_client, "generate_embedding", lambda text, **kw: None)
        with pytest.raises(RuntimeError, match="9999"):
            cr.embed_query("frage")


class TestWorkerDefault:
    """Der Worker schaltet nur um, wenn ein eigener Endpunkt konfiguriert ist —
    sonst liefe die Vektorsuche gegen den 27B."""

    def _retrieval(self, monkeypatch, value):
        import importlib
        import scripts.dossier_worker as w
        monkeypatch.setenv("RESEARCH_EMBED_HOST", value) if value else \
            monkeypatch.delenv("RESEARCH_EMBED_HOST", raising=False)
        importlib.reload(w)
        return w.RUN_DEFAULTS["retrieval"]

    def test_vector_when_endpoint_configured(self, monkeypatch):
        assert self._retrieval(monkeypatch, "http://127.0.0.1:8091") == "vector"

    def test_fts_without_endpoint(self, monkeypatch):
        assert self._retrieval(monkeypatch, "") == "fts"


class TestFallbackIsVisible:
    """Fällt der Endpunkt im Lauf aus, darf das Dossier nicht sterben — aber der
    Rückfall auf Volltext muss in den Notizen stehen, nicht stillschweigend."""

    def test_search_closure_falls_back_and_notes_it(self):
        import inspect
        src = inspect.getsource(cr.run)
        assert "_mode[\"backend\"] = search_corpus" in src
        assert "notes.append" in src.split("_mode[\"fell_back\"]")[1][:400]
