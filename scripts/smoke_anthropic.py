#!/usr/bin/env python3
"""Phase-1 smoke test: anthropic_client.chat_structured returns a valid result.

Sends one sample RSS-style entry through the relevance schema via Claude and
prints the parsed result. Requires ANTHROPIC_API_KEY (exits cleanly with a hint
if unset). Costs a few cents.

Usage:
    python scripts/smoke_anthropic.py
    ANTHROPIC_MODEL_CLASSIFY=claude-sonnet-4-6 python scripts/smoke_anthropic.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL_CLASSIFY
from pipeline import anthropic_client
from pipeline.models import RelevanceResult
from pipeline.llm_processor import RELEVANCE_SYSTEM

SAMPLE_TITLE = "Startup raises $40M to scale precision-fermentation dairy proteins"
SAMPLE_EXCERPT = (
    "The company says its animal-free whey protein, brewed by engineered microbes, "
    "has reached cost parity with conventional whey and will launch in three CPG "
    "brands this year. The round was led by a climate-focused VC."
)


def main() -> int:
    if not ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY not set — set it in .env to run the smoke test.")
        return 2
    print(f"Model: {ANTHROPIC_MODEL_CLASSIFY}")
    prompt = (f"Analyze this RSS feed entry and determine if it's a relevant trend signal.\n"
              f"Title: {SAMPLE_TITLE}\n\nExcerpt: {SAMPLE_EXCERPT}")
    result = anthropic_client.chat_structured(
        model=ANTHROPIC_MODEL_CLASSIFY,
        prompt=prompt,
        schema=RelevanceResult,
        system=RELEVANCE_SYSTEM,
        temperature=0.0,
    )
    if result is None:
        print("FAIL: chat_structured returned None")
        return 1
    assert isinstance(result, RelevanceResult)
    print(f"OK: is_relevant={result.is_relevant} confidence={result.confidence} "
          f"primary_vertical={result.primary_vertical}")
    print(f"reason: {result.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
