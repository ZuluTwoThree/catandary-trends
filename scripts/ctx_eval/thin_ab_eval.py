#!/usr/bin/env python3
"""Wortzahlen und Guard-Quoten zweier Arme vergleichen (16K vs. 262144 Kontext).

  python scripts/ctx_eval/thin_ab_eval.py c16k=dump_a.jsonl c256k=dump_b.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.config import STAGE5_MIN_BODY_WORDS  # noqa: E402

HARD_FLOOR = 60  # pipeline.content_guard: unter 60 Wörtern ist der Body Garbage


def bodies(path: str) -> dict[int, int]:
    out = {}
    for line in open(path):
        r = json.loads(line)
        try:
            body = json.loads(r.get("content") or "").get("body") or ""
        except Exception:  # noqa: BLE001
            continue
        out[r["id"]] = len(body.split())
    return out


def main() -> None:
    arms = {k: bodies(v) for k, v in (a.split("=", 1) for a in sys.argv[1:])}
    from scipy.stats import fisher_exact, wilcoxon
    print(f"{'Arm':10} {'n':>4} {'Median':>7} {'<60 (hart)':>11} {'<25 (Stub)':>11}")
    for k, d in arms.items():
        v = sorted(d.values())
        print(f"{k:10} {len(v):>4} {v[len(v)//2]:>7} "
              f"{sum(1 for x in v if x < HARD_FLOOR):>11} {sum(1 for x in v if x < STAGE5_MIN_BODY_WORDS):>11}")
    keys = list(arms)
    if len(keys) == 2:
        a, b = arms[keys[0]], arms[keys[1]]
        ids = sorted(set(a) & set(b))
        pa = [a[i] for i in ids]; pb = [b[i] for i in ids]
        ka = sum(1 for x in pa if x < HARD_FLOOR); kb = sum(1 for x in pb if x < HARD_FLOOR)
        print(f"\ngepaart über {len(ids)} Prompts")
        print(f"  unter {HARD_FLOOR} Wörtern: {keys[0]} {ka}, {keys[1]} {kb} — "
              f"Fisher p = {fisher_exact([[ka, len(ids)-ka], [kb, len(ids)-kb]])[1]:.4f}")
        if any(x != y for x, y in zip(pa, pb)):
            print(f"  Wortzahl-Verteilung (Wilcoxon, gepaart): p = {wilcoxon(pa, pb).pvalue:.4f}")


if __name__ == "__main__":
    main()
