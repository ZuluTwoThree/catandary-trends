#!/usr/bin/env python3
"""Yardstick for the signal cloud: does a different projection place topics better?

Owner question 2026-09-27: how can search and clustering in the 3D cloud get better?
Two levers are measured here against one fixed yardstick (CPU only, no GPU, no
writes to the database):

  lever 1 — the PCA bottleneck. Production goes L2 -> PCA 50 (keeps 39 % of the
            variance) -> UMAP. Variants: PCA 256, or UMAP with cosine straight on
            the 1024-dim prefix.
  lever 2 — writing style. Research, patents, funding and trade press land on
            separate continents even for the same topic, because the embedding
            encodes register. Variants: subtract each tier's mean vector
            ("tier_center") or project out the directions spanned by the tier
            means ("tier_nullspace") before projecting.

The yardstick, identical for every variant:

  base      a deterministic sample of `--per-month` signals a month over the
            window of the latest cloud run (same hash as pipeline.signal_space).
            The projection is FITTED on it.
  hits      the matches of 28 fixed search terms (titles/summaries/tags +
            research abstracts + patent abstracts, the three sources of the cloud
            search), capped per term and tier, PLACED with transform() like the
            production run places all 1.5M signals.
  fidelity  kept nearest neighbours @10 and trustworthiness of the 3D picture
            against the ORIGINAL 1024-dim space (not the preprocessed one — a
            variant must not win by redefining the space).
  purity    for labelled points, the share of their 10 nearest labelled
            neighbours that carry the same label: CPC subclass (examiner-
            assigned, patents), OpenAlex topic and subfield (research, via DOI).
            Measured in 3D and, as a ceiling, in the 1024-dim input.
  term_knn  for the hits of a term, the share of their 10 nearest neighbours
            (among base + all hits) that are hits of the same term — does a
            search light up one region or scattered dust?
  tier_gap  for each term with >= 10 hits in at least two tiers: mean distance
            between the tiers' centroids, divided by the median distance of
            random base pairs. 0 = research and market on the same spot, ~1 =
            as far apart as two random signals. Lever 2 exists to shrink this.

Output: data/space_eval/eval_projection.json (not versioned) + a table on stdout.
Usage:  .venv/bin/python scripts/space_eval/eval_projection.py [--per-month 200]
        [--variants baseline,pca256] [--terms 28]
"""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline import db as db_mod  # noqa: E402
from pipeline import signal_space as ss  # noqa: E402

OUT = ROOT / "data" / "space_eval"
SEED = 42
K = 10
TERM_CAP = 600        # hits per term, at most
TIER_CAP = 150        # ... and per tier, so one tier cannot fill the term alone
MIN_TIER_HITS = 10    # a tier needs this many hits of a term to get a centroid
FETCH_PER_SOURCE = 1500
PURITY_MAX = 20000    # labelled points per label type (evenly thinned beyond)

TERMS = [
    "solar panel", "perovskite", "solid-state battery", "lithium-ion battery",
    "green hydrogen", "carbon capture", "heat pump", "wind turbine",
    "electric vehicle", "CRISPR", "mRNA vaccine", "gene therapy", "microbiome",
    "plant-based", "precision fermentation", "cultivated meat", "insect protein",
    "large language model", "quantum computing", "semiconductor", "autonomous driving",
    "drone", "3D printing", "wearable", "blockchain", "recycling", "biodegradable packaging",
    "smart glasses",
]

FTS_VECTOR = ("to_tsvector('english', coalesce(t.title_en,'') || ' ' || "
              "coalesce(t.summary_en,'') || ' ' || coalesce(t.tags::text,''))")
TS = "websearch_to_tsquery('english', ?)"
HASH = f"mod(t.id::bigint * {ss.HASH_MUL}, {ss.HASH_MOD})"


def rows(sql: str, params=()) -> list[dict]:
    with db_mod.get_connection() as c:
        c.execute("SET statement_timeout = '600s'")
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------ the data

def window() -> list[str]:
    r = rows("SELECT months FROM signal_space_runs ORDER BY id DESC LIMIT 1")
    if r and r[0]["months"]:
        m = r[0]["months"]
        return json.loads(m) if isinstance(m, str) else list(m)
    return ss.month_window(time.strftime("%Y-%m"), ss.DEFAULT_MONTHS)


