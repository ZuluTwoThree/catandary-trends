#!/usr/bin/env python3
"""Two-layer trend & mega-trend discovery CLI (docs/mega_discovery_architecture.md).

Read-only. Reduce (PCA) → cluster (HDBSCAN) → characterize on two axes (reach +
maturity). NEW mega-candidates are named by Claude Sonnet 5.

  # Scope layer (customer-facing Macro/Micro + intersection trends)
  python scripts/discover_trends.py --layer scope --vertical FOOD
  python scripts/discover_trends.py --layer scope --pair HEALTH,TECH
  python scripts/discover_trends.py --layer scope --all-scopes

  # Mega layer (global themes, two-axis characterization, verdicts vs canonical)
  python scripts/discover_trends.py --layer mega                  # tier-balanced, source-capped
  python scripts/discover_trends.py --layer mega --strata proportional --source-cap 0
  python scripts/discover_trends.py --layer mega --sample 150000 --dim1024
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


# Mega layer runs HDBSCAN, which is costly at 100k+ points → we cluster a sample.
# WHICH sample matters more than its size: the corpus is not a neutral mix (two
# feeds hold ~25 % of it, and the market tier outweighs the early tiers 3:1), so a
# proportional draw hands density clustering the ingest bias instead of the trend
# structure. Default draw is tier-balanced and source-capped (see plan_sample).
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
def _draw(scope: str, args, default_sample: int = 0):
    """Pick the signals to cluster and load them with embeddings.

    Returns (rows, sample_report). Without --sample the scope layer still loads
    the full slice (KMeans partitions everything); the mega layer always samples.
    """
    want = args.sample or default_sample
    meta = discovery.load_scope_meta(scope, args.status, args.dim1024)
    print(f"[{scope}] {len(meta)} signals with embedding")
    if want and len(meta) > want:
        ids, rep = discovery.plan_sample(meta, want, args.strata, args.source_cap, args.seed)
        print(f"  drawing {rep['drawn']} of {len(meta)} · strata={rep['strata']}"
              + (f" · source cap {args.source_cap:.0%} (max {rep['per_source_max']})"
                 if args.source_cap else " · no source cap"))
        for tier, c in sorted(rep["tiers"].items()):
            print(f"    {tier:<8} avail {c['available']:>7} → drawn {c['drawn']:>6}")
        if rep["sources_capped"]:
            top = list(rep["sources_capped"].items())[:5]
            print("    capped: " + ", ".join(f"{s} {v['drawn']}/{v['available']}"
                                             for s, v in top))
        rows = discovery.load_scope(scope, args.status, ids=ids, dim1024=args.dim1024)
    else:
        rep = {"requested": want, "drawn": len(meta), "strata": "none (full scope)",
               "source_cap": 0}
        rows = discovery.load_scope(scope, args.status, args.limit, dim1024=args.dim1024)
    return rows, rep


def _load_reduce(scope: str, args):
    """Load a scope, build the embedding matrix, PCA-reduce. Returns (rows, Xr) or None."""
    rows, _ = _draw(scope, args)
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
    rows, sample_rep = _draw("global", args, MEGA_MAX_POINTS)
    if len(rows) < 200:
        print("  too few — skipping")
        return
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
                  "embedding_dim": "1024 (Matryoshka prefix)" if args.dim1024 else "4096",
                  "method": "PCA->HDBSCAN, two-axis (reach+maturity) characterization",
                  "sample": sample_rep},
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
    ap.add_argument("--limit", type=int, default=0,
                    help="raw SQL LIMIT (physical row order, NOT random) — smoke tests only")
    ap.add_argument("--sample", type=int, default=0,
                    help=f"signals to draw (mega default {MEGA_MAX_POINTS}; scope: full slice)")
    ap.add_argument("--strata", choices=["tier", "proportional"], default="tier",
                    help="tier = balance the 4 lead-time tiers; proportional = corpus mix")
    ap.add_argument("--source-cap", type=float, default=0.05,
                    help="max share of the sample one source may hold (0 = off)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--dim1024", action="store_true",
                    help="cluster the 1024-D Matryoshka prefix (4x less to load)")
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
