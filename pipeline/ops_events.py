"""Ereignis-Protokoll der Laeufe fuer das Ops-Dashboard (#104, Stufe 2).

Eine Zeile je Job-Lauf in `ops_events`: Job, Start, Ende, Exit-Code, Notiz.
Das ist das Langzeit-Gedaechtnis fuer "wie lang dauert der Samstag wirklich" —
die Cron-Logs wissen es, aber niemand liest 40.000 Zeilen dafuer; die
`*_last.json`-Notizen kennen nur den letzten Lauf.

Zwei Einstiege, ein Grundsatz: **das Protokoll darf nie einen Lauf verhindern.**
Ist die Datenbank nicht erreichbar, wird gewarnt und der Job laeuft weiter;
`end` ohne bekannte id ist ein No-op.

  Python (Cron-Skripte, Worker):

      from pipeline.ops_events import record
      with record("backup_db") as ev:
          ...                       # Exit-Code aus einer Exception = 1, sonst 0
          ev.note("113 GB")         # optional, sofort geschrieben

  Shell (scripts/lib/ops_events.sh, nutzt die CLI unten):

      ops_event_start full_cycle_cron
      ...
      ops_event_end "$RC" "batch=3000"

  CLI:  python -m pipeline.ops_events start <job> [--host H]   → druckt die id
        python -m pipeline.ops_events end <id> <rc> [note]
        python -m pipeline.ops_events open                       → offene Laeufe

Ein Lauf, der ohne `end` stirbt (Stromausfall, kill -9), bleibt mit leerem
`ended_at` stehen — genau das ist die Information: die Alarmregel "Job haengt"
(Stufe 5) und die Seite lesen sie als "abgebrochen, Ende unbekannt".
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone

from pipeline.db import USE_POSTGRES, get_connection

logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc) if USE_POSTGRES else datetime.now(timezone.utc).isoformat()


def start(job: str, host: str | None = None, note: str | None = None) -> int | None:
    """Neue Zeile, gibt die id zurueck — oder None, wenn die DB nicht mitspielt."""
    host = host or "local"
    try:
        with get_connection() as conn:
            if USE_POSTGRES:
                cur = conn._conn.cursor()
                cur.execute("INSERT INTO ops_events (job, host, started_at, note) "
                            "VALUES (%s, %s, %s, %s) RETURNING id", (job, host, _now(), note))
                return int(cur.fetchone()[0])
            cur = conn.execute("INSERT INTO ops_events (job, host, started_at, note) VALUES (?, ?, ?, ?)",
                               (job, host, _now(), note))
            return int(cur.lastrowid)
    except Exception as e:                                          # noqa: BLE001
        logger.warning("ops_events.start(%s): %s", job, e)
        return None


def end(event_id: int | None, rc: int, note: str | None = None) -> bool:
    """Ende + Exit-Code nachtragen. Eine vorhandene Notiz bleibt stehen, eine neue
    wird angehaengt (durch ' | ')."""
    if event_id is None:
        return False
    try:
        with get_connection() as conn:
            if note:
                conn.execute("UPDATE ops_events SET ended_at = ?, rc = ?, "
                             "note = CASE WHEN note IS NULL OR note = '' THEN ? ELSE note || ' | ' || ? END "
                             "WHERE id = ?", (_now(), int(rc), note, note, event_id))
            else:
                conn.execute("UPDATE ops_events SET ended_at = ?, rc = ? WHERE id = ?",
                             (_now(), int(rc), event_id))
        return True
    except Exception as e:                                          # noqa: BLE001
        logger.warning("ops_events.end(%s): %s", event_id, e)
        return False


def add_note(event_id: int | None, text: str) -> bool:
    """Notiz sofort anhaengen (z. B. "remote=bequiet" mitten im Lauf)."""
    if event_id is None or not text:
        return False
    try:
        with get_connection() as conn:
            conn.execute("UPDATE ops_events SET note = CASE WHEN note IS NULL OR note = '' "
                         "THEN ? ELSE note || ' | ' || ? END WHERE id = ?", (text, text, event_id))
        return True
    except Exception as e:                                          # noqa: BLE001
        logger.warning("ops_events.add_note(%s): %s", event_id, e)
        return False


class _Recorder:
    def __init__(self, event_id: int | None, owned: bool):
        self.id = event_id
        self.owned = owned

    def note(self, text: str) -> None:
        add_note(self.id, text)


@contextmanager
def record(job: str, host: str | None = None):
    """Kontext: start beim Betreten, end beim Verlassen (rc 0; bei einer
    Exception 1, bei SystemExit deren Code). Die Exception laeuft weiter.

    Steht OPS_EVENT_ID in der Umgebung, hat ein Shell-Wrapper den Lauf schon
    angelegt (scripts/lib/ops_events.sh exportiert die id): dann wird KEINE
    zweite Zeile angelegt und das Ende dem Wrapper ueberlassen — Notizen gehen
    aber an dessen Zeile. So zaehlt ein Lauf genau einmal, ob per Cron oder
    von Hand gestartet."""
    inherited = os.environ.get("OPS_EVENT_ID", "").strip()
    if inherited.isdigit():
        rec = _Recorder(int(inherited), owned=False)
    else:
        rec = _Recorder(start(job, host), owned=True)
        if rec.id is not None:
            # Kindprozesse und tiefer liegender Code finden den Lauf ueber die Umgebung.
            os.environ["OPS_EVENT_ID"] = str(rec.id)
    rc = 0
    try:
        yield rec
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        raise
    except BaseException:
        rc = 1
        raise
    finally:
        if rec.owned:
            end(rec.id, rc)
            os.environ.pop("OPS_EVENT_ID", None)


def current_event_id() -> int | None:
    """Die id des laufenden Protokolleintrags (vom Wrapper vererbt oder von
    record() gesetzt) — fuer Notizen aus tiefer liegendem Code."""
    v = os.environ.get("OPS_EVENT_ID", "").strip()
    return int(v) if v.isdigit() else None


def open_events() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, job, host, started_at FROM ops_events "
                            "WHERE ended_at IS NULL ORDER BY started_at").fetchall()
    return [dict(r) for r in rows]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ops_events CLI (#104)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("job"); s.add_argument("--host", default=None)
    s.add_argument("--note", default=None)
    e = sub.add_parser("end"); e.add_argument("id", type=int); e.add_argument("rc", type=int)
    e.add_argument("note", nargs="?", default=None)
    sub.add_parser("open")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if a.cmd == "start":
        eid = start(a.job, a.host, a.note)
        print(eid if eid is not None else "")
        return 0
    if a.cmd == "end":
        return 0 if end(a.id, a.rc, a.note) else 1
    for ev in open_events():
        print(f"{ev['id']}\t{ev['job']}\t{ev['host']}\t{ev['started_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
