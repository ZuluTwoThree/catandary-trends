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
        original = [float(i) / 1000 for i in range(1024)]
        packed = embedding_to_bytes(original)
        unpacked = bytes_to_embedding(packed)
        assert len(unpacked) == 1024
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
