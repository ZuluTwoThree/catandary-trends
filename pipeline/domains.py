"""Freely definable domains: membership from the embedding, not from a label (2026-09-30).

Owner 30.09.: pockets should be found inside domains the owner chooses — wireless (5G, 6G),
robotics (humanoid robots), electric mobility — independent of the vertical labels the
text classifier assigns, because similarity in the vector space may be more precise than
the 8B's reading. Two stages:

  1. membership (this module): a linear probe on the 1024-dim prefix, trained on seeds
     from `domains.yaml` that do not come from our own classifiers — examiner CPC codes,
     OpenAlex topics/subfields, phrases in titles and abstracts — against a random
     background of the corpus. Features are tier-centred (each tier's mean vector
     subtracted, as in the cloud's topic layout) so one threshold serves research,
     patents and the press alike. The threshold is set on a holdout to the domain's
     target precision.
  2. pockets (pipeline/emerging_snapshot.py, scope `domain:<key>`): the emerging layer
     restricted to the members — slice, cells, cohesion, archive scan and dating.

Measured first on Food/Nutrition/Agriculture (docs/domain_probe_2026-09-30.md): patents
AUC 0.97-0.99, research 0.97-0.98.

Caveats stated where they matter:
  * The background is UNLABELLED: some of it belongs to the domain. Measured precision is
    therefore a lower bound; the threshold errs on the strict side.
  * Research rows of the #114 pilot (sources "OpenAlex corpus: …") were embedded without
    the "[Science · …]" tag, all others with it. A probe could learn the tag. Rows of those
    sources are left out of TRAINING (never out of membership).
  * Phrase seeds are text matches: "5G" also hits a 5G-funded bakery. They are the only
    seed reaching the press; the probe generalises from all seeds together.

Models live in the database (table `domain_probes`, joblib bytes), so the dev and main
worktrees and the owner app see the same probe.

    .venv/bin/python -m pipeline.domains list
    .venv/bin/python -m pipeline.domains train wireless
    .venv/bin/python -m pipeline.domains measure wireless
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import yaml

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.tiers import tier_of

logger = logging.getLogger("domains")

ROOT = Path(__file__).resolve().parents[1]
DOMAINS_FILE = ROOT / "domains.yaml"
DIM = 1024
HASH_MUL = 2654435761
HASH_MOD = 2 ** 32
DEFAULT_TARGET_RECALL = 0.70         # share of a tier's seeds a member threshold keeps
MIN_THRESHOLD = 0.5
MAX_POS_PER_TIER = 30_000
BACKGROUND = 60_000
HOLDOUT_MOD = 5                           # every 5th row (by hash) is held out
TRAIN_EXCLUDE_SOURCES = ("OpenAlex corpus:%",)
MIN_POSITIVES = 200


# ------------------------------------------------------------------ definitions

def load_definitions(path: Path | None = None) -> dict[str, dict]:
    p = path or DOMAINS_FILE
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = {}
    for key, d in data.items():
        if not isinstance(d, dict):
            continue
        seeds = d.get("seeds") or {}
        out[str(key)] = {
            "key": str(key),
            "name": d.get("name") or str(key),
            "cpc": [str(x) for x in seeds.get("cpc") or []],
            "openalex_topics": [str(x) for x in seeds.get("openalex_topics") or []],
            "openalex_subfields": [str(x) for x in seeds.get("openalex_subfields") or []],
            "phrases": [str(x) for x in seeds.get("phrases") or []],
            "vector_queries": [str(x) for x in seeds.get("vector_queries") or []],
            "target_recall": float(d.get("target_recall") or DEFAULT_TARGET_RECALL),
        }
    return out


def migrate_domain_tables() -> None:
    blob = "BYTEA" if db_mod.USE_POSTGRES else "BLOB"
    ts = ("TIMESTAMP DEFAULT CURRENT_TIMESTAMP" if db_mod.USE_POSTGRES
          else "TEXT DEFAULT (datetime('now'))")
    with get_connection() as c:
        c.execute("CREATE TABLE IF NOT EXISTS domain_probes ("
                  " key TEXT PRIMARY KEY, name TEXT, definition TEXT, threshold REAL,"
                  " metrics TEXT, n_pos INTEGER, n_neg INTEGER, measured TEXT,"
                  f" model {blob}, trained_at {ts})")


# ------------------------------------------------------------------ seeds

def _hsort(ids):
    return sorted(ids, key=lambda i: (int(i) * HASH_MUL) % HASH_MOD)


def seed_ids(defn: dict) -> dict[str, set[int]]:
    """Trend ids per seed kind (only embedded signal/published rows)."""
    out: dict[str, set[int]] = {"cpc": set(), "openalex": set(), "phrases": set(), "vector": set()}
    if not db_mod.USE_POSTGRES:
        raise RuntimeError("domain seeds need the Postgres corpus (CPC, OpenAlex, full text)")
    base = "t.status IN ('signal','published') AND t.embedding_1024 IS NOT NULL"
    with get_connection() as c:
        c.execute("SET statement_timeout = '1800s'")
        if defn["cpc"]:
            pats = [p.replace(" ", "") + "%" for p in defn["cpc"]]
            out["cpc"] = {int(r["id"]) for r in c.execute(
                "SELECT DISTINCT t.id FROM patent_cpc pc JOIN raw_entries r ON r.pub_number = pc.pub_number "
                f"JOIN trends t ON t.raw_entry_id = r.id WHERE {base} AND pc.cpc LIKE ANY(?)", (pats,)).fetchall()}
        if defn["openalex_topics"] or defn["openalex_subfields"]:
            out["openalex"] = {int(r["id"]) for r in c.execute(
                "WITH ot AS (SELECT DISTINCT ON (topic) topic, subfield FROM openalex_topics ORDER BY topic) "
                "SELECT rs.trend_id AS id FROM research_signals rs "
                "JOIN research_corpus rc ON rc.doi = lower(rs.url) JOIN ot ON ot.topic = rc.topic "
                "WHERE rs.url LIKE 'https://doi.org/%%' AND (ot.topic = ANY(?) OR ot.subfield = ANY(?))",
                (defn["openalex_topics"], defn["openalex_subfields"])).fetchall()}
        if defn["phrases"]:
            q = " or ".join(defn["phrases"])
            ts = "websearch_to_tsquery('english', ?)"
            fts = ("to_tsvector('english', coalesce(t.title_en,'') || ' ' || coalesce(t.summary_en,'') "
                   "|| ' ' || coalesce(t.tags::text,''))")
            ids = {int(r["id"]) for r in c.execute(
                f"SELECT t.id FROM trends t WHERE {base} AND {fts} @@ {ts}", (q,)).fetchall()}
            ids |= {int(r["id"]) for r in c.execute(
                f"SELECT rs.trend_id AS id FROM research_signals rs WHERE rs.tsv @@ {ts}", (q,)).fetchall()}
            ids |= {int(r["id"]) for r in c.execute(
                "SELECT t.id FROM patent_search ps JOIN raw_entries r ON r.pub_number = ps.pub_number "
                f"JOIN trends t ON t.raw_entry_id = r.id WHERE {base} AND ps.tsv @@ {ts}", (q,)).fetchall()}
            out["phrases"] = ids
    for q in defn.get("vector_queries") or []:
        out["vector"] |= nearest_to_text(q, VECTOR_SEEDS)
    return out


VECTOR_SEEDS = 1000      # pgvector 0.6: an HNSW scan returns at most ef_search (1000) rows


def nearest_to_text(text: str, k: int = VECTOR_SEEDS) -> set[int]:
    """The k signals nearest to a free text (CPU embedder :8091, HNSW on embedding_1024)."""
    import os
    import httpx
    host = os.getenv("RESEARCH_EMBED_HOST") or "http://127.0.0.1:8091"
    r = httpx.post(f"{host}/v1/embeddings", json={"input": text}, timeout=60)
    r.raise_for_status()
    v = r.json()["data"][0]["embedding"][:DIM]
    lit = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
    with get_connection() as c:
        c.execute("SET hnsw.ef_search = 1000")
        rows = c.execute("SELECT id FROM trends WHERE status IN ('signal','published') "
                         "ORDER BY embedding_1024 <=> ?::vector LIMIT ?", (lit, k)).fetchall()
    return {int(r["id"]) for r in rows}


def adhoc_definition(term: str) -> dict:
    """A domain from nothing but a term (Owner 30.09.: "I don't know beforehand what will be
    searched"): seeds = the term as a phrase in titles/summaries/tags and in research and
    patent abstracts, plus the signals nearest to the term's embedding."""
    import re
    t = " ".join(term.split())
    key = "q_" + re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")[:36]
    return {"key": key, "name": t, "cpc": [], "openalex_topics": [], "openalex_subfields": [],
            "phrases": [f'"{t}"'], "vector_queries": [t],
            "target_recall": DEFAULT_TARGET_RECALL, "adhoc": True}


def background_ids(n: int, exclude: set[int]) -> list[int]:
    """A deterministic random sample of embedded signals (hash below a cut)."""
    with get_connection() as c:
        c.execute("SET statement_timeout = '1800s'")
        total = c.execute("SELECT count(*) AS n FROM trends WHERE status IN ('signal','published') "
                          "AND embedding_1024 IS NOT NULL").fetchone()["n"]
        cut = int(HASH_MOD * min(1.0, 1.3 * n / max(total, 1)))
        rows = c.execute(
            "SELECT id FROM trends WHERE status IN ('signal','published') AND embedding_1024 IS NOT NULL "
            f"AND mod(id::bigint * {HASH_MUL}, {HASH_MOD}) < ?", (cut,)).fetchall()
    ids = [int(r["id"]) for r in rows if int(r["id"]) not in exclude]
    return _hsort(ids)[:n]


def training_excluded(ids: list[int]) -> set[int]:
    if not ids:
        return set()
    with get_connection() as c:
        return {int(r["id"]) for r in c.execute(
            "SELECT t.id FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id "
            "JOIN sources s ON s.id = r.source_id WHERE t.id = ANY(?) AND s.name LIKE ANY(?)",
            (list(ids), list(TRAIN_EXCLUDE_SOURCES))).fetchall()}


# ------------------------------------------------------------------ the probe

class DomainProbe:
    """Tier-centred logistic probe with a calibrated threshold PER TIER.

    One threshold for all tiers was set by the patents (30.09., wireless: the patent
    tier's false positives forced 0.95+, and research and press lost more than half of
    their members). Each tier now gets the lowest threshold that reaches the target
    precision at that tier's own share of the domain; `threshold` is the fallback for a
    tier without seeds."""

    def __init__(self, key: str, clf, means: dict[str, np.ndarray], threshold: float,
                 tier_thresholds: dict[str, float] | None = None):
        self.key, self.clf, self.means, self.threshold = key, clf, means, float(threshold)
        self.tier_thresholds = dict(tier_thresholds or {})
        self._g = np.mean(np.vstack(list(means.values())), axis=0) if means else None

    def features(self, X: np.ndarray, tiers) -> np.ndarray:
        X = X[:, :DIM].astype(np.float32)
        X = X / np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-9, None)
        M = np.vstack([self.means.get(t or "none", self._g) for t in tiers])
        F = X - M
        return F / np.clip(np.linalg.norm(F, axis=1, keepdims=True), 1e-9, None)

    def prob(self, X: np.ndarray, tiers) -> np.ndarray:
        if len(X) == 0:
            return np.zeros(0)
        return self.clf.predict_proba(self.features(X, tiers))[:, 1]

    def thresholds_for(self, tiers) -> np.ndarray:
        return np.array([self.tier_thresholds.get(t or "none", self.threshold) for t in tiers])

    def member(self, X: np.ndarray, tiers) -> np.ndarray:
        return self.prob(X, tiers) >= self.thresholds_for(tiers)

    def dumps(self) -> bytes:
        import joblib
        buf = io.BytesIO()
        joblib.dump({"clf": self.clf, "means": self.means, "threshold": self.threshold,
                     "tier_thresholds": self.tier_thresholds}, buf)
        return buf.getvalue()

    @classmethod
    def loads(cls, key: str, blob: bytes) -> "DomainProbe":
        import joblib
        d = joblib.load(io.BytesIO(bytes(blob)))
        return cls(key, d["clf"], d["means"], d["threshold"], d.get("tier_thresholds"))

    @classmethod
    def load(cls, key: str) -> "DomainProbe":
        with get_connection() as c:
            r = c.execute("SELECT model FROM domain_probes WHERE key = ?", (key,)).fetchone()
        if not r or r["model"] is None:
            raise LookupError(f"domain '{key}' has no trained probe — python -m pipeline.domains train {key}")
        return cls.loads(key, r["model"])


