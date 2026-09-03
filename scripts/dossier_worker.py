#!/usr/bin/env python3
"""Dossier-Worker: arbeitet die Auftragszettel (dossier_orders) ab.

BEWUSST KEIN CRON-JOB. Owner-Festlegung 2026-09-01 (und schon die Radar-Regel
in save_dossier): ein Dossier ist ein datiertes Dokument auf Bestellung, nie
Automatikbetrieb. Der Owner erteilt Aufträge (Frontend /trends/dossiers oder
`--order-new`), startet diesen Worker von Hand, und bekommt jeden fertigen
Lauf im Status 'review' zur finalen Durchsicht — freigegeben wird nur von
Hand. Ebenso bewusst rein lokal: Recherche, Bericht und Endkontrolle laufen
vollständig auf dem lokalen Modell; kein Cloud-Hop, Dossiers sind proprietär.

Ablauf pro Lauf (alle offenen Aufträge, älteste zuerst):

  Phase 1 — Quant-Vorstufe (ein Embedding-Handover für alle Aufträge):
      pipeline/dossier_quant.py misst die Innovationskette je Thema
      (CPC → TIR-Trajektorie → Lead-Time → Leitpatente). Fehlt GPU/Postgres,
      wird der Grund notiert und ohne Messblock weitergemacht.
  Phase 2 — Recherche (ein 27B-Handover für alle Aufträge):
      scripts/corpus_research.py führt den agentischen Lauf aus
      (Plan → Korpus → Audit → interner Sweep → Web → Bericht), das Ergebnis
      wird als nächste Version unter dem Serien-Slug in `dossiers` abgelegt,
      pipeline/dossier_check.py liefert die Endkontrolle, der Auftrag geht
      auf 'review'.

GPU-Guards wie Stage 10 des Nachtlaufs: strikter VRAM-Vorab-Check (das 27B
lässt ~1.1 GB Reserve) + Modell-Identitäts-Check gegen /v1/models — beides in
pipeline.gpu_handover.model_on_llamacpp. Kollisionsregel: diesen Worker nicht
parallel zum 04:00-Full-Cycle laufen lassen.

    python -m scripts.dossier_worker              # alle offenen Aufträge
    python -m scripts.dossier_worker --list       # Auftragslage anzeigen
    python -m scripts.dossier_worker --order 7    # genau diesen Auftrag
    python -m scripts.dossier_worker --order-new "solid-state batteries"
    python -m scripts.dossier_worker --assume-model-up   # 27B läuft schon
"""
from __future__ import annotations

import argparse
import contextlib
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import dossier_orders as orders_mod
from pipeline import gpu_handover
from pipeline.config import EMBED_MODEL
from pipeline.dossier_check import check_result
from pipeline.dossier_quant import build_quant_evidence
from scripts import corpus_research

logger = logging.getLogger("dossier_worker")

RESEARCH_MODEL = corpus_research.MODEL          # Qwen3.8-27B
# Stage-10-Regel (scheduled_cycle.sh): das 27B braucht die Karte fast leer.
JUDGE_VRAM_FREE_MIB = 1100

RUN_DEFAULTS = {"steps": 6, "sources": 24, "per_query": 6, "scope": "both",
                "web_steps": 8, "web_sources": 12, "retrieval": "fts"}


def _params(order: dict) -> dict:
    p = dict(RUN_DEFAULTS)
    p.update({k: v for k, v in (order.get("params") or {}).items()
              if k in RUN_DEFAULTS})
    return p


def process_order(order: dict, quant: dict | None) -> bool:
    """Einen als 'running' markierten Auftrag zu Ende führen → 'review'.
    True = Dossier gespeichert; False = fehlgeschlagen (Status 'failed')."""
    oid, topic = order["id"], order["topic"]
    question = (order.get("question") or "").strip() \
        or corpus_research.foresight_question(topic)
    p = _params(order)
    t0 = time.time()
    try:
        result = corpus_research.run(
            question, p["steps"], p["sources"], p["retrieval"], p["per_query"],
            p["scope"], p["web_steps"], p["web_sources"], topic=topic,
            quant=quant if quant and quant.get("ok") else None)
        version = corpus_research.save_dossier(
            order["slug"], topic, question, result["report"], result)
        check = check_result(result)
        if quant is not None and not quant.get("ok"):
            check["findings"].append(
                f"Quant-Vorstufe entfiel: {quant.get('reason')}")
            check["quant_ok"] = False
        else:
            check["quant_ok"] = bool(quant)
        check["seconds"] = round(time.time() - t0, 1)
        orders_mod.mark_review(oid, version, check)
        logger.info("order #%d → review: dossiers %s v%d (%.0fs, ok=%s, "
                    "%d Befund(e))", oid, order["slug"], version,
                    check["seconds"], check["ok"], len(check["findings"]))
        return True
    except Exception as exc:                                        # noqa: BLE001
        logger.exception("order #%d failed", oid)
        orders_mod.mark_failed(oid, f"{type(exc).__name__}: {exc}")
        return False


