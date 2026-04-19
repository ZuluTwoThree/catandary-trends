#!/usr/bin/env python3
"""Mega-Trend Reviewer — Monthly pipeline step.

Reviews all trends per vertical, validates mega-trend assignments,
and re-assigns trends that have incorrect or missing mega_trend values.

Uses Qwen3 14B for higher reasoning quality.

Usage:
    python -m pipeline.mega_trend_reviewer              # Review all verticals
    python -m pipeline.mega_trend_reviewer DESIGN FOOD  # Review specific verticals
    python -m pipeline.mega_trend_reviewer --dry-run     # Preview without writing to DB
"""

import json
import logging
import sys
import time

from pipeline.config import (
    LOG_LEVEL,
    MODEL_GENERATE,
    load_mega_trends,
    get_mega_trend_prompt_block,
)
from pipeline.db import get_connection
from pipeline.ollama_client import chat_structured

from pydantic import BaseModel, Field

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

VERTICALS = ["FOOD", "TECH", "HEALTH", "ECO", "DESIGN",
             "FASHION", "BIZ", "LIFESTYLE"]

# Process trends in batches to fit context window (~16K tokens)
BATCH_SIZE = 25


class MegaTrendAssignment(BaseModel):
    """Assignment of a mega-trend to a single trend."""
    trend_id: int = Field(description="The trend ID")
    mega_trend: str | None = Field(description="Canonical mega-trend key, or null")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in assignment")


class BatchReviewResult(BaseModel):
    """Result of reviewing a batch of trends."""
    assignments: list[MegaTrendAssignment] = Field(description="Mega-trend assignments for each trend")


REVIEW_SYSTEM = """\
You are a senior trend analyst for Catandary Trends, a cross-industry trend intelligence platform.

## Your task
You will receive a batch of trend signals (title + summary + current mega-trend assignment). \
For each trend, assign the BEST matching mega-trend from the canonical list below.

## Reasoning approach
For each trend, ask yourself:
1. What is the STRUCTURAL DRIVER behind this trend? Not the surface topic, but the deeper shift.
2. "If I removed this structural shift from the world, would this trend signal still exist?"
3. If two mega-trends could apply, pick the one that is the ROOT CAUSE, not the symptom.

Example reasoning:
- "AI-powered skin analysis tool" → The structural driver is AI integration, not beauty → artificial_intelligence_and_automation
- "Mycelium-based packaging" → The structural driver is new bio-materials, not packaging → bio_revolution_and_new_materials
- "Luxury brand opens immersive pop-up store" → The driver is experience over ownership → experience_economy_and_immersive_design
- "Rammed earth house in flood zone" → The driver is adapting to climate, not just materials → climate_resilience_and_adaptation

## Canonical mega-trends
{mega_trend_block}

## Rules
- Use ONLY keys from the list above. Never invent new names.
- Set mega_trend to null only if the trend genuinely does not fit ANY mega-trend.
- Set confidence to how certain you are (0.5 = could go either way, 0.9 = very clear).
- Be consistent: similar trends should get the same mega-trend."""


def get_trends_for_vertical(vertical: str, only_null: bool = False) -> list[dict]:
    """Fetch published trends for a vertical.

    If only_null is True, only return trends with missing mega_trend.
    """
    with get_connection() as conn:
        query = (
            "SELECT id, title_en, summary_en, mega_trend, tags "
            "FROM trends WHERE primary_vertical = ? AND status = 'published' "
        )
        if only_null:
            query += "AND (mega_trend IS NULL OR mega_trend = '') "
        query += "ORDER BY created_at DESC"
        rows = conn.execute(query, (vertical,)).fetchall()
        return [dict(r) for r in rows]


def build_batch_prompt(trends: list[dict]) -> str:
    """Build the user prompt for a batch of trends."""
    lines = ["Review these trend signals and assign the best mega-trend for each:\n"]
    for t in trends:
        current = t.get("mega_trend") or "NONE"
        tags = t.get("tags", "[]")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []
        tag_str = ", ".join(tags[:5]) if tags else "none"
        lines.append(
            f"ID: {t['id']}\n"
            f"Title: {t['title_en']}\n"
            f"Summary: {(t.get('summary_en') or '')[:200]}\n"
            f"Tags: {tag_str}\n"
            f"Current mega-trend: {current}\n"
        )
    return "\n".join(lines)


