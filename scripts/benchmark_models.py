#!/usr/bin/env python3
"""Benchmark different LLM models on a single trend signal.

Usage:
    python scripts/benchmark_models.py

Runs the same trend through content generation with different models,
measuring speed, VRAM usage, and output quality for comparison.
"""

import json
import sys
import time

# Add project root to path
sys.path.insert(0, ".")

from pipeline.ollama_client import client, chat_structured
from pipeline.models import GeneratedContent, RelevanceResult, ClassificationResult
from pipeline.llm_processor import CONTENT_EN_SYSTEM, RELEVANCE_SYSTEM, CLASSIFICATION_SYSTEM

# ---------------------------------------------------------------------------
# Test data: a real-ish RSS entry
# ---------------------------------------------------------------------------
TEST_ENTRY = {
    "title": "CRISPR-Based Gene Therapy Shows 94% Efficacy in Sickle Cell Trial",
    "excerpt": (
        "Vertex Pharmaceuticals announced phase 3 results for its CRISPR-based gene therapy "
        "exa-cel, showing 94% of patients with sickle cell disease remained free of vaso-occlusive "
        "crises 18 months post-treatment. The one-time therapy edits patients' own stem cells to "
        "produce fetal hemoglobin. FDA approval is expected Q3 2026. The treatment costs approximately "
        "$2.2M per patient but could eliminate lifetime treatment costs estimated at $1.6M. Analysts "
        "project the therapy could reach $3B in annual revenue by 2030. The results also raise "
        "questions about healthcare equity and access in developing nations where sickle cell "
        "prevalence is highest."
    ),
    "source_name": "STAT News",
    "source_url": "https://www.statnews.com/example",
}


def get_vram_usage() -> str:
    """Try to get current VRAM usage via nvidia-smi."""
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            used, total = result.stdout.strip().split(", ")
            return f"{int(used)/1024:.1f}GB / {int(total)/1024:.1f}GB"
    except Exception:
        pass
    return "N/A"


def benchmark_content_gen(model: str) -> dict:
    """Benchmark content generation with a specific model."""
    prompt = f"""Write a trend article in English based on this information.

Original Title: {TEST_ENTRY['title']}
Original Excerpt: {TEST_ENTRY['excerpt']}
Brand: Vertex Pharmaceuticals
Product: exa-cel
Key Claims: 94% efficacy, CRISPR gene therapy, sickle cell, $2.2M cost, FDA approval expected Q3 2026
Verticals: HEALTH, TECH
PESTEL: T, S, E
Signal Type: research
Mega Trend: Personalized Medicine & Genomics
Source: {TEST_ENTRY['source_name']} ({TEST_ENTRY['source_url']})

Include this source attribution at the end: "Source: {TEST_ENTRY['source_name']}" """

    print(f"\n{'='*60}")
    print(f"MODEL: {model}")
    print(f"VRAM before: {get_vram_usage()}")
    print(f"{'='*60}")

    t0 = time.time()
    result = chat_structured(
        model=model,
        prompt=prompt,
        schema=GeneratedContent,
        system=CONTENT_EN_SYSTEM,
        temperature=0.7,
    )
    elapsed = time.time() - t0

    if result is None:
        print(f"  FAILED after {elapsed:.1f}s")
        return {"model": model, "status": "failed", "time": elapsed}

    vram = get_vram_usage()
    word_count = len(result.body.split())

    print(f"  Time: {elapsed:.1f}s")
    print(f"  VRAM after: {vram}")
    print(f"  Words: {word_count}")
    print(f"\n  TITLE: {result.title}")
    print(f"\n  SUMMARY: {result.summary}")
    print(f"\n  BODY ({word_count} words):")
    print(f"  {result.body[:500]}...")
    print()

    return {
        "model": model,
        "status": "ok",
        "time": round(elapsed, 1),
        "vram": vram,
        "word_count": word_count,
        "title": result.title,
        "summary": result.summary,
        "body": result.body,
    }


