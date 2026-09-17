#!/usr/bin/env python3
"""Rücktest der Themensuche gegen bekannte Trends (Stufe 4, 2026-09-17).

Für jeden Trend in known_trends.yaml wird die Anfrage-Maschine (Stufe 1) auf
der MARKT-Ebene befragt — die Daten der Datei sind Marktdaten (Owner
2026-09-16) — und, wo `research_institutional` gesetzt ist, zusätzlich auf der
Forschungsebene. Ein Trend gilt als gefunden, wenn die Ebene antwortet
(Status ok oder thin) UND mindestens ein Kennwort des Trends in den Titeln
der Treffer vorkommt (Kennwort-Regel: ohne sie meldete der Nest-Rücktest
15 von 20 statt 9, weil ein Feld-Nest drei Trends „traf").

Zielgröße ist die Trefferquote je Ebene, nicht der Vorlauf. Der Vorlauf wird
trotzdem ausgewiesen: Monate zwischen dem ersten tragenden Monat (≥ 3 Treffer
in einem Monat) und dem Markt-Datum, positiv = die Ebene sprach vorher.
Gegenproben dürfen auf keiner Ebene antworten.

    .venv/bin/python scripts/validate_topic_search.py [--known known_trends.yaml]
        [--out data/topic_validation.json] [--tiers market,science]

Braucht den CPU-Embedder (:8091) und die Suchtabelle topic_vectors.
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml  # noqa: E402

from pipeline import topic_report as T  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("validate_topic_search")


def has_term(rows: list[dict], terms: list[str]) -> bool:
    """Kennwort-Regel: eines der Kennwörter steht wörtlich in einem Treffer-Titel."""
    if not terms:
        return True
    text = "\n".join((r.get("title_en") or "").lower() for r in rows)
    return any(t.lower().strip() in text for t in terms if t.strip())


def lead_months(first: str | None, reference: str | None) -> int | None:
    """reference − first in months; positive = the tier spoke before the date."""
    if not first or not reference:
        return None
    return (int(reference[:4]) - int(first[:4])) * 12 + (int(reference[5:7]) - int(first[5:7]))


def judge(trend: dict, tiers_out: dict) -> dict:
    """Per trend: found per tier (answered + term rule), leads."""
    out = {"key": trend["key"], "name": trend.get("name"), "uncertain": bool(trend.get("uncertain")),
           "mainstream": trend.get("mainstream"), "tiers": {}}
    for tier, d in tiers_out.items():
        answered = d["status"] != "none"
        term_ok = d.get("term_ok", False)
        ref = trend.get("research_institutional") if tier == "science" else trend.get("mainstream")
        out["tiers"][tier] = {
            "status": d["status"], "hits": d["hits"], "head": d["head"], "cut": d["cut"],
            "term_ok": term_ok, "found": answered and term_ok,
            "first_hit": d.get("first_hit"), "sustained": d.get("first_month"),
            "lead_sustained": lead_months(d.get("first_month"), ref),
            "lead_first_hit": lead_months(d.get("first_hit"), ref),
            "reference": ref,
        }
    return out


def summarise(results: list[dict], controls: list[dict]) -> dict:
    counted = [r for r in results if not r["uncertain"]]
    summary: dict = {"trends": len(results), "counted": len(counted), "tiers": {}}
    tiers = sorted({t for r in results for t in r["tiers"]})
    for t in tiers:
        rows = [r["tiers"][t] for r in counted if t in r["tiers"] and r["tiers"][t]["reference"]]
        found = [r for r in rows if r["found"]]
        leads = [r["lead_sustained"] for r in found if r["lead_sustained"] is not None]
        first = [r["lead_first_hit"] for r in found if r["lead_first_hit"] is not None]
        summary["tiers"][t] = {
            "checked": len(rows), "found": len(found),
            "hit_rate": round(len(found) / len(rows), 3) if rows else None,
            "answered_without_term": sum(1 for r in rows if r["status"] != "none" and not r["term_ok"]),
            "median_lead_sustained": statistics.median(leads) if leads else None,
            "median_lead_first_hit": statistics.median(first) if first else None,
            "before_reference": sum(1 for x in leads if x > 0),
        }
    summary["controls"] = {"checked": len(controls),
                           "answered": [c["key"] for c in controls if any(d["status"] != "none" for d in c["tiers"].values())]}
    return summary


def run_one(query: str, tiers: list[str], terms: list[str], corpus: dict, idx: dict) -> dict:
    vec = T.embed_query(query)
    results = {}
    for t in tiers:
        rows = T.search_tier(vec, t)
        a = T.assess_tier(rows, t)
        a["term_ok"] = has_term(a["hits"], terms)
        results[t] = a
    rep = T.build_report(query, tiers, results, corpus, [], [], idx, None)
    for t in tiers:
        rep["tiers"][t]["term_ok"] = results[t]["term_ok"]
    return rep["tiers"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--known", default="known_trends.yaml")
    ap.add_argument("--out", default="data/topic_validation.json")
    ap.add_argument("--tiers", default="market,science",
                    help="Ebenen, die geprüft werden (science nur mit research_institutional)")
    args = ap.parse_args()
    from pipeline.topic_vectors import index_status
    data = yaml.safe_load(open(args.known, encoding="utf-8"))
    want = [t.strip() for t in args.tiers.split(",") if t.strip()]
    corpus = T.corpus_stats()
    idx = index_status()
    t0 = time.time()
    results = []
    for tr in data.get("trends", []):
        tiers = [t for t in want if t != "science" or tr.get("research_institutional")]
        out = run_one(tr["query"], tiers, tr.get("terms", []), corpus, idx)
        j = judge(tr, out)
        results.append(j)
        m = j["tiers"].get("market", {})
        logger.info("%-24s market %-5s hits %4d term %s sustained %s lead %s",
                    tr["key"], m.get("status"), m.get("hits", 0), "y" if m.get("term_ok") else "n",
                    m.get("sustained"), m.get("lead_sustained"))
    controls = []
    for c in data.get("controls", []):
        out = run_one(c["query"], [t for t in want], [], corpus, idx)
        controls.append({"key": c["key"], "tiers": {t: {"status": d["status"], "hits": d["hits"], "head": d["head"]}
                                                     for t, d in out.items()}})
    summary = summarise(results, controls)
    summary["seconds"] = round(time.time() - t0, 1)
    summary["params"] = {"head_min": T.HEAD_MIN, "drop": T.DROP, "floor": T.FLOOR}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"summary": summary, "trends": results, "controls": controls},
                                         indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