def run_worker(only_order: int | None = None, assume_model_up: bool = False,
               skip_quant: bool = False) -> int:
    orders_mod.ensure_schema()
    if only_order is not None:
        o = orders_mod.get_order(only_order)
        if not o:
            logger.error("order #%d existiert nicht", only_order)
            return 1
        if o["status"] == "failed":
            orders_mod.requeue(only_order)
            o = orders_mod.get_order(only_order)
        if o["status"] != "queued":
            logger.error("order #%d ist %s, nicht queued", only_order, o["status"])
            return 1
        todo = [o]
    else:
        todo = orders_mod.queued_orders()
    if not todo:
        logger.info("keine offenen Aufträge")
        return 0
    logger.info("%d Auftrag/Aufträge: %s", len(todo),
                ", ".join(f"#{o['id']} {o['topic']!r}" for o in todo))

    # --- Phase 1: Quant-Vorstufe (Embedding-Modell) -----------------------
    quants: dict[int, dict | None] = {}
    wants_quant = [o for o in todo
                   if not skip_quant and o.get("params", {}).get("quant", True)]
    if wants_quant:
        try:
            # Ein Handover für alle Messungen; die embed_query-internen
            # Handover sehen das laufende Modell und tun nichts.
            with gpu_handover.embed_on_llamacpp(EMBED_MODEL):
                for o in wants_quant:
                    logger.info("Quant-Messung für #%d %r", o["id"], o["topic"])
                    quants[o["id"]] = build_quant_evidence(o["topic"])
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("Quant-Phase nicht möglich (%s) — Dossiers laufen "
                           "ohne Messblock", exc)
            for o in wants_quant:
                quants.setdefault(o["id"], {
                    "ok": False, "reason": f"embedding backend unavailable: {exc}",
                    "sources": [], "note": None, "summary": None})

    # --- Phase 2: Recherche (27B) ----------------------------------------
    if assume_model_up:
        served = gpu_handover._served_model()
        if not served or RESEARCH_MODEL not in served:
            logger.error("--assume-model-up, aber :8090 serviert %r statt %s — "
                         "Abbruch (Identitäts-Guard)", served, RESEARCH_MODEL)
            return 1
        ctx = contextlib.nullcontext()
    else:
        ctx = gpu_handover.model_on_llamacpp(
            RESEARCH_MODEL, vram_free_below_mib=JUDGE_VRAM_FREE_MIB)

    done = failed = skipped = 0
    try:
        with ctx:
            for o in todo:
                if not orders_mod.mark_running(o["id"]):
                    logger.warning("order #%d nicht mehr queued — übersprungen",
                                   o["id"])
                    skipped += 1
                    continue
                if process_order(o, quants.get(o["id"])):
                    done += 1
                else:
                    failed += 1
    except RuntimeError as exc:
        # GPU-Guard hat abgelehnt (VRAM/Identität/Preflight): klare Diagnose,
        # alle unberührten Aufträge bleiben queued.
        logger.error("GPU-Handover verweigert: %s", exc)
        return 1
    logger.info("fertig: %d review, %d failed, %d übersprungen",
                done, failed, skipped)
    return 0 if failed == 0 else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--list", action="store_true", help="Auftragslage anzeigen")
    ap.add_argument("--order", type=int, help="nur diesen Auftrag abarbeiten "
                                              "(failed wird erneut eingereiht)")
    ap.add_argument("--order-new", metavar="TOPIC",
                    help="neuen Auftrag anlegen (und mit --run sofort abarbeiten)")
    ap.add_argument("--slug", help="Serien-Slug für --order-new (Default: aus TOPIC)")
    ap.add_argument("--question", help="eigene Frage für --order-new "
                                       "(Default: Foresight-Standardfrage)")
    ap.add_argument("--run", action="store_true",
                    help="mit --order-new: den neuen Auftrag sofort abarbeiten")
    ap.add_argument("--assume-model-up", action="store_true",
                    help=f"kein GPU-Handover; verlangt, dass :8090 bereits "
                         f"{RESEARCH_MODEL} serviert")
    ap.add_argument("--skip-quant", action="store_true",
                    help="Quant-Vorstufe für diesen Lauf auslassen")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s")

    if args.list:
        orders_mod.ensure_schema()
        rows = orders_mod.list_orders(limit=40)
        if not rows:
            print("keine Aufträge")
            return 0
        for o in rows:
            extra = ""
            if o["status"] == "review":
                c = o.get("check") or {}
                extra = (f"  v{o.get('dossier_version')} "
                         f"{'✓ Endkontrolle sauber' if c.get('ok') else '⚠ ' + str(len(c.get('findings') or [])) + ' Befund(e)'}")
            elif o["status"] == "failed":
                extra = f"  {o.get('error') or ''}"
            print(f"#{o['id']:>4} [{o['status']:>9}] {o['slug']} — "
                  f"{o['topic']}{extra}")
        return 0

    new_id = None
    if args.order_new:
        orders_mod.ensure_schema()
        new_id = orders_mod.create_order(args.order_new, slug=args.slug,
                                         question=args.question)
        print(f"Auftrag #{new_id} angelegt ({args.order_new!r})")
        if not args.run:
            return 0

    only = args.order if args.order is not None else (new_id if args.run else None)
    return run_worker(only_order=only, assume_model_up=args.assume_model_up,
                      skip_quant=args.skip_quant)


if __name__ == "__main__":
    raise SystemExit(main())
