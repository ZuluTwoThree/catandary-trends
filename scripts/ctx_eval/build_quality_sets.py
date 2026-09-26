#!/usr/bin/env python3
"""Prompt-Sätze für Phase 4 (Qualität statt Tempo), gleiche Eingaben je Arm.

  judge_hand.jsonl   Richter-Prompts (wie draft_judge.judge_one) für Trends mit
                     HANDENTSCHEIDUNG (trends.reviewed_at gesetzt, status published/rejected),
                     ausgewogen; Label = status. Maßstab: Übereinstimmung publish ↔ published.
  rel_hand.jsonl     Relevanz-Prompts (Stufe 2) für dieselben Rohdaten; Label = status.
  gemma_ab.jsonl     70 Content-Prompts (erste 70 aus gemma_stage6.jsonl) + Quelltext-Blob für
                     pipeline.grounding.ungrounded_specifics (Methode A/B #11, Fisher-Test).
Liest nur.
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
from pipeline import draft_judge as dj  # noqa: E402
from pipeline.models import RelevanceResult  # noqa: E402
from pipeline.llamacpp_client import _json_schema  # noqa: E402

OUT = ROOT / "data" / "ctx_eval" / "prompts"
rnd = random.Random(7)


def judge_prompt(d):
    src = ((d["re_title"] or "") + " | " + (d["raw_content"] or d["excerpt"] or ""))[:dj.JUDGE_SOURCE_MAX_CHARS]
    ext = dj._extraction_block(d.get("extraction_json"))
    return (f"SOURCE ({d['source_name'] or 'unknown'}):\n{src}{ext}\n\n"
            f"DRAFT ARTICLE:\n{d['title_en']}\n\n{(d['body_en'] or '')[:2200]}\n\n"
            'Answer with JSON only: {"publish": true/false, "signal": true/false, '
            '"category": "ok"|"no_signal"|"thin_content"|"source_mismatch"|"broken_text", '
            '"note": "<= 12 words"}')


def main():
    per_class = int(sys.argv[1]) if len(sys.argv) > 1 else 75
    with get_connection() as c:
        rows = []
        for status in ("published", "rejected"):
            rows += [dict(r) for r in c.execute(
                "SELECT t.id, t.status, t.title_en, t.body_en, t.source_name, re.title AS re_title, "
                "       re.raw_content, re.excerpt, re.extraction_json "
                "  FROM trends t JOIN raw_entries re ON re.id = t.raw_entry_id "
                " WHERE t.reviewed_at IS NOT NULL AND t.status = ? AND t.body_en IS NOT NULL "
                "   AND t.created_at > now() - interval '60 days' "
                "   AND length(COALESCE(re.raw_content, re.excerpt, '')) > 300 "
                " ORDER BY random() LIMIT ?", (status, per_class)).fetchall()]
    rnd.shuffle(rows)
    with (OUT / "judge_hand.jsonl").open("w") as f, (OUT / "rel_hand.jsonl").open("w") as g:
        for d in rows:
            f.write(json.dumps({"stage": "judge", "id": d["id"], "label": d["status"],
                                "system": dj.JUDGE_SYSTEM, "prompt": judge_prompt(d),
                                "schema": _json_schema(dj.JudgeVerdict, True), "schema_name": "JudgeVerdict",
                                "max_tokens": 2048, "temperature": 0.0}, ensure_ascii=False) + "\n")
            text = d["raw_content"] if len(d["raw_content"] or "") > len(d["excerpt"] or "") else (d["excerpt"] or "")
            g.write(json.dumps({"stage": "relevance", "id": d["id"], "label": d["status"],
                                "system": lp.RELEVANCE_SYSTEM,
                                "prompt": f"""Analyze this RSS feed entry and determine if it's a relevant trend signal.
Classify the vertical based purely on the content, not on where the source comes from.
Title: {d['re_title']}
Excerpt: {text[:lp.RELEVANCE_CHARS]}""",
                                "schema": _json_schema(RelevanceResult, False), "schema_name": "RelevanceResult",
                                "max_tokens": 2048, "temperature": 0.0}, ensure_ascii=False) + "\n")
    print(f"judge_hand/rel_hand: {len(rows)} Zeilen ({sum(1 for r in rows if r['status']=='published')} published, "
          f"{sum(1 for r in rows if r['status']=='rejected')} rejected)")
    # Gemma A/B: erste 70 Content-Prompts + Quelltext für das Grounding
    ids = []
    items = [json.loads(l) for l in (OUT / "gemma_stage6.jsonl").open()][:70]
    with get_connection() as c:
        with (OUT / "gemma_ab.jsonl").open("w") as f:
            for it in items:
                r = c.execute("SELECT title, excerpt, raw_content FROM raw_entries WHERE id = ?", (it["id"],)).fetchone()
                r = dict(r)
                it["source_blob"] = f"{r['title'] or ''} {r['raw_content'] or r['excerpt'] or ''}"
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
                ids.append(it["id"])
    print(f"gemma_ab: {len(ids)} Prompts")


if __name__ == "__main__":
    main()
