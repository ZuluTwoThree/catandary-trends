"""Distilled embedding classifier — inference side (issue #10).

Cheap linear heads on the 4096-dim signal embeddings replace the per-item LLM
calls for classification on mass-ingest paths (deep backfill). Heads are
trained by scripts/train_distill_heads.py on the LLM-assigned labels already
in `trends` (teacher = the 8B pipeline) and persisted under models/distill/.

Usage:
    from pipeline.distill import DistillClassifier
    clf = DistillClassifier.load()          # raises if models missing
    out = clf.classify(vec)                 # vec: list[float] | np.ndarray
    # → {"primary_vertical": "TECH", "vertical_confidence": 0.91,
    #    "mega_trend": "...", "mega_top3": [...], "pestel": ["T","E"],
    #    "relevance": 0.87}                  (relevance None if head not trained)

The heads are taxonomy-bounded — novelty detection stays with the discovery
loop (scripts/discover_trends.py → curated mega_trends.yaml → retrain).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from pipeline.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

MODELS_DIR = Path(PROJECT_ROOT) / "models" / "distill"
PESTEL_DIMS = ["P", "E", "S", "T", "En", "L"]


def _normalize(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=np.float32)
    if X.ndim == 1:
        X = X[None, :]
    return X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)


class DistillClassifier:
    """Loads the persisted heads and classifies embeddings (batch-first)."""

    def __init__(self, vertical, mega, pestel, relevance, meta: dict):
        self._vertical = vertical
        self._mega = mega
        self._pestel = pestel
        self._relevance = relevance
        self.meta = meta

    @classmethod
    def load(cls, models_dir: Path | None = None) -> "DistillClassifier":
        import joblib
        d = models_dir or MODELS_DIR
        meta_path = d / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"no trained distill heads under {d} — run scripts/train_distill_heads.py")
        meta = json.loads(meta_path.read_text())
        rel_path = d / "relevance.joblib"
        return cls(
            vertical=joblib.load(d / "vertical.joblib"),
            mega=joblib.load(d / "mega.joblib"),
            pestel=joblib.load(d / "pestel.joblib"),
            relevance=joblib.load(rel_path) if rel_path.exists() else None,
            meta=meta,
        )

    # ------------------------------------------------------------- batch API
    def classify_batch(self, X) -> list[dict]:
        """Classify a batch of embeddings. X: (n, 4096) array-like."""
        Xn = _normalize(X)
        n = Xn.shape[0]

        v_scores = self._vertical.decision_function(Xn)
        if v_scores.ndim == 1:
            v_scores = np.stack([-v_scores, v_scores], axis=1)
        v_classes = np.asarray(self._vertical.classes_)
        v_order = np.argsort(-v_scores, axis=1)
        # softmax over decision scores → a usable confidence proxy
        v_exp = np.exp(v_scores - v_scores.max(axis=1, keepdims=True))
        v_prob = v_exp / v_exp.sum(axis=1, keepdims=True)

        m_scores = self._mega.decision_function(Xn)
        if m_scores.ndim == 1:
            m_scores = np.stack([-m_scores, m_scores], axis=1)
        m_classes = np.asarray(self._mega.classes_)
        m_order = np.argsort(-m_scores, axis=1)

        p_pred = self._pestel.predict(Xn)

        rel = None
        if self._relevance is not None:
            rel = self._relevance.predict_proba(Xn)[:, 1]

        out = []
        for i in range(n):
            top_v = v_order[i, 0]
            out.append({
                "primary_vertical": str(v_classes[top_v]),
                "vertical_confidence": float(v_prob[i, top_v]),
                "vertical_top2": [str(c) for c in v_classes[v_order[i, :2]]],
                "mega_trend": str(m_classes[m_order[i, 0]]),
                "mega_top3": [str(c) for c in m_classes[m_order[i, :3]]],
                "pestel": [PESTEL_DIMS[j] for j in range(len(PESTEL_DIMS))
                           if p_pred[i, j] == 1],
                "relevance": float(rel[i]) if rel is not None else None,
            })
        return out

    def classify(self, vec) -> dict:
        """Single-embedding convenience wrapper."""
        return self.classify_batch(vec)[0]

    @property
    def has_relevance_head(self) -> bool:
        return self._relevance is not None
