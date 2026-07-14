#!/usr/bin/env python3
"""Regenerate published articles from the 30B era with the current model (#47).

The retro-audit (scripts/audit_published.py) localised the fabrication in the
corpus to the qwen3-30b era (2026-06-26 be444d0 → 2026-07-14 e423ee0): 44.0% of
those 12,939 articles invent a specific, against 2.2% before it. This rewrites
them with the current Stage-6 model.

Runs over an id range so each of the four batches (#47) is independently
resumable and reviewable. Dry-run by default.

IMPORTANT: --execute also refreshes grounding_flags for every row it rewrites.
Without that the audit marking would keep pointing at a body that no longer
exists — the article would read clean and still be flagged (or worse, the other
way round).

    python scripts/regen_published.py --id-from 250832 --id-to 275157 --sample 60
    python scripts/regen_published.py --id-from 250832 --id-to 275157 --execute
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import gpu_handover, llamacpp_client
from pipeline.config import STAGE5_MODEL, STAGE5_BACKEND
from pipeline.db import get_connection
from pipeline.grounding import ungrounded_specifics
from pipeline.models import GeneratedContent
from pipeline import llm_processor as P


def load(id_from: int, id_to: int, sample: int, only_flagged: bool) -> list[dict]:
    where = "AND t.grounding_flags::text <> '[]'" if only_flagged else ""
    order = "RANDOM()" if sample else "t.id"
    with get_connection() as c:
        rows = c.execute(
            "SELECT t.id, t.title_en, t.body_en, t.trend_signal_type, t.source_name, "
            "       r.title AS raw_title, r.excerpt, r.raw_content "
            "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
            "WHERE t.status = 'published' AND t.body_en IS NOT NULL "
            f"  AND t.id >= ? AND t.id <= ? {where} "
            f"ORDER BY {order} LIMIT ?",
            (id_from, id_to, sample or 10_000_000)).fetchall()
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
    ap.add_argument("--id-from", type=int, required=True)
    ap.add_argument("--id-to", type=int, required=True)
    ap.add_argument("--sample", type=int, default=0,
                    help="random N from the range instead of all (for a dry probe)")
    ap.add_argument("--only-flagged", action="store_true",
                    help="restrict to rows the audit flagged (default: whole range — "
                         "the gate misses vague bodies, see #47)")
    ap.add_argument("--execute", action="store_true", help="write bodies + flags back")
    args = ap.parse_args()

    rows = load(args.id_from, args.id_to, args.sample, args.only_flagged)
    print(f"Regen {len(rows):,} published · id {args.id_from:,}–{args.id_to:,} · "
          f"{STAGE5_MODEL}{'' if args.execute else '  [DRY RUN]'}\n")

    t0 = time.time()
    before_bad = after_bad = fixed = broke = failed = 0
    ctx = (gpu_handover.content_gen_on_llamacpp(STAGE5_MODEL)
           if STAGE5_BACKEND == "llamacpp" else __import__("contextlib").nullcontext())
    with ctx:
        for i, d in enumerate(rows, 1):
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
            elif now and not was:
                broke += 1
            if args.execute:
                # Body and flags move together: a stale grounding_flags row is
                # worse than none, it lies about a body that no longer exists.
                with get_connection() as c:
                    c.execute(
                        "UPDATE trends SET body_en = ?, title_en = ?, "
                        "grounding_flags = ?, grounding_checked_at = NOW() WHERE id = ?",
                        (new.body, new.title or d["title_en"], json.dumps(now), d["id"]))
            if i % 100 == 0:
                el = time.time() - t0
                eta = (len(rows) - i) * el / i / 60
                print(f"  … {i:,}/{len(rows):,} · {after_bad/i*100:.1f}% noch auffällig "
                      f"· {el/i:.1f}s/Art · ETA {eta:.0f} min")

    n = len(rows) - failed
    print(f"\n{'':<28}{'VORHER':>9}{'NACHHER':>9}")
    print("-" * 46)
    print(f"{'Artikel mit erfundenen':<28}{before_bad:>9}{after_bad:>9}")
    print(f"{'Rate':<28}{before_bad/max(n,1)*100:>8.1f}%{after_bad/max(n,1)*100:>8.1f}%")
    print(f"\n  bereinigt:                  {fixed}")
    print(f"  neu verschlechtert:         {broke}")
    print(f"  Generierung fehlgeschlagen: {failed}")
    print(f"  Laufzeit:                   {(time.time()-t0)/60:.0f} min")
    if not args.execute:
        print("\n(DRY RUN — nichts geschrieben. --execute zum Anwenden.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
