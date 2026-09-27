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

Memory (the reason for --dim, 2026-09-26): the Sunday retrain via
scripts/discovery_loop.py was OOM-killed on three consecutive Sundays (rc=-9,
56.6 GB RSS) and nobody noticed — the productive heads are from 2026-08-07.
Two causes, both fixed here:

  * the loader collected per-chunk arrays and ended with one np.vstack, which
    holds the whole matrix TWICE (1.83M x 4096 x 4 B = 29.9 GB each). It now
    counts the rows first and streams them into a preallocated matrix, keyset-
    paginated like pipeline.foresight (no server-side cursor).
  * 4096 dimensions are the matrix; --dim 1024 trains on the Matryoshka prefix
    (trends.embedding_1024 IS trends.embedding[:1024], see db.insert_trend), so
    the matrix is 7.5 GB and each sklearn train/holdout copy 6.7 GB instead of
    26.9. This is the default. Inference needs no change: DistillClassifier
    slices every incoming vector to the head own n_features_in_.

A preflight refuses to start when the estimate does not fit in MemAvailable —
a legible error in the log beats a SIGKILL nobody reads.

Holdout metrics are written to data/distill_heads_report.{json,md}; models to
models/distill/ (+ meta.json with training provenance, including the dim).

    python scripts/train_distill_heads.py                    # full, 1024-dim
    python scripts/train_distill_heads.py --dim 4096         # the old matrix
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

DIM_FULL = 4096          # trends.embedding
DIM_PREFIX = 1024        # trends.embedding_1024 = embedding[:1024] (Matryoshka)
DIM = DIM_FULL           # kept for callers that import it
PAGE = 20_000            # keyset page size


def _emb_column(dim: int) -> str:
    """The column that already holds this prefix.

    Under Postgres the prefix has its own column (embedding_1024), which also
    means a quarter of the text to transfer and parse. SQLite (tests) has only
    the full blob, so it is sliced while streaming.
    """
    if dim >= DIM_FULL or not db_mod.USE_POSTGRES:
        return "embedding"
    return "embedding_1024"


def _peak_rss_gb() -> float:
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024


def _mem_available_gb() -> float:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return 0.0


def _preflight(n: int, dim: int, label: str) -> None:
    """Refuse to start when the matrix plus one sklearn copy cannot fit.

    sklearn gets X[tr] / X[te] as fancy-index COPIES, so the peak is the matrix
    plus ~90 % of it. 56.6 GB on 2026-09-20 was exactly that arithmetic at
    4096 dim; a SIGKILL in a Sunday cron log is the worst way to learn it.

    The factor is MEASURED, not derived: loading peaks higher than the matrix
    itself (one Python string plus one temporary array per row), 2.2x the matrix
    at 1024 dim and 2.5x at 4096 in the runs of 2026-09-26, which is more than
    the 1.9x of the later fit copy. 2.5 is therefore the honest bound; being
    wrong in this direction only costs a legible refusal.
    """
    need = n * dim * 4 * 2.5 / 1024 ** 3
    avail = _mem_available_gb()
    print(f"preflight: {n:,} x {dim} -> ~{need:.1f} GB peak, "
          f"{avail:.1f} GB available ({label})", flush=True)
    if avail and need > 0.8 * avail:
        raise MemoryError(
            f"{need:.1f} GB estimated peak vs {avail:.1f} GB available — "
            f"use --dim {DIM_PREFIX} or --sample N instead of being OOM-killed")


