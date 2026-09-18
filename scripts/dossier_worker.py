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

  Phase 0 — Intake (Stufe 1, 2026-09-19; pipeline/dossier_brief.py):
      deterministischer Fragecheck (kein Fragesatz → 'failed' mit Grund, kein
      Modellaufruf), dann auf dem 27B: strukturierter Auftrag (Fragetyp,
      Entscheidung, Leser, Pflichtpunkte, Artefakt-Weiche), Feldprofil, Plan —
      alles auf den Zettel. Mit Checkpoint (params {"checkpoint": true} —
      Desk-Default; CLI --order-new und Newsletter-Deep-Dive: aus;
      DOSSIER_CHECKPOINT=0 erzwingt aus) hält der Auftrag in
      'awaiting_confirmation', bis der Owner im Desk bestätigt oder in einem
      Satz korrigiert (--confirm N [--note …] von hier). Der nächste Worker-
      Start rechnet dann mit den gespeicherten Artefakten weiter — nach einer
      Korrektur mit neuer Frage und neuem Intake, ohne zweiten Halt.

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
    python -m scripts.dossier_worker --confirm 7 [--note "…"]   # Checkpoint bestätigen
"""
from __future__ import annotations

import argparse
import contextlib
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import dossier_brief
from pipeline import dossier_orders as orders_mod
from pipeline import gpu_handover
from pipeline.config import EMBED_MODEL
from pipeline.dossier_check import check_result
from pipeline.dossier_corpus_stats import build_corpus_evidence
from pipeline.dossier_quant import build_quant_evidence
from scripts import corpus_research

logger = logging.getLogger("dossier_worker")

RESEARCH_MODEL = corpus_research.MODEL          # Qwen3.8-27B
# Stage-10-Regel (scheduled_cycle.sh): das 27B braucht die Karte fast leer.
JUDGE_VRAM_FREE_MIB = 1100

RUN_DEFAULTS = {"steps": 6, "sources": 24, "per_query": 6, "scope": "both",
                "web_steps": 14, "web_sources": 32,
                # Vektorsuche, sobald ein EIGENER Embedding-Endpunkt konfiguriert
                # ist (#97, 2026-09-09). Ohne ihn bleibt es bei Volltext: waehrend
                # der Lauf laeuft, haelt :8090 den 27B, ein Embedding-Request
                # dorthin kaeme vom Chatmodell. Faellt der Endpunkt im Lauf aus,
                # schaltet corpus_research selbst auf Volltext zurueck und
                # vermerkt es in den Notizen.
                "retrieval": "vector" if os.getenv("RESEARCH_EMBED_HOST") else "fts",
                # Messkette (M1/M2/M4/M6, 2026-09-06). Default an; ein
                # Auftrag mit params {"measure": false} oder DOSSIER_MEASURE=0
                # reproduziert den Pfad davor.
                "measure": os.getenv("DOSSIER_MEASURE", "1")
                          not in ("0", "false", "no"),
                # DR-Vorlauf (2026-09-07; Default AN seit 2026-09-13): Primaer-
                # quellen zuerst lesen, Faktenzettel und Kalender-Kandidaten VOR
                # dem Schreiben, Sampling nach Modellkarte. In der LFP-Serie war
                # das der einzige Hebel, der die Faktenquote verlaesslich ueber
                # die Untergrenze hob (v8: 2,90 gegen 1,0-2,4 ohne). Kostet
                # ~12 min je Dossier. DOSSIER_DR=0 oder params {"dr": false}
                # reproduzieren den Pfad davor.
                "dr": os.getenv("DOSSIER_DR", "1")
                      not in ("0", "false", "no", ""),
                # CPC-Anker fuer die Patentmessung (2026-09-13): die Kaskade
                # findet fuer eine Themenformulierung wie "LFP cells for storage
                # and EVs" keine Klasse mit Trefferdichte; der Owner kennt sie
                # (H01M4/5825). None = raten wie bisher.
                "cpc": None,
                # Landschafts-Modus (2026-09-13): breites Feld → Teilfeld-Karte,
                # ein Suchschritt je Teilfeld, Landkarten-Frage statt der
                # Kommerzialisierungs-Frage EINER Technologie.
                "mode": "technology",
                # Owner-Checkpoint (Stufe 1, 2026-09-19): nach Auftrag/Profil/Plan
                # anhalten. Default AN (Desk-Aufträge, auch ältere Zettel ohne den
                # Parameter); --order-new und der Newsletter-Deep-Dive schreiben
                # false; DOSSIER_CHECKPOINT=0 erzwingt aus (checkpoint_enabled).
                "checkpoint": True}


def checkpoint_enabled(p: dict) -> bool:
    if os.getenv("DOSSIER_CHECKPOINT", "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool(p.get("checkpoint", True))


def _params(order: dict) -> dict:
    p = dict(RUN_DEFAULTS)
    p.update({k: v for k, v in (order.get("params") or {}).items()
              if k in RUN_DEFAULTS})
    return p


def default_question(order: dict, p: dict) -> str:
    topic = order["topic"]
    return (corpus_research.landscape_question(topic) if p["mode"] == "landscape"
            else corpus_research.foresight_question(topic))


def intake(order: dict, p: dict, question: str) -> tuple[dict, dict | None, dict]:
    """Phase 0 auf dem 27B: Auftrag → Feldprofil → Plan (drei Aufrufe; das
    Profil nur, wenn der Lauf es braucht — measure + Web). Der Auftrag ist der
    einzige zusätzliche Modellaufruf gegenüber vorher: Profil und Plan
    rechnete run() bisher selbst und bekommt sie jetzt herein."""
    topic = order["topic"]
    brief = dossier_brief.build_brief(topic, question, p).model_dump()
    profile = None
    if p["measure"] and p["web_steps"] > 0:
        prof = corpus_research.topic_profile(topic, question, [])
        profile = prof.model_dump() if prof is not None else None
    plan_obj, landscape, _ = corpus_research.build_plan(
        question, p["steps"], topic, p["scope"], p["mode"])
    plan = corpus_research.plan_record(plan_obj, landscape)
    logger.info("intake #%d: type=%s artefact=%s must_answer=%d profile=%s plan=%d step(s)",
                order["id"], brief["question_type"], brief["artefact"],
                len(brief["must_answer"]), "yes" if profile else "no", len(plan["steps"]))
    return brief, profile, plan


def process_order(order: dict, quant: dict | None,
                  corpus_stats: dict | None = None) -> str:
    """Einen als 'running' markierten Auftrag weiterführen. Rückgabe:
    'review' (Dossier gespeichert), 'awaiting' (Checkpoint: Auftrag wartet auf
    den Owner), 'failed' (Status 'failed', auch bei abgewiesenem Intake)."""
    oid, topic = order["id"], order["topic"]
    p = _params(order)
    # Phase 0a — deterministisch, vor jedem Modellaufruf: das Fragefeld muss
    # eine Frage sein (datacenter v1: eine Leserbeschreibung wurde Thema).
    ok, reason = dossier_brief.deterministic_question_check(order.get("question"))
    if not ok:
        logger.warning("order #%d intake rejected: %s", oid, reason)
        orders_mod.reject_intake(oid, reason)
        return "failed"
    question = orders_mod.effective_question(order, default_question(order, p))
    t0 = time.time()
    try:
        # Phase 0b — Intake. Gespeicherte Artefakte gelten nur nach einer
        # Bestätigung OHNE Korrektur; eine Korrektur ändert die Frage, also
        # werden Auftrag, Profil und Plan neu gerechnet (ohne zweiten Halt).
        confirmed = bool(order.get("confirmed_at"))
        corrected = bool((order.get("owner_note") or "").strip())
        brief, profile, plan = order.get("brief"), order.get("profile"), order.get("plan")
        if not (confirmed and not corrected and brief and plan):
            brief, profile, plan = intake(order, p, question)
            if not brief.get("is_question", True):
                logger.warning("order #%d intake rejected by the brief: %s",
                               oid, brief.get("rejection_reason"))
                orders_mod.reject_intake(oid, brief.get("rejection_reason") or "no question")
                return "failed"
            if checkpoint_enabled(p) and not confirmed:
                orders_mod.mark_awaiting(oid, brief, profile, plan)
                logger.info("order #%d → awaiting_confirmation (checkpoint: brief, "
                            "profile, plan on the slip — confirm in the desk or with "
                            "--confirm %d)", oid, oid)
                return "awaiting"
            orders_mod.store_intake(oid, brief, profile, plan)
        else:
            logger.info("order #%d: confirmed — using the stored brief/profile/plan", oid)
        result = corpus_research.run(
            question, p["steps"], p["sources"], p["retrieval"], p["per_query"],
            p["scope"], p["web_steps"], p["web_sources"], topic=topic,
            # Auch eine GESCHEITERTE Messung wird durchgereicht: ihr Anhang
            # macht den Ausfall im Dossier sichtbar (vorher verschwand er).
            quant=quant if (quant and (quant.get("ok") or p["measure"]))
                  else None,
            measure=p["measure"], corpus_stats=corpus_stats, dr=p["dr"],
            mode=p["mode"], brief=brief, profile=profile, plan=plan)
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
        # Stufe 0 (Messlatte): Nutzen U + dritte Ampel je Lauf — Replay über
        # das, was gerade gespeichert wurde. Darf den Lauf nie scheitern lassen.
        try:
            from pipeline import dossier_utility
            preset = (brief or {}).get("question_type")
            if preset not in dossier_utility.WEIGHT_PRESETS:
                preset = dossier_utility.DEFAULT_PRESET
            ev = dossier_utility.record_run(order["slug"], version, oid,
                                            result, check, preset=preset)
            if ev:
                logger.info("order #%d outcome: U=%.3f delivery_ready=%s reader=%s",
                            oid, ev["utility"], ev["delivery_ready"],
                            ev["reader_answers"])
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("order #%d: dossier_run_outcomes nicht geschrieben (%s: %s)",
                           oid, type(exc).__name__, exc)
        return "review"
    except Exception as exc:                                        # noqa: BLE001
        logger.exception("order #%d failed", oid)
        orders_mod.mark_failed(oid, f"{type(exc).__name__}: {exc}")
        return "failed"


def _llama_unit_active() -> bool:
    try:
        r = gpu_handover._run(["systemctl", "--user", "is-active",
                               gpu_handover.LLAMA_UNIT], timeout=15)
        return r.stdout.strip() == "active"
    except Exception:                                               # noqa: BLE001
        return False


def _restore_resting_server(was_active: bool) -> None:
    """Ruhezustand wiederherstellen. Die Handover stoppen llama-server am Ende
    und hängen start-active.sh auf das Ruhemodell (208K-8B) zurück — lief der
    Server vor dem Worker, wird er hier wieder gestartet, damit die Karte
    nachher so dasteht wie vorher (Nachtlauf/Morgenroutinen erwarten das)."""
    if not was_active:
        return
    logger.info("Ruhezustand: llama-server wieder starten (start-active.sh → %s)",
                gpu_handover._current_symlink_target())
    try:
        gpu_handover._run(["systemctl", "--user", "start",
                           gpu_handover.LLAMA_UNIT], timeout=60)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("llama-server konnte nicht neu gestartet werden: %s", exc)


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
        if o["status"] == "awaiting_confirmation":
            logger.error("order #%d wartet am Checkpoint auf dich — im Desk bestätigen "
                         "oder: --confirm %d [--note \"…\"]", only_order, only_order)
            return 1
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
    # Nur wenn wir selbst umhängen: den Ausgangszustand merken, um ihn am
    # Ende wiederherzustellen (bei --assume-model-up bleibt alles wie es ist).
    was_active = False if assume_model_up else _llama_unit_active()
    try:
        return _run_phases(todo, assume_model_up, skip_quant)
    finally:
        _restore_resting_server(was_active)


def _run_phases(todo: list[dict], assume_model_up: bool, skip_quant: bool) -> int:
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
                    quants[o["id"]] = build_quant_evidence(
                        o["topic"], measure=_params(o)["measure"],
                        cpc=_params(o)["cpc"])
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("Quant-Phase nicht möglich (%s) — Dossiers laufen "
                           "ohne Messblock", exc)
            for o in wants_quant:
                quants.setdefault(o["id"], {
                    "ok": False, "reason": f"embedding backend unavailable: {exc}",
                    "sources": [], "note": None, "summary": None})

    # --- Phase 1b: Korpus-Zaehlung (CPU/SQL, kein Modell) ------------------
    tallies: dict[int, dict | None] = {}
    for o in todo:
        if not _params(o)["measure"]:
            continue
        try:
            tallies[o["id"]] = build_corpus_evidence(o["topic"])
        except Exception as exc:                                    # noqa: BLE001
            logger.warning("Korpus-Zaehlung fuer #%d nicht moeglich: %s",
                           o["id"], exc)

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

    done = failed = skipped = awaiting = 0
    try:
        with ctx:
            for o in todo:
                if not orders_mod.mark_running(o["id"]):
                    logger.warning("order #%d nicht mehr queued — übersprungen",
                                   o["id"])
                    skipped += 1
                    continue
                outcome = process_order(o, quants.get(o["id"]), tallies.get(o["id"]))
                if outcome == "review":
                    done += 1
                elif outcome == "awaiting":
                    awaiting += 1
                else:
                    failed += 1
    except RuntimeError as exc:
        # GPU-Guard hat abgelehnt (VRAM/Identität/Preflight): klare Diagnose,
        # alle unberührten Aufträge bleiben queued.
        logger.error("GPU-Handover verweigert: %s", exc)
        return 1
    logger.info("fertig: %d review, %d awaiting_confirmation, %d failed, %d übersprungen",
                done, awaiting, failed, skipped)
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
    ap.add_argument("--cpc", help="CPC-Anker für die Patentmessung bei --order-new "
                                  "(z. B. H01M4/5825); ohne: Kaskade rät")
    ap.add_argument("--mode", choices=("technology", "landscape"), default=None,
                    help="--order-new: 'landscape' = breites Feld in Teilfeldern (Karte + ein "
                         "Suchschritt je Teilfeld); Default technology")
    ap.add_argument("--no-dr", action="store_true",
                    help="--order-new ohne DR-Vorlauf (Faktenzettel/Kalender-Kandidaten)")
    ap.add_argument("--run", action="store_true",
                    help="mit --order-new: den neuen Auftrag sofort abarbeiten")
    ap.add_argument("--checkpoint", action="store_true",
                    help="--order-new: nach Auftrag/Profil/Plan auf Bestätigung warten "
                         "(Desk-Default; CLI-Aufträge laufen sonst durch)")
    ap.add_argument("--confirm", type=int, metavar="N",
                    help="Auftrag N am Checkpoint bestätigen (→ queued; mit --run sofort weiter)")
    ap.add_argument("--note", help="--confirm: Korrektur in einem Satz (wird als "
                                   "'Owner correction: …' an die Frage gehängt)")
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
                rd = c.get("reader_ok")
                extra = (f"  v{o.get('dossier_version')} "
                         f"{'✓ Endkontrolle sauber' if c.get('ok') else '⚠ ' + str(len(c.get('findings') or [])) + ' Befund(e)'}"
                         + ("" if rd is None else (" · Leser ✓" if rd else " · Leser ✗")))
            elif o["status"] == "failed":
                extra = f"  {o.get('error') or ''}"
            elif o["status"] == "awaiting_confirmation":
                b = o.get("brief") or {}
                extra = (f"  ⏸ Checkpoint: {b.get('question_type', '?')} / "
                         f"{b.get('artefact', '?')} · {len(b.get('must_answer') or [])} "
                         f"Pflichtpunkte — --confirm {o['id']} [--note …]")
            print(f"#{o['id']:>4} [{o['status']:>9}] {o['slug']} — "
                  f"{o['topic']}{extra}")
        return 0

    if args.confirm is not None:
        orders_mod.ensure_schema()
        if not orders_mod.confirm(args.confirm, args.note):
            o = orders_mod.get_order(args.confirm)
            print(f"Auftrag #{args.confirm} ist {'unbekannt' if not o else o['status']}, "
                  f"nicht awaiting_confirmation")
            return 1
        print(f"Auftrag #{args.confirm} bestätigt"
              + (f" mit Korrektur: {args.note!r}" if args.note else "") + " → queued")
        if not args.run:
            return 0
        return run_worker(only_order=args.confirm, assume_model_up=args.assume_model_up,
                          skip_quant=args.skip_quant)

    new_id = None
    if args.order_new:
        orders_mod.ensure_schema()
        # CLI-Aufträge laufen ohne Checkpoint durch (Owner sitzt am Terminal);
        # --checkpoint schaltet ihn ein wie im Desk.
        params = {"checkpoint": bool(args.checkpoint)}
        if args.cpc:
            params["cpc"] = args.cpc.replace(" ", "").upper()
        if args.no_dr:
            params["dr"] = False
        if args.mode:
            params["mode"] = args.mode
        new_id = orders_mod.create_order(args.order_new, slug=args.slug,
                                         question=args.question, params=params)
        print(f"Auftrag #{new_id} angelegt ({args.order_new!r})")
        if not args.run:
            return 0

    only = args.order if args.order is not None else (new_id if args.run else None)
    return run_worker(only_order=only, assume_model_up=args.assume_model_up,
                      skip_quant=args.skip_quant)


if __name__ == "__main__":
    try:
        from pipeline.ops_events import record  # Laufprotokoll fuer /trends/ops (#104)
    except ImportError:  # Paket nicht im Pfad (Cron ohne cd, 12.09.: Backup fiel aus) — Protokoll ist optional, der Job nicht
        from contextlib import nullcontext as record
    with record("dossier_worker"):
        raise SystemExit(main())
