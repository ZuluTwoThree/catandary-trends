"""Zweiter Vektorraum über den Quelltext (#102, 2026-09-10).

Der bestehende Vektor kommt aus `title + excerpt[:500]` — Median 588 Zeichen.
Er bleibt unangetastet (Dedup-Semantik, 1,7 Mio. Zeilen). Dieser Lauf rechnet
einen ZWEITEN über den vollen verfügbaren Quelltext nach HTML-Reinigung.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import embed_full_text as eft
from pipeline.text_clean import clean_source_text


class TestTextSelection:
    def test_full_text_beats_the_teaser(self):
        got = eft.text_for({"title_en": "T", "raw_content": "Der ganze Text.", "excerpt": "Anriss"})
        assert "Der ganze Text." in got and "Anriss" not in got

    def test_teaser_is_used_when_the_full_text_is_gone(self):
        """Nach der Retention bleibt nur der Anriss — er ist besser als nichts."""
        got = eft.text_for({"title_en": "T", "raw_content": None, "excerpt": "Nur der Anriss."})
        assert "Nur der Anriss." in got

    def test_html_is_removed(self):
        got = eft.text_for({"title_en": "T", "raw_content": '<p class="x">Text &#8212; hier.</p>'})
        assert "<p" not in got and "Text — hier." in got

    def test_title_leads(self):
        assert eft.text_for({"title_en": "Titel", "excerpt": "Rumpf"}).startswith("Titel\n")

    def test_length_is_capped(self):
        got = eft.text_for({"title_en": "T", "raw_content": "x" * 50_000})
        assert len(got) == eft.MAX_EMBED_CHARS

    def test_no_five_hundred_char_cap(self):
        """Der Sinn der Übung: der Dedup-Ausschnitt schneidet bei 500 ab."""
        got = eft.text_for({"title_en": "T", "raw_content": "y" * 3_000})
        assert len(got) > 2_900


class TestThinRowsAreStampedNotEmbedded:
    def test_thin_rows_never_reach_the_embedder(self, monkeypatch):
        called = []
        monkeypatch.setattr(eft, "embed_chunk_resilient",
                            lambda texts, state: called.append(texts) or [[0.0] * 1024] * len(texts))
        monkeypatch.setattr(eft, "get_connection", lambda: _NullConn())
        stat = eft.run([{"id": 1, "title_en": "T", "excerpt": "kurz", "raw_content": None}],
                       apply=False)
        assert stat["too_thin"] == 1 and called == []

    def test_rich_rows_are_embedded(self, monkeypatch):
        monkeypatch.setattr(eft, "embed_chunk_resilient",
                            lambda texts, state: [[0.1] * 1024] * len(texts))
        monkeypatch.setattr(eft, "get_connection", lambda: _NullConn())
        stat = eft.run([{"id": 1, "title_en": "T", "raw_content": "w" * 2_000, "excerpt": None}],
                       apply=False)
        assert stat["embedded"] == 1 and stat["too_thin"] == 0

    def test_a_short_vector_is_not_stamped(self, monkeypatch):
        """Ein zu schmaler Vektor heisst: falsches Modell. Zeile bleibt offen."""
        monkeypatch.setattr(eft, "embed_chunk_resilient",
                            lambda texts, state: [[0.1] * 768] * len(texts))
        monkeypatch.setattr(eft, "get_connection", lambda: _NullConn())
        stat = eft.run([{"id": 1, "title_en": "T", "raw_content": "w" * 2_000, "excerpt": None}],
                       apply=False)
        assert stat["embed_failed"] == 1 and stat["embedded"] == 0


class _NullConn:
    def execute(self, *a, **k):
        return self
    def fetchall(self):
        return []
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class TestModelGuard:
    def test_chat_model_is_refused(self, monkeypatch):
        monkeypatch.setattr(eft, "EMBED_BACKEND", "llamacpp")
        monkeypatch.setattr(eft, "served_model_id", lambda: "./models/Qwen3-8B-UD-Q4_K_XL.gguf")
        with pytest.raises(SystemExit, match="kein Embedding-Modell"):
            eft.assert_embedding_model()

    def test_embedding_model_passes(self, monkeypatch):
        monkeypatch.setattr(eft, "EMBED_BACKEND", "llamacpp")
        monkeypatch.setattr(eft, "served_model_id", lambda: "Qwen3-Embedding-8B-Q4_K_M.gguf")
        eft.assert_embedding_model()

    def test_other_backends_are_not_checked(self, monkeypatch):
        monkeypatch.setattr(eft, "EMBED_BACKEND", "ollama")
        eft.assert_embedding_model()


class TestCleaner:
    def test_wording_survives(self):
        assert clean_source_text("Exactly 2,000 flights.") == "Exactly 2,000 flights."
