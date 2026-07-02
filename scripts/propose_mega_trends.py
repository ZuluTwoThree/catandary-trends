#!/usr/bin/env python3
"""Propose mega-trend taxonomy changes from the signal-space clusters (read-only).

Clusters the signal pool at *mega-trend altitude* (few coarse clusters, near the
~21 canonical count), compares each cluster to the canonical mega_trends.yaml via
the already-assigned `trends.mega_trend` labels, and proposes:

  • NEW    — a cohesive cluster with no dominant existing mega-trend
  • SPLIT  — one existing mega-trend spread as the dominant label across ≥2 clusters
  • MERGE  — one cluster where ≥2 existing mega-trends each hold a big share
  • COVERED — cluster maps cleanly onto one existing mega-trend (+ momentum update)

It NEVER touches mega_trends.yaml. It writes a candidate file (default
`mega_trends.candidate.yaml`) with proposed NEW entries in the canonical schema +
a SPLIT/MERGE section, and prints a human-readable diff. NEW candidates are
LLM-labelled (name_en/name_de/description) via the local llama-server unless
--no-label is given (then names are derived from the top tags).

    python scripts/propose_mega_trends.py --status signal,published
    python scripts/propose_mega_trends.py --k 24 --no-label
    python scripts/propose_mega_trends.py --status signal --limit 200000

Design notes:
  - Altitude: default k is silhouette-picked in a MEGA range (16-30), NOT the fine
    range of cluster_trajectory_demo — proposals must sit at mega-trend granularity.
  - Momentum uses share-of-voice (early vs late window), not raw counts, so a
    growing corpus / uneven source onboarding doesn't masquerade as trend growth.
  - Read-only + candidate file: the taxonomy is product-facing; a human approves.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import yaml
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from pipeline.config import (
    PROJECT_ROOT, load_mega_trends, STAGE_8B_MODEL, STAGE_8B_BACKEND,
)
from pipeline.db import get_connection


# ----------------------------------------------------------------- data loading
def load_signals(status: str, limit: int) -> list[dict]:
    where = ["t.embedding IS NOT NULL"]
    params: list = []
    if status and status.lower() != "all":
        sts = [s.strip() for s in status.split(",")]
        where.append(f"t.status IN ({','.join('?' * len(sts))})")
        params += sts
    sql = ("SELECT t.id, t.title_en, t.mega_trend, t.tags, t.primary_vertical, "
           "       r.published_date, t.embedding "
           "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
           f"WHERE {' AND '.join(where)}")
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
    out = []
    for r in rows:
        emb = r["embedding"]
        if not isinstance(emb, (bytes, bytearray)) or len(emb) < 4:
            continue
        r["_emb"] = bytes(emb)
        r["embedding"] = None
        try:
            r["tags"] = json.loads(r["tags"]) if r["tags"] else []
        except Exception:
            r["tags"] = []
        out.append(r)
    return out


def build_matrix(rows: list[dict]) -> np.ndarray:
    dim = len(rows[0]["_emb"]) // 4
    X = np.empty((len(rows), dim), dtype=np.float32)
    for i, r in enumerate(rows):
        X[i] = np.frombuffer(r["_emb"], dtype=np.float32)
        r["_emb"] = None
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)  # spherical
    return X


def pick_k(X: np.ndarray, lo: int, hi: int) -> int:
    n = X.shape[0]
    if n < 200:
        return max(2, min(lo, n // 20))
    sample = X if n <= 4000 else X[np.random.default_rng(42).choice(n, 4000, replace=False)]
    best_k, best_s = lo, -1.0
    for k in range(lo, hi + 1):
        labels = KMeans(n_clusters=k, n_init=4, random_state=42).fit_predict(sample)
        s = silhouette_score(sample, labels, sample_size=min(2000, len(sample)), random_state=42)
        if s > best_s:
            best_k, best_s = k, s
    return best_k


# ---------------------------------------------------------------- momentum (SoV)
def month_key(d) -> str | None:
    s = str(d)[:7]
    return s if len(s) == 7 and s[4] == "-" else None


def sov_momentum(members: list[dict], all_month_totals: Counter, months: list[str]) -> tuple[str, float]:
    """Share-of-voice Δ between the early and late thirds of the covered window."""
    if len(months) < 6:
        return "unknown", 0.0
    third = len(months) // 3
    early, late = months[:third], months[-third:]
    m_cnt = Counter(month_key(m["published_date"]) for m in members)
    def share(win):
        num = sum(m_cnt.get(mo, 0) for mo in win)
        den = sum(all_month_totals.get(mo, 0) for mo in win)
        return (num / den) if den else 0.0
    delta = (share(late) - share(early)) * 100  # percentage points
    tag = "rising" if delta > 1.0 else "declining" if delta < -1.0 else "stable"
    return tag, round(delta, 1)


# ------------------------------------------------------------------ LLM labeling
def llm_label(top_tags: list[str], titles: list[str]) -> dict | None:
    """Name + describe a NEW candidate cluster via the local llama-server."""
    from pydantic import BaseModel

    class MegaLabel(BaseModel):
        name_en: str
        name_de: str
        description: str

    from pipeline import llamacpp_client
    sys_p = ("You name cross-industry MEGA-TRENDS (10-25 year horizon) for a trend "
             "intelligence taxonomy. Given representative signal titles and tags, "
             "output a broad, durable mega-trend name (not a narrow product), a "
             "German name, and a one-sentence description. Broad and timeless, not "
             "a passing micro-trend.")
    prompt = ("Representative titles:\n- " + "\n- ".join(titles[:8]) +
              "\n\nTop tags: " + ", ".join(top_tags[:12]) +
              "\n\nName this mega-trend.")
    try:
        r = llamacpp_client.chat_structured(model=STAGE_8B_MODEL, prompt=prompt,
                                            schema=MegaLabel, system=sys_p, temperature=0.3)
        return r.model_dump() if r else None
    except Exception:
        return None


# Tags that make bad mega-trend names (geographies, signal-types, generic terms).
# Only used for the --no-label placeholder; the LLM path names properly.
_GENERIC_TAGS = {
    "germany", "usa", "china", "europe", "uk", "us", "eu", "france", "india",
    "regulation", "government regulation", "government policy", "economic_policy",
    "product_launch", "product launch", "consumer_behavior", "consumer behavior",
    "funding", "research", "market_shift", "partnership", "innovation",
    "sustainability", "policy", "data_privacy", "data privacy",
}


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    s = re.sub(r"^_?review_?", "", s)  # drop the [REVIEW] prefix from the slug
    return s or "unnamed_mega_trend"


# ------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Propose mega-trend taxonomy changes (read-only)")
    ap.add_argument("--status", default="signal,published",
                    help="trend statuses to cluster (comma list, or 'all')")
    ap.add_argument("--k", type=int, help="cluster count (default: silhouette in --k-range)")
    ap.add_argument("--k-range", default="16,30", help="mega-altitude k search range lo,hi")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--new-purity", type=float, default=0.35,
                    help="max dominant-existing share for a cluster to count as NEW")
    ap.add_argument("--covered-purity", type=float, default=0.55,
                    help="min dominant-existing share for a cluster to count as COVERED")
    ap.add_argument("--min-cohesion", type=float, default=0.30,
                    help="absolute cohesion floor for a NEW candidate (the effective bar is "
                         "max(this, median cluster cohesion) — below it a no-dominant cluster is NOISE)")
    ap.add_argument("--no-label", action="store_true", help="skip LLM naming (use tag-derived names)")
    ap.add_argument("--out", default=str(PROJECT_ROOT / "mega_trends.candidate.yaml"))
    args = ap.parse_args()

    rows = load_signals(args.status, args.limit)
    print(f"signals (status={args.status}) with embedding: {len(rows)}")
    if len(rows) < 200:
        print("Too few signals for a meaningful proposal.")
        return 0
    X = build_matrix(rows)

    lo, hi = (int(x) for x in args.k_range.split(","))
    k = args.k or pick_k(X, lo, hi)
    print(f"clustering {X.shape[0]}×{X.shape[1]} into k={k} at mega-altitude (spherical KMeans) ...\n")
    km = KMeans(n_clusters=k, n_init=8, random_state=42).fit(X)
    labels, centroids = km.labels_, km.cluster_centers_

    # global monthly totals (SoV denominator)
    all_months = Counter(month_key(r["published_date"]) for r in rows if month_key(r["published_date"]))
    months = sorted(m for m in all_months if m)

    canonical = {mt["key"]: mt for mt in load_mega_trends()}
    clusters: dict[int, list[dict]] = defaultdict(list)
    for i, lab in enumerate(labels):
        # int() — KMeans labels are np.int32, which yaml.safe_dump can't represent
        clusters[int(lab)].append(rows[i])

    analyses = []
    for cid, members in clusters.items():
        idx = [i for i, l in enumerate(labels) if l == cid]
        cohesion = float(np.mean(X[idx] @ centroids[cid]))  # mean cosine to centroid
        strength = "strong" if cohesion > 0.60 else "moderate" if cohesion > 0.45 else "weak"
        mt_dist = Counter(m["mega_trend"] for m in members if m["mega_trend"])
        dom, dom_n = (mt_dist.most_common(1)[0] if mt_dist else (None, 0))
        purity = dom_n / len(members)
        verts = [v for v, _ in Counter(m["primary_vertical"] for m in members if m["primary_vertical"]).most_common(3)]
        tags = [t for t, _ in Counter(t for m in members for t in (m["tags"] or [])).most_common(12)]
        # representative titles = closest to centroid
        sims = X[idx] @ centroids[cid]
        rep = [members[j]["title_en"] for j in np.argsort(-sims)[:8] if members[j]["title_en"]]
        mom, delta = sov_momentum(members, all_months, months)
        analyses.append(dict(cid=cid, size=len(members), cohesion=cohesion, strength=strength,
                             dom=dom, purity=purity, mt_dist=mt_dist, verts=verts, tags=tags,
                             rep=rep, momentum=mom, delta=delta))

    # A genuine NEW mega-trend is a *coherent* cluster with no existing mega-trend
    # covering it — not a low-cohesion grab-bag (KMeans' residual junk-drawer).
    # Gate NEW on above-typical cohesion (mega-clusters are broad, so use the run's
    # own median as the bar, with an absolute floor).
    med_coh = float(np.median([a["cohesion"] for a in analyses]))
    new_coh_bar = max(args.min_cohesion, med_coh)
    for a in analyses:
        if a["purity"] >= args.covered_purity and a["dom"]:
            a["verdict"] = "COVERED"
        elif a["purity"] < args.new_purity:
            a["verdict"] = "NEW" if a["cohesion"] >= new_coh_bar else "NOISE"
        else:
            big = [(k_, n_) for k_, n_ in a["mt_dist"].items() if n_ / a["size"] >= 0.25]
            a["verdict"] = "MERGE" if len(big) >= 2 else "MIXED"

    # SPLIT detection: an existing mega-trend dominant in ≥2 substantial clusters
    dom_clusters = defaultdict(list)
    for a in analyses:
        if a["dom"] and a["purity"] >= 0.30 and a["size"] >= max(50, len(rows) // (k * 3)):
            dom_clusters[a["dom"]].append(a["cid"])
    splits = {mt: cids for mt, cids in dom_clusters.items() if len(cids) >= 2}

    # ---- report ----
    order = {"NEW": 0, "MERGE": 1, "MIXED": 2, "NOISE": 3, "COVERED": 4}
    analyses.sort(key=lambda a: (order[a["verdict"]], -a["size"]))
    print("=" * 78)
    print(f"MEGA-TREND PROPOSAL — {k} clusters over {len(rows)} signals "
          f"({len(canonical)} canonical mega-trends)")
    print("=" * 78)
    counts = Counter(a["verdict"] for a in analyses)
    print("verdicts:", dict(counts), "| SPLIT candidates:", len(splits), "\n")

    candidates = []
    for a in analyses:
        head = (f"━━ [{a['verdict']}] cluster {a['cid']} · {a['size']} signals · "
                f"{a['strength']} (coh {a['cohesion']:.2f}) · momentum {a['momentum']} ({a['delta']:+.1f}pp)")
        print(head)
        print(f"     verticals: {a['verts']} | dominant existing: {a['dom']} ({a['purity']*100:.0f}%)")
        print(f"     tags: {', '.join(a['tags'][:8])}")
        print(f"     • {a['rep'][0][:88] if a['rep'] else '—'}")
        if a["verdict"] == "NEW":
            label = None
            if not args.no_label and STAGE_8B_BACKEND == "llamacpp":
                label = llm_label(a["tags"], a["rep"])
            if (label or {}).get("name_en"):
                name_en = label["name_en"]
            else:
                # tag-derived placeholder — drop geographic/generic tags that make
                # bogus names ("Germany", "Regulation"), keep the first thematic one.
                themal = [t for t in a["tags"] if t.lower() not in _GENERIC_TAGS]
                base = (themal[0] if themal else (a["tags"][0] if a["tags"] else f"cluster {a['cid']}"))
                name_en = "[REVIEW] " + base.replace("_", " ").title()
            cand = {
                "key": slug(name_en),
                "name_en": name_en,
                "name_de": (label or {}).get("name_de", ""),
                "description": (label or {}).get("description",
                               f"Auto-proposed from cluster {a['cid']}; tags: {', '.join(a['tags'][:8])}"),
                "horizon": "unknown (review)",
                "momentum": a["momentum"],
                "cluster_strength": a["strength"],
                "signal_count": a["size"],
                "verticals": a["verts"],
                "_provenance": f"cluster {a['cid']}, purity {a['purity']:.2f}, cohesion {a['cohesion']:.2f}",
            }
            candidates.append(cand)
            print(f"     → PROPOSED NEW: {name_en}  (key: {cand['key']})")
        print()

    if splits:
        print("── SPLIT candidates (one mega-trend spread across multiple dense clusters) ──")
        for mt, cids in splits.items():
            print(f"   {mt}  → clusters {cids} (consider splitting into sub-mega-trends)")
        print()

    # canonical mega-trends not dominant anywhere → possibly stale/fragmented
    orphan = [k_ for k_ in canonical if k_ not in {a["dom"] for a in analyses if a["dom"]}]
    if orphan:
        print("── Canonical mega-trends NOT dominant in any cluster (review: too broad/stale?) ──")
        print("  ", ", ".join(orphan), "\n")

    # ---- write candidate file (never touches mega_trends.yaml) ----
    out = {
        "_meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "note": "PROPOSAL ONLY — review + merge into mega_trends.yaml by hand.",
            "signals": len(rows), "k": k, "status": args.status,
        },
        "proposed_new": candidates,
        "split_candidates": {mt: cids for mt, cids in splits.items()},
        "canonical_orphans": orphan,
    }
    Path(args.out).write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"→ wrote {len(candidates)} NEW candidate(s) + {len(splits)} split(s) to {args.out}")
    print("  (mega_trends.yaml is untouched — review the candidate file and merge by hand)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
