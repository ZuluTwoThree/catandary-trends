#!/usr/bin/env python3
"""Auto-publish high-confidence trend drafts.

Publishes drafts that meet the confidence threshold without manual review.
Run hourly via cron: 0 * * * * python pipeline/auto_publisher.py
"""

import argparse
import logging
import sys

from pipeline.config import AUTO_PUBLISH_CONFIDENCE, LOG_LEVEL
from pipeline.db import get_trends, init_db, update_trend_status

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Sentence-terminal characters. A body that doesn't end in one of these is
# truncated mid-sentence (a grammar/max_tokens artifact of content-gen). The
# content guard retries once but returns the last result anyway, so a still-
# truncated body would otherwise be auto-published on confidence alone (#18).
# This is the publish gate: incomplete bodies stay 'draft' for review, backend-
# agnostically (also covers the Ollama path, which has no content-gen validator).
_TERMINAL_PUNCT = (".", "!", "?", '"', "”", "’", "'", ")", "…")


def _body_complete(body: str | None) -> bool:
    """True if the article body ends in sentence-terminal punctuation."""
    if not body or not body.strip():
        return False
    return body.rstrip().endswith(_TERMINAL_PUNCT)


def auto_publish(min_confidence: float = AUTO_PUBLISH_CONFIDENCE,
                 dry_run: bool = False) -> dict:
    """Auto-publish drafts above the confidence threshold.

    Returns stats dict with counts.
    """
    init_db()

    drafts = get_trends(status="draft", limit=500)
    published = 0
    skipped = 0
    held_truncated = 0

    for trend in drafts:
        confidence = trend.get("confidence", 0.0) or 0.0
        trend_id = trend["id"]
        title = trend.get("title_en", "Untitled")

        if confidence < min_confidence:
            logger.debug("Skipped #%d: '%s' (conf=%.2f < %.2f)",
                         trend_id, title[:60], confidence, min_confidence)
            skipped += 1
            continue

        # Publish gate: never auto-publish a mid-sentence/truncated body (#18) —
        # keep it as a draft for manual review instead.
        if not _body_complete(trend.get("body_en")):
            logger.warning("Held #%d (truncated body, not auto-published): '%s'",
                           trend_id, title[:60])
            held_truncated += 1
            continue

        if dry_run:
            logger.info("[DRY RUN] Would publish #%d: '%s' (conf=%.2f)",
                        trend_id, title[:60], confidence)
        else:
            update_trend_status(trend_id, "published", auto_published=True)
            logger.info("Auto-published #%d: '%s' (conf=%.2f)",
                        trend_id, title[:60], confidence)
        published += 1

    logger.info("Auto-publish complete: %d published, %d skipped, %d held (truncated) "
                "(threshold=%.2f%s)", published, skipped, held_truncated, min_confidence,
                ", DRY RUN" if dry_run else "")

    return {"published": published, "skipped": skipped, "held_truncated": held_truncated}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-publish high-confidence trend drafts")
    parser.add_argument("--min-confidence", type=float, default=AUTO_PUBLISH_CONFIDENCE,
                        help=f"Minimum confidence to auto-publish (default: {AUTO_PUBLISH_CONFIDENCE})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be published without actually publishing")
    args = parser.parse_args()

    result = auto_publish(min_confidence=args.min_confidence, dry_run=args.dry_run)
    sys.exit(0 if result["published"] >= 0 else 1)
