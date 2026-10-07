"""Kollisionswächter der GPU-Cron-Wrapper (#98): scripts/lib/gpu_guard.sh.

Kein bats im Repo — pytest ruft die Shell-Funktionen auf und schiebt ein
Fake-`pgrep` / Fake-`systemctl` per PATH davor. Getestet werden die Verträge,
auf die sich die Wrapper verlassen: frei/belegt/Skip nach Wartezeit, Ausschluss
der eigenen Prozesskette, die Statusnotiz für die Morgen-Mail und das
"Cleanup nur eigene Server"-Verhalten der Unit-Besitzvermerke.
"""
import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "lib" / "gpu_guard.sh"

FAKE_PGREP = textwrap.dedent("""\
    #!/usr/bin/env bash
    # Fake pgrep: gibt die PIDs aus $FAKE_PGREP_OUT aus (leer = kein Treffer).
    # FAKE_PGREP_SELF=1: meldet die eigene Elternshell (= Nachkomme des Aufrufers).
    # FAKE_PGREP_COUNTDOWN=<datei>: so lange belegt, wie die Zahl darin > 0 ist.
    if [ -n "${FAKE_PGREP_COUNTDOWN:-}" ] && [ -s "$FAKE_PGREP_COUNTDOWN" ]; then
      n=$(cat "$FAKE_PGREP_COUNTDOWN")
      if [ "$n" -gt 0 ]; then echo $((n-1)) > "$FAKE_PGREP_COUNTDOWN"; echo "$FAKE_FOREIGN_PID"; exit 0; fi
      exit 1
    fi
    if [ "${FAKE_PGREP_SELF:-0}" = "1" ]; then echo "$PPID"; exit 0; fi
    if [ -s "${FAKE_PGREP_OUT:-/nonexistent}" ]; then cat "$FAKE_PGREP_OUT"; exit 0; fi
    exit 1
""")

FAKE_SYSTEMCTL = textwrap.dedent("""\
    #!/usr/bin/env bash
    # Fake systemctl: protokolliert Aufrufe, `show -p MainPID --value` liefert $FAKE_MAINPID.
    echo "$*" >> "$FAKE_SYSTEMCTL_LOG"
    case "$*" in
      *"show -p MainPID"*) echo "${FAKE_MAINPID:-0}" ;;
    esac
    exit 0
""")


@pytest.fixture
def foreign(tmp_path):
    """Ein lebender, fremder Prozess (nicht in der Kette der Test-Shell) — ein
    toter/erfundener PID zählt für den Wächter zu Recht nicht als Job."""
    p = subprocess.Popen(["sleep", "60"])
    yield p.pid
    p.kill()
    p.wait()


@pytest.fixture
def env(tmp_path, foreign):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name, body in (("pgrep", FAKE_PGREP), ("systemctl", FAKE_SYSTEMCTL)):
        p = fake_bin / name
        p.write_text(body)
        p.chmod(0o755)
    data = tmp_path / "data"
    e = dict(os.environ)
    e.update({
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "FAKE_PGREP_OUT": str(tmp_path / "pids"),
        "FAKE_SYSTEMCTL_LOG": str(tmp_path / "systemctl.log"),
        "GPU_GUARD_POLL_SEC": "0",
        "GPU_GUARD_DATA_DIR": str(data),
        "FAKE_FOREIGN_PID": str(foreign),
    })
    e.pop("FAKE_PGREP_SELF", None)
    e.pop("FAKE_PGREP_COUNTDOWN", None)
    return e


def run(script: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", f'source "{GUARD}"\n{script}'],
                          env=env, capture_output=True, text=True, timeout=60)


class TestWait:
    def test_free_when_no_gpu_job_runs(self, env):
        r = run("gpu_guard_wait testjob 0", env)
        assert r.returncode == 0
        assert "warte" not in r.stdout

    def test_foreign_job_blocks_and_skips_after_budget(self, env, foreign):
        Path(env["FAKE_PGREP_OUT"]).write_text(f"{foreign}\n")
        r = run("gpu_guard_wait testjob 0", env)
        assert r.returncode == 1
        assert "SKIP" in r.stdout and str(foreign) in r.stdout
        assert "[gpu_guard/testjob]" in r.stdout

    def test_becomes_free_within_budget(self, env):
        cd = Path(env["GPU_GUARD_DATA_DIR"]).parent / "countdown"
        cd.write_text("2")
        env["FAKE_PGREP_COUNTDOWN"] = str(cd)
        r = run("gpu_guard_wait testjob 5", env)
        assert r.returncode == 0, r.stdout
        assert "warte" in r.stdout and "frei nach" in r.stdout

    def test_default_budget_is_90_minutes(self, env):
        r = run("echo $GPU_GUARD_MAX_MIN", env)
        assert r.stdout.strip() == "90"


