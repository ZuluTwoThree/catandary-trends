#!/usr/bin/env python3
"""Realistische Prompt-Sätze für den Kontext-/Parallelitätstest aus echten DB-Einträgen.

Baut dieselben Prompts, die die Pipeline schickt (gleiche Builder/Konstanten aus
pipeline.llm_processor, pipeline.reclassify, pipeline.draft_judge), aus Einträgen
der letzten Tage und schreibt je Stufe eine JSONL-Datei nach data/ctx_eval/prompts/:

  8b_stage234.jsonl   Relevanz (15 %) + Extraktion (85 %) — der parallele 8B-Teil des
                      Nachtlaufs im Hybrid-Modus (RSS_CLASSIFY_MODE=hybrid: die Klassifikation
                      machen die Distill-Heads, das 8B sieht nur das unsichere Relevanz-Band
                      und die Extraktion; Verhältnis 25.09.2026: 337 Relevanz-Fallbacks,
                      1.842 Extraktionen)
  8b_classification.jsonl  Stage 4 auf dem 8B — nur im Fallback RSS_CLASSIFY_MODE=llm,
                      in Produktion nicht auf dem Modell (größter System-Prompt, 2.272 Tokens)
  8b_reclassify.jsonl Stage 8 (sequentiell in Produktion)
  gemma_stage6.jsonl  Stage 6 Content-Gen (build_content_prompt, T=0.7, max_tokens 2048)
  27b_judge.jsonl     Stage 10 Richter (judge_one-Prompt: 12.000 Zeichen Quelle + Extraktion)
  emb.jsonl           Stage 5 Embeddings (title + excerpt[:500])

Jede Zeile: {"stage", "id", "system", "prompt", "schema", "require_all", "max_tokens",
"temperature"} bzw. {"stage": "emb", "input": ...}. Liest nur; schreibt nichts in die DB.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.db import get_connection  # noqa: E402
from pipeline import llm_processor as lp  # noqa: E402
from pipeline import reclassify as rc  # noqa: E402
from pipeline import draft_judge as dj  # noqa: E402
from pipeline.models import (ClassificationResult, ExtractionResult, GeneratedContent,  # noqa: E402
                             RelevanceResult)
from pipeline.llamacpp_client import _json_schema  # noqa: E402

OUT = ROOT / "data" / "ctx_eval" / "prompts"
DAYS = 10
SEED = 42
# Ausgabe-Budgets wie im Nachtlauf: scheduled_cycle.sh exportiert LLAMACPP_MAX_TOKENS=2048
MAX_TOKENS = 2048


def _text(row) -> str:
    """Wie run_pipeline_batch seit 2026-09-09: raw_content, wenn länger als der Teaser."""
    ex = row["excerpt"] or ""
    rc_ = row["raw_content"] or ""
    return rc_ if len(rc_) > len(ex) else ex


def _load(model, raw, default):
    try:
        return model.model_validate_json(raw) if raw else default
    except Exception:  # noqa: BLE001
        try:
            return model.model_validate(json.loads(raw))
        except Exception:  # noqa: BLE001
            return default


def _item(stage, id_, system, prompt, schema, require_all, max_tokens, temperature):
    return {"stage": stage, "id": id_, "system": system, "prompt": prompt,
            "schema": _json_schema(schema, require_all), "schema_name": schema.__name__,
            "max_tokens": max_tokens, "temperature": temperature}


def build_8b(rows, n, rnd):
    rel, ext, cls = [], [], []
    for r in rows:
        text = _text(r)
        e = _load(ExtractionResult, r["extraction_json"], ExtractionResult())
        rel.append(_item("relevance", r["id"], lp.RELEVANCE_SYSTEM,
                         f"""Analyze this RSS feed entry and determine if it's a relevant trend signal.
Classify the vertical based purely on the content, not on where the source comes from.
Title: {r['title']}
Excerpt: {text[:lp.RELEVANCE_CHARS]}""", RelevanceResult, False, MAX_TOKENS, 0.0))
        ext.append(_item("extraction", r["id"], lp.EXTRACTION_SYSTEM,
                         f"""Extract structured information from this text.
Title: {r['title']}
Text: {text[:lp.EXTRACT_CHARS]}""", ExtractionResult, bool(lp.EXTRACTION_STRICT), MAX_TOKENS, 0.0))
        cls.append(_item("classification", r["id"], lp.CLASSIFICATION_SYSTEM,
                         f"""Classify this trend signal.

