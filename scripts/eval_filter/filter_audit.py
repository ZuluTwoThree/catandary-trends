#!/usr/bin/env python3
"""Do the relevance gates throw good signals away? Stages 1 and 2 (Owner 2026-10-02).

Read-only, CPU only. Compares what the relevance gates DROPPED (raw_entries filtered as
not_relevant_distill:<p> — the embedding head — or not_relevant (8B band)) with what the
pipeline KEPT (the signal space: trends status signal/published), in the embedding.

Stage 1a  Proximity: for a capped sample per tier × head-score band, the cosine to the
          nearest kept signal OF THE SAME TIER (the embedding carries register, so other
          tiers would understate it), against kept signals' own nearest-other-kept cosine.
          If dropped items sit as close to kept ones as kept ones sit to each other, the
          gate is not separating topics, only cutting through them.
Stage 1b  What is thrown away: the dropped items of each tier are partitioned like the
          emerging layer (fine k-means, cohesion gate) and each dense pocket is labelled
          from its titles; for each pocket, how many KEPT signals of the tier lie inside it
          (cosine to the pocket centre >= the pocket's own radius). A pocket with almost
          no kept counterpart is a topic the gate removes wholesale.
Stage 2   Lost early signals: share of dropped vs kept items that fall into the current
          emerging nests (every scope's latest run; centroid cosine >= nest threshold),
          overall and for young nests (on record / in the signal space for <= 18 months).

Kept vectors come from the domain service's copy (~/.cache/catandary/domain_service),
dropped vectors from raw_entries.embedding_blob (4096-dim; the first 1024 = the same
Matryoshka prefix as trends.embedding_1024).

    .venv/bin/python scripts/eval_filter/filter_audit.py            # ~30-60 min
    .venv/bin/python scripts/eval_filter/filter_audit.py --quick    # small caps, ~5 min
Writes data/filter_audit.json and prints a summary.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.config import DATA_DIR  # noqa: E402
from pipeline.db import get_connection  # noqa: E402
from pipeline.domain_service import CACHE_DIR, ST_PUBLISHED, TIER_NAMES  # noqa: E402
from pipeline.emerging import detect_nests, pick_cells, title_terms  # noqa: E402
from pipeline.tiers import tier_of  # noqa: E402

DIM = 1024
HASH_MUL, HASH_MOD = 2654435761, 2 ** 32
BANDS = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.7)]
CHUNK = 50_000


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def l2(X: np.ndarray) -> np.ndarray:
    return X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)


def band_of(p: float | None) -> str:
    if p is None:
        return "8B"
    for lo, hi in BANDS:
        if lo <= p < hi:
            return f"{lo:.1f}-{hi:.1f}"
    return ">=0.7"


# ------------------------------------------------------------------ data

def load_kept():
    meta = np.load(CACHE_DIR / "meta.npz")
    X = np.load(CACHE_DIR / "vectors.npy", mmap_mode="r")
    keep = meta["status"] <= ST_PUBLISHED
    return X, meta["ids"], meta["tier"], meta["month"], keep


def dropped_index() -> list[dict]:
    """id, tier, reason score, title of every relevance-dropped entry WITH a vector."""
    out = []
    with get_connection() as c:
        c.execute("SET statement_timeout = '3600s'")
        rows = c.execute(
            "SELECT r.id, r.title, r.filter_reason, s.name, s.source_type "
            "FROM raw_entries r JOIN sources s ON s.id = r.source_id "
            "WHERE r.filtered_out AND r.embedding_blob IS NOT NULL "
            "AND r.filter_reason LIKE 'not_relevant%%'").fetchall()
    for r in rows:
        reason = r["filter_reason"] or ""
        p = None
        if reason.startswith("not_relevant_distill:"):
            try:
                p = float(reason.split(":", 1)[1])
            except ValueError:
                p = None
        out.append({"id": int(r["id"]), "title": r["title"] or "", "p": p,
                    "head": reason.startswith("not_relevant_distill:"),
                    "tier": tier_of(r["name"], r["source_type"]) or "none"})
    return out


def fetch_vectors(ids: list[int]) -> np.ndarray:
    X = np.zeros((len(ids), DIM), np.float32)
    pos = {i: k for k, i in enumerate(ids)}
    with get_connection() as c:
        for s in range(0, len(ids), 2000):
            part = ids[s:s + 2000]
            for r in c.execute("SELECT id, embedding_blob FROM raw_entries WHERE id = ANY(?)",
                               (part,)).fetchall():
                v = np.frombuffer(bytes(r["embedding_blob"]), np.float32)
                X[pos[int(r["id"])]] = v[:DIM]
    return l2(X)


def hsample(items: list[dict], k: int) -> list[dict]:
    return sorted(items, key=lambda d: (d["id"] * HASH_MUL) % HASH_MOD)[:k]


def nearest(Q: np.ndarray, K: np.ndarray, exclude_self: bool = False) -> np.ndarray:
    """Max cosine of each row of Q against the rows of K (float16 store, chunked)."""
    best = np.full(len(Q), -1.0, np.float32)
    for s in range(0, K.shape[0], CHUNK):
        S = Q @ np.asarray(K[s:s + CHUNK], dtype=np.float32).T
        if exclude_self:
            S[S > 0.9999] = -1.0
        best = np.maximum(best, S.max(axis=1))
    return best


def quantiles(v: np.ndarray) -> dict:
    if not len(v):
        return {}
    q = np.quantile(v, [0.1, 0.5, 0.9])
    return {"n": int(len(v)), "p10": round(float(q[0]), 3), "median": round(float(q[1]), 3),
            "p90": round(float(q[2]), 3), "share_ge_0_85": round(float((v >= 0.85).mean()), 3),
            "share_ge_0_90": round(float((v >= 0.90).mean()), 3)}


# ------------------------------------------------------------------ stages

def stage1a(dropped, KX, kept_rows_by_tier, cap) -> dict:
    out = {}
    for tier in ("science", "patent", "funding", "market"):
        K = kept_rows_by_tier.get(tier)
        if K is None or not len(K):
            continue
        Kmat = KX[K] if len(K) < 400_000 else KX[np.sort(K[np.argsort((K * HASH_MUL) % HASH_MOD)[:400_000]])]
        Kmat = np.asarray(Kmat, np.float32)
        res = {}
        groups = defaultdict(list)
        for d in dropped:
            if d["tier"] == tier:
                groups[band_of(d["p"]) if d["head"] else "8B"].append(d)
        for band, items in sorted(groups.items()):
            sample = hsample(items, cap)
            Q = fetch_vectors([d["id"] for d in sample])
            res[band] = quantiles(nearest(Q, Kmat))
            res[band]["dropped_total"] = len(items)
            log(f"1a {tier:8s} {band:8s} {res[band]}")
        ctrl = K[np.argsort((K * HASH_MUL) % HASH_MOD)[:cap]]
        Qc = l2(np.asarray(KX[np.sort(ctrl)], np.float32))
        res["kept (control)"] = quantiles(nearest(Qc, Kmat, exclude_self=True))
        res["kept (control)"]["kept_total"] = int(len(K))
        log(f"1a {tier:8s} kept     {res['kept (control)']}")
        out[tier] = res
    return out


def stage1b(dropped, KX, kept_rows_by_tier, cap, min_pocket=40) -> dict:
    out = {}
    for tier in ("science", "patent", "funding", "market"):
        items = hsample([d for d in dropped if d["tier"] == tier], cap)
        if len(items) < 500:
            continue
        X = fetch_vectors([d["id"] for d in items])
        nests = detect_nests(X, k=pick_cells(len(items)), min_size=min_pocket)
        K = kept_rows_by_tier.get(tier)
        Kmat = np.asarray(KX[K], np.float32) if K is not None and len(K) else np.zeros((0, DIM), np.float32)
        pockets = []
        for n in nests:
            mem = n["members"]
            sims_self = X[mem] @ n["centroid"]
            radius = float(np.percentile(sims_self, 25))
            kept_in = 0
            for s in range(0, Kmat.shape[0], CHUNK):
                kept_in += int((Kmat[s:s + CHUNK] @ n["centroid"] >= radius).sum())
            titles = [items[i]["title"] for i in mem]
            central = [items[i]["title"] for i in mem[np.argsort(-sims_self)[:4]]]
            ps = [items[i]["p"] for i in mem if items[i]["p"] is not None]
            pockets.append({
                "size": int(len(mem)), "terms": title_terms(titles, top=4),
                "examples": [t[:110] for t in central], "radius": round(radius, 3),
                "kept_inside": kept_in, "kept_per_dropped": round(kept_in / len(mem), 2),
                "head_p_median": round(float(np.median(ps)), 2) if ps else None,
                "share_8b": round(sum(1 for i in mem if not items[i]["head"]) / len(mem), 2)})
        pockets.sort(key=lambda p: -p["size"])
        covered = sum(p["size"] for p in pockets)
        out[tier] = {"sample": len(items), "pockets": pockets,
                     "in_pockets": round(covered / len(items), 3),
                     "orphan_pockets": [p for p in pockets if p["kept_per_dropped"] < 0.5]}
        log(f"1b {tier}: {len(pockets)} pockets in {len(items)} dropped, "
            f"{len(out[tier]['orphan_pockets'])} with fewer than one kept per two dropped")
    return out


def stage2(dropped, KX, kept_rows_by_tier, cap) -> dict:
    with get_connection() as c:
        runs = [int(r["id"]) for r in c.execute(
            "SELECT max(id) AS id FROM emerging_runs GROUP BY scope").fetchall()]
        rows = c.execute(
            "SELECT run_id, centroid, threshold, age_months, calendar FROM emerging_nests "
            "WHERE run_id = ANY(?)", (runs,)).fetchall()
    C = l2(np.vstack([np.frombuffer(bytes(r["centroid"]), np.float32)[:DIM] for r in rows]))
    thr = np.array([float(r["threshold"]) for r in rows], np.float32)
    this_year = date.today().year

    def young(r) -> bool:
        cal = json.loads(r["calendar"]) if r["calendar"] else None
        if cal:
            firsts = [(cal.get(k) or {}) for k in ("science", "patent")]
            firsts = [f for f in firsts if f.get("first") is not None]
            if firsts:
                return all(not f.get("edge") and f["first"] >= this_year - 1 for f in firsts)
        return r["age_months"] is not None and r["age_months"] <= 18
    yng = np.array([young(r) for r in rows])

    def hit_rates(Q: np.ndarray) -> tuple[float, float]:
        A = (Q @ C.T) >= thr[None, :]
        return float(A.any(axis=1).mean()), float(A[:, yng].any(axis=1).mean()) if yng.any() else 0.0

    out = {"nests": int(len(rows)), "young_nests": int(yng.sum()), "runs": len(runs)}
    for tier in ("science", "patent", "funding", "market"):
        items = hsample([d for d in dropped if d["tier"] == tier], cap)
        K = kept_rows_by_tier.get(tier)
        if len(items) < 200 or K is None:
            continue
        d_any, d_young = hit_rates(fetch_vectors([d["id"] for d in items]))
        ctrl = np.sort(K[np.argsort((K * HASH_MUL) % HASH_MOD)[:cap]])
        k_any, k_young = hit_rates(l2(np.asarray(KX[ctrl], np.float32)))
        out[tier] = {"dropped_sample": len(items), "dropped_in_any_nest": round(d_any, 3),
                     "kept_in_any_nest": round(k_any, 3), "dropped_in_young_nest": round(d_young, 4),
                     "kept_in_young_nest": round(k_young, 4),
                     "estimated_dropped_in_young_nests": int(round(d_young * sum(
                         1 for d in dropped if d["tier"] == tier)))}
        log(f"2  {tier}: {out[tier]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    cap1, cap1b, cap2 = (800, 6000, 1500) if args.quick else (3000, 30000, 6000)
    t0 = time.time()
    log("loading the kept copy …")
    KX, kids, ktier, kmonth, keep = load_kept()
    kept_rows_by_tier = {TIER_NAMES[t]: np.flatnonzero(keep & (ktier == t)) for t in range(len(TIER_NAMES))}
    log("kept per tier: " + ", ".join(f"{t} {len(v):,}" for t, v in kept_rows_by_tier.items()))
    dropped = dropped_index()
    by = Counter((d["tier"], "head" if d["head"] else "8B") for d in dropped)
    log(f"dropped with a vector: {len(dropped):,} — " + ", ".join(f"{k[0]}/{k[1]} {v:,}" for k, v in sorted(by.items())))
    report = {"date": date.today().isoformat(), "quick": args.quick,
              "kept_per_tier": {t: int(len(v)) for t, v in kept_rows_by_tier.items()},
              "dropped_with_vector": {f"{k[0]}/{k[1]}": v for k, v in sorted(by.items())}}
    report["stage1a_proximity"] = stage1a(dropped, KX, kept_rows_by_tier, cap1)
    report["stage1b_dropped_topics"] = stage1b(dropped, KX, kept_rows_by_tier, cap1b)
    report["stage2_emerging"] = stage2(dropped, KX, kept_rows_by_tier, cap2)
    report["seconds"] = round(time.time() - t0)
    out = DATA_DIR / ("filter_audit_quick.json" if args.quick else "filter_audit.json")
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"written {out} ({report['seconds']} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
