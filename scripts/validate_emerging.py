#!/usr/bin/env python3
"""Does the emerging detector find trends that actually happened, and how early?

    .venv/bin/python scripts/validate_emerging.py
    .venv/bin/python scripts/validate_emerging.py --from 2023-01 --to 2026-07 --step 3
    .venv/bin/python scripts/validate_emerging.py --trends rag,glp1 --step 6

Without this number every claim about early detection is a claim, not a result
(Owner 2026-09-15). The test is a backtest: for a series of dates T, the
detector runs on the slice of signals that existed BEFORE T, and each known
trend from `known_trends.yaml` is matched against the nest centres. The first T
at which a trend is found, compared with the month it became mainstream, is its
lead time.

What this test can and cannot say:

* It is a backtest on `published_date`, not a point-in-time reconstruction. A
  source we only added in 2026 contributes nothing to a 2024 slice (there is no
  backfill), so the early slices are what the OLD source set produced. That
  makes the result conservative for early dates and honest for recent ones.
* A trend that broke before our corpus had any usable coverage cannot show a
  lead time. The report prints the slice size at every date so a lead of "we
  had 3,000 documents that quarter" is not read as a finding.
* Controls are the other half of the test. Three topics that must never match
  are checked at every date; if one does, the threshold is too loose and the
  rest of the table means nothing.
* Semantic closeness alone measures the FIELD, not the trend. The first version
  of this test (2026-09-15) reported a 26-month lead for "LLM agents", "small
  on-device models" and "vision-language-action models" alike, because one
  134-document pocket called "Machine Learning · Neural Networks" sat close to
  all three queries. A match therefore also requires one of the trend's own
  terms to appear in the matched pocket's titles or tags. Both numbers are
  reported: the loose one says when the field was there, the strict one says
  when the thing itself was.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import llamacpp_client
from pipeline.emerging import (MIN_COHESION, build_matrix, describe_nests,
                               detect_nests, pick_cells)
from pipeline.foresight import load_signals

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("validate_emerging")

# Calibrated 2026-09-15 against the live global run: true topics scored 0.82 to
# 0.86 against their own nest, three nonsense controls 0.53 to 0.60. 0.75 sits
# in the empty middle; the report prints every margin so the gap stays visible.
MATCH_SIM = float(os.getenv("EMERGING_MATCH_SIM", "0.75"))
WINDOW_DAYS = 90
DIM = 1024
# The backtest keeps the n densest pockets of each slice instead of applying the
# production density bar. Measured 2026-09-15: the same absolute bar keeps 98
# pockets in the last 90 days and 7 in a 2025 slice, because the corpus itself
# got denser (concept-scoped research sweeps), not because 2025 held no trends.
# Every match reports the matched pocket's density, so the table still says
# which finds would have cleared the production bar.
TOP_N = 60


def load_known(path: str) -> tuple[list[dict], list[dict]]:
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return doc.get("trends") or [], doc.get("controls") or []


def embed(text: str, host: str) -> np.ndarray:
    """Query vector in the same space as `trends.embedding_1024`."""
    vec = llamacpp_client.generate_embedding(text, host=host) if host else None
    if not vec:
        raise RuntimeError(
            "no embedding returned. Start the CPU embedder "
            "(systemctl --user start catandary-embed-cpu) or set "
            "RESEARCH_EMBED_HOST to a server that runs qwen3-embedding.")
    if len(vec) < DIM:
        raise RuntimeError(
            f"embedding endpoint returned {len(vec)} dimensions — that is a chat "
            f"model answering /v1/embeddings, not the embedding model.")
    v = np.asarray(vec[:DIM], dtype=np.float32)
    return v / max(float(np.linalg.norm(v)), 1e-9)


def month_iter(start: str, end: str, step: int) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        m += step
        while m > 12:
            m -= 12
            y += 1
    return out


def months_between(a: str, b: str) -> int:
    """b - a in months; positive when b is later."""
    return (int(b[:4]) - int(a[:4])) * 12 + (int(b[5:7]) - int(a[5:7]))


def nest_text(nest: dict) -> str:
    """Everything the pocket itself says, normalised for substring matching."""
    parts = list(nest.get("top_tags") or []) + list(nest.get("name_titles") or [])
    return " " + " ".join(parts).lower().replace("_", " ") + " "


def has_term(nest: dict, terms: list[str]) -> bool:
    if not terms:
        return True                       # no terms declared → semantic only
    text = nest_text(nest)
    return any(t.lower() in text for t in terms)


def run_date(month: str, seed: int = 42, top_n: int = TOP_N) -> tuple[np.ndarray, list[dict], int]:
    """Detect nests in the 90 days before `month`. Returns (centroids, nests, n)."""
    until = f"{month}-01"
    since = (datetime.strptime(until, "%Y-%m-%d") - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    rows = load_signals(dim1024=True, since=since, until=until)
    if len(rows) < 200:
        return np.zeros((0, DIM), dtype=np.float32), [], len(rows)
    X = build_matrix(rows)
    nests = detect_nests(X, k=pick_cells(X.shape[0]), seed=seed, top_n=top_n)
    if not nests:
        return np.zeros((0, DIM), dtype=np.float32), [], len(rows)
    describe_nests(nests, rows, X=X)
    cen = np.vstack([n["centroid"] for n in nests])
    cen = cen / np.clip(np.linalg.norm(cen, axis=1, keepdims=True), 1e-9, None)
    n_rows = len(rows)
    del X, rows
    return cen, nests, n_rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Backtest the emerging detector")
    ap.add_argument("--known", default="known_trends.yaml")
    ap.add_argument("--from", dest="start", default="2021-07",
                    help="first test date; the corpus carries ~80-120k signals a "
                         "year back to 2019")
    ap.add_argument("--to", dest="end", default=None, help="default: last full month")
    ap.add_argument("--step", type=int, default=3, help="months between test dates")
    ap.add_argument("--trends", default=None, help="comma list of keys, default all")
    ap.add_argument("--match-sim", type=float, default=MATCH_SIM)
    ap.add_argument("--top-n", type=int, default=TOP_N,
                    help="densest pockets kept per date (relative gate)")
    ap.add_argument("--out", default="data/emerging_validation.json")
    args = ap.parse_args()

    end = args.end or (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    dates = month_iter(args.start, end, args.step)
    trends, controls = load_known(args.known)
    if args.trends:
        keep = {k.strip() for k in args.trends.split(",")}
        trends = [t for t in trends if t["key"] in keep]
    if not trends:
        print("no trends selected", file=sys.stderr)
        return 1

    host = os.getenv("RESEARCH_EMBED_HOST") or "http://127.0.0.1:8091"
    logger.info("embedding %d trends + %d controls via %s", len(trends), len(controls), host)
    Q = np.vstack([embed(t["query"], host) for t in trends])
    C = np.vstack([embed(c["query"], host) for c in controls]) if controls else np.zeros((0, DIM), np.float32)

    per_date: list[dict] = []
    best_seen = {t["key"]: 0.0 for t in trends}
    first_hit: dict[str, str] = {}     # strict: similar AND says one of its words
    loose_hit: dict[str, str] = {}     # semantic only — the field, not the trend
    first_match: dict[str, dict] = {}
    control_hits: list[dict] = []

    for month in dates:
        t0 = time.time()
        cen, nests, n_rows = run_date(month, top_n=args.top_n)
        dense = sum(1 for n in nests if n["cohesion"] >= MIN_COHESION)
        row = {"month": month, "signals": n_rows, "nests": len(nests),
               "above_production_bar": dense, "hits": {}}
        if len(cen):
            sims = cen @ Q.T                                   # (nests, trends)
            for j, t in enumerate(trends):
                best = float(sims[:, j].max())
                row["hits"][t["key"]] = round(best, 3)
                best_seen[t["key"]] = max(best_seen[t["key"]], best)
                if best >= args.match_sim and t["key"] not in loose_hit:
                    loose_hit[t["key"]] = month
                # strict: closest pocket that ALSO says one of the trend's words
                if t["key"] in first_hit:
                    continue
                for idx in np.argsort(-sims[:, j]):
                    if float(sims[idx, j]) < args.match_sim:
                        break
                    if not has_term(nests[idx], t.get("terms") or []):
                        continue
                    first_hit[t["key"]] = month
                    row.setdefault("matched", {})[t["key"]] = {
                        "nest": nests[idx].get("label"),
                        "llm_name": nests[idx].get("llm_label"),
                        "size": int(nests[idx]["members"].size),
                        "sim": round(float(sims[idx, j]), 3),
                        "cohesion": nests[idx]["cohesion"],
                        "above_production_bar": nests[idx]["cohesion"] >= MIN_COHESION,
                    }
                    first_match[t["key"]] = row["matched"][t["key"]]
                    break
            if len(C):
                csims = cen @ C.T
                for j, c in enumerate(controls):
                    best = float(csims[:, j].max())
                    row.setdefault("controls", {})[c["key"]] = round(best, 3)
                    if best >= args.match_sim:
                        idx = int(np.argmax(csims[:, j]))
                        control_hits.append({"month": month, "control": c["key"],
                                             "nest": nests[idx].get("label"),
                                             "sim": round(best, 3)})
        per_date.append(row)
        logger.info("%s: %d signals, %d pockets (%d above the production bar), %.0fs",
                    month, n_rows, len(nests), dense if len(cen) else 0, time.time() - t0)

    results = []
    for t in trends:
        hit = first_hit.get(t["key"])
        lead = months_between(hit, t["mainstream"]) if hit else None
        m = first_match.get(t["key"]) or {}
        results.append({
            "key": t["key"], "name": t["name"], "vertical": t.get("vertical"),
            "mainstream": t["mainstream"], "first_detected": hit,
            "lead_months": lead, "best_similarity": round(best_seen[t["key"]], 3),
            "field_first_seen": loose_hit.get(t["key"]),
            "matched_nest": m.get("nest"), "matched_size": m.get("size"),
            "matched_cohesion": m.get("cohesion"),
            "above_production_bar": m.get("above_production_bar"),
        })

    def summarise(threshold: float) -> dict:
        """Re-derive the table at another threshold from the stored similarities.

        The single number 0.75 was calibrated on one run; several misses sit
        just below it, so the reader has to see how much of the result is the
        detector and how much is the cut-off. This uses the LOOSE rule (no term
        check), so it is an upper bound on what any threshold could find."""
        hits, leads = 0, []
        for t in trends:
            for row in per_date:
                if row["hits"].get(t["key"], 0.0) >= threshold:
                    hits += 1
                    leads.append(months_between(row["month"], t["mainstream"]))
                    break
        early_n = sum(1 for x in leads if x > 0)
        return {"threshold": threshold, "found": hits, "found_early": early_n,
                "median_lead": (sorted(leads)[len(leads) // 2] if leads else None)}

    max_control = max((max(d.get("controls", {}).values(), default=0.0)
                       for d in per_date), default=0.0)
    sensitivity = [summarise(x) for x in (0.65, 0.70, 0.75, 0.80, 0.85)]

    found = [r for r in results if r["first_detected"]]
    early = [r for r in found if (r["lead_months"] or 0) > 0]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window_days": WINDOW_DAYS, "match_sim": args.match_sim,
        "dates": dates, "per_date": per_date, "trends": results,
        "controls_triggered": control_hits,
        "max_control_similarity": round(max_control, 3),
        "sensitivity": sensitivity,
        "summary": {
            "tested": len(results), "found": len(found), "found_early": len(early),
            "median_lead_months": (sorted(r["lead_months"] for r in early)[len(early) // 2]
                                   if early else None),
        },
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print(f"\nBacktest: {len(dates)} dates, {args.start} to {end}, 90-day slices, "
          f"{args.top_n} densest pockets each, match at cosine {args.match_sim}")
    print(f"'detected' = a pocket close to the trend that also SAYS one of its "
          f"words. 'field' = the same without that requirement, i.e. when the\n"
          f"surrounding field first formed a pocket. 'bar' = did the matched "
          f"pocket also clear the production density gate of {MIN_COHESION}?\n")
    print(f"{'trend':<30} {'mainstream':>10} {'detected':>9} {'lead':>6} {'field':>8}  bar")
    for r in sorted(results, key=lambda r: (r["first_detected"] is None,
                                            -(r["lead_months"] or -99))):
        lead = "" if r["lead_months"] is None else f"{r['lead_months']:+d}"
        bar = ("yes" if r["above_production_bar"] else "no ") if r["first_detected"] else "   "
        print(f"{r['name'][:30]:<30} {r['mainstream']:>10} "
              f"{r['first_detected'] or '—':>9} {lead:>6} "
              f"{r['field_first_seen'] or '—':>8}  {bar}")
    s = report["summary"]
    print(f"\n{s['found']} of {s['tested']} found, {s['found_early']} of them before "
          f"they were mainstream" +
          (f", median lead {s['median_lead_months']} months" if s["median_lead_months"] else ""))
    print(f"\nUpper bound by threshold, field matches, no term check "
          f"(controls never exceed {max_control:.2f}):")
    print("threshold  found  early  median lead")
    for row in sensitivity:
        mark = " <- used" if abs(row["threshold"] - args.match_sim) < 1e-9 else ""
        lead = "—" if row["median_lead"] is None else f"{row['median_lead']:+d} months"
        print(f"{row['threshold']:>9.2f}  {row['found']:>5}  {row['found_early']:>5}  "
              f"{lead:>11}{mark}")

    if control_hits:
        print(f"\n!! {len(control_hits)} control match(es) — the threshold is too loose:")
        for c in control_hits[:5]:
            print(f"   {c['month']} {c['control']} -> {c['nest']} ({c['sim']})")
    else:
        worst = max((max(d.get("controls", {}).values(), default=0.0) for d in per_date), default=0.0)
        print(f"Controls never matched (highest control similarity {worst:.2f}).")
    print(f"\nFull report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
