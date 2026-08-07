#!/usr/bin/env python3
"""Seed the expanded mega-trend taxonomy into `trends.mega_trend` (decision doc:
docs/mega_taxonomy_decision_2026-08-07.md, owner-approved 2026-08-07).

The four attractor labels (personalized_health, AI, financial_innovation,
clean_energy) plus the catch-all (inclusive_and_human_centric_design) hold 65 %
of the corpus while 18 keys starve. This script splits them along the discovery
clusters and writes the new assignments — which then serve as teacher labels for
the distill retrain (the head learns from `trends.mega_trend`).

Method, per attractor:
  1. Reproduce the discovery clustering (deterministic: plan_sample seed 42,
     PCA-50 seed 42, KMeans k=8 seed 42 — same path as
     `discover_trends.py --layer scope --mega <key>`).
  2. Map clusters → target keys via curated tag signatures (mirrors the D-run
     labels; a cluster that matches nothing stays with the attractor).
  3. Core members (closest `--core-frac` to their cluster centroid) become seeds
     directly.
  4. Expansion beyond the sample: nearest-centroid assignment over the FULL
     attractor population in the 1024-D Matryoshka space. A row is re-labelled
     only if its nearest centroid belongs to a mapped cluster AND its cosine
     similarity clears that cluster's conservative threshold (the 25th
     percentile of the core members' own similarity) — everything else keeps
     the attractor label. No LLM, no GPU.

  python scripts/seed_mega_keys.py --dry-run          # counts + mapping report
  python scripts/seed_mega_keys.py --execute
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

from pipeline import discovery
from pipeline.db import get_connection
from pipeline.foresight import build_matrix

SAMPLE = 40_000
K = 8
CORE_FRAC = 0.5
SIM_PCTL = 50   # expansion threshold = median core-member similarity (conservative)
MARGIN = 0.02   # expansion also needs this cosine margin over the 2nd-nearest centroid

# Cluster → target-key mapping via tag signatures (≥2 of a cluster's top-12 tags
# must hit; best score wins). Signatures written from the D-run logs
# (data/discovery/D_mega_splits.log) — the clustering is deterministic, but tag
# matching keeps the mapping readable and robust, and NOT matching is safe: the
# cluster simply stays with its attractor.
MAPPINGS: dict[str, list[tuple[str, set[str]]]] = {
    "personalized_health_and_longevity": [
        ("digital_healthcare_integration",
         {"health tech", "digital_health", "digital health", "telehealth",
          "health_tech", "healthcare access", "wellness"}),
        # Neuro→mental_health fires only on genuinely neuro-WELLNESS tags. The
        # first dry-run's broad signature (biomedical/genetic research) swept
        # cancer research and precision medicine into mental_health (57k!) —
        # those are the PH core and must stay.
        ("mental_health_and_neuro_wellness",
         {"mental health", "mental_health", "brain research", "neurology",
          "psychiatry", "psychology", "cognitive health"}),
    ],
    "artificial_intelligence_and_automation": [
        ("quantum_information_science",
         {"quantum computing", "quantum physics", "quantum materials",
          "nanotechnology", "astrophysics"}),
        ("next_generation_semiconductors",
         {"chip design", "semiconductor", "semiconductor manufacturing",
          "chip manufacturing", "semiconductor innovation", "neuromorphic computing"}),
        ("orbital_economy_expansion",
         {"space exploration", "space technology", "satellites",
          "space", "launch systems", "aerospace"}),
        # NO neuro rule here: the AI-side "neuroscience" cluster is ML research
        # (neural networks, association rules) — mapping it to mental-health
        # wellness was wrong in the first dry-run. Deviation from the B-table's
        # "Neuroscience (5.706 + 5.288)" documented in the run report.
    ],
    "financial_innovation_and_inclusion": [
        ("platformization_of_culture",
         {"music industry", "streaming services", "music streaming",
          "content monetization", "entertainment", "music rights"}),
    ],
    "clean_energy_transition": [
        # "electric vehicles" alone IS the cluster identity (the neighbouring
        # tags are generic renewables) — a strong marker in the top-3 suffices,
        # see STRONG_MARKERS below
        ("electric_and_autonomous_mobility",
         {"electric vehicles", "ev charging", "charging infrastructure",
          "automotive", "automotive industry", "e-mobility", "electric mobility",
          "sustainable transportation", "transportation", "mobility"}),
        ("climate_resilience_and_adaptation",
         {"climate change", "climate policy", "climate_change",
          "environmental policy", "climate science", "emissions"}),
        # only perovskite-/materials-SPECIFIC tags: "material science" and
        # "nanotechnology" also sit on the battery/storage clusters, which per
        # the decision doc STAY in clean_energy. If no run isolates a clean
        # perovskite cluster, this rule simply never fires — safer than moving
        # battery tech wrongly.
        ("bio_revolution_and_new_materials",
         {"perovskite solar cells", "nanomaterials", "quantum dots",
          "advanced materials", "biomaterials"}),
    ],
    "inclusive_and_human_centric_design": [
        ("creator_economy_and_platform_shift",
         {"social media", "content creation", "content_creation",
          "social media influence", "creators", "influencers"}),
        ("evolution_of_work_models",
         {"workplace culture", "workplace_culture", "remote work",
          "labor_rights", "labor rights", "hybrid work", "hr"}),
        ("education_and_lifelong_learning",
         {"education", "higher education", "stem education", "stem_education",
          "student retention", "lifelong learning", "edtech"}),
        # Urban/architecture goes to regenerative design (design-led key), not to
        # smart-spaces (IoT-led) — the cluster is architecture + sustainable
        # materials, not connected-home tech. Decision doc left this open;
        # resolved here, documented in the run report.
        ("regenerative_design_and_net_positive",
         {"urban design", "sustainable design", "architectural design",
          "interior design", "sustainable materials", "architecture"}),
        ("new_luxury_and_premiumization",
         {"brand strategy", "brand_strategy", "beauty industry",
          "consumer behavior", "consumer_behavior", "luxury"}),
        ("experience_economy_and_immersive_design",
         {"travel industry", "hotel industry", "tourism", "luxury travel",
          "post-pandemic recovery", "sustainable tourism", "cruise"}),
    ],
}


# A strong marker in a cluster's TOP-3 tags identifies the theme on its own —
# needed where tag normalisation collapses the variants of the one identifying
# tag into a single hit (electric_vehicles + "electric vehicles" → 1).
STRONG_MARKERS: dict[str, set[str]] = {
    "electric_and_autonomous_mobility": {"electric vehicles"},
    "quantum_information_science": {"quantum computing"},
    "next_generation_semiconductors": {"semiconductor", "chip design"},
    "bio_revolution_and_new_materials": {"perovskite solar cells"},
}

# Impure source clusters get a tighter core so the expansion centroid is not
# dragged by their mixed tail (the space cluster blends in UX/aviation rows).
CORE_FRAC_OVERRIDE: dict[str, float] = {
    "orbital_economy_expansion": 0.3,
}


def _norm(tag: str) -> str:
    return (tag or "").lower().replace("_", " ").replace("-", " ").strip()


def match_cluster(top_tags: list[str], rules: list[tuple[str, set[str]]],
                  min_hits: int = 2) -> str | None:
    """Best-scoring target key for a cluster's top tags, or None (stays put)."""
    tags = {_norm(t) for t in top_tags}
    top3 = {_norm(t) for t in top_tags[:3]}
    best, best_score = None, 0
    for target, sig in rules:
        if top3 & {_norm(m) for m in STRONG_MARKERS.get(target, ())}:
            return target
        score = len(tags & {_norm(s) for s in sig})
        if score > best_score:
            best, best_score = target, score
    return best if best_score >= min_hits else None


