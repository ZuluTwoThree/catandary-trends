"""Alarme des Ops-Dashboards (#104, Stufe 5).

Nach jeder Messung ruft scripts/ops_sampler.py `run(sample)` auf. Jede Regel
schaut auf die frische Messung (und, wo noetig, auf die Datenbank) und liefert
die Befunde, die JETZT gelten. `sync()` vergleicht sie mit den offenen Zeilen
in `ops_alerts`: neu → Zeile anlegen, alt und nicht mehr gemeldet → entwarnen.
Beides in EINER Mail je Lauf ("raised … / resolved …"), dazwischen Ruhe —
die Tabelle ist das Gedaechtnis, das Doppel-Mails verhindert.

Wichtig fuer die Entwarnung: eine Regel, die in dieser Minute nichts pruefen
KONNTE (SMART kommt nur alle 10 Minuten, der Backlog auch), meldet das als
"nicht geprueft" — ihre offenen Alarme bleiben dann stehen. Sonst wuerde jede
Zwischenminute jeden SMART-Alarm entwarnen und die volle Minute ihn neu
ausloesen: neun Mails die Stunde fuer einen Zustand, der sich nicht aendert.

Schwellen: ops_alerts.yaml im Repo-Root (Defaults unten), ohne Code aenderbar.
Der Alarmpfad darf den Sampler nie zu Fall bringen — `run()` faengt alles.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from pipeline.config import PROJECT_ROOT
from pipeline.db import USE_POSTGRES, get_connection

logger = logging.getLogger(__name__)

THRESHOLDS_PATH = PROJECT_ROOT / "ops_alerts.yaml"
DEFAULTS: dict = {
    "disk_free_pct_min": 10, "disk_free_pct_min_system": 20,
    "disk_temp_hdd_max_c": 55, "disk_temp_ssd_max_c": 68,
    "nvme_wear_pct_max": 90, "nvme_spare_pct_min": 10,
    "gpu_temp_max_c": 88, "gpu_foreign_vram_mib": 1500,
    "db_connections_pct_max": 80,
    "job_slow_factor": 2.0, "job_hang_hours": 6,
    "job_failed_lookback_days": 14, "job_failed_ignore_rc": [75],
    "backlog_growth_days": 3, "sampler_stale_min": 5,
}


def load_thresholds(path: Path = THRESHOLDS_PATH) -> dict:
    t = dict(DEFAULTS)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            t.update({k: v for k, v in data.items() if k in DEFAULTS and v is not None})
    except OSError:
        pass
    except yaml.YAMLError as e:
        logger.warning("ops_alerts.yaml unlesbar (%s) — Defaults", e)
    return t


@dataclass(frozen=True)
class Finding:
    kind: str
    key: str
    message: str


@dataclass
class RuleResult:
    """`checked=False` = diese Minute keine Aussage moeglich → offene Alarme
    dieser Art bleiben unangetastet."""
    kind: str
    checked: bool
    findings: list[Finding]


# --- Regeln ---------------------------------------------------------------------------

def rule_disks(sample: dict, prev_full: dict | None, t: dict) -> list[RuleResult]:
    disks = sample.get("disks") or []
    free: list[Finding] = []
    temp: list[Finding] = []
    smart: list[Finding] = []
    smart_checked = False
    prev_smart = {d.get("dev"): (d.get("smart") or {}) for d in (prev_full or {}).get("disks") or []}
    for d in disks:
        dev = d.get("dev", "?")
        for m in d.get("mounts") or []:
            size, avail = m.get("size_bytes") or 0, m.get("avail_bytes")
            if not size or avail is None or size < 2 * 1024 ** 3:
                continue
            free_pct = 100.0 * avail / size
            limit = t["disk_free_pct_min_system"] if m.get("mount") == "/" else t["disk_free_pct_min"]
            if free_pct < limit:
                free.append(Finding("disk_free", m.get("mount", dev),
                                    f"{m.get('mount')} ({dev}): {free_pct:.1f} % free, limit {limit} %"))
        s = d.get("smart")
        tc = (s or {}).get("temp_c") if s else None
        if tc is None:
            tc = d.get("temp_c")
        if tc is not None:
            lim = t["disk_temp_hdd_max_c"] if d.get("rotational") else t["disk_temp_ssd_max_c"]
            if tc > lim:
                temp.append(Finding("disk_temp", dev, f"{dev}: {tc} °C, limit {lim} °C"))
        if s and not s.get("error") and not s.get("standby"):
            smart_checked = True
            p = prev_smart.get(dev) or {}
            if s.get("passed") is False:
                smart.append(Finding("disk_smart", dev, f"{dev}: SMART overall health FAILED"))
            if s.get("type") == "nvme":
                if (s.get("critical_warning") or 0) > 0:
                    smart.append(Finding("disk_smart", dev, f"{dev}: NVMe critical warning {s['critical_warning']}"))
                if (s.get("percentage_used") or 0) >= t["nvme_wear_pct_max"]:
                    smart.append(Finding("disk_smart", dev, f"{dev}: {s['percentage_used']} % worn"))
                if s.get("available_spare") is not None and s["available_spare"] < t["nvme_spare_pct_min"]:
                    smart.append(Finding("disk_smart", dev, f"{dev}: spare {s['available_spare']} %"))
                if _rose(p.get("media_errors"), s.get("media_errors")):
                    smart.append(Finding("disk_smart", dev, f"{dev}: media errors rising {p.get('media_errors')} → {s.get('media_errors')}"))
                # Das Laufwerk als Kronzeuge: steigt die Zeit ueber SEINER
                # eigenen Schwelle, ist es zu heiss — unabhaengig davon, welche
                # Zahl wir oben gesetzt haben. Anlass 2026-09-16: der Alarm
                # feuerte bei 65,8 °C, waehrend dasselbe Laufwerk
                # warning_temp_time 0 meldete, also nie gewarnt hatte.
                for k, label in (("warning_temp_time", "minutes above its own warning temperature"),
                                 ("critical_comp_time", "minutes above its own CRITICAL temperature")):
                    if _rose(p.get(k), s.get(k)):
                        smart.append(Finding("disk_smart", dev,
                                             f"{dev}: {label} rising {p.get(k)} → {s.get(k)}"))
            elif s.get("type") == "ata":
                for k, label in (("reallocated", "reallocated sectors"), ("pending", "pending sectors"),
                                 ("uncorrectable", "uncorrectable sectors")):
                    if _rose(p.get(k), s.get(k)):
                        smart.append(Finding("disk_smart", dev, f"{dev}: {label} rising {p.get(k)} → {s.get(k)}"))
    return [RuleResult("disk_free", bool(disks), free), RuleResult("disk_temp", bool(disks), temp),
            RuleResult("disk_smart", smart_checked, smart)]


def _rose(prev, cur) -> bool:
    try:
        return prev is not None and cur is not None and int(cur) > int(prev)
    except (TypeError, ValueError):
        return False


def rule_gpu(sample: dict, open_jobs: list[str], t: dict) -> list[RuleResult]:
    temp: list[Finding] = []
    foreign: list[Finding] = []
    tc = sample.get("gpu_temp_c")
    if tc is not None and tc > t["gpu_temp_max_c"]:
        temp.append(Finding("gpu_temp", "local", f"GPU {tc} °C, limit {t['gpu_temp_max_c']} °C"))
    # Fremd = Speicher belegt, aber weder antwortet unser llama-server (/v1/models)
    # noch haelt ein bekannter Job die Karte. Der Ruhezustand (8B geladen, ~22 GB)
    # ist KEIN Alarm — dort antwortet der Server.
    used = sample.get("gpu_mem_used_mib")
    if (used is not None and used > t["gpu_foreign_vram_mib"] and not sample.get("gpu_model")
            and not sample.get("gpu_job") and not open_jobs):
        foreign.append(Finding("gpu_foreign", "local",
                               f"{used} MiB VRAM held, but no llama-server answers and no known job owns the card"))
    return [RuleResult("gpu_temp", tc is not None, temp), RuleResult("gpu_foreign", used is not None, foreign)]


def rule_db(sample: dict, t: dict) -> RuleResult:
    n, mx = sample.get("db_connections"), sample.get("db_max_connections")
    if n is None or not mx:
        return RuleResult("db_connections", False, [])
    pct = 100.0 * n / mx
    f = [Finding("db_connections", "db", f"{n} of {mx} connections ({pct:.0f} %)")] if pct > t["db_connections_pct_max"] else []
    return RuleResult("db_connections", True, f)


def rule_jobs(open_events: list[dict], medians: dict[str, float], t: dict, now: datetime) -> list[RuleResult]:
    slow: list[Finding] = []
    hang: list[Finding] = []
    for ev in open_events:
        started = ev["started_at"]
        if isinstance(started, str):
            started = datetime.fromisoformat(started)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        hours = (now - started).total_seconds() / 3600
        job = ev["job"]
        if hours > t["job_hang_hours"]:
            # lokale Uhrzeit mit Zonenkuerzel — die Mail vom 12.09. sagte "07:49 UTC" fuer 07:49 CEST
            hang.append(Finding("job_hang", job, f"{job} running for {hours:.1f} h (started {started.astimezone():%d.%m. %H:%M %Z})"))
        med = medians.get(job)
        if med and hours * 3600 > t["job_slow_factor"] * med:
            slow.append(Finding("job_slow", job, f"{job} running {hours:.1f} h, median is {med / 3600:.1f} h"))
    return [RuleResult("job_slow", True, slow), RuleResult("job_hang", True, hang)]


def rule_job_failed(last_runs: list[dict], t: dict) -> RuleResult:
    """Letzter ABGESCHLOSSENER Lauf eines Jobs endete mit rc != 0.

    Anlass 2026-09-26: der Sonntags-Retrain der Distill-Heads endete drei
    Sonntage in Folge mit rc=1 (der Trainer wurde bei 56 GB OOM-getoetet). Die
    Zeile stand jedes Mal in ops_events, aber keine Regel las sie — der
    Waechter prueft nur die Stage-Bilanz des Cycles, und am Wochenende gibt es
    die nicht. Der Alarm bleibt stehen, bis ein spaeterer Lauf desselben Jobs
    mit rc=0 endet; ein Skip des Kollisionswaechters (rc=75) ist kein Defekt
    (`job_failed_ignore_rc` in der yaml, ohne Code erweiterbar).
    """
    ignore = {int(x) for x in (t.get("job_failed_ignore_rc") or [])}
    f = [Finding("job_failed", r["job"],
                 f"{r['job']} last run ended rc={r['rc']} "
                 f"({r['ended_at'].astimezone():%d.%m. %H:%M %Z})")
         for r in last_runs
         if r.get("rc") is not None and int(r["rc"]) != 0 and int(r["rc"]) not in ignore]
    return RuleResult("job_failed", True, f)


def rule_backlog(daily_max: list[int | None], t: dict) -> RuleResult:
    """`daily_max`: Tagesmaximum des Backlogs, aelteste zuerst, letzter = heute."""
    n = int(t["backlog_growth_days"])
    vals = [v for v in daily_max if v is not None]
    if len(vals) < n + 1:
        return RuleResult("backlog_growth", False, [])
    tail = vals[-(n + 1):]
    rising = all(tail[i] < tail[i + 1] for i in range(n))
    f = [Finding("backlog_growth", "backlog", f"backlog rising {n} days: {' → '.join(str(v) for v in tail)}")] if rising else []
    return RuleResult("backlog_growth", True, f)


# --- Datenbank-Lesen fuer die Regeln ---------------------------------------------------------

def _db_context(t: dict | None = None) -> dict:
    """prev_full (SMART-Vergleich), offene Laeufe, Mediane, Backlog-Tagesmaxima,
    letzter abgeschlossener Lauf je Job."""
    t = t or load_thresholds()
    ctx: dict = {"prev_full": None, "open": [], "medians": {}, "daily_max": []}
    with get_connection() as conn:
        rows = conn.execute("SELECT disks FROM ops_samples WHERE is_full = ? ORDER BY ts DESC LIMIT 2",
                            (True if USE_POSTGRES else 1,)).fetchall()
        if len(rows) >= 2:
            d = rows[1]["disks"] if hasattr(rows[1], "keys") else rows[1][0]
            if isinstance(d, str):
                import json
                d = json.loads(d)
            ctx["prev_full"] = {"disks": d}
        ctx["open"] = [dict(r) for r in conn.execute(
            "SELECT job, started_at FROM ops_events WHERE ended_at IS NULL").fetchall()]
        if USE_POSTGRES:
            cur = conn._conn.cursor()
            # je Job der NEUESTE abgeschlossene Lauf im Rueckblickfenster
            cur.execute("""SELECT DISTINCT ON (job) job, rc, ended_at FROM ops_events
                            WHERE ended_at IS NOT NULL
                              AND started_at > now() - make_interval(days => %s)
                            ORDER BY job, ended_at DESC""",
                        (int(t["job_failed_lookback_days"]),))
            ctx["last_runs"] = [{"job": r[0], "rc": r[1], "ended_at": r[2]} for r in cur.fetchall()]
            cur.execute("""SELECT job, percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM ended_at - started_at))
                             FROM ops_events WHERE rc = 0 AND ended_at IS NOT NULL
                              AND started_at > now() - interval '28 days'
                            GROUP BY job HAVING count(*) >= 3""")
            ctx["medians"] = {r[0]: float(r[1]) for r in cur.fetchall()}
            cur.execute("""SELECT date(ts) AS d, max(backlog_unprocessed) FROM ops_samples
                            WHERE is_full AND ts > now() - interval '10 days' GROUP BY 1 ORDER BY 1""")
            ctx["daily_max"] = [r[1] for r in cur.fetchall()]
        else:
            rows = conn.execute("""SELECT date(ts) AS d, max(backlog_unprocessed) AS m FROM ops_samples
                                    WHERE is_full = 1 GROUP BY 1 ORDER BY 1""").fetchall()
            ctx["daily_max"] = [r["m"] for r in rows]
    return ctx


def evaluate(sample: dict, ctx: dict, t: dict, now: datetime | None = None) -> list[RuleResult]:
    now = now or datetime.now(timezone.utc)
    prev_full = ctx.get("prev_full") if sample.get("is_full") else None
    results: list[RuleResult] = []
    disk_results = rule_disks(sample, prev_full, t)
    if not sample.get("is_full"):
        # SMART nur in vollen Messungen — ohne Daten keine Aussage.
        disk_results = [r if r.kind != "disk_smart" else RuleResult("disk_smart", False, []) for r in disk_results]
    results += disk_results
    results += rule_gpu(sample, [e["job"] for e in ctx.get("open", [])], t)
    results.append(rule_db(sample, t))
    results += rule_jobs(ctx.get("open", []), ctx.get("medians", {}), t, now)
    results.append(rule_job_failed(ctx["last_runs"], t) if ctx.get("last_runs") is not None
                   else RuleResult("job_failed", False, []))
    results.append(rule_backlog(ctx.get("daily_max", []), t) if sample.get("is_full")
                   else RuleResult("backlog_growth", False, []))
    return results


# --- Abgleich mit ops_alerts + Mail ------------------------------------------------------------

def sync(results: list[RuleResult], now: datetime | None = None) -> tuple[list[Finding], list[dict]]:
    """Neue Befunde anlegen, verschwundene entwarnen. Gibt (raised, resolved) zurueck."""
    now = now or datetime.now(timezone.utc)
    ts = now if USE_POSTGRES else now.isoformat()
    active = {(f.kind, f.key): f for r in results for f in r.findings}
    checked_kinds = {r.kind for r in results if r.checked}
    raised: list[Finding] = []
    resolved: list[dict] = []
    with get_connection() as conn:
        open_rows = [dict(r) for r in conn.execute(
            "SELECT id, kind, key, message FROM ops_alerts WHERE resolved_at IS NULL").fetchall()]
        open_keys = {(r["kind"], r["key"]) for r in open_rows}
        for (kind, key), f in active.items():
            if (kind, key) not in open_keys:
                conn.execute("INSERT INTO ops_alerts (kind, key, message, raised_at, mailed_at) VALUES (?, ?, ?, ?, ?)",
                             (kind, key, f.message, ts, ts))
                raised.append(f)
        for r in open_rows:
            if r["kind"] in checked_kinds and (r["kind"], r["key"]) not in active:
                conn.execute("UPDATE ops_alerts SET resolved_at = ? WHERE id = ?", (ts, r["id"]))
                resolved.append(r)
    return raised, resolved


def notify(raised: list[Finding], resolved: list[dict]) -> bool:
    if not raised and not resolved:
        return True
    try:
        from scripts.review_notify import send  # derselbe Resend-Transport wie Waechter/Morgen-Mail
    except Exception as e:                                          # noqa: BLE001
        logger.warning("ops_alerts: mailer nicht importierbar: %s", e)
        return False
    head = ("ALERT: " + raised[0].message) if raised else ("resolved: " + resolved[0]["message"])
    if len(raised) + len(resolved) > 1:
        head += f" (+{len(raised) + len(resolved) - 1})"
    subject = f"Catandary ops — {head}"
    lines = []
    if raised:
        lines += ["Raised:"] + [f"  - [{f.kind}] {f.message}" for f in raised] + [""]
    if resolved:
        lines += ["Resolved:"] + [f"  - [{r['kind']}] {r['message']}" for r in resolved] + [""]
    lines += ["Dashboard: /trends/ops · thresholds: ops_alerts.yaml"]
    text = "\n".join(lines)
    import html as _h
    items = "".join(f"<li style='color:#ff6b3a'>[{_h.escape(f.kind)}] {_h.escape(f.message)}</li>" for f in raised) + \
            "".join(f"<li style='color:#22c55e'>resolved: [{_h.escape(r['kind'])}] {_h.escape(r['message'])}</li>" for r in resolved)
    body_html = (f"<div style='background:#0a0c0a;padding:24px;font-family:IBM Plex Sans,Helvetica,Arial,sans-serif;color:#d8d5c8'>"
                 f"<div style='max-width:620px;margin:0 auto;border:1px solid #2a2d25;border-left:3px solid #ff6b3a;padding:22px'>"
                 f"<div style='font-family:IBM Plex Mono,monospace;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:#ff6b3a'>Ops alert</div>"
                 f"<ul style='font-size:14px;line-height:1.6'>{items}</ul>"
                 f"<div style='font-family:IBM Plex Mono,monospace;font-size:10px;color:#8a8d82'>/trends/ops · ops_alerts.yaml</div>"
                 f"</div></div>")
    return send(subject, body_html, text)


def run(sample: dict, *, mail: bool = True) -> dict:
    """Vom Sampler nach jeder Messung. Faengt alles — ein Fehler hier darf die
    Messung nie kosten."""
    out = {"raised": 0, "resolved": 0, "mailed": None, "error": None}
    try:
        t = load_thresholds()
        ctx = _db_context(t)
        results = evaluate(sample, ctx, t)
        raised, resolved = sync(results)
        out["raised"], out["resolved"] = len(raised), len(resolved)
        if mail and (raised or resolved):
            out["mailed"] = notify(raised, resolved)
    except Exception as e:                                          # noqa: BLE001
        logger.warning("ops_alerts.run: %s", e)
        out["error"] = str(e)[:200]
    return out


def sampler_stale(now: datetime | None = None, t: dict | None = None) -> tuple[bool, str]:
    """Fuer den Morgen-Waechter: (stale?, Beschreibung). Der Sampler kann sich
    nicht selbst als tot melden."""
    t = t or load_thresholds()
    now = now or datetime.now(timezone.utc)
    with get_connection() as conn:
        row = conn.execute("SELECT max(ts) AS last FROM ops_samples").fetchone()
    last = row["last"] if hasattr(row, "keys") else row[0]
    if last is None:
        return True, "ops_samples is empty — the sampler has never written"
    if isinstance(last, str):
        last = datetime.fromisoformat(last)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = now - last
    if age > timedelta(minutes=float(t["sampler_stale_min"])):
        return True, f"last sample {last:%d.%m. %H:%M} UTC ({age.total_seconds() / 60:.0f} min ago), limit {t['sampler_stale_min']} min"
    return False, f"last sample {age.total_seconds() / 60:.0f} min ago"