def term_hits(term: str, first: str, until: str) -> list[int]:
    """Up to FETCH_PER_SOURCE matches per source inside the window, hash-ordered."""
    date = "r.published_date >= ? AND r.published_date < ?"
    base = "t.status IN ('signal','published') AND t.embedding_1024 IS NOT NULL"
    sqls = [
        f"SELECT t.id FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id "
        f"WHERE {base} AND {date} AND {FTS_VECTOR} @@ {TS} ORDER BY {HASH} LIMIT {FETCH_PER_SOURCE}",
        f"SELECT t.id FROM research_signals rs JOIN trends t ON t.id = rs.trend_id "
        f"JOIN raw_entries r ON r.id = t.raw_entry_id "
        f"WHERE {base} AND {date} AND rs.tsv @@ {TS} ORDER BY {HASH} LIMIT {FETCH_PER_SOURCE}",
        f"SELECT t.id FROM patent_search ps JOIN raw_entries r ON r.pub_number = ps.pub_number "
        f"JOIN trends t ON t.raw_entry_id = r.id "
        f"WHERE {base} AND {date} AND ps.tsv @@ {TS} ORDER BY {HASH} LIMIT {FETCH_PER_SOURCE}",
    ]
    out: list[int] = []
    for sql in sqls:
        try:
            out += [int(r["id"]) for r in rows(sql, (first, until, term))]
        except Exception as e:  # noqa: BLE001 — one source may time out, like the cloud search
            log(f"  {term!r}: source failed ({e.__class__.__name__}) — continuing")
    return sorted(set(out), key=lambda i: (i * ss.HASH_MUL) % ss.HASH_MOD)


def cap_by_tier(ids: list[int], tier: dict[int, str | None]) -> list[int]:
    per: dict[str | None, int] = {}
    keep = []
    for i in ids:
        t = tier.get(i)
        if per.get(t, 0) >= TIER_CAP:
            continue
        per[t] = per.get(t, 0) + 1
        keep.append(i)
        if len(keep) >= TERM_CAP:
            break
    return keep


def labels(ids: list[int]) -> tuple[dict[int, set], dict[int, str], dict[int, str]]:
    """CPC subclasses (patents), OpenAlex topic and subfield (research)."""
    cpc: dict[int, set] = {}
    for start in range(0, len(ids), 20000):
        chunk = ids[start:start + 20000]
        for r in rows("""SELECT t.id, array_agg(DISTINCT pc.subclass) AS subs
                         FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id
                         JOIN patent_cpc pc ON pc.pub_number = r.pub_number
                         WHERE t.id = ANY(?) AND r.pub_number IS NOT NULL AND pc.subclass IS NOT NULL
                         GROUP BY t.id""", (chunk,)):
            cpc[int(r["id"])] = set(r["subs"])
    doi: dict[int, str] = {}
    for start in range(0, len(ids), 20000):
        chunk = ids[start:start + 20000]
        for r in rows("SELECT trend_id, lower(url) AS doi FROM research_signals "
                      "WHERE trend_id = ANY(?) AND url LIKE 'https://doi.org/%%'", (chunk,)):
            doi[int(r["trend_id"])] = r["doi"]
    topic_of_doi: dict[str, str] = {}
    dois = list(set(doi.values()))
    for start in range(0, len(dois), 20000):
        for r in rows("SELECT doi, topic FROM research_corpus WHERE doi = ANY(?) AND topic IS NOT NULL",
                      (dois[start:start + 20000],)):
            topic_of_doi[r["doi"]] = r["topic"]
    sub_of = {r["topic"]: r["subfield"] for r in rows(
        "SELECT DISTINCT ON (topic) topic, subfield FROM openalex_topics ORDER BY topic")}
    topic = {i: topic_of_doi[d] for i, d in doi.items() if d in topic_of_doi}
    subfield = {i: sub_of[t] for i, t in topic.items() if t in sub_of}
    return cpc, topic, subfield


# ---------------------------------------------------------------- preprocess

