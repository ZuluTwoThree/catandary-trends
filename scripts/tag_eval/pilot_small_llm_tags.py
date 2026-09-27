"""Pilot A (2026-09-27): could a small LLM hand out the tags the 8B used to?

Until 03.07.2026 every research and patent signal went through the LLM
classification step and got tags from Qwen3-8B; since the distill path none
do. This pilot sends the PRODUCTION classification prompt and schema
(pipeline.llm_processor.CLASSIFICATION_SYSTEM + the step_classification user
prompt, ClassificationResult via llamacpp_client.chat_structured) to a test
server and compares the answers with the tags the 8B stored back then.

    LLAMACPP_HOST=http://127.0.0.1:8094 python scripts/tag_eval/pilot_small_llm_tags.py --label qwen3.5-4b
    python scripts/tag_eval/pilot_small_llm_tags.py --compare        # after all runs

The historic tags are a reference, not the truth: they came from a slightly
different input (with extraction fields) on the same 8B. That is why the 8B
runs again under identical conditions as a baseline — the fair comparison is
small model vs 8B-today; the historic tags show how far both drift.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import db  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "tag_eval"


def sample(n: int) -> list[dict]:
    half = n // 2
    q = """
        SELECT t.id, t.title_en AS title, r.excerpt, t.tags, t.mega_trend, t.trend_signal_type
        FROM trends t JOIN raw_entries r ON r.id = t.raw_entry_id JOIN sources s ON s.id = r.source_id
        WHERE t.status = 'signal' AND t.created_at < '2026-07-03'
          AND jsonb_array_length(coalesce(t.tags, '[]'::jsonb)) > 0
          AND length(coalesce(r.excerpt, '')) > 200 AND {cond} AND mod(t.id, 53) = 0
        ORDER BY t.id LIMIT ?"""
    with db.get_connection() as c:
        c.execute("SET statement_timeout = '300s'")
        pat = c.execute(q.format(cond="(lower(s.name) LIKE 'google patents%%' OR lower(s.name) LIKE 'epo %%')"), (half,)).fetchall()
        sci = c.execute(q.format(cond="(s.source_type = 'research' OR lower(s.name) LIKE 'openalex%%')"), (n - half,)).fetchall()
    out = [dict(r) | {"tier": "patent"} for r in pat] + [dict(r) | {"tier": "science"} for r in sci]
    for r in out:
        if isinstance(r["tags"], str):
            r["tags"] = json.loads(r["tags"])
    return out


def run(label: str, n: int, workers: int) -> None:
    from pipeline import llamacpp_client
    from pipeline.llm_processor import CLASSIFICATION_SYSTEM
    from pipeline.models import ClassificationResult

    items = sample(n)
    print(f"{label}: {len(items)} items against {llamacpp_client.LLAMACPP_HOST}", flush=True)

    def one(it):
        prompt = (f"Classify this trend signal.\n\nTitle: {it['title']}\nExcerpt: {(it['excerpt'] or '')[:1000]}\n"
                  "Brand: Unknown\nProduct: Unknown\nKey Claims: None")
        t = time.time()
        try:
            res = llamacpp_client.chat_structured(model=label, prompt=prompt, schema=ClassificationResult,
                                                  system=CLASSIFICATION_SYSTEM, temperature=0.0)
        except Exception as e:  # noqa: BLE001 — a failure is a data point here
            return {"id": it["id"], "ok": False, "error": str(e)[:200], "s": time.time() - t}
        if res is None:
            return {"id": it["id"], "ok": False, "error": "None", "s": time.time() - t}
        return {"id": it["id"], "ok": True, "tags": res.tags, "mega": res.mega_trend,
                "signal_type": res.trend_signal_type, "s": round(time.time() - t, 2)}

    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(one, items))
    wall = time.time() - t0
    ok = [r for r in results if r["ok"]]
    report = {"label": label, "n": len(items), "ok": len(ok), "wall_s": round(wall, 1),
              "items_per_s": round(len(items) / wall, 2), "workers": workers,
              "median_latency_s": sorted(r["s"] for r in results)[len(results) // 2],
              "results": results, "reference": items}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"pilot_small_llm_{label}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(f"{label}: {len(ok)}/{len(items)} valid, {report['items_per_s']} items/s, "
          f"median {report['median_latency_s']} s", flush=True)


# ---------------------------------------------------------------- compare

def norm_tag(t: str) -> str:
    t = re.sub(r"[-_/]+", " ", str(t).lower()).strip()
    words = [w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w for w in t.split()]
    return " ".join(words)


def words(tags) -> set[str]:
    return {w for t in tags for w in norm_tag(t).split() if len(w) > 2}


def overlap(a, b) -> dict:
    A, B = {norm_tag(t) for t in a}, {norm_tag(t) for t in b}
    wa, wb = words(a), words(b)
    return {"tag_jaccard": len(A & B) / len(A | B) if A | B else 1.0,
            "word_jaccard": len(wa & wb) / len(wa | wb) if wa | wb else 1.0}


def compare() -> None:
    runs = {}
    for p in sorted(OUT.glob("pilot_small_llm_*.json")):
        d = json.loads(p.read_text())
        runs[d["label"]] = d
    if not runs:
        print("no runs yet")
        return
    ref = next(iter(runs.values()))["reference"]
    hist = {r["id"]: r for r in ref}
    by = {lab: {r["id"]: r for r in d["results"] if r["ok"]} for lab, d in runs.items()}
    summary = {}
    base = next((lab for lab in runs if lab.startswith("qwen3-8b")), None)
    for lab, d in runs.items():
        res = by[lab]
        vs_hist = [overlap(r["tags"], hist[i]["tags"]) for i, r in res.items()]
        row = {"valid": f"{d['ok']}/{d['n']}", "items_per_s": d["items_per_s"],
               "median_latency_s": d["median_latency_s"],
               "tags_per_item": round(sum(len(r["tags"]) for r in res.values()) / max(1, len(res)), 1),
               "vs_historic_8b_word_jaccard": round(sum(x["word_jaccard"] for x in vs_hist) / max(1, len(vs_hist)), 3),
               "vs_historic_8b_tag_jaccard": round(sum(x["tag_jaccard"] for x in vs_hist) / max(1, len(vs_hist)), 3),
               "mega_same_as_historic": round(sum(1 for i, r in res.items() if r["mega"] == hist[i]["mega_trend"]) / max(1, len(res)), 3),
               "signal_type_same_as_historic": round(sum(1 for i, r in res.items() if r["signal_type"] == hist[i]["trend_signal_type"]) / max(1, len(res)), 3)}
        if base and lab != base:
            common = [i for i in res if i in by[base]]
            ov = [overlap(res[i]["tags"], by[base][i]["tags"]) for i in common]
            row["vs_8b_today_word_jaccard"] = round(sum(x["word_jaccard"] for x in ov) / max(1, len(ov)), 3)
            row["vs_8b_today_tag_jaccard"] = round(sum(x["tag_jaccard"] for x in ov) / max(1, len(ov)), 3)
            row["mega_same_as_8b_today"] = round(sum(1 for i in common if res[i]["mega"] == by[base][i]["mega"]) / max(1, len(common)), 3)
        summary[lab] = row
    # a few side-by-side examples for reading, not for scoring
    ex = []
    for r in ref[:6] + ref[-6:]:
        ex.append({"title": r["title"][:90], "tier": r["tier"], "historic_8b": r["tags"][:8],
                   **{lab: by[lab].get(r["id"], {}).get("tags", [])[:8] for lab in runs}})
    out = {"summary": summary, "examples": ex}
    (OUT / "pilot_small_llm_compare.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--label", help="model label for this run (file name)")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--compare", action="store_true")
    args = ap.parse_args()
    if args.compare:
        compare()
    else:
        if not args.label:
            ap.error("--label is required for a run")
        run(args.label, args.n, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
