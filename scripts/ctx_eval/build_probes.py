#!/usr/bin/env python3
"""Maximal-Längen-Sonden (Phase 3): eine Anfrage in der längsten erlaubten Länge je Modell.
Quelle: der längste CJK-Volltext in der DB (12.000 Zeichen ≈ 8.300 Qwen-Tokens statt ~4.000 bei
Latein) — der schlimmste reale Fall für Extraktion (8B), Richter (27B) und Content (Gemma, hier
mit 4.000-Zeichen-Kappe wie in Produktion, plus vollem Extraktionsblock)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from pipeline.db import get_connection
from pipeline import llm_processor as lp, draft_judge as dj
from pipeline.models import ExtractionResult, ClassificationResult, GeneratedContent
from pipeline.llamacpp_client import _json_schema
OUT = ROOT / "data/ctx_eval/prompts"
with get_connection() as c:
    r = dict(c.execute(r"SELECT re.id, re.title, re.raw_content, re.url, s.name AS source_name FROM raw_entries re JOIN sources s ON s.id=re.source_id WHERE re.raw_content IS NOT NULL AND length(re.raw_content)>=12000 AND re.raw_content ~ '[一-鿿぀-ヿ]{20}' ORDER BY length(regexp_replace(re.raw_content, '[^一-鿿぀-ヿ]', '', 'g')) DESC LIMIT 1").fetchone())
text = r["raw_content"]
ext = ExtractionResult(brand_name="Probe", product_name="Probe", key_claims=[text[i:i+200] for i in range(0, 1600, 200)],
                       key_figures=[f"{i} 件" for i in range(10)], dates=["2026-09-25"] * 5, quotes=[text[:300]] * 3, geography=["東京", "上海"])
cls = ClassificationResult(verticals=["TECH"], pestel=["T"], tags=["probe"], trend_signal_type="market_shift", regions=["APAC"], mega_trend=None)
probes = {
 "probe_8b_extraction": dict(stage="extraction", system=lp.EXTRACTION_SYSTEM,
     prompt=f"Extract structured information from this text.\nTitle: {r['title']}\nText: {text[:lp.EXTRACT_CHARS]}",
     schema=_json_schema(ExtractionResult, True), schema_name="ExtractionResult", max_tokens=2048, temperature=0.0),
 "probe_27b_judge": dict(stage="judge", system=dj.JUDGE_SYSTEM,
     prompt=(f"SOURCE (probe):\n{(r['title'] + ' | ' + text)[:dj.JUDGE_SOURCE_MAX_CHARS]}"
             f"\n\nSTRUCTURED EXTRACTION (from the source):\n{json.dumps(ext.model_dump(), ensure_ascii=False)[:dj.JUDGE_EXTRACTION_MAX_CHARS]}"
             f"\n\nDRAFT ARTICLE:\nProbe\n\n{text[:2200]}\n\nAnswer with JSON only: {{\"publish\": true/false, \"signal\": true/false, \"category\": \"ok\", \"note\": \"x\"}}"),
     schema=_json_schema(dj.JudgeVerdict, True), schema_name="JudgeVerdict", max_tokens=2048, temperature=0.0),
}
p, _ = lp.build_content_prompt(r["title"], text, ext, cls, r["url"], r["source_name"])
probes["probe_gemma_content"] = dict(stage="content", system=lp.CONTENT_EN_SYSTEM_V2, prompt=p,
     schema=_json_schema(GeneratedContent, False), schema_name="GeneratedContent", max_tokens=2048, temperature=0.7)
for name, it in probes.items():
    it["id"] = r["id"]
    with (OUT / f"{name}.jsonl").open("w") as f:
        for _ in range(24):  # 24 Kopien, damit ein Server mit N Slots unter Volllast gemessen werden kann
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(name, "Zeichen system+prompt:", len(it["system"]) + len(it["prompt"]))
