"""Dry-run comparison: current 2-call EN+DE path vs. a single combined bilingual call.

Goal: test the BACKLOG hypothesis that stages 6+7 of the LLM pipeline can be
collapsed into a single structured call, halving overhead without losing
DE-quality.

Method:
- Sample N published trends joined with their raw_entries (title + excerpt
  provide the source text; classification fields provide the context).
- For each sample, run (a) the existing two-call path and (b) a new
  single-call path, timing both wall-clocks.
- Write a JSON report + a human-readable markdown side-by-side of the first
  5 samples for manual quality inspection.

Usage:
    python scripts/dryrun_bilingual_call.py              # 20 samples
    python scripts/dryrun_bilingual_call.py --n 50
    python scripts/dryrun_bilingual_call.py --n 50 --out data/bilingual_dryrun
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import BaseModel, Field

# Ensure repo root is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.config import DATABASE_PATH, MODEL_GENERATE  # noqa: E402
from pipeline.llm_processor import (  # noqa: E402
    CONTENT_EN_SYSTEM,
    TRANSLATE_SYSTEM,
    step_generate_content_en,
    step_translate_to_de,
)
from pipeline.models import (  # noqa: E402
    ClassificationResult,
    ExtractionResult,
    GeneratedContent,
)
from pipeline.ollama_client import chat_structured  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u3000-\u9fff\u4e00-\u9fff\u3040-\u30ff]")


# ---- Combined bilingual schema -------------------------------------------------

class BilingualContent(BaseModel):
    """Single-call bilingual output for the combined EN+DE experiment."""
    title_en: str = Field(description="English article title")
    summary_en: str = Field(description="English 2-3 sentence summary")
    body_en: str = Field(description="English article body (150-250 words)")
    title_de: str = Field(description="Deutscher Artikel-Titel")
    summary_de: str = Field(description="Deutsche 2-3 Satz-Zusammenfassung")
    body_de: str = Field(description="Deutscher Artikel-Body (150-250 Woerter)")
    source_attribution: str = Field(description="Source attribution line")


BILINGUAL_SYSTEM = (
    CONTENT_EN_SYSTEM
    + "\n\n"
    + "Additionally, produce a high-quality German version of the same article.\n"
    + TRANSLATE_SYSTEM
    + "\n\nIMPORTANT: Return all six fields (title_en, summary_en, body_en, "
    "title_de, summary_de, body_de) in one structured response. The German "
    "version must match the English in substance and length, not be a literal "
    "word-for-word translation."
)


def step_generate_bilingual(
    title: str,
    excerpt: str,
    extraction: ExtractionResult,
    classification: ClassificationResult,
    source_url: str,
    source_name: str,
) -> BilingualContent | None:
    context = (
        f"Original Title: {title}\n"
        f"Original Excerpt: {excerpt[:1000]}\n"
        f"Brand: {extraction.brand_name or 'Unknown'}\n"
        f"Product: {extraction.product_name or 'Unknown'}\n"
        f"Key Claims: {', '.join(extraction.key_claims[:5]) if extraction.key_claims else 'N/A'}\n"
        f"Verticals: {', '.join(classification.verticals)}\n"
        f"PESTEL: {', '.join(classification.pestel)}\n"
        f"Signal Type: {classification.trend_signal_type}\n"
        f"Mega Trend: {classification.mega_trend or 'N/A'}\n"
        f"Source: {source_name} ({source_url})"
    )
    prompt = (
        "Write a trend article in BOTH English and German based on this information.\n\n"
        f"{context}\n\n"
        f'Include a source attribution at the end: "Source: {source_name}" '
        f'(English) and "Quelle: {source_name}" (German).'
    )
    return chat_structured(
        model=MODEL_GENERATE,
        prompt=prompt,
        schema=BilingualContent,
        system=BILINGUAL_SYSTEM,
        temperature=0.6,
    )


# ---- Sampling ------------------------------------------------------------------

@dataclass
class Sample:
    trend_id: int
    title: str
    excerpt: str
    source_name: str
    source_url: str
    verticals: list[str]
    pestel: list[str]
    mega_trend: str | None


def load_samples(n: int) -> list[Sample]:
    con = sqlite3.connect(DATABASE_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT t.id, r.title, r.excerpt, t.source_name, t.source_url,
               t.verticals, t.pestel, t.mega_trend
        FROM trends t
        JOIN raw_entries r ON t.raw_entry_id = r.id
        WHERE t.status = 'published'
          AND r.title IS NOT NULL AND LENGTH(r.excerpt) > 80
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (n,),
    ).fetchall()
    con.close()

    out: list[Sample] = []
    for r in rows:
        try:
            verticals = json.loads(r["verticals"] or "[]")
            pestel = json.loads(r["pestel"] or "[]")
        except json.JSONDecodeError:
            verticals, pestel = [], []
        out.append(
            Sample(
                trend_id=r["id"],
                title=r["title"],
                excerpt=r["excerpt"],
                source_name=r["source_name"] or "Unknown",
                source_url=r["source_url"] or "",
                verticals=verticals,
                pestel=pestel,
                mega_trend=r["mega_trend"],
            )
        )
    return out


def build_minimal_inputs(s: Sample) -> tuple[ExtractionResult, ClassificationResult]:
    extraction = ExtractionResult(
        brand_name=None,
        product_name=None,
        source_type="trade_media",
        key_claims=[],
    )
    classification = ClassificationResult(
        verticals=s.verticals or ["BIZ"],
        primary_vertical=(s.verticals or ["BIZ"])[0],
        pestel=s.pestel or ["E"],
        tags=[],
        trend_signal_type="market_shift",
        regions=["Global"],
        mega_trend=s.mega_trend,
    )
    return extraction, classification


# ---- Run -----------------------------------------------------------------------

@dataclass
class RunResult:
    trend_id: int
    title: str
    two_call_ok: bool
    two_call_seconds: float
    one_call_ok: bool
    one_call_seconds: float
    two_call_en: dict | None
    two_call_de: dict | None
    one_call: dict | None
    one_call_cjk: bool


def run_two_call(s: Sample, ext: ExtractionResult, cls: ClassificationResult) -> tuple[bool, float, dict | None, dict | None]:
    t0 = time.perf_counter()
    en = step_generate_content_en(
        title=s.title,
        excerpt=s.excerpt,
        extraction=ext,
        classification=cls,
        source_url=s.source_url,
        source_name=s.source_name,
    )
    if en is None:
        return False, time.perf_counter() - t0, None, None
    de = step_translate_to_de(en, s.source_name)
    elapsed = time.perf_counter() - t0
    return (
        de is not None,
        elapsed,
        _gc_to_dict(en),
        _gc_to_dict(de) if de else None,
    )


def run_one_call(s: Sample, ext: ExtractionResult, cls: ClassificationResult) -> tuple[bool, float, dict | None, bool]:
    t0 = time.perf_counter()
    bi = step_generate_bilingual(
        title=s.title,
        excerpt=s.excerpt,
        extraction=ext,
        classification=cls,
        source_url=s.source_url,
        source_name=s.source_name,
    )
    elapsed = time.perf_counter() - t0
    if bi is None:
        return False, elapsed, None, False
    combined_de = (bi.title_de or "") + (bi.summary_de or "") + (bi.body_de or "")
    cjk = bool(_CJK_RE.search(combined_de))
    return True, elapsed, bi.model_dump(), cjk


def _gc_to_dict(gc: GeneratedContent | None) -> dict | None:
    if gc is None:
        return None
    return {
        "title": gc.title,
        "summary": gc.summary,
        "body": gc.body,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20, help="Sample size (default 20)")
    parser.add_argument(
        "--out",
        type=str,
        default="data/bilingual_dryrun",
        help="Output file prefix (writes .json + .md)",
    )
    args = parser.parse_args()

    print(f"Loading {args.n} samples...")
    samples = load_samples(args.n)
    if not samples:
        print("No samples found.", file=sys.stderr)
        return 1
    print(f"Got {len(samples)} samples. Starting run...\n")

    results: list[RunResult] = []
    for i, s in enumerate(samples, 1):
        print(f"[{i}/{len(samples)}] {s.title[:70]}")
        ext, cls = build_minimal_inputs(s)

        two_ok, two_s, en, de = run_two_call(s, ext, cls)
        print(f"    2-call: {'OK' if two_ok else 'FAIL'} in {two_s:5.1f}s")

        one_ok, one_s, bi, cjk = run_one_call(s, ext, cls)
        cjk_tag = " [CJK!]" if cjk else ""
        print(f"    1-call: {'OK' if one_ok else 'FAIL'} in {one_s:5.1f}s{cjk_tag}")

        results.append(
            RunResult(
                trend_id=s.trend_id,
                title=s.title,
                two_call_ok=two_ok,
                two_call_seconds=two_s,
                one_call_ok=one_ok,
                one_call_seconds=one_s,
                two_call_en=en,
                two_call_de=de,
                one_call=bi,
                one_call_cjk=cjk,
            )
        )

    # ---- Aggregate
    two_ok_count = sum(1 for r in results if r.two_call_ok)
    one_ok_count = sum(1 for r in results if r.one_call_ok)
    cjk_count = sum(1 for r in results if r.one_call_cjk)
    two_total = sum(r.two_call_seconds for r in results if r.two_call_ok)
    one_total = sum(r.one_call_seconds for r in results if r.one_call_ok)
    two_mean = two_total / two_ok_count if two_ok_count else 0.0
    one_mean = one_total / one_ok_count if one_ok_count else 0.0
    speedup = (two_mean / one_mean) if one_mean else 0.0

    print("\n=== Summary ===")
    print(f"Samples:     {len(results)}")
    print(f"2-call:      {two_ok_count} ok, mean {two_mean:5.1f}s, total {two_total:6.1f}s")
    print(f"1-call:      {one_ok_count} ok, mean {one_mean:5.1f}s, total {one_total:6.1f}s")
    print(f"CJK leaks:   {cjk_count} / {one_ok_count} 1-call outputs")
    print(f"Speedup:     {speedup:.2f}x (1-call mean vs 2-call mean)")

    # ---- Persist
    out_prefix = Path(args.out)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = out_prefix.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "n": len(results),
                "two_call": {
                    "ok": two_ok_count,
                    "mean_seconds": round(two_mean, 2),
                    "total_seconds": round(two_total, 1),
                },
                "one_call": {
                    "ok": one_ok_count,
                    "mean_seconds": round(one_mean, 2),
                    "total_seconds": round(one_total, 1),
                    "cjk_leaks": cjk_count,
                },
                "speedup": round(speedup, 2),
                "results": [asdict(r) for r in results],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nJSON report: {json_path}")

    # Markdown side-by-side for first 5 successful pairs
    md_path = out_prefix.with_suffix(".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Bilingual Dry-Run — {len(results)} samples\n\n")
        f.write(
            f"- **2-call mean:** {two_mean:.1f}s ({two_ok_count}/{len(results)} ok)\n"
            f"- **1-call mean:** {one_mean:.1f}s ({one_ok_count}/{len(results)} ok)\n"
            f"- **Speedup:** {speedup:.2f}x\n"
            f"- **CJK leaks (1-call):** {cjk_count}\n\n"
        )
        f.write("## Side-by-side (first 5 successful pairs)\n\n")
        shown = 0
        for r in results:
            if shown >= 5 or not (r.two_call_ok and r.one_call_ok):
                continue
            shown += 1
            f.write(f"### {shown}. Trend #{r.trend_id} — {r.title}\n\n")
            f.write(f"- 2-call: {r.two_call_seconds:.1f}s  |  1-call: {r.one_call_seconds:.1f}s"
                    f"{' [CJK]' if r.one_call_cjk else ''}\n\n")
            f.write("**EN (2-call)**\n\n")
            f.write(f"> {r.two_call_en['title']}\n\n")
            f.write(f"{r.two_call_en['body']}\n\n")
            f.write("**EN (1-call)**\n\n")
            f.write(f"> {r.one_call['title_en']}\n\n")
            f.write(f"{r.one_call['body_en']}\n\n")
            f.write("**DE (2-call)**\n\n")
            f.write(f"> {r.two_call_de['title']}\n\n")
            f.write(f"{r.two_call_de['body']}\n\n")
            f.write("**DE (1-call)**\n\n")
            f.write(f"> {r.one_call['title_de']}\n\n")
            f.write(f"{r.one_call['body_de']}\n\n")
            f.write("---\n\n")
    print(f"Markdown:    {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
