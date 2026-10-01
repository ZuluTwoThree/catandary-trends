#!/usr/bin/env python3
"""Can a domain be cut out of the vector space — not by label, by embedding?

Owner 30.09.2026: Food, Agriculture and Nutrition are three domains of their own. One
independent yes/no probe per domain (a signal may belong to several — most nutrition
patents also carry food classes). Labels per domain:

  food         patents: A23* except A23L33, A21B/C/D, A22B/C, C12C/G/J, C13B/K
               research: OpenAlex subfield Food Science
  nutrition    patents: A23L33 (modifying nutritive qualities, dietetics, supplements)
               research: Nutrition and Dietetics
  agriculture  patents: A01B/C/D/F/G/H/J/K/M, C05B/C/D/F/G
               research: Agronomy and Crop Science, Horticulture, Soil Science,
                         Animal Science and Zoology

Owner question 30.09.2026: two-stage pocket discovery — first restrict the signals to
a domain via their embeddings, then look for pockets inside it. Stage 1 is measured
here: a linear probe on the 1024-dim prefix, trained on labels that do NOT come from
our own classifiers:

  patents   food = any CPC subclass of the food classes (A23*, A21B/C/D, A22B/C, C12C/G/J,
            C13B/K) assigned by the patent examiners (patent_cpc)
  research  food = OpenAlex primary topic in the subfields Food Science / Nutrition and
            Dietetics (research_corpus via DOI)

Research rows of the #114 pilot are embedded with --clean-text (no "[Science · …]" tag),
all other research signals with it — a probe could learn the tag instead of the topic.
Training and holdout therefore use NON-pilot research only; the pilot rows are a
separate out-of-sample check (recall on 130k known-food papers embedded differently).

Two feature variants: raw prefix, and tier-centred (each tier's mean subtracted — the
"topic" layout's step, docs/space_eval_2026-09-28.md), so one threshold can serve
research, patents and press alike.

Then the probe is applied to the emerging layer's 90-day slice: how much of the
predicted Food region carries the FOOD vertical label, and how much FOOD-labelled
material lies outside it — plus title samples of both disagreements for the eye
(press has no external truth).

    .venv/bin/python scripts/space_eval/eval_domain_probe.py [--per-class 40000]
Output: data/space_eval/eval_domain_probe.json + samples on stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline import db  # noqa: E402
from pipeline import signal_space as ss  # noqa: E402
from pipeline.foresight import build_matrix, load_signals  # noqa: E402
from pipeline.tiers import tier_of  # noqa: E402

OUT = ROOT / "data" / "space_eval"
DOMAINS = {
    "food": {
        "cpc": "((pc.subclass LIKE 'A23%%' AND pc.cpc NOT LIKE 'A23L33%%') OR pc.subclass IN "
               "('A21B','A21C','A21D','A22B','A22C','C12C','C12G','C12J','C13B','C13K'))",
        "subfields": ("Food Science",), "vertical": "FOOD"},
    "nutrition": {
        "cpc": "(pc.cpc LIKE 'A23L33%%')",
        "subfields": ("Nutrition and Dietetics",), "vertical": "HEALTH"},
    "agriculture": {
        "cpc": "(pc.subclass IN ('A01B','A01C','A01D','A01F','A01G','A01H','A01J','A01K','A01M',"
               "'C05B','C05C','C05D','C05F','C05G'))",
        "subfields": ("Agronomy and Crop Science", "Horticulture", "Soil Science",
                      "Animal Science and Zoology"), "vertical": "FOOD"},
}
SEED = 42


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def rows(sql, p=()):
    with db.get_connection() as c:
        c.execute("SET statement_timeout = '1800s'")
        return [dict(r) for r in c.execute(sql, p).fetchall()]


def hsort(ids):
    return sorted(ids, key=lambda i: (i * ss.HASH_MUL) % ss.HASH_MOD)


def labels():
    flags = ", ".join(f"bool_or({d['cpc']}) AS {k}" for k, d in DOMAINS.items())
    pat = rows(f"""SELECT t.id, {flags}
                   FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id
                   JOIN patent_cpc pc ON pc.pub_number = r.pub_number
                   WHERE t.status = 'signal' AND t.embedding_1024 IS NOT NULL AND r.pub_number IS NOT NULL
                   GROUP BY t.id""")
    res = rows("""WITH ot AS (SELECT DISTINCT ON (topic) topic, subfield FROM openalex_topics ORDER BY topic)
                  SELECT rs.trend_id AS id, ot.subfield, s.name LIKE 'OpenAlex corpus:%%' AS pilot
                  FROM research_signals rs
                  JOIN research_corpus rc ON rc.doi = lower(rs.url)
                  JOIN ot ON ot.topic = rc.topic
                  JOIN trends t ON t.id = rs.trend_id
                  JOIN raw_entries r ON r.id = t.raw_entry_id JOIN sources s ON s.id = r.source_id
                  WHERE rs.url LIKE 'https://doi.org/%%'""")
    return pat, res


def metrics(y, p, thr=0.5):
    pred = p >= thr
    tp = int((pred & y).sum()); fp = int((pred & ~y).sum()); fn = int((~pred & y).sum())
    prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
    return {"precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / max(prec + rec, 1e-9), 4), "n": int(len(y)), "pos": int(y.sum())}


def thr_for_precision(y, p, target=0.9):
    order = np.argsort(-p); ys = y[order]; ps = p[order]
    tp = np.cumsum(ys); prec = tp / np.arange(1, len(ys) + 1)
    ok = np.where(prec >= target)[0]
    if not len(ok):
        return None
    k = ok[-1]
    return {"threshold": round(float(ps[k]), 4), "recall": round(float(tp[k] / max(ys.sum(), 1)), 4)}


def main() -> int:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--per-class", type=int, default=40000, help="cap per tier and class")
    ap.add_argument("--window-days", type=int, default=90)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    pat, res = labels()
    for r in res:
        for k, d in DOMAINS.items():
            r[k] = r["subfield"] in d["subfields"]
    log(f"labels: patents {len(pat):,}, research {len(res):,} ({sum(r['pilot'] for r in res):,} from the pilot); "
        + ", ".join(f"{k}: {sum(r[k] for r in pat):,} patents / {sum(r[k] and not r['pilot'] for r in res):,} papers"
                    for k in DOMAINS))

    # the 90-day slice of the emerging layer — tier means, and where the probes are applied
    since = (datetime.now() - timedelta(days=args.window_days)).strftime("%Y-%m-%d")
    sl = load_signals(status="signal,published", dim1024=True, since=since)
    S = ss.l2(build_matrix(sl).astype(np.float32)[:, :1024])
    s_tier = np.array([tier_of(r.get("source_name"), r.get("source_type"), r.get("trend_signal_type")) or "none" for r in sl])
    s_vert = np.array([r.get("primary_vertical") or "none" for r in sl])
    log(f"90-day slice: {len(sl):,} signals since {since}")
    means = {t: S[s_tier == t].mean(axis=0) for t in np.unique(s_tier)}
    g = S.mean(axis=0)

    def centre(M, tiers):
        return ss.l2(M - np.vstack([means.get(t, g) for t in tiers]))

    Sc = centre(S, s_tier)
    report = {"created": time.strftime("%Y-%m-%d %H:%M"), "per_class": args.per_class,
              "slice": {"since": since, "n": int(len(sl))}, "domains": {}}
    member = {}
    for dom, spec in DOMAINS.items():
        ids, y, tier = [], [], []
        sizes = {}
        for tname, rs in (("patent", pat), ("science", [r for r in res if not r["pilot"]])):
            pos = hsort([r["id"] for r in rs if r[dom]])[: args.per_class]
            neg = hsort([r["id"] for r in rs if not r[dom]])[: args.per_class]
            sizes[tname] = [len(pos), len(neg)]
            ids += pos + neg; y += [1] * len(pos) + [0] * len(neg); tier += [tname] * (len(pos) + len(neg))
        X, _ = ss.load_vectors(ids)
        X = centre(ss.l2(X), tier)
        y = np.array(y, bool); tier = np.array(tier)
        holdout = np.array([(i * ss.HASH_MUL) % ss.HASH_MOD % 5 == 0 for i in ids])
        clf = LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced")
        clf.fit(X[~holdout], y[~holdout])
        r = {"train_sizes": sizes}
        for tname in ("patent", "science"):
            m = holdout & (tier == tname)
            if y[m].sum() == 0:
                continue
            p = clf.predict_proba(X[m])[:, 1]
            r[tname] = {**metrics(y[m], p), "auc": round(float(roc_auc_score(y[m], p)), 4),
                        "at_precision_0.9": thr_for_precision(y[m], p)}
        pilot_ids = hsort([x["id"] for x in res if x["pilot"] and x[dom]])[: args.per_class]
        if pilot_ids:
            Xp, _ = ss.load_vectors(pilot_ids)
            Xp = centre(ss.l2(Xp), ["science"] * len(pilot_ids))
            r["pilot_recall@0.5"] = round(float((clf.predict_proba(Xp)[:, 1] >= 0.5).mean()), 4)
        ps = clf.predict_proba(Sc)[:, 1]
        for thr in (0.5, 0.7):
            pred = ps >= thr
            vc = {}
            for v in np.unique(s_vert[pred]):
                vc[str(v)] = int((s_vert[pred] == v).sum())
            tc = {str(t): int((s_tier[pred] == t).sum()) for t in np.unique(s_tier[pred])}
            r[f"slice@{thr}"] = {"members": int(pred.sum()),
                                 "by_vertical": dict(sorted(vc.items(), key=lambda kv: -kv[1])),
                                 "by_tier": tc}
        member[dom] = ps >= 0.7
        report["domains"][dom] = r
        log(f"{dom}: " + json.dumps({k: v for k, v in r.items() if not k.startswith("slice")}))
        log(f"{dom} slice@0.7: " + json.dumps(r["slice@0.7"]))
        rng = np.random.default_rng(SEED)
        exp = spec["vertical"]
        idx = np.where((ps >= 0.7) & (s_vert != exp))[0]
        print(f"--- {dom}: member at 0.7 but labelled other than {exp} ({len(idx):,}) ---")
        for i in (rng.choice(idx, min(8, len(idx)), replace=False) if len(idx) else []):
            rr = sl[i]
            print(f"  {ps[i]:.2f} {s_tier[i]:8s} {s_vert[i]:9s} {(rr.get('title_en') or '')[:95]}")
    doms = list(member)
    report["overlap@0.7"] = {f"{a}&{b}": int((member[a] & member[b]).sum())
                             for i, a in enumerate(doms) for b in doms[i + 1:]}
    report["union@0.7"] = int(np.logical_or.reduce([member[d] for d in doms]).sum())
    log(f"overlap@0.7: {report['overlap@0.7']}, union {report['union@0.7']:,}")
    report["seconds"] = round(time.time() - t0)
    (OUT / "eval_domain_probe.json").write_text(json.dumps(report, indent=2))
    log(f"done in {report['seconds']} s -> {OUT / 'eval_domain_probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