def tier_codes(meta: list[dict]) -> np.ndarray:
    return np.array([ss.TIER_CODES.get(m.get("tier"), 0) for m in meta], dtype=np.int32)


def prep_identity(Xb, tb, Xh, th):
    return Xb, Xh


def _tier_means(Xb, tb):
    return {c: Xb[tb == c].mean(axis=0) for c in np.unique(tb)}


def prep_tier_center(Xb, tb, Xh, th):
    """Subtract each tier's mean (fitted on the base sample), renormalise."""
    mu = _tier_means(Xb, tb)
    g = Xb.mean(axis=0)

    def apply(X, t):
        M = np.vstack([mu.get(c, g) for c in t])
        return ss.l2(X - M)
    return apply(Xb, tb), apply(Xh, th)


def prep_tier_nullspace(Xb, tb, Xh, th):
    """Remove the subspace spanned by (tier mean - global mean), renormalise."""
    mu = _tier_means(Xb, tb)
    g = Xb.mean(axis=0)
    D = np.vstack([m - g for m in mu.values()]).T          # (1024, tiers)
    Q, _ = np.linalg.qr(D)
    Q = Q[:, : np.linalg.matrix_rank(D)]

    def apply(X):
        return ss.l2(X - (X @ Q) @ Q.T)
    return apply(Xb), apply(Xh)


VARIANTS = {
    "baseline":           (prep_identity, 50, "euclidean"),
    "pca256":             (prep_identity, 256, "euclidean"),
    "cosine1024":         (prep_identity, None, "cosine"),
    "tier_center":        (prep_tier_center, 50, "euclidean"),
    "tier_nullspace":     (prep_tier_nullspace, 50, "euclidean"),
    "tier_center+pca256": (prep_tier_center, 256, "euclidean"),
    "tier_center+cos1024": (prep_tier_center, None, "cosine"),
}


def fit_variant(name, Xb, tb, Xh, th):
    from sklearn.decomposition import PCA
    import umap

    prep, dims, metric = VARIANTS[name]
    Pb, Ph = prep(Xb, tb, Xh, th)
    var = None
    if dims:
        pca = PCA(n_components=dims, random_state=SEED, svd_solver="randomized")
        Zb = pca.fit_transform(Pb)
        Zh = pca.transform(Ph)
        var = float(pca.explained_variance_ratio_.sum())
    else:
        Zb, Zh = Pb, Ph
    reducer = umap.UMAP(n_components=3, n_neighbors=ss.UMAP_NEIGHBOURS, min_dist=ss.UMAP_MIN_DIST,
                        metric=metric, random_state=SEED, n_jobs=1)
    Yb = reducer.fit_transform(Zb)
    Yh = reducer.transform(Zh) if len(Zh) else np.zeros((0, 3))
    return np.asarray(Yb, np.float64), np.asarray(Yh, np.float64), Pb, Ph, var


# ------------------------------------------------------------------ metrics

def knn_idx(P: np.ndarray, k: int, metric: str = "euclidean") -> np.ndarray:
    from sklearn.neighbors import NearestNeighbors
    nn = NearestNeighbors(n_neighbors=min(k + 1, len(P)), metric=metric).fit(P)
    return nn.kneighbors(P, return_distance=False)[:, 1:]


def thin(idx: np.ndarray, cap: int) -> np.ndarray:
    return idx if len(idx) <= cap else idx[np.linspace(0, len(idx) - 1, cap, dtype=int)]


def purity(P: np.ndarray, ids: list[int], lab: dict, same, metric: str) -> float | None:
    sel = thin(np.array([j for j, i in enumerate(ids) if i in lab]), PURITY_MAX)
    if len(sel) < 2 * K:
        return None
    nb = knn_idx(P[sel], K, metric)
    L = [lab[ids[j]] for j in sel]
    return float(np.mean([np.mean([same(L[a], L[b]) for b in row]) for a, row in enumerate(nb)]))


def term_knn(P: np.ndarray, term_of: np.ndarray, metric: str) -> dict:
    """term_of: -1 for base points, term index for hits."""
    nb = knn_idx(P, K, metric)
    out = {}
    for t in np.unique(term_of[term_of >= 0]):
        rows_t = np.where(term_of == t)[0]
        out[int(t)] = float(np.mean(term_of[nb[rows_t]] == t))
    return out


