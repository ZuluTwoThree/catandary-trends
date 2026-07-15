#!/usr/bin/env python3
"""Controlled A/B: why does Stage 6 land at 108 words when the spec says 150-250?

The corpus is inconsistent: the pre-30B era (14B/35B) averages 209 words and hits
the 150-250 band 79.6% of the time; the current pipeline lands at 108 (1.7% in
band). Two candidate causes:

  (a) PROMPT: step_generate_content_en puts "150-250 words" only in the system
      prompt, then buries it under ~9 lines of context (brand/claims/verticals/
      PESTEL/mega/source). The A/B harness that measured Gemma at 175 words
      repeated the instruction as the LAST line — a recency effect the live path
      does not have.
  (b) MODEL: Gemma/30B may simply write shorter than the 14B/35B did.

This isolates (a): the EXACT live prompt vs the same prompt + a trailing
word-count line. Same entries, same model, same temperature, no guard/re-rolls
(they would mask the raw propensity).

Read-only: generates in memory, writes nothing.

    python scripts/ab_wordcount.py --n 40
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import gpu_handover, llamacpp_client
from pipeline.config import STAGE5_MODEL
from pipeline.db import get_connection
from pipeline.grounding import ungrounded_specifics
from pipeline.models import GeneratedContent
from pipeline import llm_processor as P

REMINDER = "\nWrite the trend article (150-250 words).\n"


def sample(n: int) -> list[dict]:
    """Fresh full-text-enriched entries from the last cycle."""
    with get_connection() as c:
        rows = c.execute(
            "SELECT t.title_en, t.trend_signal_type, t.mega_trend, t.verticals, t.pestel, "
            "       t.brands, t.source_name, t.source_url, "
            "       r.title AS raw_title, r.excerpt, r.raw_content "
            "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
            "WHERE t.body_en IS NOT NULL AND t.created_at > '2026-07-15 19:25:00' "
            "ORDER BY RANDOM() LIMIT ?", (n,)).fetchall()
    return [dict(r) for r in rows]


def live_prompt(e: dict) -> str:
    """Mirrors step_generate_content_en's construction as closely as the stored
    row allows (the extraction/classification objects are gone post-hoc)."""
    excerpt = (e["raw_content"] or e["excerpt"] or "")[:P.CONTENT_CHARS]
    context = (f"Original Title: {e['raw_title'] or e['title_en']}\n"
               f"Original Excerpt: {excerpt}\n"
               f"Brand: Unknown\nProduct: Unknown\nKey Claims: N/A\n"
               f"Verticals: {e.get('verticals') or 'N/A'}\n"
               f"PESTEL: {e.get('pestel') or 'N/A'}\n"
               f"Signal Type: {e.get('trend_signal_type') or 'N/A'}\n"
               f"Mega Trend: {e.get('mega_trend') or 'N/A'}\n"
               f"Source: {e['source_name']} ({e.get('source_url') or ''})")
    framing = P.signal_type_framing(e.get("trend_signal_type"))
    fb = f"Signal-type framing: {framing}\n\n" if framing else ""
    return (f"Write a trend article in English based on this information.\n"
            f"The source below may be in German or another language — translate it "
            f"and write the title and body entirely in English.\n\n{fb}{context}\n\n")


def gen(prompt: str) -> GeneratedContent | None:
    try:
        return llamacpp_client.chat_structured(
            model=STAGE5_MODEL, system=P.CONTENT_EN_SYSTEM_V2, prompt=prompt,
            schema=GeneratedContent, temperature=0.7)
    except Exception as e:  # noqa: BLE001
        print(f"    gen failed: {type(e).__name__}: {str(e)[:80]}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args()

    entries = sample(args.n)
    print(f"Wortzahl-A/B · {len(entries)} Einträge · {STAGE5_MODEL}\n"
          f"  A = exakter Live-Prompt (Wortzahl nur im System-Prompt)\n"
          f"  B = Live-Prompt + Reminder als letzte Zeile\n")

    res: dict[str, list[int]] = {"A live": [], "B +reminder": []}
    fab: dict[str, int] = {"A live": 0, "B +reminder": 0}
    with gpu_handover.content_gen_on_llamacpp(STAGE5_MODEL):
        for i, e in enumerate(entries, 1):
            base = live_prompt(e)
            src = f"{e['raw_title'] or ''} {e['raw_content'] or e['excerpt'] or ''}"
            for key, p in (("A live", base), ("B +reminder", base + REMINDER)):
                c = gen(p)
                if not c:
                    continue
                res[key].append(len(c.body.split()))
                fab[key] += 1 if ungrounded_specifics(c.body, src) else 0
            if i % 10 == 0:
                print(f"    … {i}/{len(entries)}")

    print(f"\n{'VARIANTE':<16}{'N':>5}{'MEDIAN':>8}{'⌀':>7}{'IM BAND':>10}{'FABRIK.':>9}")
    print("-" * 56)
    for k, v in res.items():
        if not v:
            continue
        v2 = sorted(v)
        band = sum(1 for x in v if 150 <= x <= 250) / len(v) * 100
        print(f"{k:<16}{len(v):>5}{v2[len(v2)//2]:>8}{st.mean(v):>7.0f}"
              f"{band:>9.0f}%{fab[k]/len(v)*100:>8.1f}%")
    print("\nReferenz: Vor-30B-Korpus (14B/35B) Median 209 · 79.6% im Band")
    print("          Live-Cycle 2026-07-15 (946 Art.) Median 108 · 1.7% im Band")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
