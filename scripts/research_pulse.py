#!/usr/bin/env python3
"""Research Pulse (#73 Teil 1): Wochen-Synthese je Mega-Signal-Theme.

Rechnet für eine ISO-Woche je Theme Frische-Volumen (Woche vs. Median der vier
Vorwochen), Embedding-Cluster (KMeans, fester Seed) mit Top-Papers und — sofern
nicht --no-llm — einen 100–150-Wörter-Absatz auf Gemma-4-26B (T=0.2, fester
Seed). Ergebnis: eine versionierte Zeile je Theme in `research_pulse`
(pipeline/research_pulse.py, docs/research_pulse.md).

Ablauf: erst alle Themes CPU/SQL (Stats + Cluster, Sekunden), dann EIN GPU-
Handover (pipeline.gpu_handover.content_gen_on_llamacpp) für alle Texte, dann
speichern. Der Ruhezustand von :8090 wird wie beim Dossier-Worker wieder-
hergestellt (lief llama-server vorher, wird er nach dem Handover neu gestartet
— start-active.sh zeigt dann wieder aufs 208K-8B).

    python scripts/research_pulse.py                      # Vorwoche, alle 28 Themes
    python scripts/research_pulse.py --week 2026-W35 --no-llm
    python scripts/research_pulse.py --themes quantum_information_science,orbital_economy
    python scripts/research_pulse.py --limit 3            # die 3 volumenstärksten Themes

Der Frontend-Knopf „Recompute" (/trends/foresight/research/pulse/<theme>) ruft
genau dieses Skript mit --themes <key> [--week …] auf (lib/researchPulseWorker.ts).
Kollisionsregel wie Dossier-Worker: nicht parallel zum 04:00-Full-Cycle.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from pipeline import gpu_handover  # noqa: E402
from pipeline import research_pulse as rp  # noqa: E402
from pipeline.config import DATA_DIR, load_mega_trends  # noqa: E402
from pipeline.db import get_connection  # noqa: E402

logger = logging.getLogger("research_pulse")
LAST_PATH = DATA_DIR / "research_pulse_last.json"


def _llama_unit_active() -> bool:
    try:
        r = gpu_handover._run(["systemctl", "--user", "is-active",
                               gpu_handover.LLAMA_UNIT], timeout=15)
        return r.stdout.strip() == "active"
    except Exception:                                               # noqa: BLE001
        return False


def _restore_resting_server(was_active: bool) -> None:
    """Handover stoppt llama-server und hängt start-active.sh aufs Ruhemodell
    zurück — lief der Server vorher, hier wieder starten (Dossier-Worker-Regel)."""
    if not was_active:
        return
    logger.info("Ruhezustand: llama-server wieder starten (start-active.sh → %s)",
                gpu_handover._current_symlink_target())
    try:
        gpu_handover._run(["systemctl", "--user", "start",
                           gpu_handover.LLAMA_UNIT], timeout=60)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("llama-server konnte nicht neu gestartet werden: %s", exc)


def select_themes(all_themes: list[dict], keys: list[str] | None) -> list[dict]:
    if not keys:
        return all_themes
    by_key = {t["key"]: t for t in all_themes}
    unknown = [k for k in keys if k not in by_key]
    if unknown:
        raise SystemExit(f"unknown theme key(s): {', '.join(unknown)}")
    return [by_key[k] for k in keys]


def run(year: int, week: int, themes: list[dict], use_llm: bool,
        limit: int | None) -> dict:
    t_all = time.time()
    summary = {"year": year, "week": week, "started_at": datetime.now().isoformat(timespec="seconds"),
               "themes": 0, "with_text": 0, "skipped_text": 0, "errors": [],
               "model": None, "llm": use_llm, "status": "running"}

    # Phase 1 — Messblock + Cluster (CPU/SQL)
    results: list[dict] = []
    with get_connection() as conn:
        rp.ensure_schema(conn)
        for th in themes:
            t0 = time.time()
            try:
                res = rp.compute_theme(conn, th, year, week)
            except Exception as exc:                                 # noqa: BLE001
                logger.exception("compute failed for %s", th["key"])
                summary["errors"].append(f"{th['key']}: compute {type(exc).__name__}: {exc}")
                continue
            res["seconds"] = time.time() - t0
            res["theme_info"] = th
            results.append(res)
            logger.info("%-52s week_n=%5d ratio=%s k=%d clusters=%d (%.1fs)",
                        th["key"], res["stats"]["week_n"], res["stats"]["ratio"],
                        res["stats"]["k"], len(res["clusters"]), res["seconds"])
    if limit is not None:
        results.sort(key=lambda r: -r["stats"]["week_n"])
        results = results[:limit]

    # Phase 2 — Texte (ein Handover für alle)
    texts: dict[str, tuple[str | None, str | None]] = {}
    model_id: str | None = None
    if use_llm:
        todo = [r for r in results if r["stats"]["week_n"] >= rp.MIN_PAPERS_FOR_TEXT]
        for r in results:
            if r not in todo:
                texts[r["theme"]] = (None, f"no text: {r['stats']['week_n']} papers "
                                           f"(< {rp.MIN_PAPERS_FOR_TEXT})")
        if todo:
            was_active = _llama_unit_active()
            try:
                with gpu_handover.content_gen_on_llamacpp(rp.PULSE_MODEL):
                    # /v1/models meldet den Pfad (./models/…gguf) — Basename speichern
                    model_id = Path(gpu_handover._served_model() or rp.PULSE_MODEL).name
                    summary["model"] = model_id
                    for r in todo:
                        t0 = time.time()
                        try:
                            text, note = rp.generate_text(r["theme_info"], r["stats"], r["clusters"])
                        except Exception as exc:                     # noqa: BLE001
                            logger.exception("text failed for %s", r["theme"])
                            text, note = None, f"llm {type(exc).__name__}: {exc}"
                            summary["errors"].append(f"{r['theme']}: {note}")
                        texts[r["theme"]] = (text, note)
                        r["seconds"] += time.time() - t0
                        logger.info("%-52s text=%s words (%.0fs)%s", r["theme"],
                                    rp.word_count(text or ""), time.time() - t0,
                                    f" — {note}" if note else "")
            except RuntimeError as exc:
                logger.error("GPU-Handover verweigert: %s", exc)
                summary["errors"].append(f"handover: {exc}")
                for r in todo:
                    texts.setdefault(r["theme"], (None, f"handover refused: {exc}"))
            finally:
                _restore_resting_server(was_active)
    else:
        for r in results:
            texts[r["theme"]] = (None, "no-llm run")

    # Phase 3 — speichern
    with get_connection() as conn:
        for r in results:
            text, note = texts.get(r["theme"], (None, None))
            rid = rp.save_pulse(conn, r, text, model_id if text else None, r["seconds"], note)
            summary["themes"] += 1
            if text:
                summary["with_text"] += 1
            else:
                summary["skipped_text"] += 1
            logger.debug("saved research_pulse id=%d for %s", rid, r["theme"])

    summary["seconds"] = round(time.time() - t_all, 1)
    summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
    summary["status"] = "ok" if not summary["errors"] else "errors"
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--week", help="ISO-Woche, z. B. 2026-W35 (Default: letzte abgeschlossene Woche)")
    ap.add_argument("--themes", help="Komma-Liste von Theme-Keys (Default: alle aus mega_trends.yaml)")
    ap.add_argument("--no-llm", action="store_true", help="nur Stats + Cluster, kein Gemma-Text")
    ap.add_argument("--limit", type=int, help="höchstens N Themes (die volumenstärksten) verarbeiten")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s: %(message)s")

    year, week = rp.parse_week(args.week) if args.week else rp.default_week(date.today())
    keys = [k.strip() for k in args.themes.split(",") if k.strip()] if args.themes else None
    themes = select_themes(load_mega_trends(), keys)
    start, end = rp.iso_week_bounds(year, week)
    logger.info("Research Pulse %d-W%02d (%s – %s): %d theme(s), llm=%s, model=%s",
                year, week, start, end, len(themes), not args.no_llm, rp.PULSE_MODEL)

    summary = run(year, week, themes, use_llm=not args.no_llm, limit=args.limit)
    try:
        LAST_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    except OSError as exc:
        logger.warning("could not write %s: %s", LAST_PATH, exc)
    logger.info("done: %d themes, %d with text, %d without, %d error(s), %.0fs",
                summary["themes"], summary["with_text"], summary["skipped_text"],
                len(summary["errors"]), summary["seconds"])
    return 0 if not summary["errors"] else 2


if __name__ == "__main__":
    try:
        from pipeline.ops_events import record  # Laufprotokoll fuer /trends/ops (#104)
    except ImportError:  # Paket nicht im Pfad (Cron ohne cd, 12.09.: Backup fiel aus) — Protokoll ist optional, der Job nicht
        from contextlib import nullcontext as record
    with record("research_pulse"):
        raise SystemExit(main())
