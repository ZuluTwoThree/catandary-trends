#!/usr/bin/env python3
"""Daily Digest (Stage 10b): Tagesüberblick über die veröffentlichten Artikel eines
Nachtlaufs, für die Morgen-Mail (pipeline/daily_digest.py).

Im Nachtlauf (scheduled_cycle.sh, direkt nach dem Richter, auf demselben
Qwen3.8-27B-Server):
    python -m scripts.daily_digest --since "$CYCLE_STARTED_AT"

Von Hand (holt sich Qwen3.8 per GPU-Handover und stellt danach den Ruhezustand her):
    python -m scripts.daily_digest --since "2026-10-16 02:45" --handover
    python -m scripts.daily_digest --since-hours 8 --dry-run      # nur zählen, kein Modell
    python -m scripts.daily_digest --since "…" --handover --preview data/digest.html

Exit: 0 ok/leer, 1 Fehler, 75 GPU belegt (nur mit --handover).
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import daily_digest as dd  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("daily_digest")

# Das 27B füllt die Karte mit 17,6 GB; neben NeMo/Whisper (2,4 GB) passt es (Stage 10).
VRAM_MAX_MIB = int(os.getenv("JUDGE_VRAM_MAX_MIB", "3500"))


def _parse(ts: str) -> datetime:
    d = datetime.fromisoformat(ts.strip().replace("Z", "+00:00"))
    return d if d.tzinfo else d.astimezone()


def foreign_gpu_job() -> str | None:
    """Läuft ein anderer GPU-Job (Kollisionswächter-Muster)? Dann kein Handover."""
    from pipeline.ops_probe import gpu_guard_patterns
    r = subprocess.run(["pgrep", "-f", "-a", gpu_guard_patterns()], capture_output=True, text=True)
    me = os.getpid()
    for line in r.stdout.splitlines():
        pid, _, cmd = line.partition(" ")
        if pid.isdigit() and int(pid) != me and "daily_digest" not in cmd and "pgrep" not in cmd:
            return cmd[:160]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--since", help="Laufbeginn (ISO, lokale Zeit ohne Zone)")
    g.add_argument("--since-hours", type=float, help="Fenster: die letzten N Stunden")
    ap.add_argument("--until", help="Fensterende (Default: jetzt)")
    ap.add_argument("--handover", action="store_true",
                    help="Qwen3.8-27B per GPU-Handover laden, danach Ruhezustand herstellen")
    ap.add_argument("--dry-run", action="store_true", help="nur zählen und Prompts bauen, kein Modell, nichts speichern")
    ap.add_argument("--preview", help="zusätzlich den Mail-Abschnitt als HTML-Datei schreiben")
    a = ap.parse_args()

    until = _parse(a.until) if a.until else datetime.now(timezone.utc).astimezone()
    since = _parse(a.since) if a.since else until - timedelta(hours=a.since_hours)
    data = dd.collect(since, until)
    verts = dd.by_vertical(data)
    logger.info("window %s .. %s: %d published articles, %d stories, %d sections",
                since.isoformat(timespec="minutes"), until.isoformat(timespec="minutes"),
                len(data.articles), len(data.groups), len(verts))

    if a.dry_run:
        est = lambda t: int(len(t) / 3.0) + 1  # noqa: E731
        for v, arts in verts.items():
            p, n, drop = dd.fit_vertical(v, arts, data, counter=est)
            print(f"{v:10s} {len(arts):5d} articles  ~{n:6d} tokens (estimate)  dropped {drop}")
        return 0
    if not data.articles:
        logger.info("no published articles in the window — nothing to digest")
        return 0

    def run() -> dict:
        return dd.generate(data, since, until)

    try:
        if a.handover:
            job = foreign_gpu_job()
            if job:
                logger.error("GPU busy (%s) — no handover", job)
                return 75
            os.environ.setdefault("GPU_JOB_NAME", "daily_digest")
            from pipeline import gpu_handover
            try:
                with gpu_handover.model_on_llamacpp(dd.DIGEST_MODEL, vram_free_below_mib=VRAM_MAX_MIB):
                    res = run()
            finally:
                # Der Handover stellt nur den Symlink zurück; das 8B startet erst hier wieder.
                gpu_handover.unit_start()
        else:
            res = run()
    except Exception as e:                                       # noqa: BLE001
        logger.error("digest failed: %r", e)
        return 1

    dd.save(res)
    t = dd.totals(res)
    logger.info("digest saved: %d words, %d citations, %d invalid, %d unbacked numbers, %.0fs",
                t["words"], t["cited"], t["bad_ids"], t["bad_numbers"], res.get("total_seconds", 0))
    if a.preview:
        Path(a.preview).write_text(dd.render_mail_html(res), encoding="utf-8")
        logger.info("preview → %s", a.preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