def tier_gap(P: np.ndarray, term_of: np.ndarray, tiers: np.ndarray, ref: float, cosine: bool) -> dict:
    out = {}
    for t in np.unique(term_of[term_of >= 0]):
        cents = []
        for c in np.unique(tiers[term_of == t]):
            m = (term_of == t) & (tiers == c)
            if m.sum() >= MIN_TIER_HITS:
                v = P[m].mean(axis=0)
                cents.append(v / max(np.linalg.norm(v), 1e-9) if cosine else v)
        if len(cents) < 2:
            continue
        d = [(1 - float(a @ b)) if cosine else float(np.linalg.norm(a - b))
             for i, a in enumerate(cents) for b in cents[i + 1:]]
        out[int(t)] = float(np.mean(d)) / ref
    return out


def random_pair_ref(P: np.ndarray, cosine: bool, n: int = 20000) -> float:
    rng = np.random.default_rng(SEED)
    a, b = rng.integers(0, len(P), n), rng.integers(0, len(P), n)
    if cosine:
        return float(np.median(1 - np.sum(P[a] * P[b], axis=1)))
    return float(np.median(np.linalg.norm(P[a] - P[b], axis=1)))


def mean(d: dict) -> float | None:
    return round(float(np.mean(list(d.values()))), 4) if d else None


# --------------------------------------------------------------------- main

