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
# Fifth head (#110): trend_signal_type for press signals. Optional — the
# classifier loads it when the file exists; scripts/train_signal_type_head.py writes it.
SIGNAL_TYPE_HEAD_FILE = "signal_type.joblib"
# FALLBACK only. Since 2026-09-26 the trainer calibrates this threshold per head
# and stores it in meta.json (`mega_abstain_threshold`); DistillClassifier prefers
# that value. The reason is that the decision-value SCALE is not a constant of
# nature: it depends on the embedding width AND the class weighting. Measured on
# 20k rows, the 4096-dim unweighted head abstains on 7.2 % of signals at -1.0, the
# 1024-dim balanced head on 12.9 % at the same number — and more abstaining means
# more mega_trend=NULL, i.e. emptier theme pages. The number below stays right for
# the heads it was calibrated on (4096, unweighted), which is why it remains the
# fallback for models trained before the threshold was recorded.
# Abstain (mega_trend=None) only when even the best class is DEEPLY rejected —
# a gross no-fit like the Supergirl box-office trend (all 21 scores ≤ -1.6).
# 0.0 (the OvR boundary) was too aggressive: 22% of plausible in-top-3 labels
# sit at a slightly-negative max (p10 -0.66) and shouldn't be dropped. -1.0
# keeps those and abstains only on genuine no-fits. Cross-label misassignments
# (right vs wrong class) are handled separately by the top-3 plausibility gate
# (mega_in_top3), used in the cycle and the #39 backfill.
MEGA_ABSTAIN_THRESHOLD = -1.0


def _normalize(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=np.float32)
    if X.ndim == 1:
        X = X[None, :]
    return X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)


class _HeadInput:
    """Feeds every head the width it was trained on, from one 4096-dim input.

    Since 2026-09-26 the four main heads are trained on the 1024-dim Matryoshka
    prefix (memory: scripts/train_distill_heads.py), while signal_type (#110)
    is still a 4096-dim head. `trends.embedding_1024` IS `embedding[:1024]`
    (db.insert_trend), so slicing then L2-normalising here is bit-for-bit what
    the trainer did — callers keep passing the full vector and need no change.
    Mixed widths are normal, so each width is prepared once and reused.
    """

    def __init__(self, X):
        self._raw = np.asarray(X, dtype=np.float32)
        if self._raw.ndim == 1:
            self._raw = self._raw[None, :]
        self._cache: dict[int, np.ndarray] = {}

    @property
    def width(self) -> int:
        return int(self._raw.shape[1])

    @property
    def rows(self) -> int:
        return int(self._raw.shape[0])

    def for_head(self, head) -> np.ndarray:
        d = int(getattr(head, "n_features_in_", 0) or self.width)
        if d > self.width:
            raise ValueError(
                f"head expects {d} dims, got {self.width} — the embedding is "
                "narrower than the head was trained on")
        if d not in self._cache:
            self._cache[d] = _normalize(self._raw if d == self.width
                                        else self._raw[:, :d])
        return self._cache[d]


def _mega_abstain_threshold(meta: dict) -> float:
    """The threshold this mega head was calibrated with, else the 4096 fallback."""
    for value in (meta.get("mega_abstain_threshold"),
                  (meta.get("report") or {}).get("mega_trend", {}).get("abstain_threshold")):
        if isinstance(value, (int, float)):
            return float(value)
    return MEGA_ABSTAIN_THRESHOLD


