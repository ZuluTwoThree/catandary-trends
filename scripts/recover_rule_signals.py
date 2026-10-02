#!/usr/bin/env python3
"""Bring back the patents and funding rows the relevance head dropped (Owner 2026-10-02).

Until 02.10. the signal path let the press-trained relevance head decide alone, at 0.5,
for patents and funding too. The blind audit (docs/filter_audit_2026-10-02.md) found
92-96 % signals among the dropped patents and 42-87 % among the dropped funding rows;
since 02.10. both tiers are judged by pipeline/signal_rules.py. This script applies the
same rules to what was dropped BEFORE, using the vector stored with each dropped row
(raw_entries.embedding_blob) — no GPU, no re-embedding:

  * rule says drop  -> filter_reason becomes 'rule:<reason>' (still filtered)
  * near-duplicate of a kept signal of its tier, or of a row recovered earlier in this run
    (cosine > DUPLICATE_SIMILARITY_THRESHOLD on the 1024 prefix) -> 'duplicate: embedding'
  * otherwise -> inserted as a signal exactly like signal_batch does (distill heads for
    vertical / PESTEL / mega trend on the stored vector), the raw entry becomes
    processed, filtered_out = FALSE, filter_reason 'recovered:<old reason>'

Rows WITHOUT a stored vector are out of scope (they would need the GPU embedder; mostly
the July backfill of SEC Form D / SBIR). Nothing is deleted; every change is recorded in
filter_reason, so it can be told apart and undone.

    .venv/bin/python scripts/recover_rule_signals.py                 # dry run: counts per outcome
    .venv/bin/python scripts/recover_rule_signals.py --apply         # write, batched
    .venv/bin/python scripts/recover_rule_signals.py --apply --limit 2000   # a first slice

Kept vectors for the duplicate check come from the domain service's copy
(~/.cache/catandary/domain_service, rebuilt by `pipeline.domain_service --rebuild`).
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from slugify import slugify  # noqa: E402

from pipeline.config import DUPLICATE_SIMILARITY_THRESHOLD  # noqa: E402
from pipeline.crs import compute_crs  # noqa: E402
from pipeline.db import get_connection, insert_trend  # noqa: E402
from pipeline.domain_service import CACHE_DIR, ST_PUBLISHED, TIER_NAMES  # noqa: E402
from pipeline.llm_processor import _distill_signal_type  # noqa: E402
from pipeline.signal_rules import rule_tier, verdict  # noqa: E402

DIM = 1024
BATCH = 500


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def candidates(limit: int) -> list[dict]:
    with get_connection() as c:
        c.execute("SET statement_timeout = '3600s'")
        rows = c.execute(
            "SELECT r.id, r.title, r.excerpt, r.url, r.pub_number, r.filter_reason, "
            "s.name AS source_name, s.source_type "
            "FROM raw_entries r JOIN sources s ON s.id = r.source_id "
            "WHERE r.filtered_out AND r.embedding_blob IS NOT NULL "
            "AND r.filter_reason LIKE 'not_relevant%%' "
            "AND (r.pub_number IS NOT NULL OR s.source_type = 'api') ORDER BY r.id").fetchall()
    out = [dict(r) for r in rows if rule_tier(dict(r))]
    return out[:limit] if limit else out


def vectors(ids: list[int]) -> np.ndarray:
    pos = {i: k for k, i in enumerate(ids)}
    X = np.zeros((len(ids), 4096), np.float32)
    with get_connection() as c:
        for s in range(0, len(ids), 2000):
            for r in c.execute("SELECT id, embedding_blob FROM raw_entries WHERE id = ANY(?)",
                               (ids[s:s + 2000],)).fetchall():
                v = np.frombuffer(bytes(r["embedding_blob"]), np.float32)
                X[pos[int(r["id"])], :len(v)] = v[:4096]
    return X


def l2(X):
    return X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)


def kept_matrix(tier: str) -> np.ndarray:
    meta = np.load(CACHE_DIR / "meta.npz")
    X = np.load(CACHE_DIR / "vectors.npy", mmap_mode="r")
    rows = np.flatnonzero((meta["status"] <= ST_PUBLISHED) & (meta["tier"] == TIER_NAMES.index(tier)))
    return np.asarray(X[rows], np.float32)


def max_cos(Q: np.ndarray, K: np.ndarray) -> np.ndarray:
    best = np.full(len(Q), -1.0, np.float32)
    for s in range(0, K.shape[0], 50_000):
        best = np.maximum(best, (Q @ K[s:s + 50_000].T).max(axis=1))
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    t0 = time.time()
    rows = candidates(args.limit)
    by_tier: dict[str, list[dict]] = {}
    for r in rows:
        by_tier.setdefault(rule_tier(r), []).append(r)
    log("candidates with a stored vector: " + ", ".join(f"{t} {len(v):,}" for t, v in by_tier.items()))
    outcome: Counter = Counter()
    if args.apply:
        from pipeline.distill import DistillClassifier
        clf = DistillClassifier.load()
    for tier, items in by_tier.items():
        decided = [(r, verdict(r)) for r in items]
        for r, v in decided:
            if v:
                outcome[f"{tier}/rule:{v}"] += 1
        keep = [r for r, v in decided if not v]
        K = kept_matrix(tier)
        log(f"{tier}: {len(items):,} candidates, {len(keep):,} pass the rules; "
            f"duplicate check against {len(K):,} kept signals")
        recovered = np.zeros((len(keep), DIM), np.float32)
        n_rec = 0
        for s in range(0, len(keep), BATCH):
            part = keep[s:s + BATCH]
            V = vectors([r["id"] for r in part])
            Q = l2(V[:, :DIM])
            dup = max_cos(Q, K) > DUPLICATE_SIMILARITY_THRESHOLD
            preds = clf.classify_batch(V) if args.apply else [None] * len(part)
            writes = []
            for j, r in enumerate(part):
                if not dup[j] and n_rec and float((recovered[:n_rec] @ Q[j]).max()) > DUPLICATE_SIMILARITY_THRESHOLD:
                    dup[j] = True
                if dup[j]:
                    outcome[f"{tier}/duplicate"] += 1
                    writes.append(("dup", r, None, None))
                    continue
                recovered[n_rec] = Q[j]
                n_rec += 1
                outcome[f"{tier}/recovered"] += 1
                writes.append(("rec", r, V[j], preds[j]))
            if args.apply:
                apply_batch(writes)
            log(f"  {tier} {min(s + BATCH, len(keep)):,}/{len(keep):,} — {dict(outcome)}")
        if args.apply:
            apply_rules([(r, v) for r, v in decided if v])
    log(("APPLIED " if args.apply else "DRY RUN ") + str(dict(outcome)) + f" ({time.time() - t0:.0f} s)")
    return 0


def apply_rules(pairs: list[tuple[dict, str]]) -> None:
    with get_connection() as c:
        for k in range(0, len(pairs), 1000):
            for r, v in pairs[k:k + 1000]:
                c.execute("UPDATE raw_entries SET filter_reason = ? WHERE id = ?", (f"rule:{v}", r["id"]))
            c.commit()


def apply_batch(writes) -> None:
    for kind, r, vec, pred in writes:
        old = r["filter_reason"]
        if kind == "dup":
            with get_connection() as c:
                c.execute("UPDATE raw_entries SET filter_reason = ? WHERE id = ?",
                          ("duplicate: embedding", r["id"]))
            continue
        title = r["title"] or "(untitled signal)"
        conf = pred["relevance"] if pred["relevance"] is not None else pred["vertical_confidence"]
        e = {"id": r["id"], "source_name": r["source_name"], "source_type": r["source_type"],
             "pub_number": r["pub_number"], "title": title}
        sig_type = _distill_signal_type(e, pred)
        insert_trend(r["id"], {
            "title_en": title, "title_de": None, "summary_en": None, "summary_de": None,
            "body_en": None, "body_de": None,
            "slug": f"{slugify(title, max_length=70)}-{r['id']}",
            "verticals": [pred["primary_vertical"]], "primary_vertical": pred["primary_vertical"],
            "pestel": pred["pestel"], "tags": [], "trend_signal_type": sig_type,
            "mega_trend": pred["mega_trend"], "trend_level": "micro", "brands": [], "regions": [],
            "trend_score": compute_crs(confidence=conf, num_verticals=1, num_pestel=len(pred["pestel"]),
                                       signal_type=sig_type, source_type=r["source_type"]) / 100.0,
            "confidence": conf, "source_url": r["url"], "source_name": r["source_name"] or "Unknown",
            "embedding": vec.astype(np.float32).tobytes(), "status": "signal",
        })
        with get_connection() as c:
            c.execute("UPDATE raw_entries SET processed = TRUE, filtered_out = FALSE, "
                      "filter_reason = ? WHERE id = ?", (f"recovered:{old}"[:200], r["id"]))


if __name__ == "__main__":
    raise SystemExit(main())