def main() -> int:
    global SEED
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--per-month", type=int, default=200)
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--terms", type=int, default=len(TERMS))
    ap.add_argument("--seed", type=int, default=SEED,
                    help="PCA/UMAP seed — a second seed shows how much of a gap is noise")
    ap.add_argument("--out", default="eval_projection.json")
    args = ap.parse_args()
    SEED = args.seed
    t_all = time.time()
    OUT.mkdir(parents=True, exist_ok=True)

    months = window()
    first, until = f"{months[0]}-01", f"{ss._next_month(months[-1])}-01"
    log(f"window {months[0]} .. {months[-1]} ({len(months)} months)")
    base_ids = [i for i, _ in ss.sample_ids(months, args.per_month)]
    log(f"base sample: {len(base_ids):,} signals ({args.per_month}/month)")

    terms = TERMS[: args.terms]
    raw_hits = {}
    for term in terms:
        t0 = time.time()
        raw_hits[term] = term_hits(term, first, until)
        log(f"  {term!r}: {len(raw_hits[term]):,} candidates ({time.time() - t0:.1f}s)")

    cand = sorted({i for v in raw_hits.values() for i in v})
    Xc, mc = ss.load_vectors(cand)
    tier_c = {i: m.get("tier") for i, m in zip(cand, mc)}
    hit_ids, hit_term = [], []
    for k, term in enumerate(terms):
        kept = cap_by_tier(raw_hits[term], tier_c)
        hit_ids += kept
        hit_term += [k] * len(kept)
    pos_c = {i: j for j, i in enumerate(cand)}
    Xh = ss.l2(Xc[[pos_c[i] for i in hit_ids]]) if hit_ids else np.zeros((0, 1024), np.float32)
    mh = [mc[pos_c[i]] for i in hit_ids]
    del Xc
    log(f"hits: {len(hit_ids):,} over {len(terms)} terms (cap {TERM_CAP}/term, {TIER_CAP}/tier)")

    Xb, mb = ss.load_vectors(base_ids)
    Xb = ss.l2(Xb)
    tb, th = tier_codes(mb), tier_codes(mh)
    all_ids = base_ids + hit_ids
    term_of = np.concatenate([np.full(len(base_ids), -1), np.array(hit_term, dtype=np.int64)])
    tiers_all = np.concatenate([tb, th])
    cpc, topic, subfield = labels(sorted(set(all_ids)))
    log(f"labels: {len(cpc):,} with CPC, {len(topic):,} with OpenAlex topic, {len(subfield):,} subfield")

    def pur(P, metric):
        # the same signal can be in base and hits: purity counts each once (first occurrence)
        seen, keep = set(), []
        for j, i in enumerate(all_ids):
            if i not in seen:
                seen.add(i)
                keep.append(j)
        Pk, ik = P[keep], [all_ids[j] for j in keep]
        return {
            "cpc": purity(Pk, ik, cpc, lambda a, b: bool(a & b), metric),
            "topic": purity(Pk, ik, topic, lambda a, b: a == b, metric),
            "subfield": purity(Pk, ik, subfield, lambda a, b: a == b, metric),
        }

    report = {
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "window": [months[0], months[-1]], "per_month": args.per_month,
        "n_base": len(base_ids), "n_hits": len(hit_ids), "terms": terms,
        "hits_per_term": {t: int(sum(1 for x in hit_term if x == k)) for k, t in enumerate(terms)},
        "labelled": {"cpc": len(cpc), "topic": len(topic), "subfield": len(subfield)},
        "k": K, "seed": SEED, "variants": {},
    }
    X_all = np.vstack([Xb, Xh])
    t0 = time.time()
    report["input_space"] = {
        "purity": pur(X_all, "cosine"),
        "term_knn": mean(term_knn(X_all, term_of, "cosine")),
        "tier_gap": mean(tier_gap(X_all, term_of, tiers_all, random_pair_ref(Xb, True), True)),
    }
    log(f"input space (1024, cosine): {report['input_space']}  ({time.time() - t0:.0f}s)")

    for name in [v.strip() for v in args.variants.split(",") if v.strip()]:
        t0 = time.time()
        log(f"variant {name} ...")
        Yb, Yh, Pb, Ph, var = fit_variant(name, Xb, tb, Xh, th)
        fit_s = time.time() - t0
        Y = np.vstack([Yb, Yh])
        keep, trust = ss.quality(Xb, Yb)
        P_in = np.vstack([Pb, Ph])
        r = {
            "pca_variance": round(var, 4) if var is not None else None,
            "keep10_vs_original": round(keep, 4), "trust_vs_original": round(trust, 4),
            "purity_3d": pur(Y, "euclidean"),
            "term_knn_3d": mean(term_knn(Y, term_of, "euclidean")),
            "tier_gap_3d": mean(tier_gap(Y, term_of, tiers_all, random_pair_ref(Yb, False), False)),
            "tier_gap_input": mean(tier_gap(P_in, term_of, tiers_all, random_pair_ref(Pb, True), True)),
            "term_knn_per_term_3d": {terms[k]: round(v, 4) for k, v in
                                     term_knn(Y, term_of, "euclidean").items()},
            "fit_s": round(fit_s, 1), "total_s": round(time.time() - t0, 1),
        }
        report["variants"][name] = r
        log(f"  {name}: keep {r['keep10_vs_original']} trust {r['trust_vs_original']} "
            f"purity {r['purity_3d']} term_knn {r['term_knn_3d']} tier_gap {r['tier_gap_3d']} "
            f"(input {r['tier_gap_input']})  {r['total_s']}s")
        (OUT / args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))

    report["duration_s"] = round(time.time() - t_all, 1)
    report["peak_rss_gb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2, 2)
    (OUT / args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False))

    fmt = lambda v: "   —  " if v is None else f"{v:6.3f}"  # noqa: E731
    print("\nvariant               keep10  trust   cpc    topic  subfld termknn tiergap tgap_in")
    ins = report["input_space"]
    print(f"{'(input 1024, cosine)':21s}   —      —   {fmt(ins['purity']['cpc'])} {fmt(ins['purity']['topic'])} "
          f"{fmt(ins['purity']['subfield'])} {fmt(ins['term_knn'])} {fmt(ins['tier_gap'])}    —")
    for name, r in report["variants"].items():
        p = r["purity_3d"]
        print(f"{name:21s} {fmt(r['keep10_vs_original'])} {fmt(r['trust_vs_original'])} {fmt(p['cpc'])} "
              f"{fmt(p['topic'])} {fmt(p['subfield'])} {fmt(r['term_knn_3d'])} {fmt(r['tier_gap_3d'])} "
              f"{fmt(r['tier_gap_input'])}")
    log(f"done in {report['duration_s']:.0f}s, peak {report['peak_rss_gb']} GB -> {OUT / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