class TestOwnProcessChain:
    def test_self_and_ancestors_are_not_foreign(self, env):
        # Die Shell schreibt ihre eigene PID als "Treffer" — der Wächter muss sie
        # (wie die cron-Shell darüber) als eigene Kette erkennen.
        r = run('echo $$ > "$FAKE_PGREP_OUT"; gpu_guard_busy', env)
        assert r.returncode == 1, r.stdout

    def test_own_descendants_are_not_foreign(self, env):
        # $(pgrep …) läuft in einer Subshell mit derselben Kommandozeile wie der
        # Wrapper — ein Treffer darauf wäre ein Selbst-Deadlock.
        env["FAKE_PGREP_SELF"] = "1"
        r = run("gpu_guard_busy", env)
        assert r.returncode == 1, r.stdout

    def test_dead_pid_is_not_a_job(self, env):
        Path(env["FAKE_PGREP_OUT"]).write_text("999999\n")
        r = run("gpu_guard_busy", env)
        assert r.returncode == 1, r.stdout


class TestPatterns:
    def test_known_gpu_jobs_are_covered(self, env):
        r = run("echo $GPU_GUARD_PATTERNS", env)
        for name in ("scheduled_cycle", "full_cycle_cron", "run_full_cycle",
                     "signal_batch", "weekly_ingesters",
                     "research_pulse", "newsletter_deep_dive"):
            assert name in r.stdout, name

    def test_history_embed_blocks_only_the_local_gpu_worker(self, env):
        """The wrapper, `status`/`check` and the 5080 worker use no local VRAM; only the
        `work --handover` worker does. A bare `history_embed` pattern made the cycle wait
        90 min on the remote worker and then fail with rc=75 (review 2026-10-04)."""
        import re
        pat = run("echo $GPU_GUARD_PATTERNS", env).stdout.strip()
        local = "/x/.venv/bin/python scripts/history_embed.py work --handover --host http://127.0.0.1:8090 --name 3090"
        assert re.search(pat, local)
        for cmd in ("/x/.venv/bin/python scripts/history_embed.py work --host http://100.94.255.57:8095 --name 5080",
                    "/x/.venv/bin/python scripts/history_embed.py status",
                    "/x/.venv/bin/python scripts/history_embed.py check --host http://127.0.0.1:8091",
                    "bash scripts/run_history_embed.sh"):
            assert not re.search(pat, cmd), cmd


class TestNote:
    def test_note_writes_json_for_the_morning_mail(self, env):
        r = run("gpu_guard_note weekly_ingesters blocked gpu_steps_done=1 "
                "gpu_steps_skipped=2 'blocked_by=1234 scheduled_cycle.sh' rc=75", env)
        assert r.returncode == 0, r.stderr
        note = json.loads((Path(env["GPU_GUARD_DATA_DIR"]) / "weekly_ingesters_last.json").read_text())
        assert note["job"] == "weekly_ingesters" and note["status"] == "blocked"
        assert note["gpu_steps_done"] == 1 and note["gpu_steps_skipped"] == 2
        assert note["blocked_by"] == "1234 scheduled_cycle.sh" and note["rc"] == 75
        assert note["date"].endswith("+00:00")


class TestUnitOwnership:
    def test_record_then_stop_own_server(self, env):
        env["FAKE_MAINPID"] = "4242"
        r = run("llama_unit_record_owner judge && llama_unit_stop_owned judge", env)
        assert r.returncode == 0, r.stdout
        assert "eigenen llama-server (PID 4242) gestoppt" in r.stdout
        assert "stop llama-server.service" in Path(env["FAKE_SYSTEMCTL_LOG"]).read_text()
        assert not (Path(env["GPU_GUARD_DATA_DIR"]) / "llama-server.judge.pid").exists()

    def test_foreign_server_is_left_running(self, env):
        env["FAKE_MAINPID"] = "4242"
        run("llama_unit_record_owner judge", env)
        pidfile = Path(env["GPU_GUARD_DATA_DIR"]) / "llama-server.judge.pid"
        assert pidfile.read_text().split()[0] == "4242"
        env["FAKE_MAINPID"] = "5151"      # jemand anders hat die Unit neu gestartet
        r = run("llama_unit_stop_owned judge", env)
        assert r.returncode == 0
        assert "gehört nicht diesem Job" in r.stdout
        assert "stop" not in Path(env["FAKE_SYSTEMCTL_LOG"]).read_text()
        assert not pidfile.exists()

    def test_unit_not_running_is_a_noop(self, env):
        env["FAKE_MAINPID"] = "0"
        r = run("llama_unit_stop_owned judge", env)
        assert r.returncode == 0
        assert "stop" not in Path(env["FAKE_SYSTEMCTL_LOG"]).read_text()


