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

Damit aus "Ende unbekannt" kein Dauer-Alarm wird (12.09.: ein um 07:49 hart
gekillter Nachhol-Lauf des Backups stand um 13:50 als "running for 6 h" in der
Mail — es lief laengst nichts mehr), traegt jede Zeile seit 2026-09-12 die
**pid** des Prozesses, der sie angelegt hat (Python: der Interpreter, Wrapper:
`$$` der Bash). `close_orphans()` — vom Sampler jede Minute vor den Alarmregeln
aufgerufen — schliesst offene Zeilen dieses Hosts, deren Prozess nicht mehr lebt
(oder deren pid inzwischen ein JUENGERER Prozess traegt): `ended_at` = jetzt,
`rc` NULL, Notiz "process gone". Zeilen ohne pid (Altbestand, fremder Host)
bleiben unangetastet. Und `record()` faengt SIGTERM (nur wenn das Skript keinen
eigenen Handler hat): SystemExit(143) → das Ende wird gestempelt, laufende
`subprocess.run`-Kinder werden dabei wie bei jeder Exception beendet.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from pipeline.db import USE_POSTGRES, get_connection

logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc) if USE_POSTGRES else datetime.now(timezone.utc).isoformat()


def start(job: str, host: str | None = None, note: str | None = None,
          pid: int | None = None) -> int | None:
    """Neue Zeile, gibt die id zurueck — oder None, wenn die DB nicht mitspielt.
    `pid` = der Prozess, dessen Leben den Lauf bedeutet (Default: dieser
    Interpreter; der Shell-Wrapper uebergibt sein `$$`)."""
    host = host or "local"
    pid = os.getpid() if pid is None else int(pid)
    try:
        with get_connection() as conn:
            if USE_POSTGRES:
                cur = conn._conn.cursor()
                cur.execute("INSERT INTO ops_events (job, host, started_at, note, pid) "
                            "VALUES (%s, %s, %s, %s, %s) RETURNING id", (job, host, _now(), note, pid))
                return int(cur.fetchone()[0])
            cur = conn.execute("INSERT INTO ops_events (job, host, started_at, note, pid) VALUES (?, ?, ?, ?, ?)",
                               (job, host, _now(), note, pid))
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
    prev_term = _install_sigterm_handler() if rec.owned else None
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
        if prev_term is not None:
            try:
                signal.signal(signal.SIGTERM, prev_term)
            except (ValueError, OSError):
                pass


def _on_sigterm(signum, frame):                                    # noqa: ARG001
    """SIGTERM → SystemExit(143): das `finally` in record() stempelt das Ende,
    subprocess.run() beendet dabei sein Kind (except: kill; raise)."""
    raise SystemExit(128 + signal.SIGTERM)


def _install_sigterm_handler():
    """Nur im Hauptthread und nur, wenn das Skript SIGTERM nicht selbst behandelt
    (SIG_DFL = ohne uns stuerbe der Prozess ohne `finally`). Gibt den vorigen
    Handler zurueck, wenn wir einen gesetzt haben, sonst None."""
    if threading.current_thread() is not threading.main_thread():
        return None
    try:
        if signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL:
            return None
        return signal.signal(signal.SIGTERM, _on_sigterm)
    except (ValueError, OSError):
        return None


def current_event_id() -> int | None:
    """Die id des laufenden Protokolleintrags (vom Wrapper vererbt oder von
    record() gesetzt) — fuer Notizen aus tiefer liegendem Code."""
    v = os.environ.get("OPS_EVENT_ID", "").strip()
    return int(v) if v.isdigit() else None


def open_events() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT id, job, host, started_at, pid FROM ops_events "
                            "WHERE ended_at IS NULL ORDER BY started_at").fetchall()
    return [dict(r) for r in rows]


