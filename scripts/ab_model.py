#!/usr/bin/env python3
"""Controlled A/B: is fabrication model-specific? Qwen3-30B vs Gemma-4-26B (#11)

Four levers against the ~30% fabrication rate are refuted (prompt prohibition,
re-roll, more input, temperature). The last untested one is the MODEL itself.

Same entries, same prompt, same temperature — only the model changes. Each model
is loaded once via the GPU handover (they cannot coexist in 24 GB), all entries
are generated, then the next model is swapped in.

Read-only: generates in memory, writes nothing to the DB.

    python scripts/ab_model.py --n 40
    python scripts/ab_model.py --n 40 --temp 0.7
"""
from __future__ import annotations

import argparse
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import gpu_handover, llamacpp_client
from pipeline.db import get_connection
from pipeline.grounding import ungrounded_specifics
from pipeline.models import GeneratedContent
from pipeline import llm_processor as P

MODELS = {
    "qwen3-30b": "Qwen3-30B-A3B-Q4_K_M.gguf",
    "gemma4-26b": "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
}


def sample_entries(n: int) -> list[dict]:
    with get_connection() as c:
        rows = c.execute(
            "SELECT t.title_en, t.trend_signal_type, r.title AS raw_title, "
            "       r.excerpt, r.raw_content, t.source_name "
            "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
            "WHERE t.body_en IS NOT NULL AND t.created_at > NOW() - INTERVAL '5 hours' "
            "ORDER BY t.id DESC LIMIT ?", (n,)).fetchall()
    return [dict(r) for r in rows]


def gen(entry: dict, model: str, temp: float) -> str | None:
    """Generate with the live prompt; no validate-retries so we measure the RAW
    propensity to fabricate (the guard would mask it)."""
    src = (entry["raw_content"] or entry["excerpt"] or "")[:P.CONTENT_CHARS]
    framing = P.signal_type_framing(entry.get("trend_signal_type"))
    context = (f"Original Title: {entry['raw_title'] or entry['title_en']}\n"
               f"Original Excerpt: {src}\n"
               f"Source: {entry['source_name']}\n")
    if framing:
        context += f"\nAngle: {framing}\n"
    context += "\nWrite the trend article (150-250 words)."
    try:
        res = llamacpp_client.chat_structured(
            model=model, system=P.CONTENT_EN_SYSTEM_V2, prompt=context,
            schema=GeneratedContent, temperature=temp)
        return res.body if res else None
    except Exception as e:  # noqa: BLE001
        print(f"    gen failed ({model}): {type(e).__name__}: {str(e)[:90]}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--temp", type=float, default=0.7, help="production default 0.7")
    ap.add_argument("--models", default="qwen3-30b,gemma4-26b")
    ap.add_argument("--samples", type=int, default=0,
                    help="print N example bodies per model for qualitative review")
    args = ap.parse_args()

    picked = [m.strip() for m in args.models.split(",")]
    entries = sample_entries(args.n)
    print(f"Model A/B · {len(entries)} entries · T={args.temp} · {picked}\n")

    res: dict[str, list[int]] = {}
    words: dict[str, list[int]] = {}
    samples: dict[str, list[tuple]] = {}
    for key in picked:
        gguf = MODELS[key]
        print(f"--- loading {key} ({gguf}) ---")
        res[key], words[key], samples[key] = [], [], []
        try:
            with gpu_handover.content_gen_on_llamacpp(gguf):
                for i, e in enumerate(entries, 1):
                    body = gen(e, gguf, args.temp)
                    if not body:
                        continue
                    src_blob = f"{e['raw_title'] or ''} {e['raw_content'] or e['excerpt'] or ''}"
                    ung = ungrounded_specifics(body, src_blob)
                    res[key].append(len(ung))
                    words[key].append(len(body.split()))
                    if len(samples[key]) < args.samples:
                        samples[key].append((e['raw_title'] or e['title_en'], body, ung))
                    if i % 10 == 0:
                        print(f"    … {i}/{len(entries)}")
        except Exception as e:  # noqa: BLE001
            print(f"  !! {key} failed: {type(e).__name__}: {str(e)[:120]}")

    print(f"\n{'MODELL':<14}{'N':>5}{'MIT ERFUND.':>13}{'RATE':>9}{'⌀ TOKENS':>10}{'⌀ WÖRTER':>10}")
    print("-" * 62)
    for key in picked:
        v = res.get(key) or []
        if not v:
            print(f"{key:<14}{'—':>5}  (keine Ergebnisse)")
            continue
        bad = sum(1 for x in v if x > 0)
        print(f"{key:<14}{len(v):>5}{bad:>13}{bad/len(v)*100:>8.1f}%"
              f"{st.mean(v):>10.2f}{st.mean(words[key]):>10.0f}")
    print("\nBaseline (live 30B, T=0.7, 2 Cycles + A/B): ~30-37% mit erfundenen Spezifika")
    if args.samples:
        import textwrap
        for key in picked:
            for title, body, ung in samples.get(key, []):
                print(f"\n{'='*76}\n[{key}] erfunden: {ung if ung else '— keine'}")
                print(f"QUELL-TITEL: {title[:70]}")
                print(textwrap.fill(body[:620], 74, initial_indent='  ', subsequent_indent='  '))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
