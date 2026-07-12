#!/usr/bin/env python3
"""Re-roll drafts held by the auto-publish gates (#11 follow-up, owner 2026-07-12).

High-confidence drafts (conf >= threshold) that the grounding gate held — body
contains a number/date absent from the source ("fabricated specifics") — or whose
body is truncated, get ONE regeneration pass with an EXPLICIT grounding
instruction in the prompt (the in-run guard alone let these through 3 retries).
After regen the same gates are re-checked; clean bodies are written back and the
normal auto_publisher publishes them. Still-failing drafts stay held (honest).

    python scripts/reroll_held_drafts.py --dry-run     # count + show what would run
    python scripts/reroll_held_drafts.py --limit 20    # bounded smoke run
    python scripts/reroll_held_drafts.py               # full backlog
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import gpu_handover, llamacpp_client
from pipeline.auto_publisher import _body_complete, _source_text
from pipeline.config import (AUTO_PUBLISH_CONFIDENCE, LOG_LEVEL, STAGE5_BACKEND,
                             STAGE5_MODEL)
from pipeline.db import get_connection, update_trend_status
from pipeline.grounding import ungrounded_specifics
from pipeline.llm_processor import (CONTENT_EN_SYSTEM_V2, make_content_guard,
                                    signal_type_framing)
from pipeline.models import GeneratedContent

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# The explicit constraint the held drafts get — the difference to the normal
# Stage-6 prompt. Numbers only from the source, or write around them.
GROUNDING_RULE = """
STRICT GROUNDING RULE (this article failed a fact check — follow exactly):
- Use ONLY numbers, dates, percentages, prices and quantities that appear
  LITERALLY in the source material above.
- Do NOT add, estimate, convert, round or infer any figure.
- If a detail is not in the source, write the sentence WITHOUT a figure
  (e.g. "raised a funding round" instead of inventing an amount).
"""


def fetch_held(limit: int = 0) -> list[dict]:
    """Drafts at/above the publish threshold that a gate is holding."""
    sql = ("SELECT id, raw_entry_id, title_en, body_en, verticals, pestel, "
           "       trend_signal_type, mega_trend, brands, source_url, source_name, confidence "
           "FROM trends WHERE status='draft' AND confidence >= %s ORDER BY id DESC")
    with get_connection() as c:
        cur = c._conn.cursor()
        cur.execute(sql, (AUTO_PUBLISH_CONFIDENCE,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return rows[:limit] if limit else rows


def reroll_one(t: dict) -> tuple[str, GeneratedContent | None]:
    """→ (outcome, content). outcome ∈ regenerated | still_failing | clean | no_source."""
    source = _source_text(t["raw_entry_id"])
    if not source:
        return "no_source", None
    truncated = not _body_complete(t["body_en"])
    fabricated = ungrounded_specifics(t["body_en"] or "", source)
    if not truncated and not fabricated:
        return "clean", None   # already passes → auto_publish will take it

    framing = signal_type_framing(t["trend_signal_type"])
    framing_block = f"Signal-type framing: {framing}\n\n" if framing else ""
    import json
    verts = t["verticals"] if isinstance(t["verticals"], list) else json.loads(t["verticals"] or "[]")
    pestel = t["pestel"] if isinstance(t["pestel"], list) else json.loads(t["pestel"] or "[]")
    context = f"""Source material: {source[:1400]}
Verticals: {', '.join(verts)}
PESTEL: {', '.join(pestel)}
Signal Type: {t['trend_signal_type']}
Mega Trend: {t['mega_trend'] or 'N/A'}
Source: {t['source_name']} ({t['source_url']})"""
    prompt = (f"Write a trend article in English based on this information.\n"
              f"The source below may be in German or another language — translate it and "
              f"write the title and body entirely in English.\n\n"
              f"{framing_block}{context}\n{GROUNDING_RULE}\n")
    guard = make_content_guard(source)
    content = llamacpp_client.chat_structured(
        model=STAGE5_MODEL, prompt=prompt, schema=GeneratedContent,
        system=CONTENT_EN_SYSTEM_V2, temperature=0.6,
        validate=guard, max_validate_retries=3)
    if content is None:
        return "still_failing", None
    # re-check the actual gates on the new body
    if not _body_complete(content.body) or ungrounded_specifics(content.body, source):
        return "still_failing", None
    return "regenerated", content


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-publish", action="store_true",
                    help="regenerate only; don't run auto_publish at the end")
    args = ap.parse_args()

    held = fetch_held(args.limit)
    logger.info("held high-confidence drafts: %d%s", len(held),
                f" (limited to {args.limit})" if args.limit else "")
    if args.dry_run:
        n_trunc = n_fab = n_clean = 0
        for t in held[:500]:
            source = _source_text(t["raw_entry_id"]) or ""
            if not _body_complete(t["body_en"]):
                n_trunc += 1
            elif source and ungrounded_specifics(t["body_en"] or "", source):
                n_fab += 1
            else:
                n_clean += 1
        logger.info("dry-run sample (500): truncated=%d fabricated=%d clean/would-publish=%d",
                    n_trunc, n_fab, n_clean)
        return 0

    if STAGE5_BACKEND != "llamacpp":
        logger.error("STAGE5_BACKEND must be llamacpp for the re-roll (set env like scheduled_cycle.sh)")
        return 1

    # published: regenerated body passed the gates AND we published it inline
    # (auto_publish's own 500-row batch can't cover the whole backlog reliably).
    stats = {"regenerated": 0, "published": 0, "still_failing": 0, "clean": 0, "no_source": 0}
    with gpu_handover.content_gen_on_llamacpp(STAGE5_MODEL):
        for i, t in enumerate(held):
            try:
                outcome, content = reroll_one(t)
            except Exception as e:
                logger.warning("#%d error: %s", t["id"], e)
                outcome, content = "still_failing", None
            stats[outcome] += 1
            if content is not None:
                with get_connection() as c:
                    cur = c._conn.cursor()
                    cur.execute(
                        "UPDATE trends SET title_en=%s, summary_en=%s, body_en=%s WHERE id=%s",
                        (content.title, content.summary, content.body, t["id"]))
                    c._conn.commit()
                if not args.skip_publish:
                    update_trend_status(t["id"], "published", auto_published=True)
                    stats["published"] += 1
            # a 'clean' draft already passes the gate but auto_publish's batch may
            # have missed it (500-row cap) — publish it here too.
            elif outcome == "clean" and not args.skip_publish:
                update_trend_status(t["id"], "published", auto_published=True)
                stats["published"] += 1
            if (i + 1) % 25 == 0:
                logger.info("progress %d/%d — %s", i + 1, len(held), stats)
    logger.info("re-roll done: %s", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
