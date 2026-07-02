#!/usr/bin/env python3
"""Embedding-distillation prototype (issue #10) — CPU-only, read-only.

Validates the deep-backfill thesis: cheap linear heads on the existing
4096-dim signal embeddings can replace the per-item LLM calls for
classification. Trains on the LLM-assigned labels already stored in `trends`
and reports holdout agreement against the issue-#10 targets
(vertical >= ~90 % top-1, mega-trend top-1/top-3, PESTEL micro-F1).

Deliberately NOT covered here (documented gap): the relevance head —
filtered-out entries carry no embeddings (filtering happens before Stage 5),
so its training data is GPU-gated.

Read-only on the DB (safe while the GPU classification job writes), CPU-only.

    python scripts/distill_prototype.py                  # 210k sample
    python scripts/distill_prototype.py --sample 60000   # quicker smoke run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from pipeline.config import DATA_DIR
from pipeline.db import get_connection

PESTEL_DIMS = ["P", "E", "S", "T", "En", "L"]


def load_sample(n: int) -> tuple[np.ndarray, list[dict]]:
    """Random sample of embedded trends with their LLM labels (read-only)."""
    t0 = time.time()
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT id, primary_vertical, mega_trend, pestel, embedding "
            "FROM trends WHERE embedding IS NOT NULL AND primary_vertical IS NOT NULL "
            "ORDER BY RANDOM() LIMIT ?", (n,)).fetchall()]
    keep = [r for r in rows
            if isinstance(r["embedding"], (bytes, bytearray)) and len(r["embedding"]) >= 4]
    dim = len(keep[0]["embedding"]) // 4
    X = np.empty((len(keep), dim), dtype=np.float32)
    for i, r in enumerate(keep):
        X[i] = np.frombuffer(r["embedding"], dtype=np.float32)
        r["embedding"] = None
        try:
            r["pestel"] = json.loads(r["pestel"]) if r["pestel"] else []
        except Exception:
            r["pestel"] = []
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    print(f"loaded {len(keep)} × {dim} in {time.time()-t0:.0f}s")
    return X, keep


def _head(seed: int = 42) -> SGDClassifier:
    # log_loss SGD: fast on 4096-dim float32 at 100k+ rows, gives class scores
    # for top-k agreement without calibration.
    return SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=15, tol=1e-3,
                         random_state=seed)


def eval_vertical(Xtr, Xte, ytr, yte) -> dict:
    t0 = time.time()
    clf = _head().fit(Xtr, ytr)
    acc = float((clf.predict(Xte) == yte).mean())
    return {"top1_agreement": round(acc, 4), "n_train": len(ytr),
            "n_test": len(yte), "train_s": round(time.time() - t0, 1),
            "classes": len(clf.classes_)}


def eval_mega(Xtr, Xte, ytr, yte) -> dict:
    t0 = time.time()
    clf = _head().fit(Xtr, ytr)
    scores = clf.decision_function(Xte)
    if scores.ndim == 1:  # binary edge case
        scores = np.stack([-scores, scores], axis=1)
    order = np.argsort(-scores, axis=1)
    classes = np.asarray(clf.classes_)
    top1 = classes[order[:, 0]]
    yte_arr = np.asarray(yte)
    top1_acc = float((top1 == yte_arr).mean())
    top3 = classes[order[:, :3]]
    top3_acc = float(np.mean([yte_arr[i] in top3[i] for i in range(len(yte_arr))]))
    return {"top1_agreement": round(top1_acc, 4), "top3_agreement": round(top3_acc, 4),
            "n_train": len(ytr), "n_test": len(yte),
            "train_s": round(time.time() - t0, 1), "classes": len(classes)}


def eval_pestel(Xtr, Xte, ytr_sets, yte_sets) -> dict:
    t0 = time.time()
    mlb = MultiLabelBinarizer(classes=PESTEL_DIMS)
    Ytr, Yte = mlb.fit_transform(ytr_sets), mlb.transform(yte_sets)
    clf = OneVsRestClassifier(_head(), n_jobs=-1).fit(Xtr, Ytr)
    P = clf.predict(Xte)
    tp = float(np.logical_and(P == 1, Yte == 1).sum())
    fp = float(np.logical_and(P == 1, Yte == 0).sum())
    fn = float(np.logical_and(P == 0, Yte == 1).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    per_label = {}
    for j, lab in enumerate(PESTEL_DIMS):
        agree = float((P[:, j] == Yte[:, j]).mean())
        per_label[lab] = round(agree, 4)
    return {"micro_f1": round(f1, 4), "micro_precision": round(prec, 4),
            "micro_recall": round(rec, 4), "exact_match": round(float((P == Yte).all(axis=1).mean()), 4),
            "per_label_agreement": per_label, "train_s": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Embedding-distillation prototype (issue #10)")
    ap.add_argument("--sample", type=int, default=210_000, help="total rows to sample")
    ap.add_argument("--holdout", type=float, default=0.15, help="holdout fraction")
    args = ap.parse_args()

    t0 = time.time()
    X, rows = load_sample(args.sample)
    n = len(rows)
    rng = np.random.default_rng(42)
    idx = rng.permutation(n)
    n_te = int(n * args.holdout)
    te, tr = idx[:n_te], idx[n_te:]

    report: dict = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "sample": n, "holdout": n_te, "dim": int(X.shape[1]),
        "label_distribution": {
            "vertical": dict(Counter(r["primary_vertical"] for r in rows).most_common()),
            "mega_trend_null_share": round(
                sum(1 for r in rows if not r["mega_trend"]) / n, 4),
        },
        "targets_issue_10": {"vertical_top1": ">=0.90", "mega_trend": "top-1/top-3 reported",
                             "relevance_head": "GPU-gated (no embeddings for filtered_out) — open"},
    }

    # --- Vertical head (8 classes) ---
    yv = np.asarray([r["primary_vertical"] for r in rows])
    report["vertical"] = eval_vertical(X[tr], X[te], yv[tr], yv[te])
    print("vertical:", report["vertical"])

    # --- Mega-trend head (canonical classes; rows with a label only) ---
    has_mt = np.asarray([bool(r["mega_trend"]) for r in rows])
    tr_mt = tr[has_mt[tr]]
    te_mt = te[has_mt[te]]
    ym = np.asarray([r["mega_trend"] or "" for r in rows])
    report["mega_trend"] = eval_mega(X[tr_mt], X[te_mt], ym[tr_mt], ym[te_mt])
    print("mega_trend:", report["mega_trend"])

    # --- PESTEL multi-label head ---
    yp = [set(r["pestel"]) & set(PESTEL_DIMS) for r in rows]
    report["pestel"] = eval_pestel(X[tr], X[te], [yp[i] for i in tr], [yp[i] for i in te])
    print("pestel:", report["pestel"])

    report["total_s"] = round(time.time() - t0, 1)

    out_json = DATA_DIR / "distill_prototype_report.json"
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    v, m, p = report["vertical"], report["mega_trend"], report["pestel"]
    md = f"""# Distillation-Prototyp — Holdout-Report (Issue #10)

