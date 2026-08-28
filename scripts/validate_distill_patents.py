#!/usr/bin/env python3
"""Validiert den Distill-Relevanz-Head gegen die Juni-Patent-Kohorte (Owner 2026-08-29).

Hintergrund: Der Samstags-Patent-Pass (82255c7) filtert über den Distill-Head;
Live-Test 28.08. behielt nur ~6 % — der 8B-LLM-Pfad im Juni behielt ~20 %.
Dieses Skript misst, ob der Head patent-blind ist:

  A) Recall auf den BEHALTENEN:   Head-Scores der ~16k Juni-Patent-Signale
     aus ihren GESPEICHERTEN trends-Embeddings (CPU, Sekunden).
  B) Rezept-Gegenprobe (--sample): dieselben Patente frisch embedded mit dem
     exakten Samstags-Rezept (title\nexcerpt[:500]) — trennt Head-Problem
     von Embedding-Rezept-Drift. Braucht den Embedding-Server (:8090).
  C) Gegenseite (--sample): vom 8B VERWORFENE Patente (filter_reason
     'not_relevant') durch den Head — lehnt er dieselben ab, oder alles?

Ausgabe: Keep-Rates @0.5, Score-Dezile, Schwellen für 80/90 % Recall auf B,
JSON-Protokoll nach data/distill_patent_validation.json.

Aufruf (Server muss laufen, kein Handover — read-only außer der JSON-Datei):
  EMBED_BACKEND=llamacpp .venv/bin/python scripts/validate_distill_patents.py --sample 5000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pipeline.db import USE_POSTGRES, get_connection, _vector_to_bytes  # noqa: E402
from pipeline.distill import DistillClassifier  # noqa: E402


def _scores(clf: DistillClassifier, X: np.ndarray, chunk: int = 4096) -> np.ndarray:
    out = []
    for i in range(0, len(X), chunk):
        res = clf.classify_batch(X[i:i + chunk])
        out.extend(r["relevance"] for r in res)
    return np.asarray(out, dtype=np.float64)


def _stats(name: str, s: np.ndarray) -> dict:
    dec = {f"p{p}": round(float(np.percentile(s, p)), 3) for p in (5, 10, 25, 50, 75, 90, 95)}
    d = {"n": int(len(s)), "keep@0.5": round(float((s >= 0.5).mean()), 3),
         "keep@0.3": round(float((s >= 0.3).mean()), 3),
         "keep@0.2": round(float((s >= 0.2).mean()), 3), **dec}
    print(f"{name:34s} n={d['n']:6d}  keep@0.5={d['keep@0.5']:.1%}  "
          f"keep@0.3={d['keep@0.3']:.1%}  keep@0.2={d['keep@0.2']:.1%}  median={d['p50']:.3f}")
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=5000,
                    help="Stichprobengröße für Teil B (Re-Embed) und C (Verworfene)")
    ap.add_argument("--skip-embed", action="store_true",
                    help="nur Teil A (gespeicherte Embeddings, kein GPU-Bedarf)")
    ap.add_argument("--bdds-sample", type=int, default=0,
                    help="Teil D: N zufällige unverarbeitete BDDS-Patente aus dem "
                         "Samstags-Fenster scoren (erwartete Keep-Rate des Cron-Passes)")
    ap.add_argument("--bdds-window", default="2026-06-30",
                    help="published_date-Untergrenze für Teil D")
    args = ap.parse_args()
    if not USE_POSTGRES:
        print("targets PostgreSQL (Prod-Kohorte) — DATABASE_URL fehlt"); return 2

    clf = DistillClassifier.load()
    if not clf.has_relevance_head:
        print("kein Relevanz-Head trainiert"); return 2
    report: dict = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "heads_trained": clf.meta.get("trained")}

    # ---- A: Juni-behaltene Patente, gespeicherte Embeddings --------------
    with get_connection() as c:
        rows = c.execute(
            "SELECT t.id, t.raw_entry_id, t.embedding::text AS emb FROM trends t "
            "WHERE t.trend_signal_type = 'patent' AND t.embedding IS NOT NULL").fetchall()
    X = np.empty((len(rows), 4096), dtype=np.float32)
    for i, r in enumerate(rows):
        X[i] = np.frombuffer(_vector_to_bytes(r["emb"]), dtype=np.float32)
    sA = _scores(clf, X)
    report["A_kept_stored"] = _stats("A kept (gespeicherte Embeddings)", sA)

    if not args.skip_embed:
        from scripts.signal_batch import embed_batch  # braucht EMBED_BACKEND=llamacpp

        def embed_texts(pairs: list[tuple[str, str]]) -> np.ndarray:
            vecs = []
            for i in range(0, len(pairs), 64):
                chunk = pairs[i:i + 64]
                texts = [f"{t}\n{(e or '')[:500]}" for t, e in chunk]
                for v in embed_batch(texts):
                    if v is not None:
                        vecs.append(v)
            return np.asarray(vecs, dtype=np.float32)

        if args.sample > 0:
            # ---- B: Rezept-Gegenprobe auf einer Kept-Stichprobe ----------
            with get_connection() as c:
                rows = c.execute(
                    "SELECT re.title, re.excerpt FROM trends t "
                    "JOIN raw_entries re ON re.id = t.raw_entry_id "
                    "WHERE t.trend_signal_type = 'patent' AND t.embedding IS NOT NULL "
                    "AND length(coalesce(re.excerpt,'')) > 120 "
                    "ORDER BY random() LIMIT %s", (args.sample,)).fetchall()
            t0 = time.time()
            XB = embed_texts([(r["title"], r["excerpt"]) for r in rows])
            print(f"  (B: {len(XB)} embedded in {time.time()-t0:.0f}s)")
            sB = _scores(clf, XB)
            report["B_kept_reembedded"] = _stats("B kept (Samstags-Rezept, frisch)", sB)
            report["B_thresholds"] = {
                "recall80": round(float(np.percentile(sB, 20)), 3),
                "recall90": round(float(np.percentile(sB, 10)), 3)}
            print(f"  Schwelle für 80% Recall auf kept: {report['B_thresholds']['recall80']:.3f} · "
                  f"für 90%: {report['B_thresholds']['recall90']:.3f}")

            # ---- C: vom 8B verworfene Patente ----------------------------
            with get_connection() as c:
                rows = c.execute(
                    "SELECT re.title, re.excerpt FROM raw_entries re "
                    "WHERE re.pub_number IS NOT NULL AND re.filtered_out "
                    "AND re.filter_reason = 'not_relevant' "
                    "AND length(coalesce(re.excerpt,'')) > 120 "
                    "ORDER BY random() LIMIT %s", (args.sample,)).fetchall()
            t0 = time.time()
            XC = embed_texts([(r["title"], r["excerpt"]) for r in rows])
            print(f"  (C: {len(XC)} embedded in {time.time()-t0:.0f}s)")
            sC = _scores(clf, XC)
            report["C_rejected"] = _stats("C rejected (8B: not_relevant)", sC)

    if args.bdds_sample and not args.skip_embed:
        # ---- D: erwartete Keep-Rate des Samstags-Passes ------------------
        from scripts.signal_batch import embed_batch as _eb  # noqa: F401 (Import oben zieht env)
        with get_connection() as c:
            rows = c.execute(
                "SELECT re.title, re.excerpt FROM raw_entries re "
                "WHERE re.pub_number IS NOT NULL AND NOT re.processed AND NOT re.filtered_out "
                "AND length(coalesce(re.excerpt,'')) > 120 AND re.published_date >= %s "
                "ORDER BY random() LIMIT %s", (args.bdds_window, args.bdds_sample)).fetchall()
        t0 = time.time()
        XD = embed_texts([(r["title"], r["excerpt"]) for r in rows])
        print(f"  (D: {len(XD)} embedded in {time.time()-t0:.0f}s)")
        sD = _scores(clf, XD)
        report["D_bdds_window"] = _stats("D BDDS-Fenster (Samstags-Scope)", sD)
        order = np.argsort(-sD)
        print("  Top-5 (würde behalten):")
        for i in order[:5]:
            print(f"    {sD[i]:.2f}  {rows[i]['title'][:90]}")
        print("  Bottom-5 (würde verwerfen):")
        for i in order[-5:]:
            print(f"    {sD[i]:.2f}  {rows[i]['title'][:90]}")

    out = REPO / "data" / "distill_patent_validation.json"
    out.parent.mkdir(exist_ok=True)
    if out.exists():  # Teilläufe (z. B. D-only) ergänzen das Protokoll statt es zu ersetzen
        merged = json.loads(out.read_text())
        merged.update(report)
        report = merged
    out.write_text(json.dumps(report, indent=2))
    print(f"\nProtokoll: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
