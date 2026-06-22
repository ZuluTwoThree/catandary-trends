#!/usr/bin/env python3
"""Throughput benchmark for the parallel local llama.cpp classifier (P1 tuning).

Sends N classification prompts to the running llama-server (port 8090) at several
concurrency levels and reports req/min. Use it to tune `--parallel` / `-c` on the
server: more slots need more total context (each slot needs room for the prompt).

Per-stage prompt sizes differ — Stage 4 (classification) carries the big mega-trend
system block (~3,100 tok → needs ~4,000 tok/slot), so it caps slots harder than
relevance. Bench the stage you care about.

    # after (re)starting the server, e.g.:
    #   start-qwen3-8b.sh --parallel 32 -c 131072
    python scripts/bench_local_parallel.py --vertical DESIGN --stage classification \
        --concurrency 8,16,24,32 --n 60
"""
from __future__ import annotations
import argparse, logging, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
logging.getLogger("httpx").setLevel(logging.WARNING)

from pipeline.db import get_connection
from pipeline import llamacpp_client as lc
from pipeline.config import STAGE_8B_MODEL
from pipeline.llm_processor import RELEVANCE_SYSTEM, EXTRACTION_SYSTEM, CLASSIFICATION_SYSTEM
from pipeline.models import RelevanceResult, ExtractionResult, ClassificationResult
from scripts.signal_batch import p_relevance, p_extraction, p_classification

STAGES = {
    "relevance":      (RELEVANCE_SYSTEM,      RelevanceResult,      lambda r: p_relevance(r["title"] or "", r["excerpt"] or "")),
    "extraction":     (EXTRACTION_SYSTEM,     ExtractionResult,     lambda r: p_extraction(r["title"] or "", r["excerpt"] or "")),
    "classification": (CLASSIFICATION_SYSTEM, ClassificationResult, lambda r: p_classification(r["title"] or "", r["excerpt"] or "", ExtractionResult())),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vertical", default="DESIGN")
    ap.add_argument("--stage", default="relevance", choices=list(STAGES))
    ap.add_argument("--concurrency", default="1,8,16", help="comma list")
    ap.add_argument("--n", type=int, default=60, help="prompts per concurrency level")
    args = ap.parse_args()
    system, schema, build = STAGES[args.stage]
    levels = [int(x) for x in args.concurrency.split(",")]

    need = args.n * len(levels)
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT r.title, r.excerpt FROM raw_entries r JOIN sources s ON r.source_id=s.id "
            "WHERE s.vertical=? AND r.processed=0 LIMIT ?", (args.vertical, need)).fetchall()]
    prompts = [build(r) for r in rows]
    print(f"{len(prompts)} {args.vertical}/{args.stage} prompts | model={STAGE_8B_MODEL}\n")

    def one(p):
        return lc.chat_structured(model=STAGE_8B_MODEL, prompt=p, schema=schema,
                                  system=system, temperature=0.0)

    print(f"{'conc':<6}{'n':>5}{'time':>9}{'req/min':>10}{'ok':>6}")
    print("-" * 36)
    i = 0
    for C in levels:
        batch = prompts[i:i + args.n]; i += args.n
        if not batch:
            break
        t = time.time()
        with ThreadPoolExecutor(max_workers=C) as ex:
            res = list(ex.map(one, batch))
        dt = time.time() - t
        ok = sum(1 for r in res if r is not None)
        print(f"{C:<6}{len(batch):>5}{dt:>8.1f}s{len(batch)/dt*60:>10.0f}{ok:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
