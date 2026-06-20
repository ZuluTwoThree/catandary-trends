#!/usr/bin/env python3
"""Phase-5 decision gate: classify 500 via Haiku + 500 via Sonnet, measure cost
and agreement against the existing local qwen classification.

Pulls existing published trends (each carries a local-qwen `primary_vertical` +
`mega_trend` baseline) plus their raw_entry text — no new ingestion needed.
Runs the real pipeline classification chain (relevance → extraction →
classification) through the Anthropic API, capturing token usage for exact cost,
and reports per-model agreement + the model recommendation per the goal's rules.

Usage:
    python scripts/test_classify_models.py --dry-run     # count_tokens only, no spend
    python scripts/test_classify_models.py               # 500 Haiku + 500 Sonnet (real spend)
    python scripts/test_classify_models.py --total 200 --overlap 40
"""
from __future__ import annotations
import argparse
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import ANTHROPIC_API_KEY
from pipeline.db import get_connection
from pipeline.models import RelevanceResult, ExtractionResult, ClassificationResult
from pipeline.llm_processor import (
    RELEVANCE_SYSTEM, EXTRACTION_SYSTEM, CLASSIFICATION_SYSTEM,
)

# Pricing $/MTok (input, output) — verify against the claude-api reference.
PRICING = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}
HAIKU, SONNET = "claude-haiku-4-5", "claude-sonnet-4-6"
VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN", "FASHION", "BIZ", "LIFESTYLE"]
BATCH_DISCOUNT = 0.5          # Message Batches API
SCALE_TARGET = 50_000        # for projected full-run cost
COST_CEILING = 500.0         # abort/reevaluate threshold (50k, batched)


