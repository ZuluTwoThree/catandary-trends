#!/usr/bin/env python3
"""Relabel the press rows the source-type rule stamped `market_shift` (#110, stage 2).

Between the hybrid classification (2026-07-14) and the activation of the
signal-type head every press signal got `market_shift`. This one-off pass
runs the head (models/distill/signal_type.joblib) over exactly those rows —
press source, no patent number, created since the cutover, label
market_shift — and rewrites the label where the head is confident
(>= DISTILL_SIGNAL_TYPE_MIN_CONF). Only `trend_signal_type` and the CRS
`trend_score` (which takes the type as its maturity input) change; title,
body, embeddings, status stay. Batched commits (default 1000 rows) — never
one big UPDATE on `trends` (HNSW bloat, 2026-09-17).

    python scripts/relabel_signal_types.py            # dry-run: distribution only
    python scripts/relabel_signal_types.py --apply    # write
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import numpy as np

from pipeline import db as db_mod
from pipeline.config import DATA_DIR, DISTILL_SIGNAL_TYPE_MIN_CONF
from pipeline.crs import compute_crs
from pipeline.distill import MODELS_DIR, SIGNAL_TYPE_HEAD_FILE
from scripts.train_signal_type_head import CUTOVER, PRESS_CLASSES, load_recent


def decide(labels, conf, floor: float) -> list[str | None]:
    """New label per row, or None when nothing changes: below the floor, an
    unknown class, or the head agreeing with market_shift."""
    out = []
    for lab, c in zip(labels, conf):
        lab = str(lab)
        if c < floor or lab not in PRESS_CLASSES or lab == "market_shift":
            out.append(None)
        else:
            out.append(lab)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Relabel market_shift press rows with the signal-type head (#110)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--floor", type=float, default=DISTILL_SIGNAL_TYPE_MIN_CONF)
    ap.add_argument("--batch", type=int, default=1000)
    ap.add_argument("--sample", type=int, default=0, help="row cap for a trial (0 = all)")
    args = ap.parse_args()

    head_path = MODELS_DIR / SIGNAL_TYPE_HEAD_FILE
    if not head_path.exists():
        raise SystemExit(f"no head at {head_path} — run scripts/train_signal_type_head.py first")
    clf = joblib.load(head_path)
    t0 = time.time()
    X, meta = load_recent(args.sample)
    if not len(meta):
        print("nothing to relabel"); return 0
    P = clf.predict_proba(X)
    idx = P.argmax(axis=1)
    conf = P[np.arange(len(P)), idx]
    labels = np.asarray(clf.classes_)[idx]
    new = decide(labels, conf, args.floor)
    changes = [(m["id"], lab) for m, lab in zip(meta, new) if lab]
    dist = Counter(lab for _, lab in changes)
    summary = {
        "generated": datetime.now(timezone.utc).isoformat(), "cutover": CUTOVER,
        "floor": args.floor, "rows_considered": len(meta), "rows_changed": len(changes),
        "kept_market_shift": len(meta) - len(changes), "new_labels": dict(dist.most_common()),
        "apply": args.apply,
    }
    print(json.dumps(summary, ensure_ascii=False))

    if args.apply and changes:
        if not db_mod.USE_POSTGRES:
            raise SystemExit("apply needs the Postgres corpus")
        import psycopg2
        from psycopg2.extras import execute_batch
        conn = psycopg2.connect(db_mod.DATABASE_URL)
        try:
            cur = conn.cursor()
            ids = [i for i, _ in changes]
            want = dict(changes)
            written = 0
            for start in range(0, len(ids), args.batch):
                chunk = ids[start:start + args.batch]
                cur.execute(
                    "SELECT t.id, t.confidence, t.verticals, t.pestel, s.source_type "
                    "FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id "
                    "LEFT JOIN sources s ON s.id = r.source_id WHERE t.id = ANY(%s)", (chunk,))
                rows = []
                for tid, confidence, verticals, pestel, source_type in cur.fetchall():
                    verticals = verticals if isinstance(verticals, list) else json.loads(verticals or "[]")
                    pestel = pestel if isinstance(pestel, list) else json.loads(pestel or "[]")
                    score = compute_crs(confidence=float(confidence or 0.8), num_verticals=len(verticals),
                                        num_pestel=len(pestel), signal_type=want[tid],
                                        source_type=source_type) / 100.0
                    rows.append((want[tid], score, tid))
                execute_batch(cur, "UPDATE trends SET trend_signal_type = %s, trend_score = %s "
                                   "WHERE id = %s AND trend_signal_type = 'market_shift'", rows)
                conn.commit()
                written += len(rows)
                print(f"  {written}/{len(ids)} updated", flush=True)
            summary["rows_written"] = written
        finally:
            conn.close()
    summary["seconds"] = round(time.time() - t0, 1)
    (DATA_DIR / "relabel_signal_types_last.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
