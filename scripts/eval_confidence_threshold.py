#!/usr/bin/env python3
"""Does the 0.85 auto-publish threshold separate good articles from bad ones?

Question behind it (owner, 2026-08-18): ~320 of ~800 daily trends are never
published, and 97.5% of those fail on confidence alone — 8 on the quality
gates. The draft pile stands at ~9,900 and grows by ~340 a day. But `confidence`
is the STAGE-1 RELEVANCE score ("is this a trend signal at all?"), carried
unchanged into the trend and used nine stages later to decide publication. It
says nothing about the article that was eventually written.

So: compare the withheld band against what actually ships.

  Group A  drafts, confidence 0.75-0.85  (the band that looks publishable)
  Group B  auto-published, confidence >= 0.85  (what the threshold lets through)

Deterministic metrics first — they need no GPU and cannot flatter themselves:
fabricated figures, truncation, length against the 150-250 word target, and
evidence density (how many concrete source-supported facts the body carries).

Then a BLIND judge over the pooled, shuffled, label-stripped articles. It never
learns the group, the confidence, or that groups exist. The sharpest result is
not its average score but whether its verdicts separate the groups at all: if a
strong model cannot tell withheld from published, the threshold is not sorting
on quality.

    python -m scripts.eval_confidence_threshold --n 60 --skip-judge
    python -m scripts.eval_confidence_threshold --n 60
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import statistics as stats
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import BaseModel

from pipeline.db import get_connection
from pipeline.grounding import source_from_parts, ungrounded_specifics, _concrete_tokens

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("eval_threshold")

SEED = 20260818  # fixed so the sample is reproducible and cannot be re-rolled


def fetch(where: str, n: int, seed: int) -> list[dict]:
    """Random sample from one group. setseed() makes the draw reproducible."""
    with get_connection() as conn:
        conn.execute("SELECT setseed(%s)", (((seed % 1000) / 1000.0) - 0.5,))
        rows = conn.execute(
            "SELECT t.id, t.title_en, t.body_en, t.confidence, t.primary_vertical, "
            "       t.source_name, re.title AS re_title, re.raw_content, re.excerpt, "
            "       re.extraction_json "
            "  FROM trends t LEFT JOIN raw_entries re ON re.id = t.raw_entry_id "
            f" WHERE {where} AND t.body_en IS NOT NULL "
            "   AND t.created_at > CURRENT_DATE - 14 "
            " ORDER BY random() LIMIT %s",
            (n,),
        ).fetchall()
    return [dict(r) for r in rows]


def metrics(d: dict) -> dict:
    ext = {}
    if d.get("extraction_json"):
        try:
            ext = json.loads(d["extraction_json"]) or {}
        except (json.JSONDecodeError, TypeError):
            ext = {}
    lst = lambda k: [str(x) for x in ext.get(k) or []] if isinstance(ext.get(k), list) else []
    src = source_from_parts(d["re_title"], d["raw_content"] or d["excerpt"],
                            lst("key_claims"), lst("key_figures"), lst("dates"),
                            lst("quotes"), lst("geography"))
    body = d["body_en"] or ""
    words = len(body.split())
    flagged = ungrounded_specifics(body, src)
    body_tokens = _concrete_tokens(body)
    # Evidence density: concrete figures the body states that the source backs.
    # A body full of grounded specifics is doing the job; one with none is prose.
    grounded = len(body_tokens) - len(flagged)
    return {
        "id": d["id"], "conf": d["confidence"], "vertical": d["primary_vertical"],
        "source": d["source_name"], "title": d["title_en"], "body": body, "src": src,
        "words": words,
        "in_target": 150 <= words <= 250,
        "fabricated": len(flagged),
        "truncated": bool(body.strip()) and body.strip()[-1] not in '.!?"”',
        "grounded_specifics": grounded,
        "src_words": len(src.split()),
    }


def describe(name: str, rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {}
    med = lambda k: stats.median(r[k] for r in rows)
    pct = lambda k: 100.0 * sum(1 for r in rows if r[k]) / n
    out = {
        "n": n,
        "conf_median": stats.median(r["conf"] for r in rows),
        "words_median": med("words"),
        "in_target_pct": pct("in_target"),
        "fabricated_pct": 100.0 * sum(1 for r in rows if r["fabricated"]) / n,
        "truncated_pct": pct("truncated"),
        "grounded_median": med("grounded_specifics"),
        "src_words_median": med("src_words"),
    }
    print(f"\n--- {name} (n={n}) ---")
    print(f"  Confidence (Median)          {out['conf_median']:.3f}")
    print(f"  Woerter (Median)             {out['words_median']:.0f}")
    print(f"  im Zielkorridor 150-250      {out['in_target_pct']:.1f} %")
    print(f"  mit erfundener Zahl          {out['fabricated_pct']:.1f} %")
    print(f"  abgeschnittener Body         {out['truncated_pct']:.1f} %")
    print(f"  belegte Fakten (Median)      {out['grounded_median']:.0f}")
    print(f"  Quelltext-Woerter (Median)   {out['src_words_median']:.0f}")
    return out


JUDGE_SYSTEM = (
    "You are a senior editor at a cross-industry trend intelligence service. "
    "You decide whether a written piece belongs on the public feed. Judge only "
    "what is in front of you. Be strict and terse."
)

JUDGE_PROMPT = """Below is a generated article and the source material it was written from.