class DistillClassifier:
    """Loads the persisted heads and classifies embeddings (batch-first)."""

    def __init__(self, vertical, mega, pestel, relevance, meta: dict, signal_type=None):
        self._vertical = vertical
        self._mega = mega
        self._pestel = pestel
        self._relevance = relevance
        self._signal_type = signal_type
        self.meta = meta
        self.mega_abstain_threshold = _mega_abstain_threshold(meta)

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
        st_path = d / SIGNAL_TYPE_HEAD_FILE
        return cls(
            vertical=joblib.load(d / "vertical.joblib"),
            mega=joblib.load(d / "mega.joblib"),
            pestel=joblib.load(d / "pestel.joblib"),
            relevance=joblib.load(rel_path) if rel_path.exists() else None,
            meta=meta,
            signal_type=joblib.load(st_path) if st_path.exists() else None,
        )

    # ------------------------------------------------------------- batch API
    def classify_batch(self, X) -> list[dict]:
        """Classify a batch of embeddings. X: (n, 4096) array-like."""
        inp = _HeadInput(X)
        n = inp.rows

        v_scores = self._vertical.decision_function(inp.for_head(self._vertical))
        if v_scores.ndim == 1:
            v_scores = np.stack([-v_scores, v_scores], axis=1)
        v_classes = np.asarray(self._vertical.classes_)
        v_order = np.argsort(-v_scores, axis=1)
        # softmax over decision scores → a usable confidence proxy
        v_exp = np.exp(v_scores - v_scores.max(axis=1, keepdims=True))
        v_prob = v_exp / v_exp.sum(axis=1, keepdims=True)

        m_scores = self._mega.decision_function(inp.for_head(self._mega))
        if m_scores.ndim == 1:
            m_scores = np.stack([-m_scores, m_scores], axis=1)
        m_classes = np.asarray(self._mega.classes_)
        m_order = np.argsort(-m_scores, axis=1)
        # ABSTAIN: the OvR head always has an argmax, even for signals no
        # mega-trend fits (e.g. a superhero-movie box-office LIFESTYLE trend).
        # A max decision score < 0 means no class claims the point positively —
        # emit mega_trend=None rather than forcing the nearest (which produced
        # "future_of_food_and_agriculture" for off-topic trends). ~22% of
        # published trends fall here (LIFESTYLE 56%). See issue #39.
        m_topscore = m_scores[np.arange(n), m_order[:, 0]]

        p_pred = self._pestel.predict(inp.for_head(self._pestel))

        rel = None
        if self._relevance is not None:
            rel = self._relevance.predict_proba(inp.for_head(self._relevance))[:, 1]

        # #110: press signal type (5 classes). The head only ever speaks for
        # press entries — the caller (_distill_signal_type) keeps the
        # source-type rule for patent/research/funding and applies the
        # confidence floor. Emitted as None when the head is not installed.
        st_label = st_conf = None
        if self._signal_type is not None:
            st_prob = self._signal_type.predict_proba(inp.for_head(self._signal_type))
            st_idx = st_prob.argmax(axis=1)
            st_classes = np.asarray(self._signal_type.classes_)
            st_label = st_classes[st_idx]
            st_conf = st_prob[np.arange(n), st_idx]

        out = []
        for i in range(n):
            top_v = v_order[i, 0]
            out.append({
                "primary_vertical": str(v_classes[top_v]),
                "vertical_confidence": float(v_prob[i, top_v]),
                "vertical_top2": [str(c) for c in v_classes[v_order[i, :2]]],
                "mega_trend": (str(m_classes[m_order[i, 0]])
                               if m_topscore[i] >= self.mega_abstain_threshold else None),
                "mega_top3": [str(c) for c in m_classes[m_order[i, :3]]],
                "pestel": [PESTEL_DIMS[j] for j in range(len(PESTEL_DIMS))
                           if p_pred[i, j] == 1],
                "relevance": float(rel[i]) if rel is not None else None,
                "signal_type": str(st_label[i]) if st_label is not None else None,
                "signal_type_confidence": float(st_conf[i]) if st_conf is not None else None,
            })
        return out

    def classify(self, vec) -> dict:
        """Single-embedding convenience wrapper."""
        return self.classify_batch(vec)[0]

    @property
    def has_relevance_head(self) -> bool:
        return self._relevance is not None

    @property
    def has_signal_type_head(self) -> bool:
        return self._signal_type is not None
