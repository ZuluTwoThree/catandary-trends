#!/usr/bin/env python3
"""Two-layer trend & mega-trend discovery CLI (docs/mega_discovery_architecture.md).

Read-only. Reduce (PCA) → cluster (HDBSCAN) → characterize on two axes (reach +
maturity). NEW mega-candidates are named by Claude Sonnet 5.

  # Scope layer (customer-facing Macro/Micro + intersection trends)
  python scripts/discover_trends.py --layer scope --vertical FOOD
  python scripts/discover_trends.py --layer scope --pair HEALTH,TECH
  python scripts/discover_trends.py --layer scope --all-scopes

  # Mega layer (global themes, two-axis characterization, verdicts vs canonical)
  python scripts/discover_trends.py --layer mega
  python scripts/discover_trends.py --layer mega --limit 120000   # faster sample
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import yaml
from pydantic import BaseModel

from pipeline import discovery
from pipeline.config import PROJECT_ROOT, load_mega_trends
from pipeline.discovery import VERTICALS
from pipeline.foresight import build_matrix

# Cross-vertical pairs with enough signal/source/time depth (scope analysis 2026-07-03):
# SOLID (>=5k) + OK (>=2k). Sparser pairs and all triples are dropped.
VIABLE_PAIRS = [
    "HEALTH&TECH", "BIZ&TECH", "ECO&TECH", "BIZ&ECO", "FOOD&TECH", "ECO&FOOD",
    "BIZ&LIFESTYLE", "BIZ&HEALTH", "LIFESTYLE&TECH", "BIZ&FASHION", "FASHION&TECH",
    "ECO&HEALTH", "ECO&LIFESTYLE", "FASHION&LIFESTYLE", "HEALTH&LIFESTYLE",
    "FOOD&HEALTH", "BIZ&FOOD", "DESIGN&ECO", "ECO&FASHION", "DESIGN&FASHION",
    "DESIGN&LIFESTYLE", "DESIGN&TECH",
]


# Mega layer runs HDBSCAN, which is costly at 100k+ points. Mega-themes are large
# (tens of thousands of signals) → a random ~50k sample captures them reliably, and
# HDBSCAN is fast in a low-dim space. (Scope layer clusters the full slice with KMeans.)
MEGA_MAX_POINTS = 50_000
MEGA_REDUCE_DIM = 15


# ------------------------------------------------------------- Sonnet labeling
class MegaLabel(BaseModel):
    name_en: str
    name_de: str
    description: str


_LABEL_SYS = ("You name cross-industry MEGA-TRENDS (10-25 year horizon) for a trend "
              "intelligence taxonomy. Given representative signal titles and tags, output "
              "a broad, durable mega-trend name (not a narrow product), a German name, and "
              "a one-sentence description. Broad and timeless, not a passing micro-trend.")


def label_new(tags: list[str], titles: list[str], model: str, backend: str) -> dict | None:
    prompt = ("Representative titles:\n- " + "\n- ".join(titles[:8]) +
              "\n\nTop tags: " + ", ".join(tags[:12]) + "\n\nName this mega-trend.")
    try:
        if backend == "anthropic":
            from pipeline import anthropic_client
            r = anthropic_client.chat_structured(model=model, prompt=prompt,
                                                 schema=MegaLabel, system=_LABEL_SYS,
                                                 temperature=None)
        else:
            from pipeline import llamacpp_client
            r = llamacpp_client.chat_structured(model=model, prompt=prompt, schema=MegaLabel,
                                                system=_LABEL_SYS, temperature=0.3)
        return r.model_dump() if r else None
    except Exception:
        return None


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "unnamed"


# -------------------------------------------------------------- cluster+report
def _load_reduce(scope: str, args):
    """Load a scope, build the embedding matrix, PCA-reduce. Returns (rows, Xr) or None."""
    rows = discovery.load_scope(scope, args.status, args.limit)
    print(f"[{scope}] {len(rows)} signals with embedding")
    if len(rows) < 200:
        print("  too few — skipping\n")
        return None
    Xr = discovery.reduce_dims(build_matrix(rows), args.reduce_dim)
    return rows, Xr


def run_scope(scope: str, args) -> None:
    t0 = time.time()
    lr = _load_reduce(scope, args)
    if not lr:
        return
    rows, Xr = lr
    labels, _ = discovery.cluster_partition(Xr)  # partition: every signal placed
    res = discovery.characterize(rows, Xr, labels)
    print(f"  {res['n_clusters']} sub-themes, {round(time.time()-t0,1)}s")
    print(f"\n── {scope} · trends (by size) ──")
    for c in sorted(res["clusters"], key=lambda x: -x["size"])[:args.top]:
        lead = (f"{c['lead_tier']}→market {c['lead_months']}mo"
                if c["lead_months"] is not None else "—")
        print(f"  {c['label'][:44]:<44} n={c['size']:<5} src={c['n_sources']:<3} "
              f"reach={c['vertical_entropy']:.2f} tiers={c['maturity_span']} "
              f"dur={c['durability']:.2f} lead={lead}")
        print(f"     tags: {', '.join(c['top_tags'][:6])}")


def run_mega(args) -> None:
    t0 = time.time()
    rows = discovery.load_scope("global", args.status, args.limit)
    print(f"[global] {len(rows)} signals with embedding")
    if len(rows) < 200:
        print("  too few — skipping")
        return
    if len(rows) > MEGA_MAX_POINTS:
        idx = sorted(np.random.default_rng(42).choice(len(rows), MEGA_MAX_POINTS, replace=False))
        rows = [rows[i] for i in idx]
        print(f"  sampled to {len(rows)} for density clustering (mega-themes survive sampling)")
    Xr = discovery.reduce_dims(build_matrix(rows), MEGA_REDUCE_DIM)
    labels = discovery.cluster_density(Xr, args.min_cluster_size)  # density + noise
    res = discovery.characterize(rows, Xr, labels)
    print(f"  {res['n_clusters']} themes, {res['noise_frac']*100:.0f}% noise, "
          f"{round(time.time()-t0,1)}s")
    canonical = {mt["key"]: mt for mt in load_mega_trends()}
    clusters = res["clusters"]

    # verdict vs canonical, using the members' existing mega_trend labels
    idx_by = defaultdict(list)
    for i, lab in enumerate(labels):
        if lab >= 0:
            idx_by[int(lab)].append(i)
    dom_clusters = defaultdict(list)
    for c in clusters:
        members = [rows[i] for i in idx_by[c["cluster"]]]
        mt = Counter(m["mega_trend"] for m in members if m["mega_trend"])
        dom, dom_n = (mt.most_common(1)[0] if mt else (None, 0))
        c["dom_existing"], c["dom_purity"] = dom, round(dom_n / c["size"], 3) if c["size"] else 0
        c["_mt_dist"] = mt
        if c["dom_purity"] >= args.covered_purity and dom:
            c["verdict"] = "COVERED"
        elif c["dom_purity"] < args.new_purity:
            # a genuine NEW mega-trend must also score high on the two axes
            c["verdict"] = "NEW" if c["mega_score"] >= args.min_mega_score else "EMERGING"
        else:
            big = [k for k, n in mt.items() if n / c["size"] >= 0.25]
            c["verdict"] = "MERGE" if len(big) >= 2 else "MIXED"
        if dom and c["dom_purity"] >= 0.30 and c["size"] >= 50:
            dom_clusters[dom].append(c["cluster"])
    splits = {mt: cids for mt, cids in dom_clusters.items() if len(cids) >= 2}

    # stability
    ari = discovery.stability_ari(Xr, labels, min_cluster_size=args.min_cluster_size)

    order = {"NEW": 0, "MERGE": 1, "MIXED": 2, "EMERGING": 3, "COVERED": 4}
    clusters.sort(key=lambda c: (order[c["verdict"]], -c["mega_score"]))

    print("\n" + "=" * 82)
    print(f"MEGA DISCOVERY — {res['n_clusters']} themes over {len(rows)} signals "
          f"({res['noise_frac']*100:.0f}% noise) · {len(canonical)} canonical")
    print(f"cluster stability (ARI, 80% resample): {ari:.2f}  "
          f"{'(stable)' if ari >= 0.5 else '(weak — interpret with care)'}")
    print("=" * 82)
    print("verdicts:", dict(Counter(c["verdict"] for c in clusters)),
          "| SPLIT:", len(splits))
    print("\nranked by mega_score (reach × maturity × durability):\n")

    candidates = []
    for c in clusters:
        lead = (f"{c['lead_tier']}→market {c['lead_months']}mo"
                if c["lead_months"] is not None else "—")
        print(f"━━ [{c['verdict']:8s}] {c['label'][:40]:<40} mega={c['mega_score']:.2f} "
              f"n={c['size']} reach={c['vertical_entropy']:.2f} tiers={c['maturity_span']} "
              f"dur={c['durability']:.2f}")
        print(f"     verticals {c['verticals']} | dominant existing: {c['dom_existing']} "
              f"({c['dom_purity']*100:.0f}%) | lead: {lead}")
        print(f"     tags: {', '.join(c['top_tags'][:8])}")
        print(f"     • {c['rep_titles'][0][:88] if c['rep_titles'] else '—'}")
        if c["verdict"] == "NEW":
            label = None if args.no_label else label_new(
                c["top_tags"], c["rep_titles"], args.label_model, args.label_backend)
            name = (label or {}).get("name_en") or "[REVIEW] " + (c["label"])
            candidates.append({
                "key": _slug(name), "name_en": name,
                "name_de": (label or {}).get("name_de", ""),
                "description": (label or {}).get("description", ""),
                "mega_score": c["mega_score"], "reach": c["vertical_entropy"],
                "maturity_span": c["maturity_span"], "durability": c["durability"],
                "lead_tier": c["lead_tier"], "lead_months": c["lead_months"],
                "signal_count": c["size"], "verticals": c["verticals"],
                "_provenance": f"cluster {c['cluster']}, purity {c['dom_purity']:.2f}",
            })
            print(f"     → PROPOSED NEW: {name}")
        print()

    if splits:
        print("── SPLIT candidates (one canonical spread across dense clusters) ──")
        for mt, cids in splits.items():
            print(f"   {mt} → clusters {cids}")
        print()
    orphan = [k for k in canonical if k not in {c["dom_existing"] for c in clusters if c["dom_existing"]}]
    if orphan:
        print("── Canonical NOT dominant in any theme (too broad / stale?) ──")
        print("  ", ", ".join(orphan), "\n")

    out = {
        "_meta": {"generated": datetime.now(timezone.utc).isoformat(),
                  "note": "PROPOSAL ONLY — read-only; curate into mega_trends.yaml by hand.",
                  "signals": len(rows), "n_themes": res["n_clusters"],
                  "noise_frac": res["noise_frac"], "stability_ari": round(ari, 3),
                  "method": "PCA->HDBSCAN, two-axis (reach+maturity) characterization"},
        "proposed_new": candidates,
        "split_candidates": {mt: cids for mt, cids in splits.items()},
        "canonical_orphans": orphan,
    }
    Path(args.out).write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False),
                              encoding="utf-8")
    print(f"→ wrote {len(candidates)} NEW + {len(splits)} split(s) to {args.out}")
    print("  (mega_trends.yaml untouched)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Two-layer trend/mega-trend discovery (read-only)")
    ap.add_argument("--layer", choices=["scope", "mega"], required=True)
    ap.add_argument("--vertical", help="scope layer: one vertical")
    ap.add_argument("--pair", help="scope layer: 'A,B' cross-vertical pair")
    ap.add_argument("--all-scopes", action="store_true",
                    help="scope layer: all 8 verticals + viable pairs")
    ap.add_argument("--status", default="signal,published")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--reduce-dim", type=int, default=50)
    ap.add_argument("--min-cluster-size", type=int, default=None)
    ap.add_argument("--top", type=int, default=15, help="scope: clusters to print")
    ap.add_argument("--new-purity", type=float, default=0.35)
    ap.add_argument("--covered-purity", type=float, default=0.55)
    ap.add_argument("--min-mega-score", type=float, default=0.45,
                    help="min mega_score for a low-purity cluster to be NEW (else EMERGING)")
    ap.add_argument("--no-label", action="store_true")
    ap.add_argument("--label-backend", choices=["anthropic", "local"], default="anthropic")
    ap.add_argument("--label-model", default="claude-sonnet-5")
    ap.add_argument("--out", default=str(PROJECT_ROOT / "mega_discovery.candidate.yaml"))
    args = ap.parse_args()

    if args.layer == "mega":
        run_mega(args)
    else:
        if args.all_scopes:
            for v in VERTICALS:
                run_scope(f"vertical:{v}", args)
            for p in VIABLE_PAIRS:
                run_scope(f"pair:{p.replace('&', '&')}", args)
        elif args.pair:
            a, b = [x.strip().upper() for x in args.pair.split(",")]
            run_scope(f"pair:{a}&{b}", args)
        elif args.vertical:
            run_scope(f"vertical:{args.vertical.upper()}", args)
        else:
            ap.error("scope layer needs --vertical / --pair / --all-scopes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
