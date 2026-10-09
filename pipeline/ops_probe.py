"""Messfuehler fuer das Ops-Dashboard (#104): eine Zeile je Minute nach ops_samples.

Was gemessen wird und woher es kommt:

  GPU lokal      nvidia-smi (Speicher, Last, Temperatur, Watt); geladenes Modell
                 ueber GET /v1/models des llama-servers; welcher JOB die Karte
                 haelt aus den Besitzvermerken data/llama-server.<job>.pid
                 (gpu_guard.sh / gpu_handover.py), sonst per pgrep gegen
                 dieselbe Musterliste wie der Kollisionswaechter.
  bequiet        REMOTE_EMBED_HOST, nur ueber die Modell-API (Owner: kein SSH).
                 Backend-neutral, weil bequiet perspektivisch von Ollama auf
                 llama.cpp wechselt: llama.cpp antwortet auf /health, Ollama
                 auf /api/ps — genau eines von beiden trifft.
  Rechner        /proc/stat (CPU, als Delta zur letzten Messung), /proc/meminfo,
                 getloadavg.
  Platten        alle physischen Geraete unter /sys/block (loop/ram/zram/sr
                 ausgenommen): Fuellstand je eingehaengter Partition (statvfs),
                 Lese-/Schreibdurchsatz und Beschaeftigung aus /sys/block/*/stat
                 (Delta), Temperatur aus hwmon (NVMe ohne Root; SATA nur mit
                 drivetemp-Modul), SMART ueber `sudo -n smartctl -j -n standby
                 -A -H` — nur wenn die sudoers-Zeile aus deploy/sudoers/
                 catandary-smart eingespielt ist, sonst bleibt `smart` leer.
                 `-n standby` weckt eine schlafende HDD nicht auf.
  Postgres       Groesse, Verbindungen, max_connections, lange Abfragen.

Teure Zaehlungen (Backlog ueber get_unprocessed_entries ~2 s, Review-Queue,
Tabellengroessen, SMART) laufen nur in einer
VOLLEN Messung — jede zehnte Minute, oder mit --full. Die Zeile traegt dann
`is_full = true`; das Dashboard nimmt fuer diese Werte die letzte volle Zeile.

Deltas (CPU, Platten-I/O) brauchen die vorige Messung: data/ops_sampler_state.json.
Fehlt sie (erster Lauf, Neustart), bleiben die Delta-Felder NULL statt falsch.

Jeder Fuehler faengt seine Fehler selbst — ein ausgeschaltetes bequiet oder ein
fehlendes smartctl darf die Messung der uebrigen Werte nie verhindern.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from pipeline import remote_gpu
from pipeline.config import DATA_DIR
from pipeline.db import USE_POSTGRES, get_connection

logger = logging.getLogger(__name__)

LLAMACPP_HOST = os.getenv("LLAMACPP_HOST", "http://127.0.0.1:8090")
STATE_PATH = DATA_DIR / "ops_sampler_state.json"
RETENTION_DAYS = int(os.getenv("OPS_RETENTION_DAYS", "7"))
FULL_EVERY_MIN = int(os.getenv("OPS_FULL_EVERY_MIN", "10"))
SMARTCTL = os.getenv("SMARTCTL", "/usr/sbin/smartctl")
#: Woher der Kollisionswaechter seine Musterliste hat — hier mitgelesen, damit
#: der Sampler denselben Begriff von "GPU-Job" hat und nicht driftet.
GPU_GUARD_SH = Path(__file__).resolve().parent.parent / "scripts" / "lib" / "gpu_guard.sh"
_DEFAULT_PATTERNS = (r"scheduled_cycle\.sh|full_cycle_cron\.sh|run_full_cycle|signal_batch|"
                     r"weekly_ingesters\.sh|research_pulse|"
                     r"newsletter_deep_dive")
SKIP_BLOCK = re.compile(r"^(loop|ram|zram|sr|fd|dm-|md)")

MIB = 1024 * 1024


def _run(cmd: list[str], timeout: float = 15) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


# --- GPU lokal ------------------------------------------------------------------

def probe_gpu() -> dict:
    out = {"gpu_mem_used_mib": None, "gpu_mem_total_mib": None, "gpu_util_pct": None,
           "gpu_temp_c": None, "gpu_power_w": None}
    try:
        r = _run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,"
                  "temperature.gpu,power.draw", "--format=csv,noheader,nounits"])
        if r.returncode == 0 and r.stdout.strip():
            out.update(parse_nvidia_smi(r.stdout))
    except Exception as e:                                          # noqa: BLE001
        logger.warning("nvidia-smi: %s", e)
    return out


def parse_nvidia_smi(text: str) -> dict:
    """Erste Zeile von `--query-gpu=memory.used,memory.total,utilization.gpu,
    temperature.gpu,power.draw --format=csv,noheader,nounits`."""
    parts = [p.strip() for p in text.strip().splitlines()[0].split(",")]
    def num(i, cast):
        try:
            return cast(float(parts[i]))
        except (IndexError, ValueError):
            return None
    return {"gpu_mem_used_mib": num(0, int), "gpu_mem_total_mib": num(1, int),
            "gpu_util_pct": num(2, int), "gpu_temp_c": num(3, int),
            "gpu_power_w": num(4, float)}


def gpu_evict_patterns() -> str:
    """GPU_EVICT_PATTERNS aus scripts/lib/gpu_guard.sh (bekannte Tagesanwendungen, die der
    Nachtlauf stoppt: nemo-speech, whisper-server)."""
    try:
        m = re.search(r'GPU_EVICT_PATTERNS="\$\{GPU_EVICT_PATTERNS:-([^}]*)\}"',
                      GPU_GUARD_SH.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    except OSError:
        pass
    return "nemo-speech|whisper-server"


def probe_gpu_known() -> int | None:
    """VRAM (MiB) der bekannten Tagesanwendungen — für die Regel gpu_foreign (nicht gespeichert)."""
    pat = gpu_evict_patterns()
    if not pat:
        return 0
    try:
        r = _run(["nvidia-smi", "--query-compute-apps=process_name,used_memory", "--format=csv,noheader,nounits"])
    except Exception:                                               # noqa: BLE001
        return None
    if r.returncode != 0:
        return None
    total = 0
    for line in r.stdout.strip().splitlines():
        name, _, mem = line.rpartition(",")
        if re.search(pat, name.strip()):
            try:
                total += int(float(mem.strip()))
            except ValueError:
                pass
    return total


def probe_local_model() -> str | None:
    try:
        r = httpx.get(f"{LLAMACPP_HOST}/v1/models", timeout=3)
        r.raise_for_status()
        entry = (r.json().get("data") or [{}])[0]
        return entry.get("id") or None
    except Exception:                                               # noqa: BLE001
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def gpu_guard_patterns() -> str:
    """Die ERE-Liste aus scripts/lib/gpu_guard.sh — dieselbe Definition von
    "GPU-Job" wie der Kollisionswaechter. Fallback auf eine eingebaute Liste,
    wenn die Datei fehlt (Tests, fremde Checkouts)."""
    try:
        m = re.search(r'GPU_GUARD_PATTERNS="\$\{GPU_GUARD_PATTERNS:-([^}]+)\}"',
                      GPU_GUARD_SH.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    except OSError:
        pass
    return _DEFAULT_PATTERNS


def probe_gpu_job(data_dir: Path = DATA_DIR) -> str | None:
    """Wer haelt die Karte? Erst die Besitzvermerke (MAINPID OWNERPID je Job),
    dann — ohne Vermerk — die Prozessliste gegen die Waechter-Muster."""
    for f in sorted(data_dir.glob("llama-server.*.pid")):
        try:
            owner = int(f.read_text().split()[1])
        except (OSError, IndexError, ValueError):
            continue
        if _pid_alive(owner):
            return f.name[len("llama-server."):-len(".pid")]
    try:
        r = _run(["pgrep", "-f", "-a", gpu_guard_patterns()], timeout=5)
    except Exception:                                               # noqa: BLE001
        return None
    me = os.getpid()
    for line in r.stdout.splitlines():
        pid, _, cmd = line.partition(" ")
        if pid.strip() == str(me) or not cmd.strip():
            continue
        # Werkzeuge, die den Namen nur ZITIEREN (grep, tail, Editor), sind keine Jobs.
        if re.search(r"\b(grep|pgrep|tail|less|vim?|nano|cat)\b", cmd.split()[0]):
            continue
        m = re.search(gpu_guard_patterns(), cmd)
        if m:
            return m.group(0).removesuffix(".sh")
    return None


# --- bequiet -----------------------------------------------------------------------

def probe_remote(host: str | None = None, now: datetime | None = None) -> dict:
    """Backend-neutral: llama.cpp beantwortet /health (Ollama 404), Ollama
    beantwortet /api/ps (llama.cpp 404). Genau eines trifft — oder keines."""
    host = host if host is not None else remote_gpu.REMOTE_EMBED_HOST
    out = {"remote_backend": None, "remote_in_window": remote_gpu.window_open(now),
           "remote_model": None}
    if not host:
        return out
    try:
        r = httpx.get(f"{host}/health", timeout=2)
        if r.status_code == 200:
            out["remote_backend"] = "llamacpp"
            try:
                m = httpx.get(f"{host}/v1/models", timeout=2).json()
                out["remote_model"] = ((m.get("data") or [{}])[0]).get("id")
            except Exception:                                       # noqa: BLE001
                pass
            return out
    except Exception:                                               # noqa: BLE001
        out["remote_backend"] = "down"
        return out
    try:
        r = httpx.get(f"{host}/api/ps", timeout=2)
        if r.status_code == 200:
            out["remote_backend"] = "ollama"
            models = r.json().get("models") or []
            out["remote_model"] = models[0].get("name") if models else None
            return out
    except Exception:                                               # noqa: BLE001
        pass
    out["remote_backend"] = "down"
    return out


# --- Rechner -----------------------------------------------------------------------

def read_cpu_counters(path: str = "/proc/stat") -> list[int] | None:
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline().split()
        return [int(x) for x in first[1:]]
    except (OSError, ValueError):
        return None


def cpu_pct_from(prev: list[int] | None, cur: list[int] | None) -> float | None:
    """Anteil Nicht-Idle zwischen zwei /proc/stat-Lesungen (idle = Felder 4+5)."""
    if not prev or not cur or len(cur) < 5 or len(prev) < 5:
        return None
    total = sum(cur) - sum(prev)
    idle = (cur[3] + cur[4]) - (prev[3] + prev[4])
    if total <= 0:
        return None
    return round(100.0 * (total - idle) / total, 1)


def probe_memory(path: str = "/proc/meminfo") -> dict:
    vals = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                vals[k.strip()] = int(v.split()[0])                   # kB
    except (OSError, ValueError, IndexError):
        return {"mem_used_mib": None, "mem_total_mib": None}
    total = vals.get("MemTotal")
    avail = vals.get("MemAvailable")
    if total is None or avail is None:
        return {"mem_used_mib": None, "mem_total_mib": None}
    return {"mem_used_mib": (total - avail) // 1024, "mem_total_mib": total // 1024}


# --- Platten -----------------------------------------------------------------------

def _read(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def mounts_by_device(path: str = "/proc/mounts") -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                dev, mnt = line.split()[:2]
                if dev.startswith("/dev/") and dev[5:] not in out:
                    out[dev[5:]] = mnt.replace("\\040", " ")
    except OSError:
        pass
    return out


def list_block_devices(sys_block: Path = Path("/sys/block")) -> list[dict]:
    """Physische Geraete mit Modell, Typ und ihren Partitionen."""
    devs = []
    try:
        names = sorted(p.name for p in sys_block.iterdir())
    except OSError:
        return devs
    for name in names:
        if SKIP_BLOCK.match(name):
            continue
        base = sys_block / name
        rota = _read(base / "queue" / "rotational")
        parts = sorted(p.name for p in base.iterdir() if p.is_dir() and p.name.startswith(name))
        devs.append({
            "dev": name,
            "model": (_read(base / "device" / "model") or "").strip() or None,
            "rotational": rota == "1",
            "size_bytes": int(_read(base / "size") or 0) * 512,
            "partitions": parts,
        })
    return devs


def read_disk_stat(base: Path) -> tuple[int, int, int] | None:
    """(gelesene Bytes, geschriebene Bytes, Beschaeftigung ms) aus /sys/block/<dev>/stat."""
    txt = _read(base / "stat")
    if not txt:
        return None
    f = txt.split()
    try:
        return int(f[2]) * 512, int(f[6]) * 512, int(f[9])
    except (IndexError, ValueError):
        return None


def disk_temp_c(name: str, sys_root: Path = Path("/sys")) -> float | None:
    """NVMe: /sys/class/nvme/<ctrl>/hwmon*/temp1_input (ohne Root). SATA: nur mit
    drivetemp (/sys/block/<dev>/device/hwmon/hwmon*/temp1_input)."""
    cands: list[Path] = []
    m = re.match(r"^(nvme\d+)n\d+$", name)
    if m:
        cands += list((sys_root / "class" / "nvme" / m.group(1)).glob("hwmon*/temp1_input"))
    cands += list((sys_root / "block" / name / "device" / "hwmon").glob("hwmon*/temp1_input"))
    for c in cands:
        v = _read(c)
        if v and v.lstrip("-").isdigit():
            return round(int(v) / 1000, 1)
    return None


def smart_available() -> bool:
    return bool(shutil.which("sudo")) and Path(SMARTCTL).exists()


def probe_smart(dev: str) -> dict | None:
    """SMART-Kurzbild je Geraet; None, wenn sudo/smartctl nicht freigeschaltet
    sind oder die Platte schlaeft (-n standby → rc-Bit 1)."""
    if not smart_available():
        return None
    try:
        r = _run(["sudo", "-n", SMARTCTL, "-j", "-n", "standby", "-A", "-H", f"/dev/{dev}"],
                 timeout=25)
    except Exception as e:                                          # noqa: BLE001
        return {"error": str(e)[:80]}
    if r.returncode & 2 and not r.stdout.strip():
        return {"standby": True}
    if not r.stdout.strip():
        return {"error": (r.stderr.strip() or f"rc={r.returncode}")[:80]}
    try:
        return parse_smart_json(json.loads(r.stdout))
    except (ValueError, TypeError) as e:
        return {"error": f"json: {e}"[:80]}


def parse_smart_json(d: dict) -> dict:
    """Das Wenige, das fuer Alarme und Anzeige zaehlt — bei NVMe und ATA verschieden
    benannt, hier auf gemeinsame Schluessel gebracht."""
    out: dict = {
        "passed": (d.get("smart_status") or {}).get("passed"),
        "temp_c": (d.get("temperature") or {}).get("current"),
        "power_on_hours": (d.get("power_on_time") or {}).get("hours"),
    }
    nv = d.get("nvme_smart_health_information_log")
    if nv:
        out.update({
            "type": "nvme",
            "percentage_used": nv.get("percentage_used"),
            "available_spare": nv.get("available_spare"),
            "media_errors": nv.get("media_errors"),
            "critical_warning": nv.get("critical_warning"),
            # Minuten, die das Laufwerk ueber SEINER eigenen Warn- bzw.
            # Kritisch-Schwelle verbracht hat. Das ist die geraeteeigene
            # Wahrheit ueber "zu heiss" — genauer als jede Zahl, die wir von
            # aussen setzen, weil jeder Controller sie selbst kennt.
            "warning_temp_time": nv.get("warning_temp_time"),
            "critical_comp_time": nv.get("critical_comp_time"),
        })
        return out
    table = ((d.get("ata_smart_attributes") or {}).get("table")) or []
    by_id = {a.get("id"): (a.get("raw") or {}).get("value") for a in table}
    out.update({
        "type": "ata",
        "reallocated": by_id.get(5),
        "pending": by_id.get(197),
        "uncorrectable": by_id.get(198),
    })
    if out["power_on_hours"] is None:
        out["power_on_hours"] = by_id.get(9)
    return out


def probe_disks(prev: dict | None, elapsed_s: float | None, *, with_smart: bool,
                sys_block: Path = Path("/sys/block"), sys_root: Path = Path("/sys"),
                mounts: dict[str, str] | None = None) -> tuple[list[dict], dict]:
    """Liefert (Liste je Geraet, neue Zaehlerstaende fuer die State-Datei)."""
    mounts = mounts if mounts is not None else mounts_by_device()
    counters: dict = {}
    disks: list[dict] = []
    for d in list_block_devices(sys_block):
        name = d["dev"]
        entry = {"dev": name, "model": d["model"], "rotational": d["rotational"],
                 "size_bytes": d["size_bytes"], "temp_c": disk_temp_c(name, sys_root),
                 "mounts": [], "read_bytes_s": None, "write_bytes_s": None, "busy_pct": None}
        for part in [name, *d["partitions"]]:
            mnt = mounts.get(part)
            if not mnt:
                continue
            try:
                st = os.statvfs(mnt)
            except OSError:
                continue
            entry["mounts"].append({
                "part": part, "mount": mnt,
                "size_bytes": st.f_frsize * st.f_blocks,
                "used_bytes": st.f_frsize * (st.f_blocks - st.f_bfree),
                "avail_bytes": st.f_frsize * st.f_bavail,
            })
        cur = read_disk_stat(sys_block / name)
        if cur:
            counters[name] = list(cur)
            p = (prev or {}).get(name)
            if p and elapsed_s and elapsed_s > 0:
                rd, wr, ticks = (cur[i] - p[i] for i in range(3))
                if rd >= 0 and wr >= 0 and ticks >= 0:
                    entry["read_bytes_s"] = int(rd / elapsed_s)
                    entry["write_bytes_s"] = int(wr / elapsed_s)
                    entry["busy_pct"] = round(min(100.0, ticks / (elapsed_s * 10)), 1)
        if with_smart:
            entry["smart"] = probe_smart(name)
        disks.append(entry)
    return disks, counters


# --- Postgres ---------------------------------------------------------------------

def probe_db(full: bool) -> dict:
    out = {"db_size_bytes": None, "db_connections": None, "db_max_connections": None,
           "db_long_queries": None, "tables": None, "backlog_unprocessed": None,
           "review_queue": None, "fulltext_vectors_missing": None}
    if not USE_POSTGRES:
        return out
    try:
        with get_connection() as conn:
            cur = conn._conn.cursor()
            cur.execute("SELECT pg_database_size(current_database())")
            out["db_size_bytes"] = int(cur.fetchone()[0])
            cur.execute("SELECT count(*), "
                        "count(*) FILTER (WHERE state = 'active' AND now() - query_start > interval '60 s') "
                        "FROM pg_stat_activity WHERE datname = current_database()")
            n, longq = cur.fetchone()
            out["db_connections"], out["db_long_queries"] = int(n), int(longq)
            cur.execute("SHOW max_connections")
            out["db_max_connections"] = int(cur.fetchone()[0])
            if full:
                cur.execute("SELECT relname, pg_total_relation_size(oid) FROM pg_class "
                            "WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace "
                            "ORDER BY 2 DESC LIMIT 8")
                out["tables"] = {r[0]: int(r[1]) for r in cur.fetchall()}
                cur.execute("SELECT count(*) FROM trends WHERE status = 'draft' AND confidence >= 0.85")
                out["review_queue"] = int(cur.fetchone()[0])
                # fulltext_vectors_missing bleibt NULL: der zweite Vektorraum (#102) ist
                # seit 2026-09-11 zurueckgebaut (Owner) — kein 1,7-Mio-Scan fuer nichts.
    except Exception as e:                                          # noqa: BLE001
        logger.warning("db probe: %s", e)
    if full:
        try:
            from pipeline.db import get_unprocessed_entries
            out["backlog_unprocessed"] = len(get_unprocessed_entries(limit=99999))
        except Exception as e:                                      # noqa: BLE001
            logger.warning("backlog probe: %s", e)
    return out


# --- Zusammenbau ------------------------------------------------------------------

def load_state(path: Path = STATE_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)


def is_full_minute(now: datetime, every: int = FULL_EVERY_MIN) -> bool:
    return now.minute % every == 0


def take_sample(*, full: bool | None = None, now: datetime | None = None,
                state_path: Path = STATE_PATH) -> dict:
    """Eine komplette Messung als Dict (Spaltennamen von ops_samples), Deltas
    gegen die State-Datei, State danach fortgeschrieben."""
    now = now or datetime.now(timezone.utc)
    full = is_full_minute(now.astimezone()) if full is None else full
    state = load_state(state_path)
    prev_t = state.get("t")
    elapsed = (time.time() - prev_t) if prev_t else None
    cpu_now = read_cpu_counters()

    sample: dict = {"ts": now, "is_full": full}
    sample.update(probe_gpu())
    sample["gpu_model"] = probe_local_model()
    sample["gpu_job"] = probe_gpu_job()
    sample["gpu_known_mib"] = probe_gpu_known()     # nur für ops_alerts, nicht in COLUMNS
    sample.update(probe_remote(now=now.astimezone()))
    sample["cpu_pct"] = cpu_pct_from(state.get("cpu"), cpu_now)
    try:
        sample["load1"] = round(os.getloadavg()[0], 2)
    except OSError:
        sample["load1"] = None
    sample.update(probe_memory())
    disks, counters = probe_disks(state.get("disks"), elapsed, with_smart=full)
    sample["disks"] = disks
    sample.update(probe_db(full))

    save_state({"t": time.time(), "cpu": cpu_now, "disks": counters}, state_path)
    return sample


COLUMNS = ["ts", "is_full", "gpu_mem_used_mib", "gpu_mem_total_mib", "gpu_util_pct", "gpu_temp_c",
           "gpu_power_w", "gpu_model", "gpu_job", "remote_backend", "remote_in_window",
           "remote_model", "cpu_pct", "load1", "mem_used_mib", "mem_total_mib", "db_size_bytes",
           "db_connections", "db_max_connections", "db_long_queries", "disks", "tables",
           "backlog_unprocessed", "review_queue", "fulltext_vectors_missing"]


def write_sample(sample: dict) -> None:
    row = []
    for c in COLUMNS:
        v = sample.get(c)
        if c in ("disks", "tables"):
            v = json.dumps(v) if v is not None else None
        elif c == "ts":
            v = v if USE_POSTGRES else v.isoformat()
        elif c in ("is_full", "remote_in_window") and not USE_POSTGRES and v is not None:
            v = int(v)
        row.append(v)
    ph = ", ".join("?" for _ in COLUMNS)
    with get_connection() as conn:
        conn.execute(f"INSERT INTO ops_samples ({', '.join(COLUMNS)}) VALUES ({ph})", row)


def prune_samples(days: int = RETENTION_DAYS, now: datetime | None = None) -> int:
    """Rohwerte aelter als `days` loeschen (Owner: eine Woche reicht)."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    with get_connection() as conn:
        if USE_POSTGRES:
            cur = conn._conn.cursor()
            cur.execute("DELETE FROM ops_samples WHERE ts < %s", (cutoff,))
            return cur.rowcount
        cur = conn.execute("DELETE FROM ops_samples WHERE ts < ?", (cutoff.isoformat(),))
        return cur.rowcount
