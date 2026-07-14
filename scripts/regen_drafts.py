#!/usr/bin/env python3
"""Regenerate unpublished drafts with the current Stage-6 model (#11).

The 2,119 drafts split (see docs/draft_review_2026-07-14.md):
  A) 633 with conf>=0.85 held by the grounding gate — 85.6% invent a specific
  B/C/D) 1,595 held on relevance uncertainty — quality on par with published

Group A is the interesting one: those articles are RELEVANT (the filter was sure)
but factually contaminated. If the new model (Gemma-4-26B, 8.6% fabrication vs the
30B's 32.9%) regenerates them cleanly, the pile converts into publishable content
instead of being written off.

DRY-RUN by default: regenerates in memory, measures, writes nothing. --execute
writes the new body/title back and lets the normal auto-publisher pick them up.

    python scripts/regen_drafts.py --n 50            # measure only
    python scripts/regen_drafts.py --n 50 --execute  # write back
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import gpu_handover, llamacpp_client
from pipeline.config import STAGE5_MODEL, STAGE5_BACKEND
from pipeline.db import get_connection
from pipeline.grounding import ungrounded_specifics
from pipeline.models import GeneratedContent
from pipeline import llm_processor as P


def load_drafts(n: int, group: str) -> list[dict]:
    where = {"a": "t.confidence >= 0.85", "rest": "t.confidence < 0.85", "all": "1=1"}[group]
    with get_connection() as c:
        rows = c.execute(
            "SELECT t.id, t.title_en, t.body_en, t.confidence, t.trend_signal_type, "
            "       t.source_name, r.title AS raw_title, r.excerpt, r.raw_content "
            "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
            f"WHERE t.status = 'draft' AND t.body_en IS NOT NULL AND {where} "
            "ORDER BY t.id DESC LIMIT ?", (n,)).fetchall()
    return [dict(r) for r in rows]


def regen(entry: dict) -> GeneratedContent | None:
    src = (entry["raw_content"] or entry["excerpt"] or "")[:P.CONTENT_CHARS]
    framing = P.signal_type_framing(entry.get("trend_signal_type"))
    context = (f"Original Title: {entry['raw_title'] or entry['title_en']}\n"
               f"Original Excerpt: {src}\n"
               f"Source: {entry['source_name']}\n")
    if framing:
        context += f"\nAngle: {framing}\n"
    context += "\nWrite the trend article (150-250 words)."
    try:
        return llamacpp_client.chat_structured(
            model=STAGE5_MODEL, system=P.CONTENT_EN_SYSTEM_V2, prompt=context,
            schema=GeneratedContent, temperature=0.7)
    except Exception as e:  # noqa: BLE001
        print(f"  regen failed [{entry['id']}]: {type(e).__name__}: {str(e)[:80]}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--group", choices=["a", "rest", "all"], default="a",
                    help="a = gate-held (conf>=0.85), rest = relevance-uncertain")
    ap.add_argument("--execute", action="store_true", help="write the new bodies back")
    args = ap.parse_args()

    drafts = load_drafts(args.n, args.group)
    print(f"Regen {len(drafts)} drafts (group={args.group}) with {STAGE5_MODEL}"
          f"{'' if args.execute else '  [DRY RUN]'}\n")

    before_bad = after_bad = fixed = still_bad = failed = 0
    ctx = (gpu_handover.content_gen_on_llamacpp(STAGE5_MODEL)
           if STAGE5_BACKEND == "llamacpp" else __import__("contextlib").nullcontext())
    with ctx:
        for i, d in enumerate(drafts, 1):
            src_blob = f"{d['raw_title'] or ''} {d['raw_content'] or d['excerpt'] or ''}"
            was = ungrounded_specifics(d["body_en"] or "", src_blob)
            before_bad += 1 if was else 0
            new = regen(d)
            if not new:
                failed += 1
                continue
            now = ungrounded_specifics(new.body, src_blob)
            after_bad += 1 if now else 0
            if was and not now:
                fixed += 1
            elif now:
                still_bad += 1
            if args.execute:
                with get_connection() as c:
                    c.execute("UPDATE trends SET body_en = ?, title_en = ? WHERE id = ?",
                              (new.body, new.title or d["title_en"], d["id"]))
            if i % 10 == 0:
                print(f"  … {i}/{len(drafts)}")

    n = len(drafts) - failed
    print(f"\n{'':<28}{'VORHER':>9}{'NACHHER':>9}")
    print("-" * 46)
    print(f"{'Artikel mit erfundenen':<28}{before_bad:>9}{after_bad:>9}")
    print(f"{'Rate':<28}{before_bad/max(n,1)*100:>8.1f}%{after_bad/max(n,1)*100:>8.1f}%")
    print(f"\n  bereinigt (war schlecht, jetzt sauber): {fixed}")
    print(f"  weiterhin belastet:                    {still_bad}")
    print(f"  Generierung fehlgeschlagen:            {failed}")
    if not args.execute:
        print("\n(DRY RUN — nichts in die DB geschrieben. --execute zum Anwenden.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
