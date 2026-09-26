#!/usr/bin/env python3
"""Qualitätsvergleich zweier Arme (Phase 4) aus den Dump-Dateien von bench_parallel.py.

  --kind judge   : Übereinstimmung des Richters (publish=true) mit der Handentscheidung
                   (label_truth published/rejected) je Arm; Fisher/McNemar zwischen Armen.
  --kind relevance: is_relevant=true ↔ published (Stufe 2) — gleiche Auswertung.
  --kind grounding: Anteil Bodies mit erfundenen Spezifika (pipeline.grounding.ungrounded_specifics
                   gegen source_blob aus gemma_ab.jsonl), Fisher exakt zwischen den Armen (Methode #11).

  python scripts/ctx_eval/quality_eval.py --kind judge  A=data/ctx_eval/q_judge_q4.jsonl B=data/ctx_eval/q_judge_q8.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load(path):
    return [json.loads(l) for l in open(path) if l.strip()]


def parsed(rec):
    try:
        return json.loads(rec.get("content") or "")
    except Exception:  # noqa: BLE001
        return None


def agreement(recs, field):
    rows = {}
    for r in recs:
        p = parsed(r)
        if p is None or r.get("label_truth") is None:
            continue
        pred = bool(p.get(field))
        truth = r["label_truth"] == "published"
        rows[r["id"]] = (pred, truth)
    n = len(rows)
    agree = sum(1 for p, t in rows.values() if p == t)
    tp = sum(1 for p, t in rows.values() if p and t)
    fp = sum(1 for p, t in rows.values() if p and not t)
    fn = sum(1 for p, t in rows.values() if not p and t)
    tn = n - tp - fp - fn
    return {"n": n, "agree": agree, "acc": round(agree / n, 3) if n else None,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "json_bad": sum(1 for r in recs if r.get("json_ok") is False),
            "errors": sum(1 for r in recs if r.get("error"))}, rows


def fisher(a_yes, a_no, b_yes, b_no):
    from scipy.stats import fisher_exact
    return fisher_exact([[a_yes, a_no], [b_yes, b_no]])[1]


def mcnemar(rows_a, rows_b):
    """Diskordante Paare (A richtig/B falsch vs. umgekehrt) auf denselben IDs, exakter Binomialtest."""
    from scipy.stats import binomtest
    ids = set(rows_a) & set(rows_b)
    a_only = sum(1 for i in ids if (rows_a[i][0] == rows_a[i][1]) and not (rows_b[i][0] == rows_b[i][1]))
    b_only = sum(1 for i in ids if (rows_b[i][0] == rows_b[i][1]) and not (rows_a[i][0] == rows_a[i][1]))
    p = binomtest(a_only, a_only + b_only, 0.5).pvalue if a_only + b_only else 1.0
    return {"paired_ids": len(ids), "A_right_B_wrong": a_only, "B_right_A_wrong": b_only, "p_mcnemar": round(p, 4)}


def grounding_stats(recs, blobs):
    from pipeline.grounding import ungrounded_specifics
    out = {}
    for r in recs:
        p = parsed(r)
        if not p or not blobs.get(r["id"]):
            continue
        body = p.get("body") or ""
        ung = ungrounded_specifics(body, blobs[r["id"]])
        out[r["id"]] = (len(ung), len(body.split()))
    n = len(out)
    bad = sum(1 for k, _ in out.values() if k > 0)
    return {"n": n, "with_invented": bad, "rate": round(bad / n, 3) if n else None,
            "mean_invented_tokens": round(sum(k for k, _ in out.values()) / n, 2) if n else None,
            "mean_words": round(sum(w for _, w in out.values()) / n) if n else None,
            "json_bad": sum(1 for r in recs if r.get("json_ok") is False),
            "errors": sum(1 for r in recs if r.get("error"))}, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["judge", "relevance", "grounding"], required=True)
    ap.add_argument("arms", nargs="+", help="NAME=dump.jsonl")
    ap.add_argument("--blobs", default=str(ROOT / "data/ctx_eval/prompts/gemma_ab.jsonl"))
    a = ap.parse_args()
    arms = {k: load(v) for k, v in (x.split("=", 1) for x in a.arms)}
    if a.kind in ("judge", "relevance"):
        field = "publish" if a.kind == "judge" else "is_relevant"
        stats, rows = {}, {}
        for k, recs in arms.items():
            stats[k], rows[k] = agreement(recs, field)
            print(f"{k:12} {stats[k]}")
        keys = list(arms)
        if len(keys) == 2:
            A, B = keys
            print("McNemar:", mcnemar(rows[A], rows[B]))
            sa, sb = stats[A], stats[B]
            print("Fisher (agree/disagree):", round(fisher(sa["agree"], sa["n"] - sa["agree"], sb["agree"], sb["n"] - sb["agree"]), 4))
    else:
        blobs = {it["id"]: it["source_blob"] for it in load(a.blobs)}
        stats = {}
        for k, recs in arms.items():
            stats[k], _ = grounding_stats(recs, blobs)
            print(f"{k:12} {stats[k]}")
        keys = list(arms)
        if len(keys) == 2:
            A, B = keys
            sa, sb = stats[A], stats[B]
            print("Fisher (mit/ohne erfundene Spezifika):",
                  round(fisher(sa["with_invented"], sa["n"] - sa["with_invented"], sb["with_invented"], sb["n"] - sb["with_invented"]), 4))


if __name__ == "__main__":
    main()