def tiers_of_rows(rows: list[dict]) -> list[str]:
    return [tier_of(r.get("source_name"), r.get("source_type"), r.get("trend_signal_type")) or "none"
            for r in rows]


def threshold_for_recall(p_pos: np.ndarray, target_recall: float) -> float:
    """The threshold that keeps `target_recall` of the seeds — never below MIN_THRESHOLD.

    Why recall and not precision (30.09., wireless): a precision target needs the false-
    positive rate of the background, and at a domain share of 0.3 % (research, press) a
    single false positive among ~4,000 background rows already sinks it — the thresholds
    went to 0.99 and kept a fifth of the seeds. Seed recall is measured directly; the
    false-positive rate on the (unlabelled, hence pessimistic) background is reported
    next to it as the quality figure."""
    if not len(p_pos):
        return 0.9
    return max(MIN_THRESHOLD, float(np.quantile(p_pos, 1 - target_recall)))


def calibrate(y: np.ndarray, p: np.ndarray, target: float, prevalence: float) -> float:
    """Lowest threshold whose precision AT THE CORPUS PREVALENCE reaches `target`.

    The holdout holds positives and background in a training mix (~1:2); the corpus
    holds a few percent of the domain. Precision measured on the mix would put the
    threshold far too low (30.09., first wireless run: 53,784 "members" in 90 days,
    diagnosis devices and graph theory among them). So: precision(t) =
    TPR(t)·π / (TPR(t)·π + FPR(t)·(1-π)), with π the seeds' share of the corpus — a
    lower bound of the domain's true share, which makes the threshold stricter, not
    looser. 0.95 if no threshold reaches the target."""
    pos, neg = p[y], p[~y]
    if not len(pos) or not len(neg):
        return 0.9
    pi = min(max(prevalence, 1e-4), 0.5)
    for t in np.unique(np.round(np.concatenate([pos, neg]), 4)):
        tpr = float((pos >= t).mean())
        fpr = float((neg >= t).mean())
        if tpr == 0:
            break
        prec = tpr * pi / (tpr * pi + fpr * (1 - pi))
        if prec >= target:
            return float(t)
    return 0.95


