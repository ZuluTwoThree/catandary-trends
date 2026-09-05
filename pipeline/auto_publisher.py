#!/usr/bin/env python3
"""Auto-publish high-confidence trend drafts.

Publishes drafts that meet the confidence threshold without manual review.
Run hourly via cron: 0 * * * * python pipeline/auto_publisher.py
"""

import argparse
import logging
import sys

from pipeline.config import (AUTO_PUBLISH_CONFIDENCE, AUTO_PUBLISH_GROUNDING_GATE,
                             AUTO_PUBLISH_LIMIT, LOG_LEVEL)
from pipeline.content_guard import garbage_reasons
from pipeline.db import get_connection, get_trends, init_db, update_trend_status
from pipeline.grounding import ungrounded_specifics, source_from_parts

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


def _source_text(raw_entry_id: int | None) -> str | None:
    """The source material the content model actually saw, for the grounding gate:
    title + full text (raw_content when present, else the RSS excerpt) + the
    extracted specifics (claims/figures/dates/quotes/geography). None if
    unavailable (→ grounding gate skipped for that row, fail-open).

    Must mirror step_generate_content_en's source: content-gen prefers
    `raw_content or excerpt` (#11), so checking the body against only the short
    RSS excerpt would falsely flag a figure that is in the full text — the very
    false-hold this build avoids."""
    if not raw_entry_id:
        return None
    try:
        with get_connection() as conn:
            r = conn.execute(
                "SELECT title, raw_content, excerpt, extraction_json FROM raw_entries WHERE id = ?",
                (raw_entry_id,)).fetchone()
        if not r:
            return None
        r = dict(r) if not isinstance(r, dict) else r
        ext: dict = {}
        ej = r.get("extraction_json")
        if ej:
            import json as _json
            try:
                ext = _json.loads(ej) or {}
            except Exception:
                ext = {}
        body_source = r.get("raw_content") or r.get("excerpt") or ""
        return source_from_parts(
            r.get("title"), body_source,
            ext.get("key_claims"), ext.get("key_figures"),
            ext.get("dates"), ext.get("quotes"), ext.get("geography"),
        )
    except Exception:
        return None


def auto_publish(min_confidence: float = AUTO_PUBLISH_CONFIDENCE,
                 dry_run: bool = False, limit: int = AUTO_PUBLISH_LIMIT) -> dict:
    """Auto-publish drafts above the confidence threshold.

    `limit` caps how many drafts are scanned in one run. It defaults to
    AUTO_PUBLISH_LIMIT (generous) so a run drains the whole draft pool rather
    than leaving a permanent backlog of publishable high-confidence drafts.

    Returns stats dict with counts.
    """
    init_db()

    drafts = get_trends(status="draft", limit=limit)
    published = 0
    skipped = 0
    held_truncated = 0
    held_fabricated = 0
    held_garbled = 0

    for trend in drafts:
        confidence = trend.get("confidence", 0.0) or 0.0
        trend_id = trend["id"]
        title = trend.get("title_en", "Untitled")

        if confidence < min_confidence:
            logger.debug("Skipped #%d: '%s' (conf=%.2f < %.2f)",
                         trend_id, title[:60], confidence, min_confidence)
            skipped += 1
            continue

        source = _source_text(trend.get("raw_entry_id")) if AUTO_PUBLISH_GROUNDING_GATE else None

        # Garbage gate (#11, 2026-09-05): token soup with confidence 0.93 must
        # never go live. Body-intrinsic rules always run; the script-leak rule
        # needs the source and is skipped when it is unavailable. Checked before
        # truncation so the hold reason names the real defect.
        garbage = garbage_reasons(trend.get("body_en"), source)
        if garbage:
            logger.warning("Held #%d (garbled body %s, not auto-published): '%s'",
                           trend_id, garbage[:3], title[:60])
            held_garbled += 1
            continue

        # Publish gate: never auto-publish a mid-sentence/truncated body (#18) —
        # keep it as a draft for manual review instead.
        if not _body_complete(trend.get("body_en")):
            logger.warning("Held #%d (truncated body, not auto-published): '%s'",
                           trend_id, title[:60])
            held_truncated += 1
            continue

        # Grounding gate (#11): never auto-publish a body that invents a specific
        # (a number/date/percentage absent from the source) — content re-rolls
        # cut but don't eliminate it. Hold for review. Fail-open if the source
        # can't be loaded (source is None → skip the check, don't block publish).
        if source is not None:
            fabricated = ungrounded_specifics(trend.get("body_en") or "", source)
            if fabricated:
                logger.warning("Held #%d (ungrounded specifics %s, not auto-published): '%s'",
                               trend_id, fabricated[:5], title[:60])
                held_fabricated += 1
                continue

        if dry_run:
            logger.info("[DRY RUN] Would publish #%d: '%s' (conf=%.2f)",
                        trend_id, title[:60], confidence)
        else:
            update_trend_status(trend_id, "published", auto_published=True)
            logger.info("Auto-published #%d: '%s' (conf=%.2f)",
                        trend_id, title[:60], confidence)
        published += 1

    logger.info("Auto-publish complete: %d published, %d skipped, %d held (truncated), "
                "%d held (fabricated specifics), %d held (garbled) (threshold=%.2f%s)",
                published, skipped, held_truncated, held_fabricated, held_garbled,
                min_confidence, ", DRY RUN" if dry_run else "")

    return {"published": published, "skipped": skipped,
            "held_truncated": held_truncated, "held_fabricated": held_fabricated,
            "held_garbled": held_garbled}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-publish high-confidence trend drafts")
    parser.add_argument("--min-confidence", type=float, default=AUTO_PUBLISH_CONFIDENCE,
                        help=f"Minimum confidence to auto-publish (default: {AUTO_PUBLISH_CONFIDENCE})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be published without actually publishing")
    parser.add_argument("--limit", type=int, default=AUTO_PUBLISH_LIMIT,
                        help=f"Max drafts to scan in one run (default: {AUTO_PUBLISH_LIMIT})")
    args = parser.parse_args()

    result = auto_publish(min_confidence=args.min_confidence, dry_run=args.dry_run,
                          limit=args.limit)
    sys.exit(0 if result["published"] >= 0 else 1)