# ------------------------------------------------------------------ loaders
def _stream_trends(sample: int, dim: int) -> tuple[np.ndarray, list[dict]]:
    """Load labeled trend embeddings into ONE preallocated matrix.

    Counted first, then keyset-paginated (pipeline.foresight pattern) so no
    chunk list and no closing np.vstack — that vstack held the matrix twice.
    `sample`>0 takes a deterministic id-modulo slice, not ORDER BY RANDOM():
    reproducible, cheap, and identical across two runs, which is what an A/B
    over the dimension needs.
    """
    t0 = time.time()
    col = _emb_column(dim)
    where = f"{col} IS NOT NULL AND primary_vertical IS NOT NULL"
    params: list = []

    with db_mod.get_connection() as c:
        total = c.execute(f"SELECT COUNT(*) AS n FROM trends WHERE {where}").fetchone()["n"]
    step = 0
    if sample and total > sample:
        step = total // int(sample) + 1
        # A literal % would be read as a psycopg2 placeholder (see _load_filtered),
        # and SQLite has no mod() unless compiled with the math functions.
        where += (" AND mod(id, ?) = 0" if db_mod.USE_POSTGRES else " AND (id % ?) = 0")
        params.append(step)
        with db_mod.get_connection() as c:
            total = c.execute(f"SELECT COUNT(*) AS n FROM trends WHERE {where}",
                              tuple(params)).fetchone()["n"]
    _preflight(total, dim, f"sample step {step}" if step else "all labeled trends")

    X = np.empty((total, dim), dtype=np.float32)
    labels: list[dict] = []
    emb_sel = f"{col}::text" if db_mod.USE_POSTGRES else col
    pestel_sel = "pestel::text AS pestel" if db_mod.USE_POSTGRES else "pestel"
    kept, last_id = 0, 0
    with db_mod.get_connection() as c:
        while kept < total:
            rows = c.execute(
                f"SELECT id, primary_vertical, mega_trend, {pestel_sel}, "
                f"{emb_sel} AS embedding FROM trends WHERE {where} AND id > ? "
                f"ORDER BY id LIMIT ?", (*params, last_id, PAGE)).fetchall()
            if not rows:
                break
            for r in rows:
                last_id = r["id"]
                raw = r["embedding"]
                if isinstance(raw, str):
                    vec = np.array(raw.strip("[]").split(","), dtype=np.float32)
                else:
                    b = raw.tobytes() if isinstance(raw, memoryview) else raw
                    if not isinstance(b, (bytes, bytearray)) or len(b) < dim * 4:
                        continue
                    vec = np.frombuffer(b, dtype=np.float32, count=dim)
                if vec.shape[0] < dim:
                    continue
                X[kept] = vec[:dim]
                pestel = r["pestel"]
                labels.append({"id": r["id"], "primary_vertical": r["primary_vertical"],
                               "mega_trend": r["mega_trend"],
                               "pestel": json.loads(pestel) if isinstance(pestel, str) and pestel
                               else (pestel or [])})
                kept += 1
                if kept == total:
                    break
            del rows
    X = X[:kept]

    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    print(f"trends: {X.shape[0]} x {dim} loaded in {time.time()-t0:.0f}s "
          f"({X.nbytes / 1024**3:.1f} GB, peak RSS {_peak_rss_gb():.1f} GB)", flush=True)
    return X, labels


def _load_filtered(max_n: int, dim: int) -> np.ndarray:
    """Negatives for the relevance head: filtered_out embedding blobs (BYTEA).

    Only TRUE-irrelevance negatives — exclude entries filtered for reasons
    orthogonal to relevance (duplicates can be perfectly relevant; errors/too-old
    aren't judgments of relevance). Keeps not_relevant + off-foresight-noise
    (~92% of filtered_out); drops the ~8% duplicate/error/too_old contamination.

    Keyset-paginated like _stream_trends: the old single fetchall held every
    16 KB blob at once (322k negatives = 5.3 GB of bytes on top of the matrix).
    """
    t0 = time.time()
    # Patterns as bound params — literal % in the SQL would be read as psycopg2
    # placeholders (IndexError) under the ?→%s wrapper.
    pats = ["%duplicate%", "%error%", "too_old%", "%advertorial%", "%sponsored%"]
    excl = "(filter_reason IS NULL OR (" + " AND ".join(
        ["filter_reason NOT LIKE ?"] * len(pats)) + "))"
    where = f"filtered_out = TRUE AND embedding_blob IS NOT NULL AND {excl}"
    with db_mod.get_connection() as c:
        total = c.execute(f"SELECT COUNT(*) AS n FROM raw_entries WHERE {where}",
                          tuple(pats)).fetchone()["n"]
    if max_n:
        total = min(total, int(max_n))
    X = np.empty((total, dim), dtype=np.float32)
    kept, last_id = 0, 0
    with db_mod.get_connection() as c:
        while kept < total:
            rows = c.execute(
                f"SELECT id, embedding_blob FROM raw_entries WHERE {where} AND id > ? "
                f"ORDER BY id LIMIT ?", (*pats, last_id, PAGE)).fetchall()
            if not rows:
                break
            for r in rows:
                last_id = r["id"]
                b = r["embedding_blob"]
                if isinstance(b, memoryview):
                    b = b.tobytes()
                if not isinstance(b, (bytes, bytearray)) or len(b) != DIM_FULL * 4:
                    continue
                X[kept] = np.frombuffer(b, dtype=np.float32, count=dim)
                kept += 1
                if kept == total:
                    break
            del rows
    X = X[:kept]
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
    print(f"filtered_out negatives: {X.shape[0]} x {dim} loaded in "
          f"{time.time()-t0:.0f}s", flush=True)
    return X


