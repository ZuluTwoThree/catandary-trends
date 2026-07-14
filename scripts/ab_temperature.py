#!/usr/bin/env python3
"""Controlled A/B: does content-gen temperature drive fabrication? (#11)

Three levers against the ~32% fabrication rate are already refuted:
  - prompt prohibition (v2 says "NEVER introduce a number … not present in the
    source") — rate unchanged
  - re-roll on detection (validate=guard, max_validate_retries=3) — #11 measured
    "re-rolls do not fix it"
  - more input (full text, 4x context) — measured twice, within noise

Untested: temperature. Content-gen samples at 0.7 — exactly the regime where a
model invents plausible specifics. This regenerates the SAME entries at two
temperatures (everything else identical) and compares the grounding rate. Unlike
the full-text comparison this is not confounded: same inputs, one variable.

Read-only: generates in memory, writes nothing to the DB.

    python scripts/ab_temperature.py --n 40
    python scripts/ab_temperature.py --n 40 --temps 0.7,0.3,0.1
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import llamacpp_client
from pipeline.config import STAGE5_MODEL, MODEL_GENERATE, STAGE5_BACKEND
from pipeline.db import get_connection
from pipeline.grounding import ungrounded_specifics
from pipeline.models import GeneratedContent
from pipeline import llm_processor as P


def sample_entries(n: int) -> list[dict]:
    """Recent, already-processed entries with their source text + classification."""
    with get_connection() as c:
        rows = c.execute(
            "SELECT t.title_en, t.trend_signal_type, t.verticals, "
            "       r.title AS raw_title, r.excerpt, r.raw_content, "
            "       t.source_url, t.source_name "
            "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
            "WHERE t.body_en IS NOT NULL AND t.created_at > NOW() - INTERVAL '3 hours' "
            "ORDER BY t.id DESC LIMIT ?", (n,)).fetchall()
    return [dict(r) for r in rows]


def gen(entry: dict, temp: float) -> str | None:
    """Generate a body at `temp` using the live prompt, no validate-retries so we
    measure the RAW propensity to fabricate (the guard would mask it)."""
    src = (entry["raw_content"] or entry["excerpt"] or "")[:P.CONTENT_CHARS]
    framing = P.signal_type_framing(entry.get("trend_signal_type"))
    context = (f"Original Title: {entry['raw_title'] or entry['title_en']}\n"
               f"Original Excerpt: {src}\n"
               f"Source: {entry['source_name']}\n")
    if framing:
        context += f"\nAngle: {framing}\n"
    context += "\nWrite the trend article (150-250 words)."
    try:
        if STAGE5_BACKEND == "llamacpp":
            res = llamacpp_client.chat_structured(
                model=STAGE5_MODEL, system=P.CONTENT_EN_SYSTEM_V2, prompt=context,
                schema=GeneratedContent, temperature=temp)
        else:
            from pipeline.ollama_client import chat_structured
            res = chat_structured(model=MODEL_GENERATE, system=P.CONTENT_EN_SYSTEM_V2,
                                  prompt=context, schema=GeneratedContent,
                                  temperature=temp)
        return res.body if res else None
    except Exception as e:  # noqa: BLE001
        print(f"  gen failed (T={temp}): {e!r}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--temps", default="0.7,0.3")
    args = ap.parse_args()
    temps = [float(x) for x in args.temps.split(",")]

    entries = sample_entries(args.n)
    print(f"A/B over {len(entries)} entries · temps {temps} · backend {STAGE5_BACKEND}\n")
    res: dict[float, list[int]] = {t: [] for t in temps}
    words: dict[float, list[int]] = {t: [] for t in temps}

    # Content-gen needs the 30B; llama-server may be serving the 8B. The handover
    # swaps the start-active symlink + VRAM and restores it on exit.
    from pipeline import gpu_handover
    ctx = (gpu_handover.content_gen_on_llamacpp(STAGE5_MODEL)
           if STAGE5_BACKEND == "llamacpp" else __import__("contextlib").nullcontext())
    with ctx:
        for i, e in enumerate(entries, 1):
            src_blob = f"{e['raw_title'] or ''} {e['raw_content'] or e['excerpt'] or ''}"
            for t in temps:
                body = gen(e, t)
                if not body:
                    continue
                res[t].append(len(ungrounded_specifics(body, src_blob)))
                words[t].append(len(body.split()))
            if i % 10 == 0:
                print(f"  … {i}/{len(entries)}")

    print(f"\n{'TEMP':<8}{'N':>6}{'MIT ERFUND.':>13}{'RATE':>9}{'⌀ TOKENS':>10}{'⌀ WÖRTER':>10}")
    print("-" * 58)
    for t in temps:
        v = res[t]
        if not v:
            continue
        bad = sum(1 for x in v if x > 0)
        print(f"{t:<8.2f}{len(v):>6}{bad:>13}{bad/len(v)*100:>8.1f}%"
              f"{st.mean(v):>10.2f}{st.mean(words[t]):>10.0f}")
    print("\nBaseline (live, T=0.7, gemessen an 2 Cycles): ~31-37% mit erfundenen Spezifika")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
