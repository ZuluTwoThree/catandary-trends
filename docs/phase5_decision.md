# Phase-5 Decision Gate — Classification Model (2026-06-20)

Option-3 backfill: which API model classifies the historical signals?

## Test
`scripts/test_classify_models.py --total 1000 --overlap 100` — 500 entries via
Haiku + 500 via Sonnet, re-classifying existing published trends (each carries a
local-qwen `primary_vertical` + `mega_trend` baseline), measuring cached cost and
agreement. Real synchronous spend ~$9.5 (within the authorised ~$15).

## Results

| Model | vertical vs qwen | mega_trend vs qwen | $/50k (batched, cached) |
|---|---|---|---|
| Haiku 4.5 | **82%** | 63% | **$144** |
| Sonnet 4.6 | 63% | 47% | $252 |
| Haiku-vs-Sonnet (overlap 100) | **92%** | — | — |

## Eyeball (24 entries, qwen vs Haiku vs Sonnet)
Haiku ≈ Sonnet on vertical (2/24 disagreements). Where the API models diverge
from qwen, they are usually **more correct** (AI-scribes→HEALTH not TECH;
fitness→HEALTH not LIFESTYLE; VC story→BIZ not LIFESTYLE) — so "agreement vs qwen"
understates API quality (qwen is the noisier baseline). The lower mega_trend
agreement is mostly Haiku conservatively returning `None` when no canonical
mega-trend fits, plus the inherent subjectivity of the 22-class taxonomy.

## Decision: **Haiku (`claude-haiku-4-5`)**
- Cheapest ($144/50k batched-cached); highest consistency with the existing 41k
  qwen-classified corpus (continuity); quality ≥ qwen (often better).
- Decision rule: combined agreement Haiku 73% vs Sonnet 55% (>5pp higher) → Haiku.
- Abort threshold (vertical <80% on both) NOT triggered (Haiku 82%).
- `ANTHROPIC_MODEL_CLASSIFY=claude-haiku-4-5` (already the default).
- Production full-run uses `batch_classify` (−50%); validate that path on a small
  batch before scaling.