# ------------------------------------------------------------------ training
def _head(seed: int = 42, class_weight: str | None = None) -> SGDClassifier:
    return SGDClassifier(loss="log_loss", alpha=1e-5, max_iter=25, tol=1e-4,
                         random_state=seed, class_weight=class_weight)


def _parser() -> argparse.ArgumentParser:
    """Own function so a test can pin the defaults the Sunday cron runs with —
    `discovery_loop.retrain()` starts this script WITHOUT arguments."""
    ap = argparse.ArgumentParser(description="Train + persist distillation heads (#10)")
    ap.add_argument("--sample", type=int, default=0,
                    help="row cap (0 = all labeled trends); deterministic id-modulo slice")
    ap.add_argument("--dim", type=int, default=DIM_PREFIX, choices=[DIM_PREFIX, DIM_FULL],
                    help=f"embedding width to train on (default {DIM_PREFIX} = Matryoshka "
                         f"prefix; {DIM_FULL} is the full vector and ~4x the memory)")
    ap.add_argument("--holdout", type=float, default=0.10)
    ap.add_argument("--neg-cap", type=int, default=0, help="cap on relevance negatives (0 = all)")
    ap.add_argument("--skip-relevance", action="store_true")
    ap.add_argument("--relevance-only", action="store_true",
                    help="retrain ONLY the relevance head, keep the other 3 heads")
    ap.add_argument("--mega-only", action="store_true",
                    help="retrain ONLY the mega-trend head, keep the other 3")
    ap.add_argument("--mega-class-weight", choices=["none", "balanced"], default="balanced",
                    help="'balanced' weights the mega classes by inverse frequency. The "
                         "aggregate hides that small classes starve: with 138 holdout rows "
                         "against 18,218 for clean_energy_transition, "
                         "virtual_worlds_consolidation reached recall 0 on 2026-09-26. The "
                         "signal_type head (#110) uses balanced for exactly this reason. "
                         "Default since the Owner decision of 2026-09-26: macro recall 0.5487 "
                         "-> 0.8106 and no dead class, paid with 6,346 net worse assignments "
                         "in the large classes (details in docs/ops/logbook.md).")
    ap.add_argument("--mega-abstain-rate", type=float, default=0.072,
                    help="Share of signals that should get mega_trend=None. The threshold is "
                         "calibrated to this quantile at training time and stored with the "
                         "model, because the decision-value SCALE depends on the dimension AND "
                         "the class weighting: the productive 4096 head abstains on 7.2 %% at "
                         "-1.0, the 1024 balanced head on 12.9 %% at the same number. 0.072 "
                         "preserves the behaviour measured on 2026-09-26; raise or lower it "
                         "deliberately, never by changing the dimension.")
    return ap