def review_batch(trends: list[dict], system_prompt: str, dry_run: bool = False) -> dict:
    """Review a batch of trends and update their mega-trend assignments."""
    prompt = build_batch_prompt(trends)
    result = chat_structured(
        model=MODEL_GENERATE,
        prompt=prompt,
        schema=BatchReviewResult,
        system=system_prompt,
        temperature=0.3,
    )

    if result is None:
        logger.error("LLM returned None for batch of %d trends", len(trends))
        return {"reviewed": 0, "updated": 0, "errors": 1}

    canonical_keys = {mt["key"] for mt in load_mega_trends()}
    trend_map = {t["id"]: t for t in trends}
    updated = 0

    for assignment in result.assignments:
        tid = assignment.trend_id
        if tid not in trend_map:
            logger.warning("LLM returned unknown trend_id %d, skipping", tid)
            continue

        old = trend_map[tid].get("mega_trend")
        new = assignment.mega_trend

        # Validate against canonical list
        if new and new not in canonical_keys:
            normalized = new.lower().strip().replace("-", "_").replace(" ", "_")
            if normalized in canonical_keys:
                new = normalized
            else:
                logger.warning("Non-canonical mega_trend '%s' for trend %d, setting to None", new, tid)
                new = None

        if old != new:
            if dry_run:
                logger.info("[DRY RUN] Trend %d: '%s' → '%s' (conf=%.2f) | %s",
                            tid, old, new, assignment.confidence,
                            trend_map[tid]["title_en"][:60])
            else:
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE trends SET mega_trend = ? WHERE id = ?",
                        (new, tid),
                    )
                logger.info("Updated trend %d: '%s' → '%s' (conf=%.2f)",
                            tid, old, new, assignment.confidence)
            updated += 1

    return {"reviewed": len(result.assignments), "updated": updated, "errors": 0}


def review_vertical(vertical: str, dry_run: bool = False, only_null: bool = False) -> dict:
    """Review trends in a vertical. If only_null, only those without mega_trend."""
    trends = get_trends_for_vertical(vertical, only_null=only_null)
    if not trends:
        logger.info("No trends found for vertical %s", vertical)
        return {"vertical": vertical, "total": 0, "reviewed": 0, "updated": 0, "errors": 0}

    logger.info("Reviewing %d trends for vertical %s", len(trends), vertical)

    system_prompt = REVIEW_SYSTEM.format(mega_trend_block=get_mega_trend_prompt_block())

    total_reviewed = 0
    total_updated = 0
    total_errors = 0

    # Process in batches
    for i in range(0, len(trends), BATCH_SIZE):
        batch = trends[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(trends) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info("Batch %d/%d (%d trends)", batch_num, total_batches, len(batch))

        t0 = time.time()
        stats = review_batch(batch, system_prompt, dry_run)
        elapsed = time.time() - t0

        total_reviewed += stats["reviewed"]
        total_updated += stats["updated"]
        total_errors += stats["errors"]

        logger.info("Batch %d done in %.1fs: %d reviewed, %d updated",
                     batch_num, elapsed, stats["reviewed"], stats["updated"])

        # Brief pause between batches to let Ollama breathe
        if i + BATCH_SIZE < len(trends):
            time.sleep(2)

    result = {
        "vertical": vertical,
        "total": len(trends),
        "reviewed": total_reviewed,
        "updated": total_updated,
        "errors": total_errors,
    }
    logger.info("Vertical %s complete: %s", vertical, result)
    return result


def run_reviewer(verticals: list[str] | None = None, dry_run: bool = False, only_null: bool = False):
    """Run the mega-trend reviewer for specified or all verticals."""
    t0 = time.time()
    target_verticals = verticals or VERTICALS

    logger.info("=== Mega-Trend Reviewer starting ===")
    logger.info("Verticals: %s", target_verticals)
    logger.info("Mode: %s", "DRY RUN" if dry_run else "LIVE")
    logger.info("Scope: %s", "NULL mega-trends only" if only_null else "all trends")
    logger.info("Model: %s", MODEL_GENERATE)

    all_results = []
    for vertical in target_verticals:
        result = review_vertical(vertical, dry_run, only_null=only_null)
        all_results.append(result)

    elapsed = time.time() - t0
    total_reviewed = sum(r["reviewed"] for r in all_results)
    total_updated = sum(r["updated"] for r in all_results)
    total_errors = sum(r["errors"] for r in all_results)

    logger.info("=== Mega-Trend Reviewer complete in %.1fs ===", elapsed)
    logger.info("Total: %d reviewed, %d updated, %d errors",
                total_reviewed, total_updated, total_errors)

    for r in all_results:
        logger.info("  %s: %d/%d updated", r["vertical"], r["updated"], r["total"])

    return all_results


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dry_run = "--dry-run" in sys.argv
    only_null = "--null" in sys.argv

    verticals = [a.upper() for a in args if a.upper() in VERTICALS] or None
    run_reviewer(verticals=verticals, dry_run=dry_run, only_null=only_null)
