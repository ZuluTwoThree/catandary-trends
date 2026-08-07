#!/usr/bin/env python3
"""Reclassify the attractor-held trends with the retrained 28-class mega head
(taxonomy expansion 2026-08-07, docs/mega_taxonomy_decision_2026-08-07.md).

Scans trends whose mega_trend is one of the four attractors or the catch-all
(optionally: NULL rows too) and re-labels a row only on a clear call:

  - the head's top-1 differs from the stored label,
  - the stored label is NOT in the head's top-2 (the #39 corroboration gate —
    same rule mega_trend_reviewer/fix_mega_abstain use: the embedding actively
    disagrees, not merely prefers a sibling),
  - the top-1 decision score is positive (the class claims the point; no
    relabel onto a least-bad guess), and
  - the top-1 is one of the expansion TARGET keys (default) — the six new keys
    plus the starved keys the split activates. `--targets all` lifts that and
    allows any move the gates admit (report first: attractor→attractor churn
    is not validated).

    python scripts/reclassify_mega.py --dry-run
    python scripts/reclassify_mega.py --execute
    python scripts/reclassify_mega.py --dry-run --include-null --targets all
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

from pipeline import db as db_mod
from pipeline.distill import DistillClassifier

BATCH = 2000

SOURCES = ["personalized_health_and_longevity", "artificial_intelligence_and_automation",
           "financial_innovation_and_inclusion", "clean_energy_transition",
           "inclusive_and_human_centric_design"]

# Default move targets: the 2026-08 expansion. Everything else stays put unless
# --targets all is passed (and even then the two gates above still hold).
EXPANSION_TARGETS = [
    "quantum_information_science", "next_generation_semiconductors",
    "orbital_economy_expansion", "evolution_of_work_models",
    "education_and_lifelong_learning", "digital_healthcare_integration",
    "electric_and_autonomous_mobility", "mental_health_and_neuro_wellness",
    "climate_resilience_and_adaptation", "platformization_of_culture",
    "creator_economy_and_platform_shift", "regenerative_design_and_net_positive",
    "new_luxury_and_premiumization", "experience_economy_and_immersive_design",
    "bio_revolution_and_new_materials",
]


def decide(stored: str | None, classes: np.ndarray, scores: np.ndarray,
           allowed: set[str] | None) -> str | None:
    """Return the new key for one row, or None to keep the stored label.
    `scores` = the mega head's decision_function row over all classes."""
    order = np.argsort(-scores)
    top1, top2 = str(classes[order[0]]), str(classes[order[1]])
    if scores[order[0]] < 0:          # nobody claims the point positively
        return None
    if allowed is not None and top1 not in allowed:
        return None
    if stored is None:
        return top1
    if top1 == stored or stored in (top1, top2):
        return None                    # stored label is corroborated — keep
    return top1


def main() -> int:
    ap = argparse.ArgumentParser(description="Reclassify attractor trends with the 28-class head")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    ap.add_argument("--include-null", action="store_true",
                    help="also assign rows with mega_trend IS NULL")
    ap.add_argument("--targets", choices=["expanded", "all"], default="expanded")
    ap.add_argument("--status", default="signal,published")
    args = ap.parse_args()

    clf = DistillClassifier.load()
    classes = np.asarray(clf._mega.classes_)
    n_classes = len(classes)
    print(f"mega head: {n_classes} Klassen "
          f"(trainiert {clf.meta.get('trained', '?')})")
    missing = [k for k in EXPANSION_TARGETS if k not in set(map(str, classes))]
    if missing:
        print(f"⚠️ Head kennt {len(missing)} Ziel-Keys NICHT: {missing}")
        if args.targets == "expanded" and len(missing) == len(EXPANSION_TARGETS):
            print("abbruch — Retrain zuerst"); return 1
    allowed = set(EXPANSION_TARGETS) if args.targets == "expanded" else None

    import psycopg2
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor(name="reclass_scan")
    cur.itersize = BATCH
    sts = tuple(s.strip() for s in args.status.split(","))
    null_sql = " OR mega_trend IS NULL" if args.include_null else ""
    cur.execute(
        f"SELECT id, mega_trend, title_en, embedding::text FROM trends "
        f"WHERE status IN %s AND embedding IS NOT NULL "
        f"AND (mega_trend = ANY(%s){null_sql})", (sts, SOURCES))

    t0 = time.time()
    moves: dict[int, str] = {}
    move_from: dict[int, str | None] = {}
    matrix: Counter = Counter()
    samples: dict[tuple, list[str]] = {}
    seen = 0
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        X = np.stack([np.array(r[3].strip("[]").split(","), dtype=np.float32)
                      for r in rows])
        X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
        S = clf._mega.decision_function(X)
        for r, srow in zip(rows, S):
            seen += 1
            new = decide(r[1], classes, srow, allowed)
            if new:
                moves[r[0]] = new
                move_from[r[0]] = r[1]
                key = (r[1] or "(NULL)", new)
                matrix[key] += 1
                if len(samples.setdefault(key, [])) < 3:
                    samples[key].append((r[2] or "")[:90])
        if seen % 100_000 < BATCH:
            print(f"  … {seen:,} gescannt, {len(moves):,} Moves ({time.time()-t0:.0f}s)")
    cur.close()

    print(f"\ngescannt: {seen:,} · Moves: {len(moves):,} ({100*len(moves)/max(seen,1):.1f} %)")
    print("\n== Move-Matrix (von → nach) ==")
    for (frm, to), n in sorted(matrix.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>7,}  {frm} → {to}")
        for t in samples[(frm, to)]:
            print(f"           • {t}")

    if args.dry_run:
        print("\nDRY-RUN — nichts geschrieben.")
        conn.close()
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit = Path("data/discovery") / f"reclassify_applied_{stamp}.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("w", encoding="utf-8") as f:
        for tid, new in moves.items():
            f.write(json.dumps({"id": tid, "old": move_from[tid], "new": new}) + "\n")

    from psycopg2.extras import execute_values
    wcur = conn.cursor()
    items = list(moves.items())
    for i in range(0, len(items), 5000):
        execute_values(
            wcur,
            "UPDATE trends t SET mega_trend = v.mega FROM (VALUES %s) AS v(id, mega) "
            "WHERE t.id = v.id",
            items[i:i + 5000], page_size=5000)
    conn.commit()
    conn.close()
    print(f"\nEXECUTED — {len(items):,} Trends umgelabelt. Audit: {audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