def main() -> int:
    args = _parser().parse_args()

    t_all = time.time()
    dim = int(args.dim)
    mega_cw = None if args.mega_class_weight == "none" else args.mega_class_weight
    do_vertical = not args.relevance_only and not args.mega_only
    do_mega = not args.relevance_only
    do_pestel = not args.relevance_only and not args.mega_only
    do_relevance = not args.skip_relevance and not args.mega_only
    X, rows = _stream_trends(args.sample, dim)
    n = len(rows)
    if n < 1000:
        print("too few labeled trends", flush=True); return 1
    rng = np.random.default_rng(42)
    idx = rng.permutation(n)
    n_te = int(n * args.holdout)
    te, tr = idx[:n_te], idx[n_te:]

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    # --relevance-only keeps the existing report and just refreshes the relevance key
    existing = {}
    rep_path = Path(DATA_DIR, "distill_heads_report.json")
    if (args.relevance_only or args.mega_only) and rep_path.exists():
        existing = json.loads(rep_path.read_text())
    report: dict = existing or {
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_train": int(n - n_te), "n_holdout": int(n_te), "dim": dim,
        "backend": "postgres" if db_mod.USE_POSTGRES else "sqlite",
    }

    if do_vertical:
        # --- vertical ---
        t0 = time.time()
        yv = np.asarray([r["primary_vertical"] for r in rows])
        clf_v = _head().fit(X[tr], yv[tr])
        report["vertical"] = {
            "top1_agreement": round(float((clf_v.predict(X[te]) == yv[te]).mean()), 4),
            "classes": len(clf_v.classes_), "train_s": round(time.time() - t0, 1)}
        joblib.dump(clf_v, MODELS_DIR / "vertical.joblib")
        print("vertical:", report["vertical"], flush=True)

    if do_mega:
        # --- mega-trend (labeled rows only) ---
        t0 = time.time()
        m_mask = np.asarray([bool(r["mega_trend"]) for r in rows])
        ym = np.asarray([r["mega_trend"] or "" for r in rows])
        m_tr = tr[m_mask[tr]]; m_te = te[m_mask[te]]
        clf_m = _head(class_weight=mega_cw).fit(X[m_tr], ym[m_tr])
        scores = clf_m.decision_function(X[m_te])
        order = np.argsort(-scores, axis=1)
        classes = np.asarray(clf_m.classes_)
        top1 = float((classes[order[:, 0]] == ym[m_te]).mean())
        top3 = float(np.mean([ym[m_te][i] in classes[order[i, :3]] for i in range(len(m_te))]))
        # per-class holdout recall — the aggregate hides whether SMALL classes
        # (the 2026-08 taxonomy expansion seeds a few thousand rows each) are
        # reachable at all; a class with recall ~0 is dead weight in the yaml
        per_class = {}
        y_te = ym[m_te]
        pred1, pred3 = classes[order[:, 0]], classes[order[:, :3]]
        for c in classes:
            m = y_te == c
            if m.sum() >= 10:
                per_class[str(c)] = {
                    "n_holdout": int(m.sum()),
                    "recall_top1": round(float((pred1[m] == c).mean()), 3),
                    "recall_top3": round(float(np.mean([c in pred3[i]
                                          for i in np.where(m)[0]])), 3)}
        report["mega_trend"] = {"top1_agreement": round(top1, 4),
                                "top3_agreement": round(top3, 4),
                                "classes": len(classes),
                                "class_weight": mega_cw or "none",
                                "macro_recall_top1": round(float(np.mean(
                                    [v["recall_top1"] for v in per_class.values()])), 4)
                                if per_class else None,
                                "dead_classes": sorted(
                                    k for k, v in per_class.items() if v["recall_top1"] == 0),
                                "train_s": round(time.time() - t0, 1),
                                "per_class": per_class}
        # Abstain-Schwelle mitkalibrieren. Sie wird auf dem GANZEN Holdout genommen,
        # nicht nur auf den mega-gelabelten Zeilen: der Produktivstrom enthaelt
        # Signale, denen kein Mega-Trend passt, und genau fuer die ist das Abstain
        # da. Ohne diesen Schritt traegt `pipeline.distill.MEGA_ABSTAIN_THRESHOLD`
        # eine Zahl von der 4096er-Skala und trifft einen anderen Verteilungspunkt.
        abstain_thr = float(np.quantile(
            clf_m.decision_function(X[te]).max(axis=1), args.mega_abstain_rate))
        report["mega_trend"]["abstain_threshold"] = round(abstain_thr, 3)
        report["mega_trend"]["abstain_rate_target"] = float(args.mega_abstain_rate)
        print(f"mega abstain: Schwelle {abstain_thr:+.3f} fuer Zielquote "
              f"{args.mega_abstain_rate*100:.1f} %", flush=True)
        joblib.dump(clf_m, MODELS_DIR / "mega.joblib")
        print("mega:", {k: v for k, v in report["mega_trend"].items() if k != "per_class"}, flush=True)
        for c, m in sorted(per_class.items(), key=lambda kv: kv[1]["n_holdout"])[:12]:
            print(f"  small class {c}: n={m['n_holdout']} "
                  f"top1={m['recall_top1']} top3={m['recall_top3']}", flush=True)

    if do_pestel:
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
        print("pestel:", report["pestel"], flush=True)

    # --- relevance (calibrated; needs embed_filtered negatives) ---
    if do_relevance:
        Xneg = _load_filtered(args.neg_cap, dim)
        if Xneg.shape[0] < 5000:
            print(f"relevance head SKIPPED — only {Xneg.shape[0]} negatives "
                  "(run scripts/embed_filtered.py first)", flush=True)
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
                "dim": dim,   # --relevance-only keeps the other heads, which may
                              # have been trained at another width
                "train_s": round(time.time() - t0, 1)}
            joblib.dump(clf_r, MODELS_DIR / "relevance.joblib")
            print("relevance:", report["relevance"], flush=True)

    # Erst fertigrechnen, dann schreiben: meta.json trug bisher WEDER Laufzeit noch
    # Spitzenspeicher, weil es vor diesen drei Zeilen geschrieben wurde. Der Report
    # daneben hatte sie — die Herkunftsdatei am Modell aber nicht, und genau die
    # liest man, wenn man Wochen spaeter wissen will, was der Lauf gekostet hat.
    report["total_s"] = round(time.time() - t_all, 1)
    report["peak_rss_gb"] = round(_peak_rss_gb(), 1)
    report["dim"] = dim
    meta = {"trained": report["generated"], "n_train": report["n_train"],
            "dim": dim,
            "mega_abstain_threshold": report.get("mega_trend", {}).get("abstain_threshold"),
            "total_s": report["total_s"], "peak_rss_gb": report["peak_rss_gb"],
            "heads": [p.name for p in MODELS_DIR.glob("*.joblib")],
            "teacher": "8B LLM pipeline labels (trends table)",
            "report": report}
    (MODELS_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    Path(DATA_DIR, "distill_heads_report.json").write_text(json.dumps(report, indent=2))
    md = ["# Distillation Heads — Training Report",
          f"\nGeneriert: {report['generated']} · Train {report['n_train']:,} · "
          f"Holdout {report['n_holdout']:,} · Dim {report['dim']} · "
          f"Backend {report['backend']} · {report['total_s']}s · "
          f"Peak {report.get('peak_rss_gb', 0)} GB\n",
          "| Head | Metrik | Wert |", "|---|---|---|"]
    # .get(): --mega-only/--relevance-only ohne vorhandenen Report soll nicht NACH
    # 40 Minuten Rechnen an einem KeyError sterben.
    if isinstance(report.get("vertical"), dict):
        md.append(f"| Vertical | Top-1 | **{report['vertical']['top1_agreement']*100:.1f}%** |")
    if isinstance(report.get("mega_trend"), dict):
        m = report["mega_trend"]
        md.append(f"| Mega-Trend ({m.get('class_weight', 'none')}) | Top-1 / Top-3 / macro-R | "
                  f"**{m['top1_agreement']*100:.1f}% / {m['top3_agreement']*100:.1f}% / "
                  f"{(m.get('macro_recall_top1') or 0)*100:.1f}%** |")
        if m.get("dead_classes"):
            md.append(f"| Mega-Trend | Klassen mit Recall 0 | "
                      f"**{len(m['dead_classes'])}** ({', '.join(m['dead_classes'])}) |")
    if isinstance(report.get("pestel"), dict):
        md.append(f"| PESTEL | micro-F1 | **{report['pestel']['micro_f1']*100:.1f}%** |")
    if isinstance(report.get("relevance"), dict) and not report["relevance"].get("skipped"):
        r = report["relevance"]
        md.append(f"| Relevanz | P / R / Acc | **{r['precision']*100:.1f}% / "
                  f"{r['recall']*100:.1f}% / {r['accuracy']*100:.1f}%** |")
    md.append("\nModelle: `models/distill/` · Rohdaten: `data/distill_heads_report.json`")
    Path(DATA_DIR, "distill_heads_report.md").write_text("\n".join(md))
    print(f"\nDone in {report['total_s']}s at dim {dim} — peak RSS "
          f"{report['peak_rss_gb']} GB — models in {MODELS_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
