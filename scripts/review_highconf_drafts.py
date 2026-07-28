#!/usr/bin/env python3
"""One-off: individually review high-confidence (>=0.85) drafts and split them
into PUBLISH vs HOLD (doubtful content). Applies the auto_publisher's two
mechanical gates (body-complete + grounding) PLUS extra content-quality checks
the gates don't cover. Report-only unless --publish is passed.

Usage:
    python -m scripts.review_highconf_drafts            # report only
    python -m scripts.review_highconf_drafts --publish  # publish the PASS set
"""
import argparse
import re
from collections import Counter

from pipeline.config import AUTO_PUBLISH_CONFIDENCE
from pipeline.db import get_connection, update_trend_status
from pipeline.auto_publisher import _body_complete, _source_text
from pipeline.grounding import ungrounded_specifics

# English function words — a body with almost none is likely not English
# (HARD RULE: title+body must always be English, even for non-EN sources).
_EN_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "for",
            "with", "on", "that", "this", "as", "by", "its", "has", "have", "will",
            "from", "at", "was", "were", "be", "been", "which", "their", "it"}

# Assistant/meta/artefact strings that must never appear in a published body.
_ARTIFACT_PATTERNS = [
    r"<\s*/?\s*think", r"```", r"\bas an ai\b", r"\bi cannot\b", r"\bi'm sorry\b",
    r"\bi am sorry\b", r"\bhere('s| is) (the|a|your)\b", r"\blet's\b", r"\blet me\b",
    r"\bas a senior analyst\b", r"\bas an? language model\b", r"\[llm", r"\bTODO\b",
    r"\bplaceholder\b", r"\blorem ipsum\b", r"^\s*note:", r"\bI'll\b",
]
_ARTIFACT_RE = re.compile("|".join(_ARTIFACT_PATTERNS), re.IGNORECASE)
# Unresolved bracket placeholders like [company], [X], [insert ...]
_BRACKET_RE = re.compile(r"\[[a-z][^\]]{0,40}\]", re.IGNORECASE)


def english_ratio(text: str) -> float:
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return 0.0
    return sum(1 for w in words if w in _EN_STOP) / len(words)


def sentence_repetition(body: str) -> float:
    sents = [s.strip().lower() for s in re.split(r"[.!?]+", body) if len(s.strip()) > 15]
    if len(sents) < 2:
        return 0.0
    c = Counter(sents)
    dupes = sum(v - 1 for v in c.values() if v > 1)
    return dupes / len(sents)


def review(d: dict) -> tuple[bool, str]:
    """Return (publish_ok, reason). reason='' when publishable."""
    body = d.get("body_en") or ""
    title = d.get("title_en") or ""

    # --- auto_publisher's two mechanical gates (re-applied) ---
    if not _body_complete(body):
        return False, "truncated_body"
    src = _source_text(d.get("raw_entry_id"))
    if src is not None:
        fab = ungrounded_specifics(body, src)
        if fab:
            return False, f"ungrounded_specifics:{fab[:3]}"

    # --- integrity ---
    if not title.strip():
        return False, "no_title"
    if not (d.get("source_url") or "").strip():
        return False, "no_source_url"
    if not (d.get("slug") or "").strip():
        return False, "no_slug"

    # --- content quality ---
    wc = len(body.split())
    if wc < 50:
        return False, f"too_short:{wc}w"
    if wc > 400:
        return False, f"too_long:{wc}w"
    if _ARTIFACT_RE.search(body):
        return False, "artifact_string"
    if _BRACKET_RE.search(body):
        return False, "bracket_placeholder"
    if english_ratio(body) < 0.12:
        return False, f"non_english:{english_ratio(body):.2f}"
    if sentence_repetition(body) > 0.25:
        return False, f"repetitive:{sentence_repetition(body):.2f}"
    # Body must differ substantially from a bare title echo
    if body.strip().lower().startswith(title.strip().lower()) and wc < 60:
        return False, "title_echo"

    return True, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true", help="publish the PASS set")
    ap.add_argument("--min-confidence", type=float, default=AUTO_PUBLISH_CONFIDENCE)
    args = ap.parse_args()

    with get_connection() as c:
        rows = c.execute(
            "SELECT id, title_en, body_en, raw_entry_id, source_url, slug, "
            "primary_vertical, confidence FROM trends "
            "WHERE status='draft' AND confidence >= ?",
            (args.min_confidence,)).fetchall()
    rows = [dict(r) if not isinstance(r, dict) else r for r in rows]

    publish_ids, hold = [], Counter()
    hold_samples: dict[str, list] = {}
    for d in rows:
        ok, reason = review(d)
        if ok:
            publish_ids.append(d["id"])
        else:
            key = reason.split(":")[0]
            hold[key] += 1
            hold_samples.setdefault(key, []).append((d["id"], reason, (d.get("title_en") or "")[:70]))

    print(f"Total conf>={args.min_confidence} drafts reviewed: {len(rows)}")
    print(f"  PUBLISH (in Ordnung): {len(publish_ids)}")
    print(f"  HOLD (zweifelhaft):   {sum(hold.values())}")
    print("  HOLD breakdown:")
    for k, v in hold.most_common():
        print(f"    {k:22} {v}")
        for sid, reason, title in hold_samples[k][:3]:
            print(f"        #{sid} [{reason}] {title!r}")

    if args.publish and publish_ids:
        print(f"\nPublishing {len(publish_ids)} drafts...")
        n = 0
        for tid in publish_ids:
            update_trend_status(tid, "published", auto_published=True)
            n += 1
        print(f"Published {n}.")
    elif args.publish:
        print("\nNothing to publish.")


if __name__ == "__main__":
    main()