class TestMorningMailNote:
    """scripts/review_notify.py nimmt frische Wrapper-Notizen in die Mail auf."""

    def _write(self, tmp_path, monkeypatch, age_hours: float, status: str = "blocked"):
        import datetime
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data").mkdir(exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=age_hours)
        (tmp_path / "data" / "weekly_ingesters_last.json").write_text(json.dumps({
            "date": ts.isoformat(), "job": "weekly_ingesters", "status": status,
            "gpu_steps_done": 1, "gpu_steps_skipped": 2,
            "blocked_by": "1234 bash scripts/scheduled_cycle.sh 600", "rc": 75}))

    def test_fresh_note_is_reported(self, tmp_path, monkeypatch):
        from scripts import review_notify as rn
        self._write(tmp_path, monkeypatch, age_hours=48)
        notes = rn.gpu_job_notes()
        assert [n["job"] for n in notes] == ["weekly_ingesters"]
        line = rn._gpu_job_line(notes[0])
        assert "blocked" in line and "2 skipped" in line and "scheduled_cycle.sh" in line
        _, html_body, text = rn.build_mail(0, 0, None, [], None, None, notes)
        assert "GPU cron weekly_ingesters" in text and "GPU cron weekly_ingesters" in html_body

    def test_stale_note_is_ignored(self, tmp_path, monkeypatch):
        from scripts import review_notify as rn
        self._write(tmp_path, monkeypatch, age_hours=61)
        assert rn.gpu_job_notes() == []

    def test_ok_note_does_not_force_a_mail_but_blocked_does(self, tmp_path, monkeypatch, capsys):
        from scripts import review_notify as rn
        monkeypatch.setattr(rn, "fetch_queue", lambda: (0, 0, None, []))
        monkeypatch.setattr(rn, "judge_stats", lambda: None)
        monkeypatch.setattr(rn, "deep_dive_stats", lambda: None)
        monkeypatch.setattr("sys.argv", ["review_notify", "--dry-run"])
        self._write(tmp_path, monkeypatch, age_hours=1, status="ok")
        assert rn.main() == 0
        assert "Subject:" not in capsys.readouterr().out       # still quiet
        self._write(tmp_path, monkeypatch, age_hours=1, status="blocked")
        assert rn.main() == 0
        out = capsys.readouterr().out
        assert "Subject:" in out and "GPU cron weekly_ingesters: blocked" in out


class TestFalsePositives:
    """Prozesse, die einen Job-Namen nur ZITIEREN (Claude-Code-Tool-Shells, grep,
    pgrep, Editoren), duerfen den Waechter nicht aufhalten — 2026-09-05 hielt ein
    Wecker mit 'full_cycle_cron.sh' in der Kommandozeile den Publish 90 min auf."""

    def test_quoting_tool_shell_is_not_a_job(self, env, tmp_path):
        # Schleife statt Einzelkommando: bash -c "sleep" wuerde sleep direkt exec-en und
        # die zitierende Kommandozeile verschwinden lassen — der echte Wecker war eine Schleife.
        p = subprocess.Popen(["bash", "-c", "while :; do sleep 60; done # source /x/.claude/shell-snapshots/snap.sh full_cycle_cron.sh end"])
        try:
            (tmp_path / "pids").write_text(f"{p.pid}\n")
            r = run("gpu_guard_busy; echo rc=$?", env)
            assert "rc=1" in r.stdout, r.stdout + r.stderr          # frei
        finally:
            p.kill(); p.wait()

    def test_real_job_still_blocks(self, env, tmp_path, foreign):
        (tmp_path / "pids").write_text(f"{foreign}\n")
        r = run("gpu_guard_busy; echo rc=$?", env)
        assert "rc=0" in r.stdout, r.stdout + r.stderr              # belegt


class TestPulseNoteInMorningMail:
    """Der Samstags-Pulse (Cron seit 2026-09-18) meldet sich wie die Ingester
    über data/weekly_research_pulse_last.json in der Montags-Mail — mit Woche
    und Themenzahlen, damit „ok" auch heißt: es wurde etwas gerechnet."""

    def test_pulse_note_line_carries_week_and_theme_counts(self, tmp_path, monkeypatch):
        import datetime
        from scripts import review_notify as rn
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data").mkdir()
        ts = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=42)
        (tmp_path / "data" / "weekly_research_pulse_last.json").write_text(json.dumps({
            "date": ts.isoformat(), "job": "weekly_research_pulse", "status": "ok",
            "gpu_steps_done": 1, "gpu_steps_skipped": 0, "blocked_by": "",
            "week": "2026-W37", "themes": 28, "with_text": 19, "errors": 0, "rc": 0}))
        notes = rn.gpu_job_notes()
        assert [n["job"] for n in notes] == ["weekly_research_pulse"]
        line = rn._gpu_job_line(notes[0])
        assert "week=2026-W37" in line and "themes=28" in line and "with_text=19" in line
        assert "blocked by" not in line
        _, _, text = rn.build_mail(0, 0, None, [], None, None, notes)
        assert "GPU cron weekly_research_pulse: ok" in text