Generiert: {report['generated']} · Sample {n:,} (Holdout {n_te:,}) · dim {X.shape[1]} · Laufzeit {report['total_s']}s (CPU)

| Head | Metrik | Wert | Ziel (#10) |
|---|---|---|---|
| Vertical (8 Kl.) | Top-1-Agreement | **{v['top1_agreement']:.1%}** | ≥ ~90 % |
| Mega-Trend ({m['classes']} Kl.) | Top-1 / Top-3 | **{m['top1_agreement']:.1%} / {m['top3_agreement']:.1%}** | berichten |
| PESTEL (Multi-Label) | micro-F1 / Exact | **{p['micro_f1']:.1%} / {p['exact_match']:.1%}** | berichten |

Mega-Trend-NULL-Anteil im Sample: {report['label_distribution']['mega_trend_null_share']:.1%} (Head nur auf gelabelten Zeilen trainiert/getestet).

**Offen (GPU-gated):** Relevanz-Head — filtered_out-Einträge haben keine Embeddings (Filterung vor Stage 5); braucht einen einmaligen Embedding-Lauf über eine filtered_out-Stichprobe.

Rohdaten: `data/distill_prototype_report.json`
"""
    out_md = DATA_DIR / "distill_prototype_report.md"
    out_md.write_text(md, encoding="utf-8")
    print(f"\nreport → {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
