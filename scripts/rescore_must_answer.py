"""Pflichtpunkte eines gespeicherten Dossiers neu bewerten (2026-09-19).

Anlass: der Prüfer verlangte das Modellzitat wörtlich; seit heute gilt die
tolerante Zitatprüfung (`dossier_brief.quote_in_report`). Läuft mit
GPU-Handover auf dem 27B (ein Aufruf je Dossier) und schreibt
`result["brief_eval"]` sowie die Outcome-Zeile neu.

    .venv/bin/python scripts/rescore_must_answer.py --slug server-virtualization-scout --version 1
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import dossier_brief, dossier_utility, gpu_handover  # noqa: E402
from pipeline.db import get_connection  # noqa: E402
from scripts import corpus_research as cr  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("rescore")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--version", type=int, required=True)
    ap.add_argument("--assume-model-up", action="store_true")
    args = ap.parse_args()
    with get_connection() as c:
        row = c.execute("SELECT d.id, d.report_md, d.result, o.id AS order_id FROM dossiers d "
                        "LEFT JOIN dossier_orders o ON o.slug = d.slug AND o.dossier_version = d.version "
                        "WHERE d.slug = ? AND d.version = ?", (args.slug, args.version)).fetchone()
    if not row:
        log.error("no dossier %s v%d", args.slug, args.version)
        return 1
    row = dict(row)
    res = row["result"] if isinstance(row["result"], dict) else json.loads(row["result"] or "{}")
    must = ((res.get("brief") or {}).get("must_answer")) or []
    if not must:
        log.error("dossier has no brief / must_answer")
        return 1

    def _score():
        items = dossier_brief.must_answer_scores(row["report_md"], must, model=cr.MODEL)
        return {"items": items, "answered": sum(1 for i in items if i.get("answered")),
                "total": len(items), "rescored": True}

    if args.assume_model_up:
        ev = _score()
    else:
        with gpu_handover.model_on_llamacpp(cr.MODEL):
            ev = _score()
    res["brief_eval"] = ev
    with get_connection() as c:
        c.execute("UPDATE dossiers SET result = ? WHERE id = ?", (json.dumps(res, ensure_ascii=False), row["id"]))
    try:
        dossier_utility.record_run(args.slug, args.version, row.get("order_id"), res)
    except Exception as exc:                                        # noqa: BLE001
        log.warning("outcome not updated: %r", exc)
    for it in ev["items"]:
        log.info("%s | %s | %s", "YES" if it.get("answered") else "no ", it.get("reason") or "", it.get("item")[:80])
    log.info("must-answer: %d of %d", ev["answered"], ev["total"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
