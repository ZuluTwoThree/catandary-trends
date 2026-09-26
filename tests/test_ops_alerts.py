"""Ops-Alarme (#104, Stufe 5): Regeln auf synthetischen Messungen, der
"nicht geprueft"-Schutz gegen Entwarnungs-Flattern, Ausloesen/Entwarnen mit
genau einer Zeile je Zustand, Schwellen aus YAML, Sampler-tot fuer den Waechter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    import importlib
    from pipeline import config, db as dbm
    importlib.reload(config)
    importlib.reload(dbm)
    import pipeline.ops_alerts as oa
    importlib.reload(oa)
    dbm.init_db()
    return dbm, oa


def _sample(**over):
    base = {
        "is_full": True, "gpu_temp_c": 44, "gpu_mem_used_mib": 21986, "gpu_model": "./models/Qwen3-8B.gguf", "gpu_job": None,
        "db_connections": 3, "db_max_connections": 100,
        "disks": [
            {"dev": "nvme1n1", "rotational": False, "temp_c": 40,
             "mounts": [{"mount": "/", "size_bytes": 2_000_000_000_000, "avail_bytes": 600_000_000_000}],
             "smart": {"passed": True, "type": "nvme", "percentage_used": 1, "available_spare": 100, "media_errors": 0, "critical_warning": 0, "temp_c": 40}},
            {"dev": "sda", "rotational": True, "temp_c": None,
             "mounts": [{"mount": "/mnt/data-hdd", "size_bytes": 2_000_000_000_000, "avail_bytes": 1_000_000_000_000}],
             "smart": {"passed": True, "type": "ata", "reallocated": 0, "pending": 0, "uncorrectable": 0, "temp_c": 37}},
        ],
    }
    base.update(over)
    return base


def _findings(results):
    return sorted((f.kind, f.key) for r in results for f in r.findings)


def test_thresholds_default_and_yaml(db, tmp_path):
    _, oa = db
    t = oa.load_thresholds(tmp_path / "missing.yaml")
    assert t["gpu_temp_max_c"] == 88
    (tmp_path / "x.yaml").write_text("gpu_temp_max_c: 70\nunknown_key: 1\n")
    t2 = oa.load_thresholds(tmp_path / "x.yaml")
    assert t2["gpu_temp_max_c"] == 70 and "unknown_key" not in t2


def test_rules_quiet_on_a_healthy_sample(db):
    _, oa = db
    res = oa.evaluate(_sample(), {"prev_full": None, "open": [], "medians": {}, "daily_max": []}, oa.DEFAULTS)
    assert _findings(res) == []
    assert {r.kind for r in res if r.checked} >= {"disk_free", "disk_temp", "disk_smart", "gpu_temp", "gpu_foreign", "db_connections"}


def test_disk_rules(db):
    _, oa = db
    t = oa.DEFAULTS
    s = _sample()
    s["disks"][0]["mounts"][0]["avail_bytes"] = 300_000_000_000        # 15 % frei auf "/" → unter 20
    s["disks"][1]["temp_c"] = 57                                       # HDD zu warm (Grenze 55)
    s["disks"][1]["smart"]["temp_c"] = 57
    prev = {"disks": [{"dev": "sda", "smart": {"reallocated": 0, "pending": 0}}]}
    s["disks"][1]["smart"]["pending"] = 2                             # steigt 0 → 2
    res = oa.evaluate(s, {"prev_full": prev, "open": [], "medians": {}, "daily_max": []}, t)
    assert _findings(res) == [("disk_free", "/"), ("disk_smart", "sda"), ("disk_temp", "sda")]
    # stabil bei 2 → kein Alarm
    prev2 = {"disks": [{"dev": "sda", "smart": {"reallocated": 0, "pending": 2}}]}
    res2 = oa.evaluate(s, {"prev_full": prev2, "open": [], "medians": {}, "daily_max": []}, t)
    assert ("disk_smart", "sda") not in _findings(res2)


def test_smart_not_checked_on_non_full_sample(db):
    _, oa = db
    s = _sample(is_full=False)
    for d in s["disks"]:
        d.pop("smart")
    res = oa.evaluate(s, {"prev_full": None, "open": [], "medians": {}, "daily_max": []}, oa.DEFAULTS)
    by = {r.kind: r for r in res}
    assert by["disk_smart"].checked is False
    assert by["backlog_growth"].checked is False
    assert by["disk_free"].checked is True


def test_gpu_db_job_backlog_rules(db):
    _, oa = db
    t = dict(oa.DEFAULTS)
    now = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    s = _sample(gpu_temp_c=91, gpu_mem_used_mib=22000, gpu_model=None, gpu_job=None, db_connections=85)
    open_ev = [{"job": "full_cycle_cron", "started_at": now - timedelta(hours=7)},
               {"job": "backup_db", "started_at": now - timedelta(hours=1)}]
    ctx = {"prev_full": None, "open": open_ev, "medians": {"backup_db": 1200.0}, "daily_max": [100, 200, 300, 400]}
    res = oa.evaluate(s, ctx, t, now=now)
    f = _findings(res)
    assert ("gpu_temp", "local") in f
    assert ("gpu_foreign", "local") not in f            # ein Job laeuft → nicht fremd
    assert ("db_connections", "db") in f
    assert ("job_hang", "full_cycle_cron") in f
    assert ("job_slow", "backup_db") in f               # 1 h gegen Median 20 min
    assert ("backlog_growth", "backlog") in f
    # ohne offenen Job ist der belegte Speicher fremd
    res2 = oa.evaluate(s, {**ctx, "open": []}, t, now=now)
    assert ("gpu_foreign", "local") in _findings(res2)


def test_sync_raises_once_and_resolves_once(db, monkeypatch):
    dbm, oa = db
    s = _sample(gpu_temp_c=95)
    ctx = {"prev_full": None, "open": [], "medians": {}, "daily_max": []}
    r1 = oa.sync(oa.evaluate(s, ctx, oa.DEFAULTS))
    assert [f.kind for f in r1[0]] == ["gpu_temp"] and r1[1] == []
    r2 = oa.sync(oa.evaluate(s, ctx, oa.DEFAULTS))            # unveraendert → nichts
    assert r2 == ([], [])
    # Minute ohne GPU-Wert → gpu_temp "nicht geprueft" → Alarm bleibt offen
    r3 = oa.sync(oa.evaluate(_sample(gpu_temp_c=None), ctx, oa.DEFAULTS))
    assert r3 == ([], [])
    r4 = oa.sync(oa.evaluate(_sample(gpu_temp_c=50), ctx, oa.DEFAULTS))
    assert r4[0] == [] and [x["kind"] for x in r4[1]] == ["gpu_temp"]
    with dbm.get_connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT kind, resolved_at FROM ops_alerts").fetchall()]
    assert len(rows) == 1 and rows[0]["resolved_at"]


def test_run_never_raises_and_mails_changes(db, monkeypatch):
    _, oa = db
    sent = []
    monkeypatch.setattr(oa, "notify", lambda raised, resolved: sent.append((len(raised), len(resolved))) or True)
    out = oa.run(_sample(gpu_temp_c=95))
    assert out["raised"] == 1 and out["mailed"] is True and sent == [(1, 0)]
    out2 = oa.run(_sample(gpu_temp_c=95))
    assert out2["raised"] == 0 and out2["mailed"] is None and len(sent) == 1
    monkeypatch.setattr(oa, "_db_context", lambda t=None: (_ for _ in ()).throw(RuntimeError("db down")))
    out3 = oa.run(_sample())
    assert out3["error"] and "db down" in out3["error"]


def test_sampler_stale_for_the_watchdog(db):
    dbm, oa = db
    stale, msg = oa.sampler_stale()
    assert stale and "never" in msg
    from pipeline import ops_probe
    import importlib
    importlib.reload(ops_probe)
    now = datetime.now(timezone.utc)
    ops_probe.write_sample({"ts": now - timedelta(minutes=2), "is_full": False})
    assert oa.sampler_stale(now=now)[0] is False
    assert oa.sampler_stale(now=now + timedelta(minutes=10))[0] is True


def test_job_hang_message_uses_local_time_with_zone(db, monkeypatch):
    """12.09.: die Mail sagte 'started 07:49 UTC' — es war 07:49 CEST."""
    import time
    _, oa = db
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    try:
        now = datetime(2026, 9, 12, 11, 50, tzinfo=timezone.utc)
        ev = [{"job": "backup_db", "started_at": datetime(2026, 9, 12, 5, 49, tzinfo=timezone.utc)}]
        res = oa.rule_jobs(ev, {}, dict(oa.DEFAULTS), now)
        msg = [f.message for r in res for f in r.findings if f.kind == "job_hang"][0]
        assert "started 12.09. 07:49 CEST" in msg and "UTC" not in msg
    finally:
        monkeypatch.delenv("TZ", raising=False)
        time.tzset()


# --- Plattentemperatur, nachgeschaerft 2026-09-16 ----------------------------
# Anlass: "resolved: nvme0n1: 65.8 °C, limit 65 °C" — waehrend dasselbe
# Laufwerk warning_temp_time 0 meldete, also nach eigener Auskunft nie zu heiss
# war. Die Grenzwerte stammen jetzt aus den Datenblaettern der verbauten
# Laufwerke, und das Laufwerk selbst ist der eigentliche Kronzeuge.

def _disk(dev="nvme0n1", temp=50.0, rot=False, **smart):
    base = {"type": "nvme", "passed": True, "media_errors": 0, "critical_warning": 0,
            "percentage_used": 3, "available_spare": 100}
    base.update(smart)
    return {"dev": dev, "temp_c": temp, "rotational": rot, "smart": base}


def _temps(oa, sample, prev=None):
    return {r.kind: r for r in oa.rule_disks(sample, prev, oa.DEFAULTS)}


def test_a_normal_nvme_load_temperature_is_no_longer_an_alarm(db):
    _, oa = db
    """Kingston NV2, Lexar NM790 und Kingston A400 sind alle 0-70 °C
    spezifiziert; 65,8 °C unter Dauerlast ist Betrieb, kein Vorfall."""
    r = _temps(oa, {"disks": [_disk(temp=65.8)]})
    assert r["disk_temp"].findings == []


def test_above_the_datasheet_limit_it_still_alarms(db):
    _, oa = db
    r = _temps(oa, {"disks": [_disk(temp=69.0)]})
    assert len(r["disk_temp"].findings) == 1
    assert "69" in r["disk_temp"].findings[0].message


def test_the_spinning_disk_keeps_its_own_lower_limit(db):
    _, oa = db
    """Seagate Barracuda ST2000DM008: Betrieb 0-60 °C."""
    assert _temps(oa, {"disks": [_disk("sda", temp=54.0, rot=True)]})["disk_temp"].findings == []
    assert _temps(oa, {"disks": [_disk("sda", temp=56.0, rot=True)]})["disk_temp"].findings


def test_the_drive_itself_is_the_witness_when_it_says_it_was_too_hot(db):
    _, oa = db
    prev = {"disks": [_disk(warning_temp_time=10, critical_comp_time=0)]}
    now = {"disks": [_disk(temp=52.0, warning_temp_time=14, critical_comp_time=0)]}
    f = _temps(oa, now, prev)["disk_smart"].findings
    assert len(f) == 1
    assert "own warning temperature" in f[0].message and "10 → 14" in f[0].message


def test_time_above_the_critical_temperature_is_reported_separately(db):
    _, oa = db
    prev = {"disks": [_disk(warning_temp_time=14, critical_comp_time=0)]}
    now = {"disks": [_disk(warning_temp_time=14, critical_comp_time=1)]}
    f = _temps(oa, now, prev)["disk_smart"].findings
    assert len(f) == 1 and "CRITICAL" in f[0].message


def test_a_counter_that_stands_still_is_not_an_alarm(db):
    _, oa = db
    prev = {"disks": [_disk(warning_temp_time=314, critical_comp_time=1)]}
    now = {"disks": [_disk(warning_temp_time=314, critical_comp_time=1)]}
    assert _temps(oa, now, prev)["disk_smart"].findings == []


# --- rc != 0: drei Sonntage unbemerkt (2026-09-26) ---------------------------

def _last(job, rc, ended):
    return {"job": job, "rc": rc, "ended_at": ended}


def test_a_job_that_ended_with_an_error_is_an_alarm(db):
    """discovery_loop meldete rc=1 am 06./13./20.09. — niemand erfuhr es."""
    _, oa = db
    t = dict(oa.DEFAULTS)
    ended = datetime(2026, 9, 20, 6, 15, tzinfo=timezone.utc)
    res = oa.rule_job_failed([_last("discovery_loop", 1, ended)], t)
    assert res.checked
    assert [f.key for f in res.findings] == ["discovery_loop"]
    assert "rc=1" in res.findings[0].message


def test_a_successful_last_run_clears_the_way(db):
    _, oa = db
    ended = datetime(2026, 9, 20, 6, 15, tzinfo=timezone.utc)
    res = oa.rule_job_failed([_last("discovery_loop", 0, ended)], dict(oa.DEFAULTS))
    assert res.checked and res.findings == []


def test_a_collision_guard_skip_is_no_defect(db):
    """rc=75 heisst: fremder GPU-Job, nichts angefasst — kein Alarm."""
    _, oa = db
    ended = datetime(2026, 9, 20, 6, 15, tzinfo=timezone.utc)
    res = oa.rule_job_failed([_last("weekly_ingesters", 75, ended)], dict(oa.DEFAULTS))
    assert res.findings == []


def test_an_unknown_end_is_not_reported_as_an_error(db):
    """rc NULL = vom Sampler geschlossen; die Seite zeigt das als 'aborted'."""
    _, oa = db
    ended = datetime(2026, 9, 20, 6, 15, tzinfo=timezone.utc)
    res = oa.rule_job_failed([_last("dossier_worker", None, ended)], dict(oa.DEFAULTS))
    assert res.findings == []


def test_without_the_query_the_rule_says_nothing(db):
    """Kein last_runs im Kontext (SQLite-Pfad) → offene Alarme bleiben stehen."""
    _, oa = db
    s = _sample()
    ctx = {"prev_full": None, "open": [], "medians": {}, "daily_max": []}
    res = [r for r in oa.evaluate(s, ctx, dict(oa.DEFAULTS)) if r.kind == "job_failed"]
    assert len(res) == 1 and res[0].checked is False
