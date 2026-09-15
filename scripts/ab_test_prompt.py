#!/usr/bin/env python3
"""Content-quality A/B eval harness (issue #11, lever #6).

Regenerates a stratified sample of published trend bodies with two prompt
variants — A = the current production CONTENT_EN_SYSTEM, B = a candidate with
signal-type-specific framing and forced concreteness — and has an independent
Claude judge score them pairwise on a fixed rubric (source fidelity, specificity,
originality, cliché-freedom). Non-destructive: it never writes to `trends`; it
emits a JSON + Markdown report to data/. (The dev-only /trends/quality-preview
page that rendered a preview payload was removed on 2026-09-15; --preview is gone.)

    python scripts/ab_test_prompt.py --n 30            # 30 stratified trends
    python scripts/ab_test_prompt.py --ids 52719,675892

Runs content-gen on the same GPU path as the pipeline (llama.cpp 30B via the
handover); the judge is a cheap Anthropic call. GPU must be free.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import BaseModel, Field

from pipeline import gpu_handover, llamacpp_client
from pipeline.config import STAGE5_BACKEND, STAGE5_MODEL, ANTHROPIC_MODEL_CLASSIFY
from pipeline.db import get_connection
from pipeline.models import ClassificationResult, ExtractionResult, GeneratedContent
from pipeline.llm_processor import (
    CONTENT_EN_SYSTEM,
    CONTENT_EN_SYSTEM_V2,
    signal_type_framing,
    content_is_clean,
    make_content_guard,
)
from pipeline.grounding import ungrounded_specifics

# single source of truth: the fabrication detector lives in pipeline.grounding so
# the live guard, the publish gate and this harness all measure the same thing.
fabricated_specifics = ungrounded_specifics
from pipeline import anthropic_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATA = Path(__file__).parent.parent / "data"


# ---- sampling ---------------------------------------------------------------

def stratified_sample(n: int, ids: list[int] | None) -> list[dict]:
    """Published trends with their raw inputs, spread across signal types."""
    base = (
        "SELECT t.id, t.trend_signal_type, t.primary_vertical, "
        "       t.title_en AS stored_title, t.body_en AS stored_body, "
        "       r.title, r.excerpt, r.url, r.extraction_json, r.classification_json, "
        "       s.name AS source_name "
        "FROM trends t JOIN raw_entries r ON t.raw_entry_id = r.id "
        "LEFT JOIN sources s ON r.source_id = s.id "
    )
    with get_connection() as c:
        if ids:
            q = base + f"WHERE t.id IN ({','.join('?' * len(ids))})"
            return [dict(r) for r in c.execute(q, ids).fetchall()]
        # even spread across signal types via per-type random rank
        q = (
            "SELECT * FROM (" + base +
            "  WHERE t.status='published' AND r.excerpt IS NOT NULL AND length(r.excerpt) > 120"
            ") q ORDER BY random() LIMIT ?"
        )
        rows = [dict(r) for r in c.execute(q, (n * 4,)).fetchall()]
    # balance: keep up to ceil(n/types) per signal_type
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r.get("trend_signal_type") or "other", []).append(r)
    out: list[dict] = []
    types = list(by_type)
    i = 0
    while len(out) < n and any(by_type.values()):
        t = types[i % len(types)]
        if by_type[t]:
            out.append(by_type[t].pop())
        i += 1
    return out[:n]


def _load(js, schema, default):
    if not js:
        return default
    try:
        return schema.model_validate_json(js)
    except Exception:
        return default


# ---- generation -------------------------------------------------------------

def build_prompt(row: dict, ext: ExtractionResult, cls: ClassificationResult,
                 framing: str | None) -> str:
    context = f"""Original Title: {row['title']}
