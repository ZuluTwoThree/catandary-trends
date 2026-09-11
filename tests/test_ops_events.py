"""Ereignis-Protokoll der Laeufe (#104, Stufe 2): start/end/record in SQLite,
Uebernahme einer vom Wrapper vererbten id, Exit-Code aus SystemExit, und die
Shell-Bibliothek gegen dieselbe Datenbank."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    monkeypatch.delenv("OPS_EVENT_ID", raising=False)
    import importlib
    from pipeline import config, db as dbm
    importlib.reload(config)
    importlib.reload(dbm)
    import pipeline.ops_events as oe
    importlib.reload(oe)
    dbm.init_db()
    return dbm, oe


def _rows(dbm):
    with dbm.get_connection() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM ops_events ORDER BY id").fetchall()]


def test_start_end_and_note_append(db):
    dbm, oe = db
    eid = oe.start("full_cycle_cron", note="batch=3000")
    assert eid == 1
    assert oe.open_events()[0]["job"] == "full_cycle_cron"
    assert oe.end(eid, 75, "blocked")
    r = _rows(dbm)[0]
    assert r["rc"] == 75 and r["ended_at"] and r["note"] == "batch=3000 | blocked"
    assert oe.open_events() == []
    assert oe.end(None, 0) is False                  # kein Start → No-op


def test_record_success_and_exception(db):
    dbm, oe = db
    with oe.record("backup_db") as ev:
        ev.note("113 GB")
    with pytest.raises(RuntimeError):
        with oe.record("purge_raw_content"):
            raise RuntimeError("boom")
    with pytest.raises(SystemExit):
        with oe.record("resolve_open_licence"):
            raise SystemExit(3)
    rows = _rows(dbm)
    assert [(r["job"], r["rc"], r["note"]) for r in rows] == [
        ("backup_db", 0, "113 GB"), ("purge_raw_content", 1, None), ("resolve_open_licence", 3, None)]
    assert all(r["ended_at"] for r in rows)


def test_record_adopts_inherited_id_and_leaves_the_end_to_the_wrapper(db, monkeypatch):
    dbm, oe = db
    eid = oe.start("embed_full_text", note="limit=30000")
    monkeypatch.setenv("OPS_EVENT_ID", str(eid))
    with oe.record("embed_full_text") as ev:
        assert ev.id == eid and ev.owned is False
        ev.note("remote=bequiet")
    rows = _rows(dbm)
    assert len(rows) == 1
    assert rows[0]["ended_at"] is None and rows[0]["note"] == "limit=30000 | remote=bequiet"
    oe.end(eid, 0)
    assert _rows(dbm)[0]["rc"] == 0


def test_record_survives_a_broken_database(db, monkeypatch):
    _, oe = db
    monkeypatch.setattr(oe, "get_connection", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    with oe.record("check_source_links") as ev:        # darf nicht werfen
        assert ev.id is None
        ev.note("x")


def test_shell_library_round_trip(tmp_path):
    """ops_event_start/ops_event_end aus scripts/lib/ops_events.sh gegen eine
    frische SQLite-DB — so, wie ein Wrapper es tut."""
    env = dict(os.environ, DATABASE_URL="", DATABASE_PATH=str(tmp_path / "s.db"),
               OPS_EVENTS_PY=sys.executable)
    subprocess.run([sys.executable, "-c", "from pipeline.db import init_db; init_db()"],
                   cwd=REPO, env=env, check=True, capture_output=True)
    script = f"""
set -u
source "{REPO}/scripts/lib/ops_events.sh"
ops_event_start weekly_patents "window=2026-09-01..2026-09-08"
echo "id=$OPS_EVENT_ID"
ops_event_end 2 "density_rc=2"
"""
    r = subprocess.run(["bash", "-c", script], cwd=REPO, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "weekly_patents → #1" in r.stdout and "id=1" in r.stdout
    q = subprocess.run([sys.executable, "-c",
                        "from pipeline.db import get_connection\n"
                        "with get_connection() as c:\n"
                        "    r = c.execute('SELECT job, rc, note, ended_at IS NOT NULL AS done FROM ops_events').fetchone()\n"
                        "    print(r['job'], r['rc'], r['note'], r['done'])"],
                       cwd=REPO, env=env, capture_output=True, text=True, check=True)
    assert q.stdout.strip() == "weekly_patents 2 window=2026-09-01..2026-09-08 | density_rc=2 1"