FAKE_DOCKER = textwrap.dedent("""\\
    #!/usr/bin/env bash
    # Fake docker: protokolliert, `inspect -f {{.Name}} <id>` → /<FAKE_DOCKER_NAME_<id8>>.
    echo "$*" >> "$FAKE_DOCKER_LOG"
    case "$1" in
      inspect) id="${@: -1}"; echo "/name-${id:0:8}" ;;
      stop|start) [ "${FAKE_DOCKER_FAIL:-}" = "$1" ] && exit 1; exit 0 ;;
    esac
""")


def _evict_env(tmp_path, pids_cgroups):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for name, body in (("docker", FAKE_DOCKER), ("pgrep", FAKE_PGREP)):
        f = bindir / name
        f.write_text(body)
        f.chmod(0o755)
    proc = tmp_path / "proc"
    for pid, cg in pids_cgroups.items():
        (proc / str(pid)).mkdir(parents=True, exist_ok=True)
        (proc / str(pid) / "cgroup").write_text(cg)
    return {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "GPU_PROC_ROOT": str(proc),
            "GPU_GUARD_DATA_DIR": str(tmp_path / "data"), "FAKE_DOCKER_LOG": str(tmp_path / "docker.log"),
            "FAKE_PGREP_OUT": str(tmp_path / "pgrep.out")}


def _sh(script, env):
    return subprocess.run(["bash", "-c", f"source {GUARD}; {script}"], env=env,
                          capture_output=True, text=True)


def test_evict_stops_docker_container_once_and_restores(tmp_path):
    a, b = "a" * 64, "b" * 64
    env = _evict_env(tmp_path, {
        101: f"0::/system.slice/docker-{a}.scope\n",
        102: f"0::/system.slice/docker-{a}.scope\n",           # zweiter Prozess, selber Container
        103: f"12:memory:/docker/{b}\n",                       # cgroup v1
    })
    r = _sh("gpu_evict_pid 101 && gpu_evict_pid 102 && gpu_evict_pid 103 && echo OK", env)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout + r.stderr
    log = (tmp_path / "docker.log").read_text()
    assert log.count(f"stop -t 30 {a}") == 1 and log.count(f"stop -t 30 {b}") == 1
    state = tmp_path / "data" / "gpu_evicted_containers"
    assert state.read_text().split() == ["name-aaaaaaaa", "name-bbbbbbbb"]
    r = _sh("gpu_evict_restore && echo RESTORED", env)
    assert "RESTORED" in r.stdout, r.stdout + r.stderr
    assert "start name-aaaaaaaa" in (tmp_path / "docker.log").read_text()
    assert not state.exists()


def test_evict_restore_waits_for_foreign_gpu_job(tmp_path):
    env = _evict_env(tmp_path, {101: f"0::/system.slice/docker-{'c' * 64}.scope\n"})
    _sh("gpu_evict_pid 101", env)
    sleeper = subprocess.Popen(["sleep", "30"])
    try:
        (tmp_path / "pgrep.out").write_text(f"{sleeper.pid}\n")
        r = _sh("gpu_evict_restore; echo rc=$?", env)
    finally:
        sleeper.kill()
    assert "rc=1" in r.stdout and "NOT restarted" in r.stdout
    assert "start" not in (tmp_path / "docker.log").read_text().replace("stop -t", "")
    assert (tmp_path / "data" / "gpu_evicted_containers").exists()


def test_evict_non_container_and_failures(tmp_path):
    env = _evict_env(tmp_path, {})
    victim = subprocess.Popen(["sleep", "30"])
    r = _sh(f"gpu_evict_pid {victim.pid}; echo rc=$?", env)
    assert "rc=0" in r.stdout and victim.wait(timeout=5) != 0
    r = _sh("gpu_evict_pid 1; echo rc=$?", env)                         # init gehört root
    assert "rc=1" in r.stdout and "kill 1 failed" in r.stdout
    env = _evict_env(tmp_path, {201: f"0::/system.slice/docker-{'d' * 64}.scope\n"})
    r = _sh("gpu_evict_pid 201; echo rc=$?", {**env, "FAKE_DOCKER_FAIL": "stop"})
    assert "rc=1" in r.stdout and "docker stop name-dddddddd failed" in r.stdout
