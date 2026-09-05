"""Editorial judge for held drafts + the shared release gates (owner, 2026-08-22).

Background: 109 Haiku subagents read all 10,884 sub-threshold drafts and found
71.6 % publishable — the Stage-1 confidence barely separates publishable from
not (79 % top band vs 64 % bottom). The consequence is per-article judgment
instead of a blanket threshold:

  * scripts/release_haiku_approved.py releases the judged backlog, and
  * judge_recent_drafts() runs nightly on the fresh sub-threshold drafts with a
    LOCAL model (Qwen3.8-27B on llama-server :8090), same editorial criteria as
    the Haiku instructions. It releases or HOLDS — it never rejects; a human can
    still overrule a hold, and nothing is thrown away by a machine.

Every release path — backlog and nightly — goes through the SAME deterministic
gates (release_gates + is_duplicate_of_published): the Haiku run showed judges
approve past a grounding flag in ~4 % of cases (297/7,798), so the gates are not
optional decoration.

Published articles get auto_published=false semantics only on the human review
path; judge releases use auto_published=true (they ARE automatic) and are
counted separately in data/draft_judge_last.json for the morning report.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from pipeline import db as db_mod
from pipeline.content_guard import garbage_reasons
from pipeline.db import get_connection
from pipeline.grounding import source_from_parts, ungrounded_specifics
from pipeline.config import DUPLICATE_SIMILARITY_THRESHOLD

logger = logging.getLogger("draft_judge")

STATS_PATH = Path("data/draft_judge_last.json")
JUDGE_MODEL = "Qwen3.8-27B"
JUDGE_START_SCRIPT = "start-qwen3.8-27b.sh"

# Mirrors data/haiku_review/INSTRUCTIONS.md — the criteria that judged the
# 10,884-article backlog. Keep the two in sync when editing.
JUDGE_SYSTEM = """You are a senior editor at Catandary Trends, a cross-industry trend
intelligence service. Its promise: every published article is an evidence-based
trend signal — a development in technology, markets, regulation, science or
consumer behaviour that a foresight professional would want to know about.

You judge one DRAFT article, written by a smaller model from the SOURCE material
shown. Decide whether it belongs on the public feed.

NOT signals (no_signal): consumer buying advice and deals, how-to and support
content, sports results, celebrity news, local crime, horoscopes, individual
stock-picking, event announcements without a development.
source_mismatch: the draft asserts things the SOURCE clearly does not support.
When the SOURCE is only a headline or short teaser, do NOT use source_mismatch
merely because the draft elaborates beyond it — reserve it for drafts that
contradict the SOURCE or invent specific facts (laws, figures, names, places)
absent from it.
broken_text: cut off mid-sentence or garbled. thin_content: a signal, but says
nothing concrete. ok: none of the above.

