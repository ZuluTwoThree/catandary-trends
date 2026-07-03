#!/usr/bin/env python3
"""Train the production distillation heads (issue #10) and persist them.

Teacher = the LLM labels already stored in `trends` (~528k embedded, labeled
signals). Heads (SGD log-loss on the L2-normalized 4096-dim embeddings):

  vertical.joblib    8-class primary_vertical
  mega.joblib        canonical mega-trend classes
  pestel.joblib      6-dim multi-label (OvR)
  relevance.joblib   binary, calibrated — positives = trends, negatives =
                     filtered_out raw entries (needs scripts/embed_filtered.py
                     to have run; skipped with a warning otherwise)

Postgres-aware: trends.embedding is a pgvector — streamed via a server-side
cursor and parsed incrementally (a naive fetchall would pull ~26 GB of text).
Holdout metrics are written to data/distill_heads_report.{json,md}; models to
models/distill/ (+ meta.json with training provenance).

    python scripts/train_distill_heads.py                    # full training
    python scripts/train_distill_heads.py --sample 60000     # quick iteration
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import SGDClassifier
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from pipeline import db as db_mod
from pipeline.config import DATA_DIR
from pipeline.distill import MODELS_DIR, PESTEL_DIMS

DIM = 4096


# ------------------------------------------------------------------ loaders
def _stream_trends(sample: int) -> tuple[np.ndarray, list[dict]]:
    """Stream labeled trend embeddings into a preallocated matrix.

    Under PG uses a server-side cursor + text parse per row; under SQLite the
    raw blobs. `sample`=0 loads everything.
    """
    t0 = time.time()
    where = "embedding IS NOT NULL AND primary_vertical IS NOT NULL"
    order = f" ORDER BY RANDOM() LIMIT {int(sample)}" if sample else ""
    labels: list[dict] = []

    if db_mod.USE_POSTGRES:
        import psycopg2
        conn = psycopg2.connect(db_mod.DATABASE_URL)
        cur = conn.cursor(name="distill_stream")  # server-side cursor
        cur.itersize = 2000
        cur.execute(f"SELECT id, primary_vertical, mega_trend, pestel::text, "
                    f"embedding::text FROM trends WHERE {where}{order}")
        chunks: list[np.ndarray] = []
        buf: list[np.ndarray] = []
        for rid, vert, mega, pestel, emb in cur:
            vec = np.array(emb.strip("[]").split(","), dtype=np.float32)
            if vec.shape[0] != DIM:
                continue
            buf.append(vec)
            labels.append({"id": rid, "primary_vertical": vert, "mega_trend": mega,
                           "pestel": json.loads(pestel) if pestel else []})
            if len(buf) >= 20_000:
                chunks.append(np.vstack(buf)); buf = []
        if buf:
            chunks.append(np.vstack(buf))
        conn.close()
        X = np.vstack(chunks) if chunks else np.empty((0, DIM), dtype=np.float32)
    else:
        with db_mod.get_connection() as c:
            rows = c.execute(
                f"SELECT id, primary_vertical, mega_trend, pestel, embedding "
                f"FROM trends WHERE {where}{order}").fetchall()
        X = np.empty((len(rows), DIM), dtype=np.float32)
        kept = 0
        for r in rows:
            b = r["embedding"]
            if not isinstance(b, (bytes, bytearray)) or len(b) != DIM * 4:
                continue
            X[kept] = np.frombuffer(b, dtype=np.float32)
            pestel = r["pestel"]
            labels.append({"id": r["id"], "primary_vertical": r["primary_vertical"],
                           "mega_trend": r["mega_trend"],
                           "pestel": json.loads(pestel) if isinstance(pestel, str) and pestel
                           else (pestel or [])})
            kept += 1
        X = X[:kept]

    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    print(f"trends: {X.shape[0]} × {DIM} loaded in {time.time()-t0:.0f}s")
    return X, labels


def _load_filtered(max_n: int) -> np.ndarray:
    """Negatives for the relevance head: filtered_out embedding blobs (BYTEA).

    Only TRUE-irrelevance negatives — exclude entries filtered for reasons
    orthogonal to relevance (duplicates can be perfectly relevant; errors/too-old
    aren't judgments of relevance). Keeps not_relevant + off-foresight-noise
    (~92% of filtered_out); drops the ~8% duplicate/error/too_old contamination."""
    t0 = time.time()
    excl = ("(filter_reason IS NULL OR (filter_reason NOT LIKE '%duplicate%' "
            "AND filter_reason NOT LIKE '%error%' AND filter_reason NOT LIKE 'too_old%' "
            "AND filter_reason NOT LIKE '%advertorial%' AND filter_reason NOT LIKE '%sponsored%'))")
    with db_mod.get_connection() as c:
        rows = c.execute(
            "SELECT embedding_blob FROM raw_entries "
            f"WHERE filtered_out = TRUE AND embedding_blob IS NOT NULL AND {excl} "
            + (f"LIMIT {int(max_n)}" if max_n else "")).fetchall()
    X = np.empty((len(rows), DIM), dtype=np.float32)
    kept = 0
    for r in rows:
        b = r["embedding_blob"]
        if isinstance(b, memoryview):
            b = b.tobytes()
        if not isinstance(b, (bytes, bytearray)) or len(b) != DIM * 4:
            continue
        X[kept] = np.frombuffer(b, dtype=np.float32)
        kept += 1
    X = X[:kept]
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    print(f"filtered_out negatives: {X.shape[0]} loaded in {time.time()-t0:.0f}s")
    return X


# ------------------------------------------------------------------ training
def _head(seed: int = 42) -> SGDClassifier:
    return SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=25, tol=1e-4,
                         random_state=seed)


def main() -> int:
    ap = argparse.ArgumentParser(description="Train + persist distillation heads (#10)")
    ap.add_argument("--sample", type=int, default=0, help="row cap (0 = all labeled trends)")
    ap.add_argument("--holdout", type=float, default=0.10)
    ap.add_argument("--neg-cap", type=int, default=0, help="cap on relevance negatives (0 = all)")
    ap.add_argument("--skip-relevance", action="store_true")
    ap.add_argument("--relevance-only", action="store_true",
                    help="retrain ONLY the relevance head, keep the other 3 heads")
    args = ap.parse_args()

    t_all = time.time()
    X, rows = _stream_trends(args.sample)
    n = len(rows)
    if n < 1000:
        print("too few labeled trends"); return 1
    rng = np.random.default_rng(42)
    idx = rng.permutation(n)
    n_te = int(n * args.holdout)
    te, tr = idx[:n_te], idx[n_te:]

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    # --relevance-only keeps the existing report and just refreshes the relevance key
    existing = {}
    rep_path = Path(DATA_DIR, "distill_heads_report.json")
    if args.relevance_only and rep_path.exists():
        existing = json.loads(rep_path.read_text())
    report: dict = existing or {
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_train": int(n - n_te), "n_holdout": int(n_te), "dim": DIM,
        "backend": "postgres" if db_mod.USE_POSTGRES else "sqlite",
    }

    if not args.relevance_only:
        # --- vertical ---
        t0 = time.time()
        yv = np.asarray([r["primary_vertical"] for r in rows])
        clf_v = _head().fit(X[tr], yv[tr])
        report["vertical"] = {
            "top1_agreement": round(float((clf_v.predict(X[te]) == yv[te]).mean()), 4),
            "classes": len(clf_v.classes_), "train_s": round(time.time() - t0, 1)}
        joblib.dump(clf_v, MODELS_DIR / "vertical.joblib")
        print("vertical:", report["vertical"])

    if not args.relevance_only:
        # --- mega-trend (labeled rows only) ---
        t0 = time.time()
        m_mask = np.asarray([bool(r["mega_trend"]) for r in rows])
        ym = np.asarray([r["mega_trend"] or "" for r in rows])
        m_tr = tr[m_mask[tr]]; m_te = te[m_mask[te]]
        clf_m = _head().fit(X[m_tr], ym[m_tr])
        scores = clf_m.decision_function(X[m_te])
        order = np.argsort(-scores, axis=1)
        classes = np.asarray(clf_m.classes_)
        top1 = float((classes[order[:, 0]] == ym[m_te]).mean())
        top3 = float(np.mean([ym[m_te][i] in classes[order[i, :3]] for i in range(len(m_te))]))
        report["mega_trend"] = {"top1_agreement": round(top1, 4),
                                "top3_agreement": round(top3, 4),
                                "classes": len(classes), "train_s": round(time.time() - t0, 1)}
        joblib.dump(clf_m, MODELS_DIR / "mega.joblib")
        print("mega:", report["mega_trend"])

        # --- pestel ---
        t0 = time.time()
        mlb = MultiLabelBinarizer(classes=PESTEL_DIMS)
        Y = mlb.fit_transform([r["pestel"] for r in rows])
        clf_p = OneVsRestClassifier(_head(), n_jobs=-1).fit(X[tr], Y[tr])
        P = clf_p.predict(X[te])
        tp = float(np.logical_and(P == 1, Y[te] == 1).sum())
        fp = float(np.logical_and(P == 1, Y[te] == 0).sum())
        fn = float(np.logical_and(P == 0, Y[te] == 1).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        report["pestel"] = {
            "micro_f1": round(2 * prec * rec / (prec + rec) if prec + rec else 0.0, 4),
            "micro_precision": round(prec, 4), "micro_recall": round(rec, 4),
            "train_s": round(time.time() - t0, 1)}
        joblib.dump(clf_p, MODELS_DIR / "pestel.joblib")
        print("pestel:", report["pestel"])

    # --- relevance (calibrated; needs embed_filtered negatives) ---
    if not args.skip_relevance:
        Xneg = _load_filtered(args.neg_cap)
        if Xneg.shape[0] < 5000:
            print(f"relevance head SKIPPED — only {Xneg.shape[0]} negatives "
                  "(run scripts/embed_filtered.py first)")
            report["relevance"] = {"skipped": True, "negatives": int(Xneg.shape[0])}
        else:
            t0 = time.time()
            # balance: cap positives at ~2× negatives to bound memory
            pos_cap = min(n, 2 * Xneg.shape[0], 300_000)
            pos_idx = rng.choice(n, pos_cap, replace=False)
            Xrel = np.vstack([X[pos_idx], Xneg])
            yrel = np.concatenate([np.ones(pos_cap, dtype=np.int8),
                                   np.zeros(Xneg.shape[0], dtype=np.int8)])
            ridx = rng.permutation(len(yrel))
            r_te = ridx[: int(0.1 * len(ridx))]; r_tr = ridx[int(0.1 * len(ridx)):]
            base = _head()
            clf_r = CalibratedClassifierCV(base, method="sigmoid", cv=3)
            clf_r.fit(Xrel[r_tr], yrel[r_tr])
            prob = clf_r.predict_proba(Xrel[r_te])[:, 1]
            pred = (prob >= 0.5).astype(np.int8)
            yt = yrel[r_te]
            tp = float(((pred == 1) & (yt == 1)).sum()); fp = float(((pred == 1) & (yt == 0)).sum())
            fn = float(((pred == 0) & (yt == 1)).sum())
            report["relevance"] = {
                "precision": round(tp / (tp + fp) if tp + fp else 0.0, 4),
                "recall": round(tp / (tp + fn) if tp + fn else 0.0, 4),
                "accuracy": round(float((pred == yt).mean()), 4),
                "positives": int(pos_cap), "negatives": int(Xneg.shape[0]),
                "train_s": round(time.time() - t0, 1)}
            joblib.dump(clf_r, MODELS_DIR / "relevance.joblib")
            print("relevance:", report["relevance"])

    meta = {"trained": report["generated"], "n_train": report["n_train"],
            "heads": [p.name for p in MODELS_DIR.glob("*.joblib")],
            "teacher": "8B LLM pipeline labels (trends table)",
            "report": report}
    (MODELS_DIR / "meta.json").write_text(json.dumps(meta, indent=2))

    report["total_s"] = round(time.time() - t_all, 1)
    Path(DATA_DIR, "distill_heads_report.json").write_text(json.dumps(report, indent=2))
    md = ["# Distillation Heads — Training Report",
          f"\nGeneriert: {report['generated']} · Train {report['n_train']:,} · "
          f"Holdout {report['n_holdout']:,} · Backend {report['backend']} · "
          f"{report['total_s']}s\n",
          "| Head | Metrik | Wert |", "|---|---|---|",
          f"| Vertical | Top-1 | **{report['vertical']['top1_agreement']*100:.1f}%** |",
          f"| Mega-Trend | Top-1 / Top-3 | **{report['mega_trend']['top1_agreement']*100:.1f}% / "
          f"{report['mega_trend']['top3_agreement']*100:.1f}%** |",
          f"| PESTEL | micro-F1 | **{report['pestel']['micro_f1']*100:.1f}%** |"]
    if isinstance(report.get("relevance"), dict) and not report["relevance"].get("skipped"):
        r = report["relevance"]
        md.append(f"| Relevanz | P / R / Acc | **{r['precision']*100:.1f}% / "
                  f"{r['recall']*100:.1f}% / {r['accuracy']*100:.1f}%** |")
    md.append("\nModelle: `models/distill/` · Rohdaten: `data/distill_heads_report.json`")
    Path(DATA_DIR, "distill_heads_report.md").write_text("\n".join(md))
    print(f"\nDone in {report['total_s']}s — models in {MODELS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
