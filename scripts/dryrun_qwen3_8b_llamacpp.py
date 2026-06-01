#!/usr/bin/env python3
"""Dry-run: compare Stages 2/3/4/8 between Ollama qwen3:8b and llama.cpp Qwen3-8B.

For ~50 recent raw_entries, runs each of the four qwen3:8b-driven stages twice:
once via pipeline.ollama_client.chat_structured (current production path),
once via pipeline.llamacpp_client.chat_structured against the llama-server
serving the Qwen3-8B GGUF (env STAGE_8B_MODEL, default Qwen3-8B-UD-Q4_K_XL.gguf).

Reports per stage: schema-valid count, latency p50/p95, and field-level
inter-rater agreement (Ollama vs llama.cpp). No DB writes, no env mutation.

Validation thresholds (from goal contract):
  Schema-valide       ≥98%   per stage
  is_relevant         ≥90%   agreement
  primary_vertical    ≥85%   agreement
  trend_signal_type   ≥80%   agreement
  median latency      ≤ Ollama median × 1.5

Prerequisite: llama-server must be serving STAGE_8B_MODEL on port 8090.
Run: `ln -sfn start-qwen3-8b.sh ~/llama.cpp/start-active.sh`
     `systemctl --user restart llama-server.service`
then `STAGE_8B_MODEL=Qwen3-8B-UD-Q4_K_XL.gguf python -m scripts.dryrun_qwen3_8b_llamacpp [N]`
"""

import argparse
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection
from pipeline import llamacpp_client, ollama_client
from pipeline.llm_processor import (
    CLASSIFICATION_SYSTEM,
    EXTRACTION_SYSTEM,
    RELEVANCE_SYSTEM,
)
from pipeline.models import (
    ClassificationResult,
    ExtractionResult,
    RelevanceResult,
)
from pipeline.reclassify import CLASSIFY_SYSTEM as RECLASSIFY_SYSTEM
from pipeline.reclassify import ReclassifyResult

OLLAMA_MODEL = "qwen3:8b"


def _time_call(client_chat, **kwargs):
    """Call chat_structured and return (result, elapsed_seconds)."""
    t0 = time.time()
    result = client_chat(**kwargs)
    return result, time.time() - t0


def _fmt_pct(num: int, denom: int) -> str:
    if denom == 0:
        return "n/a"
    return f"{100 * num / denom:.0f}% ({num}/{denom})"


