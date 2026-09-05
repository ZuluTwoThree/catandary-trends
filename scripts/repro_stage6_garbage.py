#!/usr/bin/env python3
"""Reproduce the Stage-6 garbage episode of 2026-09-05 (#11) — GPU, on demand.

What happened: the backlog cycle of 2026-09-05 stored 22 CONSECUTIVE drafts
(trends 1718638–1718659, raw entries from ScienceDaily / The Conversation /
idw / New Scientist) whose bodies were token soup ("M M M M M       仪器(",
"original original original fig fig"). All 22 had full-text sources cut at the
4,000-character prompt cap; 114 other long prompts and every teaser prompt in
the same run were fine, and the 23rd entry after the run was fine again. The
llama-server log shows Gemma with n_slots=4, unified KV cache, every request on
one slot chosen "by LCP similarity" (prompt-prefix reuse, f_keep 0.34–0.86), no
errors, no truncation. Leading hypothesis: a transient slot/KV state after
prefix reuse, not a property of the prompts. The code accepted the soup because
chat_structured returned the last result after the soft budget (fixed: hard
guard, f425e35).

This script replays the SAME 22 entries with the PRODUCTION prompt
(pipeline.llm_processor.build_content_prompt) in three arms and reports the
garbage rate per arm:

  A  production      cache_prompt default (prefix reuse on), STAGE6_SOURCE_MAX_CHARS=4000
  B  no-cache        cache_prompt=false on every request
  C  short-source    STAGE6_SOURCE_MAX_CHARS=2000 (prompt below the -ub 2048 ubatch)

Each entry is generated --repeats times per arm, sequentially (like Stage 6),
through the normal GPU handover (llama-server with start-gemma4-26b.sh). The
hard guard is NOT applied — we want to see the raw output. Nothing is written
to `trends`; results go to data/repro_stage6_garbage_<date>.json + a Markdown
table on stdout.

    python scripts/repro_stage6_garbage.py                       # 22 entries × 3 arms × 3 repeats
    python scripts/repro_stage6_garbage.py --repeats 5 --arms A,B
    python scripts/repro_stage6_garbage.py --ids 1718638,1718639  # trend ids, or --raw-ids
    python scripts/repro_stage6_garbage.py --dry-run             # prompts + sizes only, no GPU

ENVIRONMENT: run with the cycle's Stage-6 settings, otherwise the model identity
check (#98) aborts against the resting 8B ("expected Qwen3.6-35B", the config
default) — e.g.
    STAGE5_BACKEND=llamacpp STAGE5_MODEL=gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf \
        python scripts/repro_stage6_garbage.py --repeats 3
(first run 2026-09-05 16:14 failed exactly so; second run with the env worked).
PRECONDITIONS: the GPU must be free (no cycle, no judge, no ingester on :8090 —
check `systemctl --user status llama-server` and `nvidia-smi`); run it from
the repo root with the venv. Expect ~2 s per generation (≈ 7 min for the
default 22 × 3 × 3). DO NOT run while a cycle holds :8090 (#98).

Reading the result: if arm A reproduces garbage and B does not, prompt-cache
reuse is the trigger → set cache_prompt=false for Stage 6 (one-line change in
step_generate_content_en: pass cache_prompt=False). If C is clean and A/B are
not, prompt length is the trigger → lower STAGE6_SOURCE_MAX_CHARS. If nothing
reproduces, the episode was state-dependent (slot corruption during that run);
the hard guard + uncached retry remain the defence.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from contextlib import nullcontext
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

INCIDENT_TREND_IDS = list(range(1718638, 1718660))  # 22 consecutive garbage drafts

ARMS = {
    "A": {"label": "production (cache on, 4000)", "cache_prompt": None, "source_max": 4000},
    "B": {"label": "no prompt cache (4000)", "cache_prompt": False, "source_max": 4000},
    "C": {"label": "short source (cache on, 2000)", "cache_prompt": None, "source_max": 2000},
}


def load_entries(trend_ids: list[int] | None, raw_ids: list[int] | None) -> list[dict]:
    from pipeline.db import get_connection
    with get_connection() as c:
        if raw_ids:
            rows = c.execute(
                "SELECT re.id AS raw_id, re.title, re.excerpt, re.raw_content, re.url, "
                "       re.extraction_json, re.classification_json, s.name AS source_name "
                "  FROM raw_entries re JOIN sources s ON s.id = re.source_id "
                f" WHERE re.id IN ({','.join('?' * len(raw_ids))}) ORDER BY re.id", raw_ids).fetchall()
        else:
            ids = trend_ids or INCIDENT_TREND_IDS
            rows = c.execute(
                "SELECT re.id AS raw_id, re.title, re.excerpt, re.raw_content, re.url, "
                "       re.extraction_json, re.classification_json, s.name AS source_name, "
                "       t.id AS trend_id, t.body_en AS stored_body "
                "  FROM trends t JOIN raw_entries re ON re.id = t.raw_entry_id "
                "  JOIN sources s ON s.id = re.source_id "
                f" WHERE t.id IN ({','.join('?' * len(ids))}) ORDER BY t.id", ids).fetchall()
    return [dict(r) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay the 2026-09-05 Stage-6 garbage entries")
    ap.add_argument("--ids", help="trend ids (default: the 22 incident drafts)")
    ap.add_argument("--raw-ids", help="raw_entry ids instead of trend ids")
    ap.add_argument("--arms", default="A,B,C")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true", help="build prompts only, no GPU")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    from pipeline import gpu_handover, llamacpp_client
    from pipeline.config import STAGE5_BACKEND, STAGE5_MODEL
    from pipeline.content_guard import garbage_reasons
    from pipeline.models import ClassificationResult, ExtractionResult, GeneratedContent
    import pipeline.llm_processor as P

    entries = load_entries([int(x) for x in args.ids.split(",")] if args.ids else None,
                           [int(x) for x in args.raw_ids.split(",")] if args.raw_ids else None)
    if not entries:
        print("no entries found"); return 1
    arms = [a.strip() for a in args.arms.split(",") if a.strip() in ARMS]
    print(f"{len(entries)} entries × {len(arms)} arms × {args.repeats} repeats")

    results: list[dict] = []
    gpu_ctx = (gpu_handover.content_gen_on_llamacpp(STAGE5_MODEL)
               if STAGE5_BACKEND == "llamacpp" and not args.dry_run else nullcontext())
    with gpu_ctx:
        for arm in arms:
            spec = ARMS[arm]
            P.CONTENT_CHARS = spec["source_max"]          # the slice build_content_prompt uses
            for e in entries:
                ext = (ExtractionResult.model_validate_json(e["extraction_json"])
                       if e.get("extraction_json") else ExtractionResult())
                cls = (ClassificationResult.model_validate_json(e["classification_json"])
                       if e.get("classification_json") else
                       ClassificationResult(verticals=["TECH"], pestel=["T"], tags=[],
                                            trend_signal_type="research", mega_trend=None, regions=[]))
                excerpt = e.get("raw_content") or e.get("excerpt") or ""
                prompt, _src = P.build_content_prompt(e["title"], excerpt, ext, cls,
                                                      e["url"], e["source_name"])
                if args.dry_run:
                    print(f"[{arm}] raw {e['raw_id']} {e['source_name']}: prompt {len(prompt):,} chars")
                    continue
                for rep in range(args.repeats):
                    t0 = time.time()
                    out = llamacpp_client.chat_structured(
                        model=STAGE5_MODEL, prompt=prompt, schema=GeneratedContent,
                        system=P.CONTENT_EN_SYSTEM_V2, temperature=0.7,
                        cache_prompt=spec["cache_prompt"], verify_model=True)
                    body = out.body if out else ""
                    reasons = garbage_reasons(body, _src)
                    results.append({"arm": arm, "raw_id": e["raw_id"], "trend_id": e.get("trend_id"),
                                    "source": e["source_name"], "rep": rep, "prompt_chars": len(prompt),
                                    "garbage": reasons, "words": len(body.split()),
                                    "seconds": round(time.time() - t0, 1), "body_head": body[:120]})
                    flag = "GARBAGE" if reasons else "ok"
                    print(f"[{arm}] raw {e['raw_id']} rep {rep}: {flag} {reasons[:2]} "
                          f"({len(body.split())}w, {time.time() - t0:.1f}s)")
    if args.dry_run:
        return 0
    out_path = Path("data") / f"repro_stage6_garbage_{date.today().isoformat()}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print("\n| Arm | Generierungen | Garbage | Quote |\n|---|---|---|---|")
    for arm in arms:
        rs = [r for r in results if r["arm"] == arm]
        g = sum(1 for r in rs if r["garbage"])
        print(f"| {arm} {ARMS[arm]['label']} | {len(rs)} | {g} | {g / max(len(rs), 1):.1%} |")
    print(f"\nresults: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