def expansion_threshold(sims: np.ndarray, pctl: float = SIM_PCTL) -> float:
    """Conservative similarity gate for full-population expansion: the given
    percentile of the CORE members' similarity to their own centroid. Members of
    the full population below it keep the attractor label."""
    return float(np.percentile(sims, pctl))


def _load_1024(scope_key: str) -> tuple[list[int], np.ndarray]:
    """All ids + 1024-D embeddings currently labelled with `scope_key`."""
    rows = discovery.load_scope(f"mega:{scope_key}", "signal,published", dim1024=True)
    ids = [r["id"] for r in rows]
    X = build_matrix(rows)
    return ids, X


def seed_attractor(attractor: str, rules: list[tuple[str, set[str]]],
                   report: list[str]) -> dict[int, str]:
    """Returns {trend_id: new_key} for one attractor."""
    t0 = time.time()
    meta = discovery.load_scope_meta(f"mega:{attractor}", "signal,published")
    ids, srep = discovery.plan_sample(meta, SAMPLE, "tier", 0.05, seed=42)
    rows = discovery.load_scope(f"mega:{attractor}", "signal,published", ids=ids)
    X4096 = build_matrix(rows)  # consumes each row's _emb — build ONCE, reuse
    Xr = discovery.reduce_dims(X4096, 50)
    labels, _ = discovery.cluster_partition(Xr, K)
    res = discovery.characterize(rows, Xr, labels)
    report.append(f"\n━━ {attractor} · {len(meta)} signals, sample {len(rows)}")

    # sample-index lists per cluster
    idx_by: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        if lab >= 0:
            idx_by.setdefault(int(lab), []).append(i)

    # map clusters, collect core members + their 1024-D centroids: the stored
    # embedding_1024 is the L2-normed 4096-prefix, so centroids computed on the
    # sample's prefix live in the same space as the full-population expansion
    X1024 = X4096[:, :1024].copy()
    del X4096
    X1024 /= np.clip(np.linalg.norm(X1024, axis=1, keepdims=True), 1e-9, None)
    id_of = [r["id"] for r in rows]
    core_ids_by_target: dict[str, list[int]] = {}
    mapped_centroids: list[tuple[str | None, np.ndarray, float]] = []

    for c in sorted(res["clusters"], key=lambda x: -x["size"]):
        cid, size = c["cluster"], c["size"]
        target = match_cluster(c["top_tags"], rules)
        tag_str = ", ".join(c["top_tags"][:5])
        report.append(f"   {'→ ' + target if target else '  (bleibt)':<42} "
                      f"n={size:<6} {c['label'][:38]:<38} [{tag_str}]")
        idxs = idx_by[cid]
        E = X1024[idxs]
        cen = E.mean(axis=0)
        cen /= max(np.linalg.norm(cen), 1e-9)
        sims = E @ cen
        if target is None:
            mapped_centroids.append((None, cen, 0.0))
            continue
        order = np.argsort(-sims)
        frac = CORE_FRAC_OVERRIDE.get(target, CORE_FRAC)
        core = order[: max(1, int(frac * size))]
        core_ids = [id_of[idxs[j]] for j in core]
        core_ids_by_target.setdefault(target, []).extend(core_ids)
        thr = expansion_threshold(sims[core])
        mapped_centroids.append((target, cen, thr))

    # expansion: nearest centroid over the attractor's FULL population
    assign: dict[int, str] = {}
    for target, ids_ in core_ids_by_target.items():
        for tid in ids_:
            assign[tid] = target
    all_ids, X_all = _load_1024(attractor)
    C = np.stack([cen for _, cen, _ in mapped_centroids])
    S = X_all @ C.T  # cosine (both sides L2-normed)
    order = np.argsort(-S, axis=1)
    nearest, second = order[:, 0], order[:, 1]
    margin = S[np.arange(len(all_ids)), nearest] - S[np.arange(len(all_ids)), second]
    n_exp = 0
    for row_i, tid in enumerate(all_ids):
        if tid in assign:
            continue
        tgt, _, thr = mapped_centroids[nearest[row_i]]
        # relabel only on a clear call: nearest centroid is a mapped one, the
        # similarity clears the cluster's own core median, AND the row is not
        # sitting on the boundary between two centroids
        if (tgt is not None and S[row_i, nearest[row_i]] >= thr
                and margin[row_i] >= MARGIN):
            assign[tid] = tgt
            n_exp += 1
    report.append(f"   core seeds {sum(len(v) for v in core_ids_by_target.values()):,} "
                  f"+ expansion {n_exp:,} = {len(assign):,} of {len(all_ids):,} "
                  f"({time.time()-t0:.0f}s)")
    return assign


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed expanded mega-trend keys (owner-approved split)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    from pipeline.config import load_mega_trends
    canon = {m["key"] for m in load_mega_trends()}
    for rules in MAPPINGS.values():
        for tgt, _ in rules:
            assert tgt in canon, f"target {tgt} fehlt in mega_trends.yaml"

    report: list[str] = []
    assign_all: dict[int, str] = {}
    origin: dict[int, str] = {}  # audit: which attractor each id came from
    for attractor, rules in MAPPINGS.items():
        a = seed_attractor(attractor, rules, report)
        assign_all.update(a)
        origin.update({tid: attractor for tid in a})

    print("\n".join(report))
    from collections import Counter
    dist = Counter(assign_all.values())
    print(f"\n== geplante Umlabelungen: {len(assign_all):,} ==")
    for k, n in dist.most_common():
        print(f"  {n:>7,}  {k}")

    if args.dry_run:
        print("\nDRY-RUN — nichts geschrieben. --execute zum Anwenden.")
        return 0

    # audit trail first (revert = replay old): data/discovery/seed_applied_*.jsonl
    import json
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    audit = Path("data/discovery") / f"seed_applied_{stamp}.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("w", encoding="utf-8") as f:
        for tid, key in assign_all.items():
            f.write(json.dumps({"id": tid, "old": origin[tid], "new": key}) + "\n")

    items = list(assign_all.items())
    with get_connection() as conn:
        for i in range(0, len(items), 5000):
            chunk = items[i:i + 5000]
            conn.executemany("UPDATE trends SET mega_trend = ? WHERE id = ?",
                             [(k, tid) for tid, k in chunk])
    print(f"\nEXECUTED — {len(items):,} trends umgelabelt. Audit: {audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
