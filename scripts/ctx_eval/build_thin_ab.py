#!/usr/bin/env python3
"""A/B-Satz für die Frage: verursacht der kleinere Kontext kurze Bodies?

Der Testlauf vom 25.09. hielt 4 von 54 Artikeln am Guard `too_short` zurück (< 60 Wörter).
Verdacht: nicht der Kontext, sondern die Kohorte — ihr Quelltext-Median lag bei 383 Zeichen
gegen 3.314 im Nachtlauf. Dieses Skript baut die Produktions-Content-Prompts für die DÜNNSTEN
Einträge des Testlaufs; `bench_parallel.py` schickt sie an zwei Testserver (16K und 262144),
`thin_ab_eval.py` vergleicht die Wortzahlen. Gleiche Prompts, gleiche Temperatur, nur -c ändert sich.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline.db import get_connection  # noqa: E402
from pipeline import llm_processor as lp  # noqa: E402
from pipeline.models import ClassificationResult, ExtractionResult, GeneratedContent  # noqa: E402
from pipeline.llamacpp_client import _json_schema  # noqa: E402

OUT = ROOT / "data" / "ctx_eval" / "prompts" / "thin_ab.jsonl"


def main() -> None:
    max_chars = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    with get_connection() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT re.id, re.title, re.excerpt, re.raw_content, re.url, re.extraction_json, "
            "       re.classification_json, s.name AS source_name "
            "  FROM raw_entries re JOIN sources s ON s.id = re.source_id "
            " WHERE re.fetched_at > now() - interval '60 minutes' "
            "   AND re.extraction_json IS NOT NULL AND re.classification_json IS NOT NULL "
            "   AND length(COALESCE(re.raw_content, re.excerpt, '')) < ? "
            " ORDER BY length(COALESCE(re.raw_content, re.excerpt, ''))", (max_chars,)).fetchall()]
    n = 0
    with OUT.open("w") as f:
        for r in rows:
            try:
                e = ExtractionResult.model_validate_json(r["extraction_json"])
                k = ClassificationResult.model_validate_json(r["classification_json"])
            except Exception:  # noqa: BLE001
                continue
            text = r["raw_content"] if len(r["raw_content"] or "") > len(r["excerpt"] or "") else (r["excerpt"] or "")
            prompt, src = lp.build_content_prompt(r["title"], text, e, k, r["url"],
                                                  r["source_name"] or "Unknown")
            f.write(json.dumps({"stage": "content", "id": r["id"], "system": lp.CONTENT_EN_SYSTEM_V2,
                                "prompt": prompt, "schema": _json_schema(GeneratedContent, False),
                                "schema_name": "GeneratedContent", "max_tokens": 2048,
                                "temperature": 0.7, "source_chars": len(text),
                                "source_blob": f"{r['title'] or ''} {text}"}, ensure_ascii=False) + "\n")
            n += 1
    print(f"{n} Prompts (< {max_chars} Zeichen Quelltext) → {OUT}")


if __name__ == "__main__":
    main()