def train(key: str, defs: dict | None = None) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from pipeline import signal_space as ss

    defs = defs or load_definitions()
    if key not in defs:
        raise KeyError(f"no domain '{key}' in {DOMAINS_FILE.name}")
    defn = defs[key]
    t0 = time.time()
    seeds = seed_ids(defn)
    pos_all = set().union(*seeds.values())
    excl = training_excluded(list(pos_all))
    pos_all -= excl
    logger.info("[%s] seeds: cpc %d, openalex %d, phrases %d, vector %d -> %d positives (%d excluded: pilot recipe)",
                key, len(seeds["cpc"]), len(seeds["openalex"]), len(seeds["phrases"]), len(seeds["vector"]),
                len(pos_all), len(excl))
    if len(pos_all) < MIN_POSITIVES:
        raise ValueError(f"[{key}] only {len(pos_all)} positive seeds — add seeds to {DOMAINS_FILE.name}")
    bg = background_ids(BACKGROUND, pos_all)
    bg_excl = training_excluded(bg)
    bg = [i for i in bg if i not in bg_excl]
    # positives capped per tier, so a seed that floods one tier cannot own the probe
    pos_list = _hsort(pos_all)
    Xp, mp = ss.load_vectors(pos_list)
    tp = [m.get("tier") or "none" for m in mp]
    keep, per = [], {}
    for i, t in enumerate(tp):
        if per.get(t, 0) < MAX_POS_PER_TIER:
            per[t] = per.get(t, 0) + 1
            keep.append(i)
    Xp, tp, pos_list = Xp[keep], [tp[i] for i in keep], [pos_list[i] for i in keep]
    Xb, mb = ss.load_vectors(bg)
    tb = [m.get("tier") or "none" for m in mb]
    Xb_n = ss.l2(Xb)
    means = {t: Xb_n[np.array(tb) == t].mean(axis=0) for t in set(tb)}
    probe = DomainProbe(key, None, means, 0.5)
    ids = pos_list + bg
    X = probe.features(np.vstack([Xp, Xb]), tp + tb)
    y = np.array([1] * len(pos_list) + [0] * len(bg), bool)
    tiers = np.array(tp + tb)
    hold = np.array([(i * HASH_MUL) % HASH_MOD % HOLDOUT_MOD == 0 for i in ids])
    clf = LogisticRegression(C=1.0, max_iter=3000, class_weight="balanced")
    clf.fit(X[~hold], y[~hold])
    probe.clf = clf
    p_hold = clf.predict_proba(X[hold])[:, 1]
    with get_connection() as c:
        corpus = c.execute("SELECT count(*) AS n FROM trends WHERE status IN ('signal','published') "
                           "AND embedding_1024 IS NOT NULL").fetchone()["n"]
    prevalence = (len(pos_all) + len(excl)) / max(corpus, 1)
    thr = threshold_for_recall(p_hold[y[hold]], defn["target_recall"])
    probe.threshold = thr
    # per tier: the domain's share of THAT tier (seeds in the tier / the tier's size,
    # the size estimated from the uniform background sample)
    seed_tiers: dict[str, int] = {}
    for t_ in tp:
        seed_tiers[t_] = seed_tiers.get(t_, 0) + 1
    bg_share = {t_: float((np.array(tb) == t_).mean()) for t_ in set(tb)}
    tier_prev: dict[str, float] = {}
    tier_thr: dict[str, float] = {}
    for t_ in sorted(set(tiers)):
        m_ = hold & (tiers == t_)
        if not y[m_].any() or not (~y[m_]).any():
            continue
        # the capped positives understate big tiers — scale by the uncapped seed count
        uncapped = seed_tiers.get(t_, 0) * (1 if per.get(t_, 0) < MAX_POS_PER_TIER else
                                            max(1.0, len(pos_all) / max(sum(per.values()), 1)))
        size = corpus * bg_share.get(t_, 0.0)
        tier_prev[t_] = uncapped / max(size, 1)
        tier_thr[t_] = threshold_for_recall(clf.predict_proba(X[m_][y[m_]])[:, 1], defn["target_recall"])
    probe.tier_thresholds = tier_thr
    metrics = {"threshold": round(thr, 4), "target_recall": defn["target_recall"],
               "seed_prevalence": round(prevalence, 5),
               "auc": round(float(roc_auc_score(y[hold], p_hold)), 4) if y[hold].any() else None,
               "seeds": {k: len(v) for k, v in seeds.items()}, "positives_per_tier": per,
               "background": len(bg), "per_tier": {}}
    for t in sorted(set(tiers)):
        m = hold & (tiers == t)
        if not m.any() or not y[m].any():
            continue
        tt = tier_thr.get(t, thr)
        pt = clf.predict_proba(X[m])[:, 1] >= tt
        tpr = float((pt & y[m]).sum() / max(y[m].sum(), 1))
        fpr = float((pt & ~y[m]).sum() / max((~y[m]).sum(), 1))
        pi = min(max(tier_prev.get(t, prevalence), 1e-4), 0.5)
        metrics["per_tier"][t] = {"threshold": round(tt, 4), "tier_prevalence": round(pi, 5),
                                  "recall": round(tpr, 3), "false_positive_rate": round(fpr, 4),
                                  "precision_at_prevalence": round(tpr * pi / max(tpr * pi + fpr * (1 - pi), 1e-9), 3),
                                  "pos": int(y[m].sum()), "n": int(m.sum())}
    metrics["seconds"] = round(time.time() - t0)
    migrate_domain_tables()
    with get_connection() as c:
        c.execute("DELETE FROM domain_probes WHERE key = ?", (key,))
        c.execute("INSERT INTO domain_probes (key, name, definition, threshold, metrics, n_pos, n_neg, model) "
                  "VALUES (?,?,?,?,?,?,?,?)",
                  (key, defn["name"], json.dumps(defn), thr, json.dumps(metrics),
                   len(pos_list), len(bg), probe.dumps()))
    logger.info("[%s] trained: threshold %.3f, AUC %s, per tier %s (%ds)", key, thr, metrics["auc"],
                json.dumps(metrics["per_tier"]), metrics["seconds"])
    return metrics


