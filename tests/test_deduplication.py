"""Tests for deduplication logic."""

import pytest

from pipeline.llm_processor import (
    bytes_to_embedding,
    cosine_similarity,
    embedding_to_bytes,
)


class TestEmbeddingSerialization:
    def test_roundtrip(self):
        original = [0.1, 0.2, 0.3, -0.4, 0.5]
        packed = embedding_to_bytes(original)
        unpacked = bytes_to_embedding(packed)
        for a, b in zip(original, unpacked):
            assert abs(a - b) < 1e-6

    def test_empty_embedding(self):
        packed = embedding_to_bytes([])
        unpacked = bytes_to_embedding(packed)
        assert unpacked == []

    def test_large_embedding(self):
        # qwen3-embedding produces 4096-dim vectors
        original = [float(i) / 1000 for i in range(4096)]
        packed = embedding_to_bytes(original)
        unpacked = bytes_to_embedding(packed)
        assert len(unpacked) == 4096
        for a, b in zip(original, unpacked):
            assert abs(a - b) < 1e-6


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 2.0, 3.0]
        b = [-1.0, -2.0, -3.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_similar_vectors(self):
        a = [1.0, 2.0, 3.0]
        b = [1.1, 2.1, 3.1]
        sim = cosine_similarity(a, b)
        assert sim > 0.99

    def test_zero_vector(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert cosine_similarity(a, b) == 0.0

    def test_similarity_range(self):
        """Cosine similarity should always be between -1 and 1."""
        import random
        random.seed(42)
        for _ in range(100):
            a = [random.uniform(-1, 1) for _ in range(50)]
            b = [random.uniform(-1, 1) for _ in range(50)]
            sim = cosine_similarity(a, b)
            assert -1.0 <= sim <= 1.0 + 1e-6


class TestDedupExcludesHandRejected:
    """A reviewer rejects the TEXT, not the story (#71).

    Their rejected article used to stay in the 30-day dedup window and killed
    the next outlet's coverage of the same event as a duplicate, so the story
    was lost. Sweep rejections (advertorials) must KEEP blocking, because there
    the source is the problem — reviewed_at is what tells the two apart.
    """

    def _insert(self, conn, tid, status, reviewed):
        conn.execute(
            "INSERT INTO trends (id, title_en, slug, source_url, status, "
            " reviewed_at, embedding, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (tid, f"T{tid}", f"t-{tid}", "https://example.com", status,
             reviewed, b"\x00" * 16),
        )

    def test_hand_rejected_leaves_the_window_sweep_rejected_stays(self):
        from pipeline.db import get_connection, get_recent_embeddings, init_db
        init_db()
        with get_connection() as conn:
            self._insert(conn, 900001, "published", None)
            self._insert(conn, 900002, "rejected", "2026-08-11 09:00:00")  # by hand
            self._insert(conn, 900003, "rejected", None)                   # sweep
            self._insert(conn, 900004, "draft", None)

        ids = {i for i, _ in get_recent_embeddings(days=30, limit=1000)}
        assert 900002 not in ids, "hand-rejected must not block a re-cover"
        assert 900003 in ids, "sweep rejection must keep suppressing follow-ups"
        assert 900001 in ids and 900004 in ids, "normal rows must still dedup"
