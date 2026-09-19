"""Ops-Dashboard-Messfuehler (#104, Stufe 1): reine Parser und Deltas, die
Platten-Enumeration gegen einen nachgebauten /sys-Baum, die Backend-Erkennung
fuer bequiet gegen einen Fake-Transport, und Schreiben/Aufraeumen in SQLite."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from pipeline import ops_probe as op


# --- Parser ----------------------------------------------------------------------

def test_parse_nvidia_smi_line():
    assert op.parse_nvidia_smi("21986, 24576, 0, 44, 20.33\n") == {
        "gpu_mem_used_mib": 21986, "gpu_mem_total_mib": 24576, "gpu_util_pct": 0,
        "gpu_temp_c": 44, "gpu_power_w": 20.33}


def test_parse_nvidia_smi_tolerates_na():
    out = op.parse_nvidia_smi("100, 200, [N/A], 33, [N/A]")
    assert out["gpu_util_pct"] is None and out["gpu_power_w"] is None
    assert out["gpu_mem_used_mib"] == 100


def test_cpu_pct_from_two_readings():
    prev = [100, 0, 50, 800, 50, 0, 0, 0, 0, 0]
    cur = [200, 0, 100, 1000, 100, 0, 0, 0, 0, 0]
    # total delta 400, idle delta 250 → 37.5 % busy
    assert op.cpu_pct_from(prev, cur) == 37.5
    assert op.cpu_pct_from(None, cur) is None
    assert op.cpu_pct_from(cur, cur) is None


def test_memory_from_meminfo(tmp_path):
    p = tmp_path / "meminfo"
    p.write_text("MemTotal:       65641472 kB\nMemFree:  1000 kB\nMemAvailable:   59772928 kB\n")
    assert op.probe_memory(str(p)) == {"mem_used_mib": (65641472 - 59772928) // 1024,
                                       "mem_total_mib": 65641472 // 1024}


def test_smart_json_nvme_and_ata():
    nvme = op.parse_smart_json({
        "smart_status": {"passed": True}, "temperature": {"current": 41},
        "power_on_time": {"hours": 1234},
        "nvme_smart_health_information_log": {"percentage_used": 3, "available_spare": 100,
                                              "media_errors": 0, "critical_warning": 0}})
    # warning_temp_time/critical_comp_time seit 2026-09-16: das Laufwerk selbst
    # sagt, wie lange es ueber SEINER Schwelle war — genauer als jede Zahl, die
    # wir von aussen setzen (Anlass: Alarm bei 65,8 °C, Zaehler stand auf 0).
    assert nvme == {"passed": True, "temp_c": 41, "power_on_hours": 1234, "type": "nvme",
                    "warning_temp_time": None, "critical_comp_time": None,
                    "percentage_used": 3, "available_spare": 100, "media_errors": 0,
                    "critical_warning": 0}
    ata = op.parse_smart_json({
        "smart_status": {"passed": True}, "temperature": {"current": 35},
        "ata_smart_attributes": {"table": [
            {"id": 5, "raw": {"value": 0}}, {"id": 9, "raw": {"value": 20000}},
            {"id": 197, "raw": {"value": 2}}, {"id": 198, "raw": {"value": 0}}]}})
    assert ata["type"] == "ata" and ata["reallocated"] == 0 and ata["pending"] == 2
    assert ata["power_on_hours"] == 20000            # aus Attribut 9, wenn power_on_time fehlt


def test_gpu_guard_patterns_read_from_the_shell_file():
    pats = op.gpu_guard_patterns()
    assert "scheduled_cycle" in pats and "research_pulse" in pats


# --- Platten gegen einen nachgebauten /sys-Baum --------------------------------------

def _fake_sys(tmp_path: Path) -> tuple[Path, Path]:
    sys_root = tmp_path / "sys"
    blk = sys_root / "block"
    for name, model, rota, parts in (("nvme1n1", "Lexar SSD NM790 2TB", "0", ["nvme1n1p1", "nvme1n1p2"]),
                                     ("sda", "ST2000DM008", "1", ["sda2"]),
                                     ("loop0", "", "0", [])):
        d = blk / name
        (d / "queue").mkdir(parents=True)
        (d / "device").mkdir()
        (d / "queue" / "rotational").write_text(rota)
        if model:
            (d / "device" / "model").write_text(model + "\n")
        (d / "size").write_text("3907029168")
        (d / "stat").write_text("1 0 2000 10 2 0 4000 20 0 500 30")     # rd 2000 sect, wr 4000 sect, ticks 500 ms
        for p in parts:
            (d / p).mkdir()
    hw = sys_root / "class" / "nvme" / "nvme1" / "hwmon1"
    hw.mkdir(parents=True)
    (hw / "temp1_input").write_text("39850\n")
    return sys_root, blk


def test_list_block_devices_skips_loop_and_reads_model(tmp_path):
    _, blk = _fake_sys(tmp_path)
    devs = {d["dev"]: d for d in op.list_block_devices(blk)}
    assert set(devs) == {"nvme1n1", "sda"}
    assert devs["nvme1n1"]["model"] == "Lexar SSD NM790 2TB"
    assert devs["nvme1n1"]["partitions"] == ["nvme1n1p1", "nvme1n1p2"]
    assert devs["sda"]["rotational"] is True
    assert devs["sda"]["size_bytes"] == 3907029168 * 512


def test_probe_disks_deltas_temp_and_mounts(tmp_path, monkeypatch):
    sys_root, blk = _fake_sys(tmp_path)
    mounts = {"nvme1n1p2": str(tmp_path)}               # ein echter Pfad fuer statvfs
    prev = {"nvme1n1": [0, 0, 0], "sda": [1000 * 512, 2000 * 512, 200]}
    disks, counters = op.probe_disks(prev, 60.0, with_smart=False, sys_block=blk,
                                     sys_root=sys_root, mounts=mounts)
    by = {d["dev"]: d for d in disks}
    nv = by["nvme1n1"]
    assert nv["temp_c"] == 39.9
    assert nv["read_bytes_s"] == 2000 * 512 // 60 and nv["write_bytes_s"] == 4000 * 512 // 60
    assert nv["busy_pct"] == round(500 / 600, 1)
    assert nv["mounts"][0]["mount"] == str(tmp_path) and nv["mounts"][0]["size_bytes"] > 0
    sd = by["sda"]
    assert sd["temp_c"] is None and sd["mounts"] == []
    assert sd["read_bytes_s"] == 1000 * 512 // 60 and sd["busy_pct"] == 0.5
    assert "smart" not in sd
    assert counters["nvme1n1"] == [2000 * 512, 4000 * 512, 500]


def test_probe_disks_without_previous_state_leaves_deltas_null(tmp_path):
    sys_root, blk = _fake_sys(tmp_path)
    disks, _ = op.probe_disks(None, None, with_smart=False, sys_block=blk, sys_root=sys_root, mounts={})
    assert all(d["read_bytes_s"] is None and d["busy_pct"] is None for d in disks)


def test_mounts_by_device_first_mount_wins(tmp_path):
    p = tmp_path / "mounts"
    p.write_text("/dev/nvme1n1p2 / ext4 rw 0 0\n/dev/nvme1n1p2 /snap/x ext4 rw 0 0\n"
                 "/dev/sda2 /mnt/data\\040hdd ext4 rw 0 0\ntmpfs /run tmpfs rw 0 0\n")
    assert op.mounts_by_device(str(p)) == {"nvme1n1p2": "/", "sda2": "/mnt/data hdd"}


# --- bequiet: Backend-Erkennung ----------------------------------------------------

def _transport(routes: dict[str, tuple[int, dict]]):
    def handler(request: httpx.Request) -> httpx.Response:
        code, body = routes.get(request.url.path, (404, {}))
        return httpx.Response(code, json=body)
    return httpx.MockTransport(handler)


def _patch_httpx_get(monkeypatch, routes):
    client = httpx.Client(transport=_transport(routes))
    monkeypatch.setattr(op.httpx, "get", lambda url, **kw: client.get(url, **kw))


def test_probe_remote_detects_llamacpp(monkeypatch):
    _patch_httpx_get(monkeypatch, {"/health": (200, {"status": "ok"}),
                                   "/v1/models": (200, {"data": [{"id": "qwen3-emb.gguf"}]})})
    out = op.probe_remote("http://x", now=datetime(2026, 9, 11, 10, 0))
    assert out["remote_backend"] == "llamacpp" and out["remote_model"] == "qwen3-emb.gguf"
    assert out["remote_in_window"] is True


def test_probe_remote_detects_ollama_with_and_without_loaded_model(monkeypatch):
    _patch_httpx_get(monkeypatch, {"/api/ps": (200, {"models": [{"name": "qwen3-embedding:latest"}]})})
    out = op.probe_remote("http://x", now=datetime(2026, 9, 11, 20, 0))
    assert out["remote_backend"] == "ollama" and out["remote_model"] == "qwen3-embedding:latest"
    assert out["remote_in_window"] is False
    _patch_httpx_get(monkeypatch, {"/api/ps": (200, {"models": []})})
    assert op.probe_remote("http://x")["remote_model"] is None


def test_probe_remote_down_and_unconfigured(monkeypatch):
    def boom(url, **kw):
        raise httpx.ConnectTimeout("timed out")
    monkeypatch.setattr(op.httpx, "get", boom)
    assert op.probe_remote("http://x")["remote_backend"] == "down"
    assert op.probe_remote("")["remote_backend"] is None


# --- GPU-Job aus den Besitzvermerken ------------------------------------------------

def test_probe_gpu_job_from_owner_file(tmp_path, monkeypatch):
    (tmp_path / "llama-server.scheduled_cycle-judge.pid").write_text(f"4242 {os.getpid()}\n")
    (tmp_path / "llama-server.dead_job.pid").write_text("1 999999\n")
    monkeypatch.setattr(op, "_run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no pgrep")))
    assert op.probe_gpu_job(tmp_path) == "scheduled_cycle-judge"


def test_probe_gpu_job_falls_back_to_process_list(tmp_path, monkeypatch):
    class R:
        stdout = (f"{os.getpid()} python -m scripts.ops_sampler\n"
                  "777 tail -f scheduled_cycle.sh.log\n"
                  "888 /bin/bash scripts/weekly_ingesters.sh\n")
    monkeypatch.setattr(op, "_run", lambda *a, **k: R())
    assert op.probe_gpu_job(tmp_path) == "weekly_ingesters"


# --- Schreiben, volle Minute, Aufraeumen (SQLite) --------------------------------------

@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "t.db"))
    import importlib
    from pipeline import config, db
    importlib.reload(config)
    importlib.reload(db)
    importlib.reload(op)
    db.init_db()
    return db


def test_is_full_minute():
    assert op.is_full_minute(datetime(2026, 9, 11, 9, 20))
    assert not op.is_full_minute(datetime(2026, 9, 11, 9, 21))


def test_write_and_prune(sqlite_db):
    now = datetime.now(timezone.utc)
    old = {"ts": now - timedelta(days=8), "is_full": True, "gpu_mem_used_mib": 1,
           "disks": [{"dev": "sda"}], "tables": {"trends": 5}}
    new = {"ts": now, "is_full": False, "gpu_mem_used_mib": 2, "remote_in_window": True}
    op.write_sample(old)
    op.write_sample(new)
    with sqlite_db.get_connection() as conn:
        rows = conn.execute("SELECT ts, is_full, disks, tables, remote_in_window FROM ops_samples ORDER BY ts").fetchall()
    assert len(rows) == 2
    assert json.loads(rows[0]["disks"]) == [{"dev": "sda"}] and rows[0]["is_full"] == 1
    assert rows[1]["disks"] is None and rows[1]["remote_in_window"] == 1
    assert op.prune_samples(days=7, now=now) == 1
    with sqlite_db.get_connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM ops_samples").fetchone()["n"] == 1


def test_ops_tables_exist_after_init(sqlite_db):
    with sqlite_db.get_connection() as conn:
        for t in ("ops_samples", "ops_events", "ops_alerts"):
            conn.execute(f"SELECT count(*) FROM {t}").fetchone()