Title: {r['title']}
Excerpt: {text[:1000]}
Brand: {e.brand_name or 'Unknown'}
Product: {e.product_name or 'Unknown'}
Key Claims: {', '.join(e.key_claims[:5]) if e.key_claims else 'None'}""",
                         ClassificationResult, False, MAX_TOKENS, 0.0))
    k_rel = round(n * 0.15); k_ext = n - k_rel
    items = rnd.sample(rel, k_rel) + rnd.sample(ext, k_ext)
    rnd.shuffle(items)
    cls_items = rnd.sample(cls, min(n, len(cls)))
    return items, cls_items


def build_reclassify(n, rnd):
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT id, title_en, summary_en FROM trends WHERE created_at > now() - interval '%d days' "
            "ORDER BY id DESC LIMIT %d" % (DAYS, n * 3)).fetchall()]
    rnd.shuffle(rows)
    return [_item("reclassify", r["id"], rc.CLASSIFY_SYSTEM,
                  f"Title: {r['title_en']}\nSummary: {(r['summary_en'] or '')[:500]}",
                  rc.ReclassifyResult, False, MAX_TOKENS, 0.0) for r in rows[:n]]


def build_gemma(rows, n, rnd):
    items = []
    for r in rows:
        e = _load(ExtractionResult, r["extraction_json"], None)
        k = _load(ClassificationResult, r["classification_json"], None)
        if e is None or k is None:
            continue
        prompt, _src = lp.build_content_prompt(r["title"], _text(r), e, k, r["url"],
                                               r["source_name"] or "Unknown")
        items.append(_item("content", r["id"], lp.CONTENT_EN_SYSTEM_V2, prompt,
                           GeneratedContent, False, MAX_TOKENS, 0.7))
    rnd.shuffle(items)
    return items[:n]


def build_judge(n, rnd):
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT t.id, t.title_en, t.body_en, t.source_name, re.title AS re_title, "
            "       re.raw_content, re.excerpt, re.extraction_json "
            "  FROM trends t JOIN raw_entries re ON re.id = t.raw_entry_id "
            " WHERE t.created_at > now() - interval '%d days' AND t.body_en IS NOT NULL "
            " ORDER BY t.id DESC LIMIT %d" % (DAYS, n * 3)).fetchall()]
    rnd.shuffle(rows)
    items = []
    for d in rows[:n]:
        src = ((d["re_title"] or "") + " | " + (d["raw_content"] or d["excerpt"] or ""))[:dj.JUDGE_SOURCE_MAX_CHARS]
        ext = dj._extraction_block(d.get("extraction_json"))
        prompt = (f"SOURCE ({d['source_name'] or 'unknown'}):\n{src}{ext}\n\n"
                  f"DRAFT ARTICLE:\n{d['title_en']}\n\n{(d['body_en'] or '')[:2200]}\n\n"
                  'Answer with JSON only: {"publish": true/false, "signal": true/false, '
                  '"category": "ok"|"no_signal"|"thin_content"|"source_mismatch"|"broken_text", '
                  '"note": "<= 12 words"}')
        items.append(_item("judge", d["id"], dj.JUDGE_SYSTEM, prompt, dj.JudgeVerdict, True, MAX_TOKENS, 0.0))
    return items


def build_emb(rows, n, rnd):
    items = [{"stage": "emb", "id": r["id"], "input": f"{r['title']}\n{(r['excerpt'] or '')[:500]}"} for r in rows]
    rnd.shuffle(items)
    return items[:n]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    rnd = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT re.id, re.title, re.excerpt, re.raw_content, re.url, re.extraction_json, "
            "       re.classification_json, s.name AS source_name "
            "  FROM raw_entries re JOIN sources s ON s.id = re.source_id "
            " WHERE re.fetched_at > now() - interval '%d days' AND re.processed = TRUE "
            "   AND re.filtered_out = FALSE AND re.extraction_json IS NOT NULL "
            "   AND re.classification_json IS NOT NULL AND re.pub_number IS NULL "
            " ORDER BY re.id DESC LIMIT %d" % (DAYS, max(n * 2, 3000))).fetchall()]
    print(f"{len(rows)} Quell-Einträge (letzte {DAYS} Tage, mit Extraktion + Klassifikation)")
    s234, s_cls = build_8b(rows, n, rnd)
    sets = {
        "8b_stage234": s234,
        "8b_classification": s_cls,
        "8b_reclassify": build_reclassify(n, rnd),
        "gemma_stage6": build_gemma(rows, n, rnd),
        "27b_judge": build_judge(n, rnd),
        "emb": build_emb(rows, n, rnd),
    }
    for name, items in sets.items():
        p = OUT / f"{name}.jsonl"
        with p.open("w") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        chars = [len((it.get("system") or "")) + len(it.get("prompt") or it.get("input") or "") for it in items]
        chars.sort()
        print(f"  {name:14} {len(items):5} Prompts  Zeichen median {chars[len(chars)//2]:6} "
              f"p99 {chars[int(len(chars)*0.99)-1]:6} max {chars[-1]:6}")


if __name__ == "__main__":
    main()