SOURCE MATERIAL:
{src}

ARTICLE:
{body}

Answer with JSON only:
{{"signal": true, "grounded": true, "substance": 3, "reason": "<=15 words"}}

signal    — does this report a genuine industry/technology/market development worth publishing as a trend signal? (false for consumer support notes, local politics, routine product bugs)
grounded  — is every specific claim in the article supported by the source material?
substance — 1 = empty prose, 5 = dense, decision-useful, concrete"""


class Verdict(BaseModel):
    signal: bool
    grounded: bool
    substance: int
    reason: str = ""


def judge(rows: list[dict], model_hint: str) -> None:
    """Blind pass. Rows are pooled and shuffled by the caller; nothing here
    reveals which group an article came from — no confidence, no status, no
    ordering. Schema-validated output so a malformed answer is retried rather
    than silently parsed into a default."""
    from pipeline.llamacpp_client import chat_structured
    for i, r in enumerate(rows, 1):
        prompt = JUDGE_PROMPT.format(src=r["src"][:2600], body=r["body"][:2600])
        v = None
        try:
            v = chat_structured(model=model_hint, system=JUDGE_SYSTEM,
                                prompt=prompt, schema=Verdict, temperature=0.0)
        except Exception as e:  # noqa: BLE001
            logger.warning("judge failed on #%s: %r", r["id"], e)
        if v is None:
            r["j_signal"] = r["j_grounded"] = None
            r["j_substance"] = 0
        else:
            r["j_signal"] = v.signal
            r["j_grounded"] = v.grounded
            r["j_substance"] = max(1, min(5, v.substance))
            r["j_reason"] = v.reason[:80]
        if i % 20 == 0:
            logger.info("judged %d/%d", i, len(rows))


def judge_summary(name: str, rows: list[dict]) -> None:
    ok = [r for r in rows if r.get("j_signal") is not None]
    if not ok:
        print(f"\n--- {name}: kein Urteil ---")
        return
    n = len(ok)
    print(f"\n--- Urteil: {name} (n={n}) ---")
    print(f"  als echtes Signal bewertet   {100*sum(1 for r in ok if r['j_signal'])/n:.1f} %")
    print(f"  als quellentreu bewertet     {100*sum(1 for r in ok if r['j_grounded'])/n:.1f} %")
    print(f"  Substanz (Median)            {stats.median(r['j_substance'] for r in ok):.1f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60, help="sample size per group")
    ap.add_argument("--skip-judge", action="store_true", help="deterministic metrics only")
    ap.add_argument("--model", default="Qwen3.8-27B", help="judge model hint for :8090")
    ap.add_argument("--out", default="data/eval_confidence_threshold.json")
    args = ap.parse_args()

    a_raw = fetch("t.status = 'draft' AND t.confidence BETWEEN 0.75 AND 0.85",
                  args.n, SEED)
    b_raw = fetch("t.status = 'published' AND t.auto_published AND t.confidence >= 0.85",
                  args.n, SEED + 1)
    A = [metrics(d) for d in a_raw]
    B = [metrics(d) for d in b_raw]
    logger.info("sampled %d withheld, %d published", len(A), len(B))

    sa = describe("A: zurueckgehalten, conf 0.75-0.85", A)
    sb = describe("B: auto-veroeffentlicht, conf >= 0.85", B)

    if not args.skip_judge:
        pool = [dict(r, _grp="A") for r in A] + [dict(r, _grp="B") for r in B]
        random.Random(SEED).shuffle(pool)          # blind: judge sees no order
        logger.info("blind judging %d articles on %s", len(pool), args.model)
        judge(pool, args.model)
        judge_summary("A zurueckgehalten", [r for r in pool if r["_grp"] == "A"])
        judge_summary("B veroeffentlicht", [r for r in pool if r["_grp"] == "B"])
        A = [r for r in pool if r["_grp"] == "A"]
        B = [r for r in pool if r["_grp"] == "B"]

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    slim = lambda rs: [{k: v for k, v in r.items() if k not in ("body", "src")} for r in rs]
    Path(args.out).write_text(json.dumps(
        {"seed": SEED, "summary_a": sa, "summary_b": sb,
         "a": slim(A), "b": slim(B)}, indent=2, default=str), encoding="utf-8")
    print(f"\nRohdaten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