Original Excerpt: {(row.get('excerpt') or '')[:1000]}
Brand: {ext.brand_name or 'Unknown'}
Product: {ext.product_name or 'Unknown'}
Key Claims: {', '.join(ext.key_claims[:5]) if ext.key_claims else 'N/A'}
Verticals: {', '.join(cls.verticals)}
PESTEL: {', '.join(cls.pestel)}
Signal Type: {cls.trend_signal_type}
Mega Trend: {cls.mega_trend or 'N/A'}
Source: {row.get('source_name') or 'Unknown'} ({row['url']})"""
    framing_block = f"\nSignal-type framing: {framing}\n" if framing else ""
    return (f"Write a trend article in English based on this information.\n"
            f"The source below may be in German or another language — translate it "
            f"and write the title and body entirely in English.\n{framing_block}\n{context}\n\n")


def gen(row: dict, ext, cls, system: str, framing: str | None, validate) -> GeneratedContent | None:
    return llamacpp_client.chat_structured(
        model=STAGE5_MODEL,
        prompt=build_prompt(row, ext, cls, framing),
        schema=GeneratedContent,
        system=system,
        temperature=0.7,
        validate=validate,
        max_validate_retries=3,
    )


# ---- judge ------------------------------------------------------------------

class JudgeScore(BaseModel):
    source_fidelity_1: int = Field(ge=1, le=5, description="Article 1: faithful to the source facts, no invented specifics")
    specificity_1: int = Field(ge=1, le=5, description="Article 1: concrete figures/names/dates vs vague abstraction")
    originality_1: int = Field(ge=1, le=5, description="Article 1: reworded and analytical, not echoing source phrasing")
    cliche_freedom_1: int = Field(ge=1, le=5, description="Article 1: free of template/filler phrasing")
    source_fidelity_2: int = Field(ge=1, le=5)
    specificity_2: int = Field(ge=1, le=5)
    originality_2: int = Field(ge=1, le=5)
    cliche_freedom_2: int = Field(ge=1, le=5)
    winner: str = Field(description="'1', '2', or 'tie' — which article is the better trend brief overall")
    reason: str = Field(description="One sentence justifying the winner")


JUDGE_SYSTEM = """You are a strict editor grading two short trend-analysis briefs written from the SAME source material. \
Grade each on a 1-5 scale for: source fidelity (no invented facts), specificity (concrete figures/names/dates over abstraction), \
originality (reworded and analytical, not echoing the source), and cliché-freedom (no template/filler phrasing like 'signals a shift', 'paving the way'). \
Then pick the better overall brief. Judge only what is written; do not reward length. Be discriminating — reserve 5 for genuinely excellent."""


def judge(source_title: str, source_excerpt: str, art1: str, art2: str) -> JudgeScore | None:
    prompt = f"""SOURCE TITLE: {source_title}
SOURCE EXCERPT: {source_excerpt[:1200]}

--- ARTICLE 1 ---
{art1}

--- ARTICLE 2 ---
{art2}