def _p(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(round(q * (len(s) - 1)))
    return s[idx]


# ---------- per-stage runners ---------------------------------------------

def run_stage2(title, excerpt, llamacpp_model):
    prompt = (
        "Analyze this RSS feed entry and determine if it's a relevant trend signal.\n"
        "Classify the vertical based purely on the content, not on where the source comes from.\n\n"
        f"Title: {title}\n\nExcerpt: {(excerpt or '')[:1500]}"
    )
    common = dict(prompt=prompt, schema=RelevanceResult, system=RELEVANCE_SYSTEM,
                  temperature=0.0)
    ollama_r, ollama_dt = _time_call(ollama_client.chat_structured,
                                     model=OLLAMA_MODEL, **common)
    llama_r, llama_dt = _time_call(llamacpp_client.chat_structured,
                                   model=llamacpp_model, **common)
    return ollama_r, ollama_dt, llama_r, llama_dt


def run_stage3(title, excerpt, llamacpp_model):
    prompt = (
        f"Extract structured information from this text.\n\n"
        f"Title: {title}\n\nText: {(excerpt or '')[:1500]}"
    )
    common = dict(prompt=prompt, schema=ExtractionResult, system=EXTRACTION_SYSTEM,
                  temperature=0.0)
    ollama_r, ollama_dt = _time_call(ollama_client.chat_structured,
                                     model=OLLAMA_MODEL, **common)
    llama_r, llama_dt = _time_call(llamacpp_client.chat_structured,
                                   model=llamacpp_model, **common)
    return ollama_r, ollama_dt, llama_r, llama_dt


def run_stage4(title, excerpt, extraction, llamacpp_model):
    """Stage 4 takes the extraction result as context. Use the ollama-extraction
    output for both calls so we isolate Stage 4 model variance (otherwise we'd
    chain noise from Stage 3 into Stage 4)."""
    if extraction is None:
        return None, 0.0, None, 0.0
    prompt = (
        f"Classify this trend signal.\n\n"
        f"Title: {title}\nExcerpt: {(excerpt or '')[:1000]}\n"
        f"Brand: {extraction.brand_name or 'Unknown'}\n"
        f"Product: {extraction.product_name or 'Unknown'}\n"
        f"Key Claims: {', '.join(extraction.key_claims[:5]) if extraction.key_claims else 'None'}"
    )
    common = dict(prompt=prompt, schema=ClassificationResult,
                  system=CLASSIFICATION_SYSTEM, temperature=0.0)
    ollama_r, ollama_dt = _time_call(ollama_client.chat_structured,
                                     model=OLLAMA_MODEL, **common)
    llama_r, llama_dt = _time_call(llamacpp_client.chat_structured,
                                   model=llamacpp_model, **common)
    return ollama_r, ollama_dt, llama_r, llama_dt


def run_stage8(title, excerpt, llamacpp_model):
    """Stage 8 reclassifies a published trend. We use raw title+excerpt as a
    proxy for the published summary — same ballpark of input length."""
    prompt = f"Title: {title}\nSummary: {(excerpt or '')[:500]}"
    common = dict(prompt=prompt, schema=ReclassifyResult,
                  system=RECLASSIFY_SYSTEM, temperature=0.0)
    ollama_r, ollama_dt = _time_call(ollama_client.chat_structured,
                                     model=OLLAMA_MODEL, **common)
    llama_r, llama_dt = _time_call(llamacpp_client.chat_structured,
                                   model=llamacpp_model, **common)
    return ollama_r, ollama_dt, llama_r, llama_dt


# ---------- agreement metrics ---------------------------------------------

def _agree(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return a == b


def _agree_str_nullable(a: str | None, b: str | None) -> bool:
    """Case-insensitive equality, treating None/empty as equivalent."""
    aa = (a or "").strip().lower()
    bb = (b or "").strip().lower()
    return aa == bb


def _jaccard(a: list[str] | None, b: list[str] | None) -> float:
    aa = set(s.lower() for s in (a or []))
    bb = set(s.lower() for s in (b or []))
    if not aa and not bb:
        return 1.0
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


# ---------- main ----------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", nargs="?", type=int, default=50, help="sample size")
    args = ap.parse_args()

    llamacpp_model = os.getenv("STAGE_8B_MODEL", "Qwen3-8B-UD-Q4_K_XL.gguf")

    with get_connection() as conn:
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute(
            "SELECT id, title, excerpt FROM raw_entries "
            "WHERE excerpt IS NOT NULL AND length(excerpt) > 200 "
            "ORDER BY id DESC LIMIT ?",
            (args.n,),
        ).fetchall()

    print(f"Sample size      : {len(rows)} raw_entries")
    print(f"Ollama model     : {OLLAMA_MODEL}")
    print(f"llama.cpp model  : {llamacpp_model}")
    print(f"Targets          : ≥98% schema, ≥90% is_relevant, ≥85% primary_vertical, "
          "≥80% signal_type, median latency ≤ Ollama × 1.5")
    print("=" * 80)

    # Counters
    stats = {st: {"ollama_ok": 0, "llama_ok": 0,
                  "ollama_dt": [], "llama_dt": []}
             for st in ("s2", "s3", "s4", "s8")}

    # Agreement
    agree_relevant = agree_pvert_s2 = both_s2 = 0
    agree_brand = agree_product = jaccard_claims_sum = both_s3 = 0
    agree_pvert_s4 = agree_signal = agree_mega = both_s4 = 0
    agree_pvert_s8 = both_s8 = 0
    jaccard_claims_count = 0

    for i, row in enumerate(rows, 1):
        title = row["title"] or ""
        excerpt = row["excerpt"] or ""
        if i % 10 == 0 or i == 1:
            print(f"[{i}/{len(rows)}] #{row['id']} {title[:60]}")

        # Stage 2 — relevance
        o, od, l, ld = run_stage2(title, excerpt, llamacpp_model)
        stats["s2"]["ollama_dt"].append(od)
        stats["s2"]["llama_dt"].append(ld)
        if o is not None:
            stats["s2"]["ollama_ok"] += 1
        if l is not None:
            stats["s2"]["llama_ok"] += 1
        if o is not None and l is not None:
            both_s2 += 1
            if o.is_relevant == l.is_relevant:
                agree_relevant += 1
            if o.primary_vertical == l.primary_vertical:
                agree_pvert_s2 += 1

        # Stage 3 — extraction
        o3, od3, l3, ld3 = run_stage3(title, excerpt, llamacpp_model)
        stats["s3"]["ollama_dt"].append(od3)
        stats["s3"]["llama_dt"].append(ld3)
        if o3 is not None:
            stats["s3"]["ollama_ok"] += 1
        if l3 is not None:
            stats["s3"]["llama_ok"] += 1
        if o3 is not None and l3 is not None:
            both_s3 += 1
            if _agree_str_nullable(o3.brand_name, l3.brand_name):
                agree_brand += 1
            if _agree_str_nullable(o3.product_name, l3.product_name):
                agree_product += 1
            jaccard_claims_sum += _jaccard(o3.key_claims, l3.key_claims)
            jaccard_claims_count += 1

        # Stage 4 — classification (use Ollama extraction as shared context)
        if o3 is not None:
            o4, od4, l4, ld4 = run_stage4(title, excerpt, o3, llamacpp_model)
            stats["s4"]["ollama_dt"].append(od4)
            stats["s4"]["llama_dt"].append(ld4)
            if o4 is not None:
                stats["s4"]["ollama_ok"] += 1
            if l4 is not None:
                stats["s4"]["llama_ok"] += 1
            if o4 is not None and l4 is not None:
                both_s4 += 1
                o_pvert = o4.verticals[0] if o4.verticals else None
                l_pvert = l4.verticals[0] if l4.verticals else None
                if o_pvert == l_pvert:
                    agree_pvert_s4 += 1
                if o4.trend_signal_type == l4.trend_signal_type:
                    agree_signal += 1
                if _agree(o4.mega_trend, l4.mega_trend):
                    agree_mega += 1

        # Stage 8 — reclassify
        o8, od8, l8, ld8 = run_stage8(title, excerpt, llamacpp_model)
        stats["s8"]["ollama_dt"].append(od8)
        stats["s8"]["llama_dt"].append(ld8)
        if o8 is not None:
            stats["s8"]["ollama_ok"] += 1
        if l8 is not None:
            stats["s8"]["llama_ok"] += 1
        if o8 is not None and l8 is not None:
            both_s8 += 1
            if o8.primary == l8.primary:
                agree_pvert_s8 += 1

    # ---- Report --------------------------------------------------------
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    n = len(rows)
    for st_key, st_label in [("s2", "Stage 2 (Relevance)"),
                              ("s3", "Stage 3 (Extraction)"),
                              ("s4", "Stage 4 (Classification)"),
                              ("s8", "Stage 8 (Reclassify)")]:
        st = stats[st_key]
        n_called = len(st["ollama_dt"])
        print(f"\n{st_label}")
        print(f"  schema-valid Ollama   : {_fmt_pct(st['ollama_ok'], n_called)}")
        print(f"  schema-valid llama.cpp: {_fmt_pct(st['llama_ok'], n_called)}")
        if st["ollama_dt"]:
            print(f"  latency Ollama p50/p95: {_p(st['ollama_dt'], 0.5):.2f}s / {_p(st['ollama_dt'], 0.95):.2f}s")
        if st["llama_dt"]:
            print(f"  latency llama   p50/p95: {_p(st['llama_dt'], 0.5):.2f}s / {_p(st['llama_dt'], 0.95):.2f}s")
            if st["ollama_dt"]:
                median_o = statistics.median(st["ollama_dt"])
                median_l = statistics.median(st["llama_dt"])
                ratio = median_l / median_o if median_o > 0 else 0
                marker = "✓" if ratio <= 1.5 else "✗"
                print(f"  median ratio llama/Ollama: {ratio:.2f}x  [target ≤ 1.5x] {marker}")

    print("\nINTER-RATER AGREEMENT (Ollama vs llama.cpp, both-valid only)")
    print(f"  Stage 2 is_relevant       : {_fmt_pct(agree_relevant, both_s2)}  [target ≥90%]")
    print(f"  Stage 2 primary_vertical  : {_fmt_pct(agree_pvert_s2, both_s2)}  [target ≥85%]")
    print(f"  Stage 3 brand_name        : {_fmt_pct(agree_brand, both_s3)}")
    print(f"  Stage 3 product_name      : {_fmt_pct(agree_product, both_s3)}")
    if jaccard_claims_count:
        print(f"  Stage 3 key_claims Jaccard: {jaccard_claims_sum / jaccard_claims_count:.2f}")
    print(f"  Stage 4 primary_vertical  : {_fmt_pct(agree_pvert_s4, both_s4)}  [target ≥85%]")
    print(f"  Stage 4 trend_signal_type : {_fmt_pct(agree_signal, both_s4)}  [target ≥80%]")
    print(f"  Stage 4 mega_trend        : {_fmt_pct(agree_mega, both_s4)}")
    print(f"  Stage 8 primary           : {_fmt_pct(agree_pvert_s8, both_s8)}  [target ≥85%]")


if __name__ == "__main__":
    main()
