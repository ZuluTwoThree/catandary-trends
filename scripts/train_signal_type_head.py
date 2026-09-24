#!/usr/bin/env python3
"""Train the fifth distill head: trend_signal_type for PRESS signals (#110).

Since the hybrid classification (#41, 2026-07-14) the signal type is derived
from the source type alone — every trade-media / press-wire / brand entry
becomes `market_shift`; product_launch, regulation, partnership and
consumer_behavior have not been assigned since. The four existing heads do
not emit a signal type. This script trains ONE additional head on the labels
the LLM path assigned before that date and leaves the other four untouched.

  Teacher   trends rows created before 2026-07-14 whose source is press
            (trade_media / press_wire / brand, no patent number) and whose
            label is one of the five press classes.
  Model     SGD log-loss on the L2-normalised 4096-dim embedding — same
            recipe as scripts/train_distill_heads.py. Two variants are
            trained (plain and class_weight='balanced'); the report shows
            both, the one with the higher macro-F1 on the holdout is
            persisted as models/distill/signal_type.joblib.
  Not here  patent / research / funding — the deterministic source-type rule
            in llm_processor._distill_signal_type stays authoritative there.

    python scripts/train_signal_type_head.py                 # full run
    python scripts/train_signal_type_head.py --sample 100000 # quick iteration
    python scripts/train_signal_type_head.py --no-write      # metrics only

Writes data/signal_type_head_report.{json,md}. `--eval-recent` (default on)
additionally streams the press rows created since 2026-07-14 — the ones the
rule labelled market_shift — and reports what the head would assign, with
title samples per class, so the owner can judge face validity.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import joblib
import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import classification_report, f1_score

from pipeline import db as db_mod
from pipeline.config import DATA_DIR
from pipeline.distill import MODELS_DIR, SIGNAL_TYPE_HEAD_FILE

DIM = 4096
CUTOVER = "2026-07-14"
PRESS_CLASSES = ("market_shift", "product_launch", "regulation",
                 "partnership", "consumer_behavior")
PRESS_SOURCE_TYPES = ("trade_media", "press_wire", "brand")

_PRESS_WHERE = (
    "t.embedding IS NOT NULL AND r.pub_number IS NULL "
    "AND COALESCE(s.source_type, 'trade_media') IN ('trade_media','press_wire','brand')"
)


def _stream(sql: str, params: tuple, sample: int) -> tuple[np.ndarray, list[dict]]:
    """Server-side cursor over trends; parses pgvector text incrementally."""
    if not db_mod.USE_POSTGRES:
        raise SystemExit("this trainer needs the Postgres corpus (pgvector text stream)")
    import psycopg2
    t0 = time.time()
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor(name="signal_type_stream")
    cur.itersize = 2000
    order = f" ORDER BY RANDOM() LIMIT {int(sample)}" if sample else ""
    cur.execute(sql + order, params)
    chunks: list[np.ndarray] = []
    buf: list[np.ndarray] = []
    meta: list[dict] = []
    for row in cur:
        emb = row[-1]
        vec = np.array(emb.strip("[]").split(","), dtype=np.float32)
        if vec.shape[0] != DIM:
            continue
        buf.append(vec)
        meta.append(dict(zip(("id", "label", "title", "status"), row[:-1])))
        if len(buf) >= 20_000:
            chunks.append(np.vstack(buf)); buf = []
    if buf:
        chunks.append(np.vstack(buf))
    conn.close()
    X = np.vstack(chunks) if chunks else np.empty((0, DIM), dtype=np.float32)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    print(f"loaded {X.shape[0]} × {DIM} in {time.time() - t0:.0f}s", flush=True)
    return X, meta


def load_teacher(sample: int) -> tuple[np.ndarray, list[dict]]:
    sql = (
        "SELECT t.id, t.trend_signal_type, t.title_en, t.status, t.embedding::text "
        "FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id "
        "LEFT JOIN sources s ON s.id = r.source_id "
        f"WHERE t.created_at < %s AND {_PRESS_WHERE} AND t.trend_signal_type = ANY(%s)"
    )
    return _stream(sql, (CUTOVER, list(PRESS_CLASSES)), sample)


def load_recent(sample: int) -> tuple[np.ndarray, list[dict]]:
    sql = (
        "SELECT t.id, t.trend_signal_type, t.title_en, t.status, t.embedding::text "
        "FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id "
        "LEFT JOIN sources s ON s.id = r.source_id "
        f"WHERE t.created_at >= %s AND {_PRESS_WHERE} AND t.trend_signal_type = 'market_shift'"
    )
    return _stream(sql, (CUTOVER,), sample)


def _fit(X: np.ndarray, y: np.ndarray, balanced: bool) -> tuple[SGDClassifier, float]:
    t0 = time.time()
    clf = SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=30, tol=1e-4,
                        class_weight="balanced" if balanced else None,
                        n_jobs=-1, random_state=110)
    clf.fit(X, y)
    return clf, time.time() - t0


def _confidence(clf: SGDClassifier, X: np.ndarray) -> np.ndarray:
    p = clf.predict_proba(X)
    return p.max(axis=1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Train the signal-type distill head (#110)")
    ap.add_argument("--sample", type=int, default=0, help="teacher row cap (0 = all)")
    ap.add_argument("--holdout", type=float, default=0.10)
    ap.add_argument("--no-write", action="store_true", help="metrics only, persist nothing")
    ap.add_argument("--no-eval-recent", action="store_true",
                    help="skip the pass over the press rows created since the cutover")
    ap.add_argument("--recent-sample", type=int, default=0)
    args = ap.parse_args()

    t_all = time.time()
    X, meta = load_teacher(args.sample)
    y = np.asarray([m["label"] for m in meta])
    if X.shape[0] < 1000:
        raise SystemExit(f"only {X.shape[0]} teacher rows — nothing to train on")
    counts = Counter(y.tolist())
    print("teacher classes:", dict(counts.most_common()), flush=True)

    rng = np.random.default_rng(110)
    idx = rng.permutation(X.shape[0])
    n_hold = int(X.shape[0] * args.holdout)
    hold, train = idx[:n_hold], idx[n_hold:]

    report: dict = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "issue": 110, "cutover": CUTOVER, "dim": DIM,
        "n_train": int(len(train)), "n_holdout": int(n_hold),
        "teacher_classes": dict(counts.most_common()),
        "variants": {},
    }
    models: dict[str, SGDClassifier] = {}
    for name, balanced in (("plain", False), ("balanced", True)):
        clf, secs = _fit(X[train], y[train], balanced)
        pred = clf.predict(X[hold])
        macro = f1_score(y[hold], pred, average="macro")
        acc = float((pred == y[hold]).mean())
        rep = classification_report(y[hold], pred, output_dict=True, zero_division=0)
        per_class = {c: {"precision": round(rep[c]["precision"], 4),
                         "recall": round(rep[c]["recall"], 4),
                         "f1": round(rep[c]["f1-score"], 4),
                         "n_holdout": int(rep[c]["support"])}
                     for c in PRESS_CLASSES if c in rep}
        report["variants"][name] = {"accuracy": round(acc, 4), "macro_f1": round(macro, 4),
                                    "train_s": round(secs, 1), "per_class": per_class}
        models[name] = clf
        print(f"{name}: acc={acc:.4f} macro_f1={macro:.4f} ({secs:.0f}s)", flush=True)
        for c, v in per_class.items():
            print(f"   {c:18s} p={v['precision']:.3f} r={v['recall']:.3f} f1={v['f1']:.3f} n={v['n_holdout']}")

    chosen = max(report["variants"], key=lambda k: report["variants"][k]["macro_f1"])
    report["chosen"] = chosen
    clf = models[chosen]
    print(f"chosen variant: {chosen}", flush=True)

    # confidence profile on the holdout (softmax max) — what a gate could use
    conf = _confidence(clf, X[hold])
    pred = clf.predict(X[hold])
    correct = pred == y[hold]
    bands = {}
    for lo in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9):
        m = conf >= lo
        bands[str(lo)] = {"share": round(float(m.mean()), 4),
                          "accuracy": round(float(correct[m].mean()), 4) if m.any() else None}
    report["holdout_confidence_bands"] = bands

    if not args.no_eval_recent:
        Xr, mr = load_recent(args.recent_sample)
        if Xr.shape[0]:
            pr = clf.predict(Xr)
            cr = _confidence(clf, Xr)
            dist = Counter(pr.tolist())
            by_status: dict[str, Counter] = defaultdict(Counter)
            for m, p in zip(mr, pr):
                by_status[m["status"] or "?"][p] += 1
            samples: dict[str, list] = defaultdict(list)
            order = np.argsort(-cr)
            for i in order:
                lab = pr[i]
                if len(samples[lab]) < 12 and mr[i]["status"] == "published":
                    samples[lab].append({"id": mr[i]["id"], "title": mr[i]["title"],
                                         "confidence": round(float(cr[i]), 3)})
            report["recent"] = {
                "n": int(Xr.shape[0]),
                "would_assign": dict(dist.most_common()),
                "would_assign_share": {k: round(v / Xr.shape[0], 4) for k, v in dist.most_common()},
                "by_status": {s: dict(c.most_common()) for s, c in by_status.items()},
                "confidence_ge_0_7_share": round(float((cr >= 0.7).mean()), 4),
                "samples_published_top_confidence": dict(samples),
            }
            print("recent press rows since cutover:", Xr.shape[0], dict(dist.most_common()), flush=True)

    report["total_s"] = round(time.time() - t_all, 1)

    rep_json = DATA_DIR / "signal_type_head_report.json"
    rep_json.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    _write_md(report, DATA_DIR / "signal_type_head_report.md")
    print(f"report → {rep_json}")

    if args.no_write:
        print("--no-write: head not persisted")
        return 0
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out = MODELS_DIR / SIGNAL_TYPE_HEAD_FILE
    joblib.dump(clf, out)
    side = MODELS_DIR / "signal_type_meta.json"   # own meta — meta.json belongs to the 4 heads
    side.write_text(json.dumps({
        "trained": report["generated"], "issue": 110, "variant": chosen,
        "classes": list(clf.classes_), "n_train": report["n_train"],
        "teacher": f"LLM-path labels on press rows created before {CUTOVER}",
        "holdout": report["variants"][chosen],
    }, indent=2))
    print(f"head → {out}")
    return 0


def _write_md(rep: dict, path: Path) -> None:
    L = [f"# Signal-type distill head — report ({rep['generated'][:16]}Z)", "",
         f"Teacher: press rows before {rep['cutover']}, train {rep['n_train']:,} / holdout {rep['n_holdout']:,}.", "",
         "| class | teacher n |", "|---|---|"]
    L += [f"| {c} | {n:,} |" for c, n in rep["teacher_classes"].items()]
    for name, v in rep["variants"].items():
        L += ["", f"## variant `{name}` — accuracy {v['accuracy']}, macro-F1 {v['macro_f1']} ({v['train_s']} s)",
              "", "| class | precision | recall | F1 | n |", "|---|---|---|---|---|"]
        L += [f"| {c} | {p['precision']} | {p['recall']} | {p['f1']} | {p['n_holdout']:,} |"
              for c, p in v["per_class"].items()]
    L += ["", f"Chosen: `{rep['chosen']}`.", "", "## Holdout accuracy by confidence band", "",
          "| conf ≥ | share | accuracy |", "|---|---|---|"]
    L += [f"| {k} | {v['share']} | {v['accuracy']} |" for k, v in rep["holdout_confidence_bands"].items()]
    if "recent" in rep:
        r = rep["recent"]
        L += ["", f"## Press rows since cutover (n = {r['n']:,}, all labelled market_shift by the rule)", "",
              "| head would assign | n | share |", "|---|---|---|"]
        L += [f"| {k} | {v:,} | {r['would_assign_share'][k]} |" for k, v in r["would_assign"].items()]
        L += ["", f"Share with confidence ≥ 0.7: {r['confidence_ge_0_7_share']}", ""]
        for lab, items in r["samples_published_top_confidence"].items():
            L += [f"### {lab} — published, highest confidence", ""]
            L += [f"- #{it['id']} ({it['confidence']}) {it['title']}" for it in items]
            L += [""]
    path.write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
