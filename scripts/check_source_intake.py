#!/usr/bin/env python3
"""Intake-Check einer (neuen) Quelle nach einem Full Cycle — neustartfest
per systemd-Timer nutzbar; Befund geht per Mail an den Owner (dieselbe
Resend-Strecke wie cycle_watchdog/review_notify).

Anlass: Cultivated X (aufgenommen 2026-08-23) soll nach dem ersten
Montags-Cycle geprüft werden, ohne an einer lebenden Claude-Session zu
hängen. Das Skript ist bewusst generisch (--source), damit künftige
Quellen-Aufnahmen denselben Check bekommen.

Prüft: (1) Cycle-Log-Endzeile + Exit-Code, (2) DB-Intake der Quelle
(raw_entries, Verarbeitungsstand, Duplikat-Quote — bei Syndication-
Schwestern wie vegconomist erwartet), (3) Stichprobe der entstandenen
Trends/Signale mit Verticals.

    python scripts/check_source_intake.py --source "Cultivated X" --no-mail
    python scripts/check_source_intake.py --source "Cultivated X" --wait 5400
"""
from __future__ import annotations

import argparse
import html
import logging
import re
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection  # noqa: E402  (lädt .env)
from scripts.review_notify import send  # noqa: E402  (Resend-Transport)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("check_source_intake")

LOG_DIR = Path.home() / "logs"
END_RE = re.compile(r"full_cycle_cron\.sh end .* \(rc=(\d+)\)")


def wait_for_cycle_end(log_path: Path, wait_s: int) -> int | None:
    """rc der end-Zeile; wartet bis zu wait_s Sekunden darauf. None = fehlt."""
    deadline = time.time() + wait_s
    while True:
        if log_path.exists():
            m = None
            for line in log_path.read_text(errors="replace").splitlines():
                mm = END_RE.search(line)
                if mm:
                    m = mm
            if m:
                return int(m.group(1))
        if time.time() >= deadline:
            return None
        time.sleep(60)


def check(source: str, log_date: str, wait_s: int) -> tuple[str, bool]:
    lines: list[str] = [f"Intake-Check '{source}' — {date.today().isoformat()}"]
    healthy = True

    log_path = LOG_DIR / f"catandary-full-cycle-{log_date}-0400.log"
    rc = wait_for_cycle_end(log_path, wait_s)
    if rc is None:
        lines.append(f"⚠ Cycle-Log {log_path.name}: keine end-Zeile gefunden "
                     f"(Lauf fehlt oder hängt — vgl. Watchdog).")
        healthy = False
    else:
        mark = "✓" if rc == 0 else "⚠"
        lines.append(f"{mark} Full Cycle rc={rc} ({log_path.name})")
        healthy &= rc == 0
        mentions = [ln for ln in log_path.read_text(errors="replace").splitlines()
                    if source.lower() in ln.lower()]
        err = [ln for ln in mentions if re.search(r"error|fail|traceback", ln, re.I)]
        if err:
            lines.append(f"⚠ {len(err)} Fehlerzeilen zur Quelle im Log, erste: {err[0][:160]}")
            healthy = False

    with get_connection() as conn:
        src = conn.execute("select id, last_fetched from sources where name = ?",
                           (source,)).fetchone()
        if not src:
            lines.append("⚠ Quelle existiert nicht in der sources-Tabelle — Poll lief nie.")
            return "\n".join(lines), False
        lines.append(f"✓ Quelle id={src['id']}, last_fetched={src['last_fetched']}")

        r = conn.execute("""
            select count(*) total,
                   count(*) filter (where processed) processed,
                   count(*) filter (where filtered_out) filtered,
                   count(*) filter (where filter_reason ilike ?) dups
            from raw_entries where source_id = ?
        """, ("%duplicate%", src["id"])).fetchone()
        lines.append(f"raw_entries: {r['total']} gesamt · {r['processed']} verarbeitet · "
                     f"{r['filtered']} gefiltert (davon {r['dups']} Duplikate — bei "
                     f"Syndication-Schwestern erwartet)")
        if r["total"] == 0:
            lines.append("⚠ Keine Einträge angekommen — Feed-Poll prüfen.")
            healthy = False

        t = conn.execute("""
            select t.status, count(*) c from trends t
            join raw_entries re on re.id = t.raw_entry_id
            where re.source_id = ? group by 1 order by 2 desc
        """, (src["id"],)).fetchall()
        lines.append("trends: " + (", ".join(f"{x['status']}={x['c']}" for x in t) or "—"))

        sample = conn.execute("""
            select t.title_en, t.primary_vertical, t.status from trends t
            join raw_entries re on re.id = t.raw_entry_id
            where re.source_id = ? order by t.id desc limit 3
        """, (src["id"],)).fetchall()
        for s in sample:
            lines.append(f"  · [{s['primary_vertical']}/{s['status']}] {s['title_en'][:90]}")

    lines.append("Befund: " + ("sauber ✓" if healthy else "AUFFÄLLIG — bitte ansehen ⚠"))
    return "\n".join(lines), healthy


def main() -> int:
    ap = argparse.ArgumentParser(description="Quellen-Intake-Check nach Full Cycle")
    ap.add_argument("--source", default="Cultivated X")
    ap.add_argument("--log-date", default=date.today().strftime("%Y%m%d"))
    ap.add_argument("--wait", type=int, default=0,
                    help="Sekunden auf die Cycle-end-Zeile warten (0 = nicht warten)")
    ap.add_argument("--no-mail", action="store_true")
    args = ap.parse_args()

    report, healthy = check(args.source, args.log_date, args.wait)
    print(report)
    if not args.no_mail:
        subject = (f"{'✓' if healthy else '⚠'} Intake-Check {args.source}: "
                   f"{'sauber' if healthy else 'auffällig'}")
        body = "<pre>" + html.escape(report) + "</pre>"
        send(subject, body, report)
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