def _proc_start_time(pid: int) -> float | None:
    """Startzeit des Prozesses als Unix-Zeit (aus /proc/<pid>/stat + btime) —
    None, wenn es den Prozess nicht gibt."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            stat = f.read()
        # Feld 22 (starttime, in Clock-Ticks seit Boot) steht HINTER dem ")"
        # des Kommandonamens, der selbst Leerzeichen enthalten darf.
        ticks = int(stat[stat.rindex(b")") + 2:].split()[19])
        with open("/proc/stat", "rb") as f:
            btime = next(int(l.split()[1]) for l in f if l.startswith(b"btime"))
        return btime + ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, StopIteration):
        return None


def process_alive_since(pid: int, started_at, *, tolerance_s: float = 120.0) -> bool:
    """Lebt der Prozess `pid` und ist es noch DERSELBE, der den Lauf angelegt hat?
    Ein Prozess, der erst nach `started_at` gestartet wurde, traegt die pid nur
    wiederverwendet — dann gilt der Lauf als tot. Ohne /proc (kein Linux) wird
    nur Existenz geprueft."""
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass                                                    # existiert, gehoert jemand anderem
    except (OverflowError, ValueError):
        return False
    t0 = _proc_start_time(int(pid))
    if t0 is None:
        return True
    if isinstance(started_at, str):
        started_at = datetime.fromisoformat(started_at)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return t0 <= started_at.timestamp() + tolerance_s


def close_orphans(host: str | None = None, *, now=None) -> list[dict]:
    """Offene Laeufe dieses Hosts schliessen, deren Prozess nicht mehr lebt
    (Stromausfall, kill -9, Tool-Timeout). `ended_at` = jetzt (das wahre Ende
    kennt niemand), `rc` bleibt NULL, Notiz sagt warum. Zeilen ohne pid oder
    eines anderen Hosts werden nie angefasst. Gibt die geschlossenen zurueck.
    Vom Sampler jede Minute aufgerufen — faengt alles, wie das ganze Modul."""
    host = host or "local"
    closed: list[dict] = []
    try:
        for ev in open_events():
            if ev.get("host") != host or ev.get("pid") is None:
                continue
            if process_alive_since(ev["pid"], ev["started_at"]):
                continue
            note = f"process {ev['pid']} gone — closed by ops_sampler, real end unknown"
            with get_connection() as conn:
                conn.execute("UPDATE ops_events SET ended_at = ?, note = CASE WHEN note IS NULL OR note = '' "
                             "THEN ? ELSE note || ' | ' || ? END WHERE id = ? AND ended_at IS NULL",
                             (now or _now(), note, note, ev["id"]))
            logger.warning("ops_events: #%s %s — %s", ev["id"], ev["job"], note)
            closed.append(ev)
    except Exception as e:                                          # noqa: BLE001
        logger.warning("ops_events.close_orphans: %s", e)
    return closed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ops_events CLI (#104)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("job"); s.add_argument("--host", default=None)
    s.add_argument("--note", default=None)
    s.add_argument("--pid", type=int, default=None,
                   help="Prozess, dessen Leben den Lauf bedeutet (Wrapper: $$); Default: dieser Interpreter")
    e = sub.add_parser("end"); e.add_argument("id", type=int); e.add_argument("rc", type=int)
    e.add_argument("note", nargs="?", default=None)
    sub.add_parser("open")
    sub.add_parser("close-orphans", help="offene Laeufe toter Prozesse dieses Hosts schliessen")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if a.cmd == "start":
        eid = start(a.job, a.host, a.note, a.pid)
        print(eid if eid is not None else "")
        return 0
    if a.cmd == "end":
        return 0 if end(a.id, a.rc, a.note) else 1
    if a.cmd == "close-orphans":
        for ev in close_orphans():
            print(f"closed #{ev['id']}\t{ev['job']}\tpid {ev['pid']}\tstarted {ev['started_at']}")
        return 0
    for ev in open_events():
        print(f"{ev['id']}\t{ev['job']}\t{ev['host']}\t{ev['started_at']}\tpid {ev.get('pid')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