def measure(key: str, window_days: int = 90, samples: int = 10) -> dict:
    """Apply the probe to the emerging layer's recent slice: size, tiers, labels, examples."""
    from pipeline.foresight import build_matrix, load_signals
    probe = DomainProbe.load(key)
    since = (datetime.now() - timedelta(days=window_days)).strftime("%Y-%m-%d")
    rows = load_signals(status="signal,published", dim1024=True, since=since)
    X = build_matrix(rows)
    tiers = tiers_of_rows(rows)
    p = probe.prob(X, tiers)
    thr = probe.thresholds_for(tiers)
    m = p >= thr
    verts: dict[str, int] = {}
    tier_c: dict[str, int] = {}
    for i in np.flatnonzero(m):
        v = rows[i].get("primary_vertical") or "none"
        verts[v] = verts.get(v, 0) + 1
        tier_c[tiers[i]] = tier_c.get(tiers[i], 0) + 1
    rng = np.random.default_rng(42)
    idx = np.flatnonzero(m)
    pick = rng.choice(idx, min(samples, len(idx)), replace=False) if len(idx) else []
    edge = np.flatnonzero((p >= thr * 0.8) & ~m)
    pick_edge = rng.choice(edge, min(samples // 2, len(edge)), replace=False) if len(edge) else []
    out = {"since": since, "slice": len(rows), "members": int(m.sum()),
           "by_tier": dict(sorted(tier_c.items(), key=lambda kv: -kv[1])),
           "by_vertical": dict(sorted(verts.items(), key=lambda kv: -kv[1])),
           "examples": [{"p": round(float(p[i]), 3), "tier": tiers[i],
                         "vertical": rows[i].get("primary_vertical"), "title": (rows[i].get("title_en") or "")[:120]}
                        for i in pick],
           "just_below": [{"p": round(float(p[i]), 3), "tier": tiers[i],
                           "title": (rows[i].get("title_en") or "")[:120]} for i in pick_edge]}
    with get_connection() as c:
        c.execute("UPDATE domain_probes SET measured = ? WHERE key = ?", (json.dumps(out), key))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Freely definable domains (two-stage pocket discovery)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    t = sub.add_parser("train"); t.add_argument("key"); t.add_argument("--measure", action="store_true")
    m = sub.add_parser("measure"); m.add_argument("key"); m.add_argument("--window-days", type=int, default=90)
    a = sub.add_parser("adhoc", help="a domain from a free term: seeds from full text + nearest vectors")
    a.add_argument("term"); a.add_argument("--measure", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    migrate_domain_tables()
    if args.cmd == "list":
        defs = load_definitions()
        with get_connection() as c:
            trained = {r["key"]: dict(r) for r in c.execute(
                "SELECT key, threshold, n_pos, trained_at FROM domain_probes").fetchall()}
        for k, d in defs.items():
            tr = trained.get(k)
            print(f"{k:20s} {d['name']:32s} "
                  + (f"trained {tr['trained_at']}, threshold {tr['threshold']:.3f}, {tr['n_pos']:,} positives"
                     if tr else "not trained"))
        return 0
    if args.cmd == "adhoc":
        defn = adhoc_definition(args.term)
        print(f"key: {defn['key']}")
        print(json.dumps(train(defn["key"], {defn["key"]: defn}), indent=2))
        args.key = defn["key"]
        if not args.measure:
            return 0
    if args.cmd == "train":
        print(json.dumps(train(args.key), indent=2))
        if not args.measure:
            return 0
    out = measure(args.key, getattr(args, "window_days", 90))
    print(json.dumps({k: v for k, v in out.items() if k not in ("examples", "just_below")}, indent=2))
    for e in out["examples"]:
        print(f"  in    {e['p']:.2f} {e['tier']:8s} {str(e['vertical']):9s} {e['title']}")
    for e in out["just_below"]:
        print(f"  below {e['p']:.2f} {e['tier']:8s} {e['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