Score both articles and pick the better trend brief."""
    return anthropic_client.chat_structured(
        model=ANTHROPIC_MODEL_CLASSIFY, prompt=prompt, schema=JudgeScore,
        system=JUDGE_SYSTEM, temperature=0.0)


# ---- main -------------------------------------------------------------------

def run(rows: list[dict]) -> dict:
    results = []
    gpu_ctx = (gpu_handover.content_gen_on_llamacpp(STAGE5_MODEL)
               if STAGE5_BACKEND == "llamacpp" else nullcontext())
    with gpu_ctx:
        for i, row in enumerate(rows, 1):
            ext = _load(row["extraction_json"], ExtractionResult, ExtractionResult())
            cls = _load(row["classification_json"], ClassificationResult,
                        ClassificationResult(verticals=[], pestel=[], tags=[],
                                             trend_signal_type=row.get("trend_signal_type") or "market_shift"))
            framing = signal_type_framing(cls.trend_signal_type)
            src = f"{row['title']} {row.get('excerpt') or ''} " + " ".join(ext.key_claims or [])
            # A = current pipeline (v1 prompt, clean guard only).
            # B = proposed pipeline (v2 prompt + grounding gate → re-rolls fabrications).
            a = gen(row, ext, cls, CONTENT_EN_SYSTEM, None, content_is_clean)
            b = gen(row, ext, cls, CONTENT_EN_SYSTEM_V2, framing, make_content_guard(src))
            if not a or not b:
                logger.warning("trend %s: a=%s b=%s — skipping", row["id"], bool(a), bool(b))
                continue
            results.append({"id": row["id"], "signal_type": cls.trend_signal_type,
                            "vertical": row["primary_vertical"], "source_title": row["title"],
                            "source_excerpt": (row.get("excerpt") or "")[:1200],
                            "a_title": a.title, "a_body": a.body,
                            "b_title": b.title, "b_body": b.body,
                            "a_fabricated": fabricated_specifics(a.body, src),
                            "b_fabricated": fabricated_specifics(b.body, src),
                            "stored_body": row.get("stored_body")})
            logger.info("generated %d/%d (trend %s, %s)", i, len(rows), row["id"], cls.trend_signal_type)

    # judge with position randomization to cancel order bias
    for r in results:
        swap = random.random() < 0.5
        art1, art2 = (r["b_body"], r["a_body"]) if swap else (r["a_body"], r["b_body"])
        js = judge(r["source_title"], r["source_excerpt"], art1, art2)
        if not js:
            r["judge"] = None
            continue
        # remap "1"/"2" back to A/B
        def side(n: int) -> str:
            is_first = (n == 1)
            return "b" if (is_first == swap) else "a"
        r["scores"] = {
            "a": {"fidelity": js.source_fidelity_2 if swap else js.source_fidelity_1,
                  "specificity": js.specificity_2 if swap else js.specificity_1,
                  "originality": js.originality_2 if swap else js.originality_1,
                  "cliche_freedom": js.cliche_freedom_2 if swap else js.cliche_freedom_1},
            "b": {"fidelity": js.source_fidelity_1 if swap else js.source_fidelity_2,
                  "specificity": js.specificity_1 if swap else js.specificity_2,
                  "originality": js.originality_1 if swap else js.originality_2,
                  "cliche_freedom": js.cliche_freedom_1 if swap else js.cliche_freedom_2},
        }
        r["winner"] = "tie" if js.winner == "tie" else side(int(js.winner)) if js.winner in ("1", "2") else "tie"
        r["judge_reason"] = js.reason

    report = summarize(results)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    DATA.mkdir(exist_ok=True)
    (DATA / f"content_ab_{ts}.json").write_text(json.dumps({"report": report, "results": results}, indent=2))
    (DATA / f"content_ab_{ts}.md").write_text(render_md(report, results))
    logger.info("wrote data/content_ab_%s.{json,md}", ts)
    print("\n" + render_md(report, results[:3]))
    return report


def summarize(results: list[dict]) -> dict:
    judged = [r for r in results if r.get("scores")]
    dims = ["fidelity", "specificity", "originality", "cliche_freedom"]
    def mean(side, d):
        vals = [r["scores"][side][d] for r in judged]
        return round(sum(vals) / len(vals), 2) if vals else None
    wins = {"a": 0, "b": 0, "tie": 0}
    for r in judged:
        wins[r.get("winner", "tie")] = wins.get(r.get("winner", "tie"), 0) + 1
    # fabrication: share of articles with >=1 ungrounded specific, and total count
    def fab(side):
        flagged = [r for r in results if r.get(f"{side}_fabricated")]
        total = sum(len(r.get(f"{side}_fabricated") or []) for r in results)
        return {"articles_with_fabrication": len(flagged),
                "rate": round(len(flagged) / len(results), 3) if results else None,
                "total_tokens": total}
    return {
        "n": len(results), "judged": len(judged),
        "mean_a": {d: mean("a", d) for d in dims},
        "mean_b": {d: mean("b", d) for d in dims},
        "wins": wins,
        "b_win_rate": round(wins["b"] / len(judged), 3) if judged else None,
        "fabrication_a": fab("a"),
        "fabrication_b": fab("b"),
    }


def render_md(report: dict, sample: list[dict]) -> str:
    L = ["# Content A/B — current (A) vs signal-type+concreteness (B)\n",
         f"- trends: {report['n']} (judged {report['judged']})",
         f"- wins: B={report['wins']['b']}  A={report['wins']['a']}  tie={report['wins']['tie']}  "
         f"→ **B win-rate {report['b_win_rate']}**",
         f"- fabricated specifics (ungrounded number/date): "
         f"A {report['fabrication_a']['articles_with_fabrication']}/{report['n']} "
         f"({report['fabrication_a']['total_tokens']} tokens), "
         f"B {report['fabrication_b']['articles_with_fabrication']}/{report['n']} "
         f"({report['fabrication_b']['total_tokens']} tokens)\n",
         "| dimension | A | B |", "|---|---|---|"]
    for d in ["fidelity", "specificity", "originality", "cliche_freedom"]:
        L.append(f"| {d} | {report['mean_a'][d]} | {report['mean_b'][d]} |")
    L.append("\n## Examples\n")
    for r in sample:
        if not r.get("scores"):
            continue
        L += [f"### trend {r['id']} — {r['signal_type']} / {r['vertical']}  (winner: {r.get('winner')})",
              f"_{r.get('judge_reason','')}_\n",
              f"**A:** {r['a_body'][:600]}\n", f"**B:** {r['b_body'][:600]}\n"]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="Content-quality A/B harness (#11)")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--ids", help="comma-separated trend ids (overrides --n)")
    args = ap.parse_args()
    if STAGE5_BACKEND != "llamacpp":
        logger.warning("STAGE5_BACKEND=%s — this harness expects llamacpp for GPU content-gen", STAGE5_BACKEND)
    ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    rows = stratified_sample(args.n, ids)
    print(f"{len(rows)} trends sampled.")
    if not rows:
        return 1
    t0 = time.time()
    run(rows)
    logger.info("done in %.0fs", time.time() - t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