publish=true only if it is a genuine signal AND the category is ok. Be strict —
the brand promise is evidence-based content."""


class JudgeVerdict(BaseModel):
    publish: bool
    signal: bool
    category: str = Field(description='"ok"|"no_signal"|"thin_content"|"source_mismatch"|"broken_text"')
    note: str = ""


# --- Shared deterministic gates ---------------------------------------------

def release_gates(title: str | None, body: str | None, re_title: str | None,
                  raw_content: str | None, excerpt: str | None,
                  extraction_json: str | None) -> tuple[bool, str]:
    """The non-negotiable checks before ANY release path may publish.

    Judges (Haiku or local) read a truncated source snippet, so they approve
    past fabrication flags in a few percent of cases — measured 297/7,798 on
    the backlog run. These gates re-check against the full stored material.
    """
    body = (body or "").strip()
    if not body:
        return False, "empty_body"
    # Garbage before truncation: soup usually ends mid-token too, and "garbled"
    # is the verdict the reviewer needs to see (#11, 2026-09-05).
    garbage = garbage_reasons(body, _judge_source(re_title, raw_content, excerpt))
    if garbage:
        return False, "garbled:" + ",".join(garbage[:3])
    if body[-1] not in '.!?"”':
        return False, "truncated"
    ext = {}
    if extraction_json:
        try:
            ext = json.loads(extraction_json) or {}
        except (json.JSONDecodeError, TypeError):
            ext = {}
    lst = lambda k: [str(x) for x in ext.get(k) or []] if isinstance(ext.get(k), list) else []
    src = source_from_parts(re_title, raw_content or excerpt,
                            lst("key_claims"), lst("key_figures"), lst("dates"),
                            lst("quotes"), lst("geography"))
    flags = ungrounded_specifics(body, src)
    if flags:
        return False, f"ungrounded:{','.join(flags[:4])}"
    return True, "ok"


def _judge_source(re_title, raw_content, excerpt) -> str:
    return f"{re_title or ''} {raw_content or excerpt or ''}"


def divert_garbled(conn, trend_id: int, reasons: list[str], dry_run: bool = False) -> None:
    """A garbage candidate is not a judgment call — it goes to status 'review'
    with its reasons, never to the LLM judge and never live (#11, 2026-09-05).
    The judged_at stamp keeps it out of tomorrow's candidate list."""
    if dry_run:
        return
    conn.execute(
        "UPDATE trends SET status = 'review', judged_at = CURRENT_TIMESTAMP, "
        "       review_reason = ? WHERE id = ? AND status = 'draft'",
        ("garbled:" + ",".join(reasons[:3]), trend_id),
    )


def duplicate_of_published(conn, trend_id: int) -> int | None:
    """Nearest already-published neighbour above the dedup threshold, or None.

    Uses the partial HNSW index on embedding_1024 WHERE status='published', so
    each newly published article immediately guards the next candidate — the
    caller publishes sequentially and near-twins within one release run cannot
    both go live."""
    row = conn.execute(
        "SELECT p.id, 1 - (p.embedding_1024 <=> t.embedding_1024) AS sim "
        "  FROM trends t, LATERAL ("
        "       SELECT id, embedding_1024 FROM trends "
        "        WHERE status = 'published' AND embedding_1024 IS NOT NULL "
        "        ORDER BY embedding_1024 <=> t.embedding_1024 LIMIT 1) p "
        " WHERE t.id = ? AND t.embedding_1024 IS NOT NULL",
        (trend_id,),
    ).fetchone()
    if not row:
        return None
    d = dict(row) if hasattr(row, "keys") else {"id": row[0], "sim": row[1]}
    return int(d["id"]) if d["sim"] is not None and d["sim"] >= DUPLICATE_SIMILARITY_THRESHOLD else None


def publish_draft(conn, trend_id: int, auto: bool) -> bool:
    """Guarded release. auto=True marks a machine-judge release; the human
    review path keeps auto_published=false."""
    rows = conn.execute(
        "UPDATE trends SET status = 'published', auto_published = ?, "
        "       published_at = COALESCE(published_at, CURRENT_TIMESTAMP), "
        "       reviewed_at = CURRENT_TIMESTAMP "
        " WHERE id = ? AND status = 'draft' RETURNING id",
        (auto, trend_id),
    ).fetchall()
    return bool(rows)


# --- Nightly judge -----------------------------------------------------------

def _fetch_candidates(since_hours: int, limit: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT t.id, t.title_en, t.body_en, t.confidence, t.source_name, "
            "       re.id AS re_id, re.url AS re_url, "
            "       re.title AS re_title, re.raw_content, re.excerpt, re.extraction_json "
            "  FROM trends t LEFT JOIN raw_entries re ON re.id = t.raw_entry_id "
            " WHERE t.status = 'draft' AND (t.confidence < 0.85 OR t.confidence IS NULL) "
            "   AND t.judged_at IS NULL "
            "   AND t.created_at > CURRENT_TIMESTAMP - make_interval(hours => ?) "
            " ORDER BY t.id LIMIT ?",
            (since_hours, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def _enrich_candidates(cands: list[dict]) -> int:
    """Backfill missing full text before judging (2026-08-25, issue #11).

    The article fetcher only touches processed=FALSE entries, so anything that
    reached content-gen text-less stays text-less forever — and the judge then
    compares the draft against a two-line teaser (41% of the first night's
    rejections were source_mismatch, several of them wrong). Same legal
    guardrails as the fetcher: opt-in sources only, robots.txt, throttled.
    Fetched text is written back to raw_entries so every later stage sees it.
    Never raises — a fetch problem must not stop the judge.
    """
    try:
        from pipeline.article_fetcher import fetch_fulltext, fulltext_source_names
        names = fulltext_source_names()
    except Exception as e:  # noqa: BLE001
        logger.warning("candidate enrichment unavailable: %r", e)
        return 0
    filled = 0
    for d in cands:
        if d.get("raw_content") or not d.get("re_url"):
            continue
        if d.get("source_name") not in names:
            continue
        try:
            text = fetch_fulltext(d["re_url"])
        except Exception:  # noqa: BLE001
            text = None
        if not text:
            continue
        d["raw_content"] = text
        try:
            with get_connection() as conn:
                conn.execute("UPDATE raw_entries SET raw_content = ? WHERE id = ?",
                             (text, d["re_id"]))
            filled += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("  #%s fulltext not persisted: %r", d["id"], e)
    return filled


def judge_one(d: dict) -> JudgeVerdict | None:
    from pipeline import llamacpp_client
    src = ((d["re_title"] or "") + " | " + (d["raw_content"] or d["excerpt"] or ""))[:4000]
    prompt = (f"SOURCE ({d['source_name'] or 'unknown'}):\n{src}\n\n"
              f"DRAFT ARTICLE:\n{d['title_en']}\n\n{(d['body_en'] or '')[:2200]}\n\n"
              'Answer with JSON only: {"publish": true/false, "signal": true/false, '
              '"category": "ok"|"no_signal"|"thin_content"|"source_mismatch"|"broken_text", '
              '"note": "<= 12 words"}')
    return llamacpp_client.chat_structured(
        model=JUDGE_MODEL, prompt=prompt, schema=JudgeVerdict,
        system=JUDGE_SYSTEM, temperature=0.0, require_all_fields=True)


def judge_recent_drafts(since_hours: int = 30, limit: int = 600,
                        dry_run: bool = False) -> dict:
    """Judge last night's sub-threshold drafts; release approvals, hold the rest.

    Returns the stats dict and persists it to STATS_PATH for the morning mail.
    """
    t0 = time.time()
    cands = _fetch_candidates(since_hours, limit)
    stats = {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "judged": 0, "released": 0, "held": 0, "gate_blocked": 0,
             "dup_blocked": 0, "garbled": 0, "errors": 0, "categories": {},
             "dry_run": dry_run}
    logger.info("draft judge: %d candidates (last %dh)", len(cands), since_hours)
    enriched = _enrich_candidates(cands)
    stats["fulltext_filled"] = enriched
    if enriched:
        logger.info("draft judge: backfilled full text for %d candidates", enriched)
    for d in cands:
        # Garbage never reaches the judge (#11, 2026-09-05): token soup is
        # diverted to status 'review' with its reasons and stamped judged.
        garbage = garbage_reasons(d["body_en"], _judge_source(d["re_title"], d["raw_content"],
                                                              d["excerpt"]))
        if garbage:
            stats["garbled"] += 1
            logger.info("  #%s garbled → review: %s", d["id"], garbage[:3])
            with get_connection() as conn:
                divert_garbled(conn, d["id"], garbage, dry_run)
            continue
        v = judge_one(d)
        if v is None:
            stats["errors"] += 1
            continue  # no judged_at stamp — an errored draft retries next night
        stats["judged"] += 1
        # Stamp every verdicted draft (held or released) so it is judged once,
        # not re-judged nightly while blocking fresh drafts (2026-08-25).
        if not dry_run:
            with get_connection() as conn:
                conn.execute("UPDATE trends SET judged_at = CURRENT_TIMESTAMP "
                             "WHERE id = ?", (d["id"],))
        cat = v.category if v.category in ("ok", "no_signal", "thin_content",
                                           "source_mismatch", "broken_text") else "other"
        stats["categories"][cat] = stats["categories"].get(cat, 0) + 1
        if not (v.publish and v.signal and cat == "ok"):
            stats["held"] += 1
            continue
        ok, reason = release_gates(d["title_en"], d["body_en"], d["re_title"],
                                   d["raw_content"], d["excerpt"], d["extraction_json"])
        if not ok:
            stats["gate_blocked"] += 1
            logger.info("  #%s gate: %s", d["id"], reason)
            continue
        with get_connection() as conn:
            dup = duplicate_of_published(conn, d["id"])
            if dup:
                stats["dup_blocked"] += 1
                logger.info("  #%s duplicate of published #%s", d["id"], dup)
                continue
            if not dry_run and publish_draft(conn, d["id"], auto=True):
                stats["released"] += 1
            elif dry_run:
                stats["released"] += 1
    stats["seconds"] = round(time.time() - t0, 1)
    STATS_PATH.parent.mkdir(exist_ok=True)
    STATS_PATH.write_text(json.dumps(stats, indent=2))
    logger.info("draft judge done in %.0fs: %d judged, %d released, %d held, "
                "%d gate-blocked, %d dup-blocked, %d garbled → review, %d errors",
                stats["seconds"], stats["judged"], stats["released"], stats["held"],
                stats["gate_blocked"], stats["dup_blocked"], stats["garbled"], stats["errors"])
    return stats


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Judge held drafts with the local 27B")
    ap.add_argument("--since-hours", type=int, default=30)
    ap.add_argument("--limit", type=int, default=600)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    judge_recent_drafts(args.since_hours, args.limit, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