def benchmark_classification(model: str) -> dict:
    """Benchmark classification with a specific model."""
    prompt = f"""Classify this trend signal.

Title: {TEST_ENTRY['title']}
Excerpt: {TEST_ENTRY['excerpt'][:1000]}
Brand: Vertex Pharmaceuticals
Product: exa-cel
Key Claims: 94% efficacy, CRISPR gene therapy, sickle cell, $2.2M cost"""

    print(f"\n{'='*60}")
    print(f"CLASSIFY with: {model}")
    print(f"{'='*60}")

    t0 = time.time()
    result = chat_structured(
        model=model,
        prompt=prompt,
        schema=ClassificationResult,
        system=CLASSIFICATION_SYSTEM,
        temperature=0.0,
    )
    elapsed = time.time() - t0

    if result is None:
        print(f"  FAILED after {elapsed:.1f}s")
        return {"model": model, "status": "failed", "time": elapsed}

    print(f"  Time: {elapsed:.1f}s")
    print(f"  VRAM: {get_vram_usage()}")
    print(f"  Verticals: {result.verticals}")
    print(f"  PESTEL: {result.pestel}")
    print(f"  Signal: {result.trend_signal_type}")
    print(f"  Mega-trend: {result.mega_trend}")
    print(f"  Tags: {result.tags}")

    return {
        "model": model,
        "status": "ok",
        "time": round(elapsed, 1),
        "verticals": result.verticals,
        "pestel": result.pestel,
        "signal_type": result.trend_signal_type,
        "mega_trend": result.mega_trend,
        "tags": result.tags,
    }


def get_available_models() -> list[str]:
    """Get list of locally available models."""
    try:
        models = client.list()
        return [m.model for m in models.models]
    except Exception:
        return []


def main():
    available = get_available_models()
    print(f"Available models: {available}\n")

    # Models to test for content generation
    content_models = []
    classify_models = []

    for m in available:
        if "embed" in m or "nomic" in m or "nuextract" in m:
            continue
        # Content gen candidates (larger models + new efficient ones)
        if any(x in m for x in ["9b", "14b", "27b", "30b", "32b", "24b", "e4b"]):
            content_models.append(m)
        # Classification candidates (all non-embedding)
        classify_models.append(m)

    # Always include current baselines
    if "qwen3:14b" not in content_models:
        content_models.insert(0, "qwen3:14b")
    if "qwen3:8b" not in classify_models:
        classify_models.insert(0, "qwen3:8b")

    print("=" * 60)
    print("CONTENT GENERATION BENCHMARK")
    print("=" * 60)

    content_results = []
    for model in content_models:
        try:
            r = benchmark_content_gen(model)
            content_results.append(r)
        except Exception as e:
            print(f"  ERROR with {model}: {e}")
            content_results.append({"model": model, "status": "error", "error": str(e)})

    print("\n" + "=" * 60)
    print("CLASSIFICATION BENCHMARK")
    print("=" * 60)

    classify_results = []
    for model in classify_models:
        try:
            r = benchmark_classification(model)
            classify_results.append(r)
        except Exception as e:
            print(f"  ERROR with {model}: {e}")
            classify_results.append({"model": model, "status": "error", "error": str(e)})

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print("\nContent Generation:")
    print(f"{'Model':<30} {'Time':>8} {'Words':>8} {'VRAM':>15}")
    print("-" * 65)
    for r in content_results:
        if r["status"] == "ok":
            print(f"{r['model']:<30} {r['time']:>7.1f}s {r['word_count']:>8} {r['vram']:>15}")
        else:
            print(f"{r['model']:<30} {'FAILED':>8}")

    print("\nClassification:")
    print(f"{'Model':<30} {'Time':>8} {'Verticals':<20} {'Mega-trend'}")
    print("-" * 80)
    for r in classify_results:
        if r["status"] == "ok":
            print(f"{r['model']:<30} {r['time']:>7.1f}s {str(r['verticals']):<20} {r['mega_trend']}")
        else:
            print(f"{r['model']:<30} {'FAILED':>8}")


if __name__ == "__main__":
    main()
