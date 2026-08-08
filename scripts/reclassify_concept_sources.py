#!/usr/bin/env python3
"""Route concept-scoped OpenAlex signals to their intended themes (2026-08-09).

The 2026-08 concept ingest (ingest_openalex CONCEPT_SHARDS) pulled works BY
OPENALEX CONCEPT — the concept is ground-truth metadata: we literally asked for
works about quantum information, telemedicine, aerospace… The distill head,
whose new-class seeds came mostly from market-style signals, routed much of
this academic text into the big attractors instead (quantum papers 72 % → AI,
edtech 81 % → AI, orbital got zero).

Fix, house-rule-konform: the concept PROPOSES the target key, the head must
CORROBORATE via its top-3 (the #39 gate used by mega_trend_reviewer and
reclassify_mega). A satellite paper that is really Earth-observation climate
work keeps climate_resilience — orbital simply won't be in its top-3.

    python scripts/reclassify_concept_sources.py --dry-run
    python scripts/reclassify_concept_sources.py --execute
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

# concept source → intended theme(s), priority-ordered. First one found in the
# head's top-3 wins; none in top-3 → the head's original call stands.
CONCEPT_TARGETS: dict[str, list[str]] = {
    "OpenAlex: Quantum information": ["quantum_information_science"],
    "OpenAlex: Photonics": ["next_generation_semiconductors", "quantum_information_science"],
    "OpenAlex: Satellite": ["orbital_economy_expansion"],
    "OpenAlex: Space exploration": ["orbital_economy_expansion"],
    "OpenAlex: Aerospace engineering": ["orbital_economy_expansion"],
    "OpenAlex: Telecommuting": ["evolution_of_work_models"],
    "OpenAlex: Human resource management": ["evolution_of_work_models"],
    "OpenAlex: Organizational behavior": ["evolution_of_work_models"],
    "OpenAlex: Educational technology": ["education_and_lifelong_learning"],
    "OpenAlex: Higher education": ["education_and_lifelong_learning"],
    "OpenAlex: Career development": ["education_and_lifelong_learning"],
    "OpenAlex: Telemedicine": ["digital_healthcare_integration"],
    "OpenAlex: Digital health": ["digital_healthcare_integration"],
    "OpenAlex: Health informatics": ["digital_healthcare_integration"],
}


def decide(stored: str | None, targets: list[str], top3: list[str]) -> str | None:
    """New key or None (keep). Concept proposes, head top-3 corroborates."""
    if stored in targets:
        return None
    for t in targets:
        if t in top3:
            return t
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Concept-informed reclassify of the OpenAlex ingest")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    clf = DistillClassifier.load()
    classes = np.asarray(clf._mega.classes_)

    import psycopg2
    conn = psycopg2.connect(db_mod.DATABASE_URL)
    cur = conn.cursor(name="concept_scan")
    cur.itersize = BATCH
    cur.execute(
        "SELECT t.id, t.mega_trend, s.name, t.embedding::text FROM trends t "
        "JOIN raw_entries r ON t.raw_entry_id = r.id "
        "JOIN sources s ON r.source_id = s.id "
        "WHERE s.name = ANY(%s) AND t.embedding IS NOT NULL",
        (list(CONCEPT_TARGETS),))

    t0 = time.time()
    moves: dict[int, str] = {}
    move_from: dict[int, str | None] = {}
    per_src: dict[str, Counter] = {}
    seen = 0
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            break
        X = np.stack([np.array(r[3].strip("[]").split(","), dtype=np.float32)
                      for r in rows])
        X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
        S = clf._mega.decision_function(X)
        order = np.argsort(-S, axis=1)[:, :3]
        for (tid, stored, src, _), o in zip(rows, order):
            seen += 1
            top3 = [str(classes[j]) for j in o]
            new = decide(stored, CONCEPT_TARGETS[src], top3)
            st = per_src.setdefault(src, Counter())
            if new:
                moves[tid] = new
                move_from[tid] = stored
                st["moved"] += 1
            elif stored in CONCEPT_TARGETS[src]:
                st["already"] += 1
            else:
                st["kept_other"] += 1
        if seen % 50_000 < BATCH:
            print(f"  … {seen:,} gescannt, {len(moves):,} Moves ({time.time()-t0:.0f}s)")
    cur.close()

    print(f"\ngescannt: {seen:,} · Moves: {len(moves):,} ({100*len(moves)/max(seen,1):.1f} %)")
    print(f"{'Quelle':<38} {'moved':>7} {'schon Ziel':>10} {'bleibt anders':>13}")
    for src in sorted(per_src):
        c = per_src[src]
        print(f"{src.replace('OpenAlex: ',''):<38} {c['moved']:>7,} "
              f"{c['already']:>10,} {c['kept_other']:>13,}")

    if args.dry_run:
        print("\nDRY-RUN — nichts geschrieben.")
        conn.close()
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit = Path("data/discovery") / f"concept_reclassify_{stamp}.jsonl"
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
    print(f"\nEXECUTED — {len(items):,} Signale umgeroutet. Audit: {audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