def get_client():
    import anthropic
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def sample(total: int) -> list[dict]:
    """Stratified sample across verticals: raw text + local-qwen baseline."""
    per = max(1, total // len(VERTICALS))
    rows = []
    with get_connection() as c:
        for v in VERTICALS:
            for r in c.execute(
                """SELECT r.id, r.title, r.excerpt, t.primary_vertical, t.mega_trend
                   FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id
                   WHERE t.status='published' AND t.primary_vertical=?
                     AND r.excerpt IS NOT NULL AND length(trim(r.excerpt)) > 20
                   ORDER BY RANDOM() LIMIT ?""", (v, per)).fetchall():
                rows.append(dict(r))
    return rows[:total]


def parse_call(client, model, prompt, schema, system, usage_acc, dry_run):
    """One structured call; accumulates usage. dry_run uses count_tokens only."""
    if dry_run:
        ct = client.messages.count_tokens(
            model=model, system=system, messages=[{"role": "user", "content": prompt}])
        usage_acc["in"] += ct.input_tokens
        usage_acc["out"] += 250  # assumed structured-output size
        return None
    resp = client.messages.parse(
        model=model, max_tokens=2048, temperature=0.0, system=system,
        messages=[{"role": "user", "content": prompt}], output_format=schema)
    u = resp.usage
    usage_acc["in"] += u.input_tokens + getattr(u, "cache_read_input_tokens", 0)
    usage_acc["out"] += u.output_tokens
    if getattr(resp, "stop_reason", None) == "refusal":
        return None
    return resp.parsed_output


def classify_one(client, model, row, usage_acc, dry_run):
    """Run the pipeline chain (relevance → extraction → classification)."""
    title, excerpt = row["title"], (row["excerpt"] or "")
    rel = parse_call(client, model,
                     f"Analyze this RSS feed entry and determine if it's a relevant trend signal.\n"
                     f"Title: {title}\n\nExcerpt: {excerpt[:1500]}",
                     RelevanceResult, RELEVANCE_SYSTEM, usage_acc, dry_run)
    ext = parse_call(client, model,
                     f"Extract structured information from this text.\n\nTitle: {title}\n\nText: {excerpt[:1500]}",
                     ExtractionResult, EXTRACTION_SYSTEM, usage_acc, dry_run)
    cls = parse_call(client, model,
                     f"Classify this trend signal.\n\nTitle: {title}\nExcerpt: {excerpt[:1000]}\n"
                     f"Brand: {(ext.brand_name if ext else None) or 'Unknown'}\n"
                     f"Key Claims: {', '.join(ext.key_claims[:5]) if ext and ext.key_claims else 'None'}",
                     ClassificationResult, CLASSIFICATION_SYSTEM, usage_acc, dry_run)
    if dry_run:
        return None
    return {
        "primary_vertical": rel.primary_vertical if rel else None,
        "mega_trend": cls.mega_trend if cls else None,
    }


def run_model(client, model, rows, dry_run):
    usage = {"in": 0, "out": 0}
    preds = {}
    for i, row in enumerate(rows, 1):
        preds[row["id"]] = classify_one(client, model, row, usage, dry_run)
        if i % 50 == 0:
            print(f"    {model}: {i}/{len(rows)}", flush=True)
    pin, pout = PRICING[model]
    cost = usage["in"] / 1e6 * pin + usage["out"] / 1e6 * pout
    return {"usage": usage, "cost": cost, "n": len(rows), "preds": preds}


def agreement(rows, preds, field):
    rows_by_id = {r["id"]: r for r in rows}
    hits = total = 0
    for rid, p in preds.items():
        base = rows_by_id[rid].get(field)
        if p is None or base is None:
            continue
        total += 1
        if str(p.get(field)) == str(base):
            hits += 1
    return (100 * hits / total) if total else 0.0, total


def report(label, res, rows, dry_run):
    n = res["n"]
    per1k = res["cost"] / n * 1000
    per1k_batch = per1k * BATCH_DISCOUNT
    proj = per1k_batch / 1000 * SCALE_TARGET
    print(f"\n[{label}]  n={n}  tokens in/out={res['usage']['in']}/{res['usage']['out']}")
    print(f"  $/1k (synchron): ${per1k:.2f}   $/1k (Batches -50%): ${per1k_batch:.2f}   "
          f"proj. {SCALE_TARGET//1000}k: ${proj:.0f}")
    if not dry_run:
        va, vn = agreement(rows, res["preds"], "primary_vertical")
        ma, mn = agreement(rows, res["preds"], "mega_trend")
        print(f"  Agreement vs qwen — vertical: {va:.0f}% (n={vn})  mega_trend: {ma:.0f}% (n={mn})")
        res["vertical_agree"], res["mega_agree"], res["proj"] = va, ma, proj
    else:
        res["proj"] = proj
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--total", type=int, default=1000)
    ap.add_argument("--overlap", type=int, default=100,
                    help="how many Haiku items to also run on Sonnet (direct agreement)")
    ap.add_argument("--dry-run", action="store_true", help="count_tokens only, no spend")
    args = ap.parse_args()

    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY not set — set it in .env first.")
        return 2

    rows = sample(args.total)
    print(f"Sample: {len(rows)} entries", end="  ")
    by_v = defaultdict(int)
    for r in rows:
        by_v[r["primary_vertical"]] += 1
    print(dict(by_v))
    half = len(rows) // 2
    haiku_rows, sonnet_rows = rows[:half], rows[half:]
    overlap_rows = haiku_rows[:args.overlap]

    client = get_client()
    print(f"\n=== {HAIKU}: {len(haiku_rows)} ===")
    h = report("HAIKU", run_model(client, HAIKU, haiku_rows, args.dry_run), haiku_rows, args.dry_run)
    print(f"\n=== {SONNET}: {len(sonnet_rows)} ===")
    s = report("SONNET", run_model(client, SONNET, sonnet_rows, args.dry_run), sonnet_rows, args.dry_run)

    if not args.dry_run and overlap_rows:
        print(f"\n=== Overlap: {len(overlap_rows)} via Sonnet (Haiku-vs-Sonnet) ===")
        so = run_model(client, SONNET, overlap_rows, False)
        hv = h["preds"]
        agree = sum(1 for rid, sp in so["preds"].items()
                    if sp and hv.get(rid) and sp["primary_vertical"] == hv[rid]["primary_vertical"])
        print(f"  Haiku-vs-Sonnet vertical agreement: {100*agree/len(overlap_rows):.0f}%")

    # Decision (goal rules)
    print("\n=== DECISION ===")
    if args.dry_run:
        print("  Dry-run — keine Agreement-/Decision-Werte. Mit echtem Lauf wiederholen.")
        return 0
    if h["vertical_agree"] < 80 and s["vertical_agree"] < 80:
        print("  ABBRUCH: vertical-Agreement < 80% bei beiden Modellen → lokal bleiben.")
        return 0
    h_comb = (h["vertical_agree"] + h["mega_agree"]) / 2
    s_comb = (s["vertical_agree"] + s["mega_agree"]) / 2
    print(f"  combined agreement — Haiku {h_comb:.0f}%  Sonnet {s_comb:.0f}%")
    if h_comb >= s_comb - 5:
        print(f"  → HAIKU empfohlen (innerhalb 5pp von Sonnet). proj. 50k batched ${h['proj']:.0f}")
    elif s["proj"] <= COST_CEILING:
        print(f"  → SONNET empfohlen. proj. 50k batched ${s['proj']:.0f} (≤ ${COST_CEILING:.0f})")
    else:
        print(f"  REEVALUIEREN: Sonnet besser, aber proj. 50k ${s['proj']:.0f} > ${COST_CEILING:.0f}-Ceiling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
