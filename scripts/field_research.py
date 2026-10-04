#!/usr/bin/env python3
"""Recherche-Entwürfe für Trajectory Sheet und Field Watch — Kommandozeile (Owner 2026-10-04).

  scripts/field_research.py regulatory <kunde> <feld>     Entwurf Anhang A „Rechtsrahmen" (Sheet)
  scripts/field_research.py reading <kunde> <feld>        Entwurf Abschnitt 7 „Einordnung" (Sheet)
  scripts/field_research.py movers <kunde> [--week D]     Entwürfe „was hinter der Bewegung steckt" (Wochenblatt)
  scripts/field_research.py setup "<phrase>"              Kandidaten-Suchphrasen, gezählt, als YAML-Entwurf
  scripts/field_research.py prospect "<firma>"            Internes Briefing vor dem Erstgespräch
  scripts/field_research.py list [<kunde>]                Entwürfe und ihr Status
  scripts/field_research.py purge [--apply]               Entwürfe älter als 1825 Tage löschen

Optionen: --llm local|anthropic (Default local = Gemma-4-26B per GPU-Handover; anthropic = Claude
über die API, Kontext verlässt dann den Rechner) · --dry-run (Auftrag zeigen, kein Modell) ·
--wait-min N (auf einen laufenden GPU-Job warten, Default 0 = sofort abbrechen).

Ablauf: Messkontext (SQL, CPU) → Korpus-Dienst als Kindprozess → GPU-Handover (nur local) →
gptr-Worker in der Recherche-venv (holt selbst nichts; Netzsperre) → Ruhezustand wieder her →
Entwurf nach data/field_watch/<kunde>/drafts/<feld>/ (status: draft). Danach: Text umschreiben,
`status: rewritten` setzen, `scripts/field_watch.py <kunde> --sheet <feld>` bauen. Mit `--draft`
baut field_watch.py ein Entwurfsblatt (Wasserzeichen, *-ENTWURF.pdf, nie im Export).

Exit 0 ok · 1 Fehler · 75 GPU belegt (Kollisionswächter).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pipeline import field_drafts, field_research as fr  # noqa: E402
from pipeline.config import DATA_DIR  # noqa: E402

try:
    from pipeline.ops_events import record as ops_record  # noqa: E402
except ImportError:  # pragma: no cover
    from contextlib import nullcontext as ops_record  # type: ignore

logger = logging.getLogger("field_research")

RESEARCH_PY = Path(os.environ.get("RESEARCH_VENV", str(Path.home() / "venvs" / "catandary-research"))) / "bin" / "python"
WORKER = REPO / "tools" / "research" / "gptr_run.py"
LOCAL_MODEL = os.environ.get("FIELD_RESEARCH_MODEL", "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf")
# Gemma-26B mit -c 16384 braucht ~15 GB; Rest der Karte für Fremde (Sprachdienste ~4,8 GB).
VRAM_RESIDUAL_MAX_MIB = int(os.environ.get("FIELD_RESEARCH_VRAM_RESIDUAL_MAX_MIB", "8500"))
WORKER_TIMEOUT_S = int(os.environ.get("FIELD_RESEARCH_WORKER_TIMEOUT", "3600"))
ANTHROPIC_HOSTS = ["api.anthropic.com"]
GPU_BUSY = 75


class GpuBusy(RuntimeError):
    pass


def llm_config(backend: str) -> dict:
    if backend == "anthropic":
        return {"backend": "anthropic", "fast": os.environ.get("FIELD_RESEARCH_FAST", "claude-haiku-4-5-20251001"),
                "smart": os.environ.get("FIELD_RESEARCH_SMART", "claude-sonnet-5")}
    return {"backend": "local", "model": "gemma-4-26b", "base_url": "http://127.0.0.1:8090/v1"}


def _ancestors(pid: int) -> set[int]:
    out = set()
    while pid > 1 and pid not in out:
        out.add(pid)
        try:
            pid = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return out


def foreign_gpu_job() -> str | None:
    """Wie der Kollisionswächter (scripts/lib/gpu_guard.sh): Besitzvermerke lebender Jobs, dann
    die Prozessliste gegen GPU_GUARD_PATTERNS — ohne die eigene Prozesskette (timeout, Shell)."""
    import re
    from pipeline.ops_probe import _pid_alive, gpu_guard_patterns
    mine = _ancestors(os.getpid())
    for f in sorted(Path(DATA_DIR).glob("llama-server.*.pid")):
        try:
            owner = int(f.read_text().split()[1])
        except (OSError, IndexError, ValueError):
            continue
        if owner not in mine and _pid_alive(owner):
            return f.name[len("llama-server."):-len(".pid")]
    pat = gpu_guard_patterns()
    r = subprocess.run(["pgrep", "-f", "-a", pat], capture_output=True, text=True, timeout=10)
    for line in r.stdout.splitlines():
        pid, _, cmd = line.partition(" ")
        if not pid.isdigit() or int(pid) in mine or not cmd.strip():
            continue
        if re.search(r"\b(grep|pgrep|tail|less|vim?|nano|cat)\b", cmd.split()[0]) or "shell-snapshots" in cmd:
            continue
        if int(pid) in _descendant_free_check(int(pid)):
            continue
        m = re.search(pat, cmd)
        if m:
            return m.group(0).removesuffix(".sh")
    return None


def _descendant_free_check(pid: int) -> set[int]:
    """Kinder der eigenen Prozesse (z. B. der Korpus-Dienst) sind keine Fremden."""
    return {pid} if os.getpid() in _ancestors(pid) else set()


def wait_for_gpu(wait_min: int) -> None:
    deadline = time.time() + wait_min * 60
    while True:
        job = foreign_gpu_job()
        if not job:
            return
        if time.time() >= deadline:
            raise GpuBusy(f"GPU-Job läuft: {job}")
        logger.info("GPU belegt durch %s — warte …", job)
        time.sleep(30)


def run_worker(spec: dict, service: tuple[str, str]) -> dict:
    """Ein gptr-Lauf in der Recherche-venv. Minimal-Umgebung: keine DB, keine Pipeline-Geheimnisse."""
    if not RESEARCH_PY.exists():
        raise RuntimeError(f"Recherche-venv fehlt ({RESEARCH_PY}) — scripts/setup_research_venv.sh")
    spec = dict(spec, service={"url": service[0], "token": service[1]})
    if spec["llm"]["backend"] == "anthropic":
        spec["allow_hosts"] = ANTHROPIC_HOSTS
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", ""),
           "LANG": os.environ.get("LANG", "C.UTF-8"), "PYTHONUNBUFFERED": "1"}
    if spec["llm"]["backend"] == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY fehlt (.env)")
        env["ANTHROPIC_API_KEY"] = key
    tmp = Path(DATA_DIR) / "field_watch" / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=tmp) as td:
        sp, op = Path(td) / "spec.json", Path(td) / "out.json"
        sp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        os.chmod(sp, 0o600)
        t0 = time.time()
        r = subprocess.run([str(RESEARCH_PY), str(WORKER), str(sp), str(op)], cwd=str(REPO), env=env,
                           capture_output=True, text=True, timeout=WORKER_TIMEOUT_S)
        out = json.loads(op.read_text(encoding="utf-8")) if op.exists() else {}
    out["worker_rc"] = r.returncode
    out["worker_seconds"] = round(time.time() - t0, 1)
    if r.returncode != 0 or out.get("error"):
        tail = (r.stderr or "")[-1500:]
        raise RuntimeError(f"gptr-Worker rc={r.returncode}: {out.get('error') or ''}\n{tail}")
    if out.get("egress_blocked"):
        logger.warning("Netzsperre hat Verbindungen verhindert: %s", out["egress_blocked"])
    return out


def with_model(llm: dict, jobs: list, wait_min: int) -> list:
    """jobs = [(spec, callback)] → führt jeden Auftrag aus, Ergebnis an callback. Ein Handover für alle."""
    from pipeline.corpus_service import running_service
    results = []
    with running_service() as svc:
        if llm["backend"] == "anthropic":
            for spec, cb in jobs:
                results.append(cb(run_worker(spec, svc)))
            return results
        from pipeline import gpu_handover
        wait_for_gpu(wait_min)
        os.environ.setdefault("GPU_JOB_NAME", "field_research")
        was_active = _unit_active(gpu_handover)
        try:
            with gpu_handover.model_on_llamacpp(LOCAL_MODEL, vram_free_below_mib=VRAM_RESIDUAL_MAX_MIB):
                served = Path(gpu_handover._served_model() or LOCAL_MODEL).name
                if served != LOCAL_MODEL:
                    raise RuntimeError(f"llama-server serviert {served}, erwartet {LOCAL_MODEL}")
                for spec, cb in jobs:
                    out = run_worker(spec, svc)
                    out["served_model"] = served
                    results.append(cb(out))
        finally:
            _restore_rest(gpu_handover, was_active)
    return results


def _unit_active(gh) -> bool:
    try:
        return gh._run(["systemctl", "--user", "is-active", gh.LLAMA_UNIT], timeout=15).stdout.strip() == "active"
    except Exception:                                               # noqa: BLE001
        return False


def _restore_rest(gh, was_active: bool) -> None:
    """Wie research_pulse: der Handover stoppt den Server und hängt den Symlink zurück;
    lief er vorher, hier wieder starten (Ruhezustand = schlankes 8B)."""
    if not was_active:
        return
    try:
        gh._run(["systemctl", "--user", "reset-failed", gh.LLAMA_UNIT], timeout=15)
        gh._run(["systemctl", "--user", "start", gh.LLAMA_UNIT], timeout=60)
    except Exception as exc:                                        # noqa: BLE001
        logger.error("Ruhezustand nicht wiederhergestellt: %s", exc)


def _meta(out: dict, llm: dict) -> dict:
    model = out.get("served_model") or (f"anthropic:{llm.get('smart')}" if llm["backend"] == "anthropic" else LOCAL_MODEL)
    return {"model": model, "backend": llm["backend"], "sources": len(out.get("sources") or []),
            "seconds": out.get("worker_seconds"), "engine": "gpt-researcher 0.16.1 (Catandary-Starter)"}


def _payload(spec: dict, out: dict, extra_sources: list[dict] | None = None) -> dict:
    s = {k: v for k, v in spec.items() if k not in ("service",)}
    return {"spec": s, "sources": (extra_sources or []) + (out.get("sources") or []),
            "source_texts": out.get("source_texts") or {}, "costs": out.get("costs"),
            "context_words": out.get("context_words"), "egress_blocked": out.get("egress_blocked")}


def _field(customer: str, field: str):
    from pipeline.field_watch import load_customer
    cust = load_customer(customer)
    f = next((x for x in cust["fields"] if x["slug"] == field), None)
    if not f:
        raise SystemExit(f"Feld {field!r} nicht in {cust['slug']}: {[x['slug'] for x in cust['fields']]}")
    return cust, f


# ---------------------------------------------------------------------------
# Modi
# ---------------------------------------------------------------------------
def cmd_regulatory(a, llm) -> int:
    cust, f = _field(a.customer, a.field)
    logger.info("EUR-Lex-Kontext für %s …", f["name"])
    block, eu_sources = fr.eurlex_context(f)
    spec = fr.regulatory_spec(f, llm, words=a.words or 700, eurlex_block=block)
    if a.dry_run:
        return _show(spec)

    def done(out):
        p = field_drafts.save_draft(cust["slug"], f["slug"], "regulatory", out["report"], _meta(out, llm),
                                    _payload(spec, out, eu_sources))
        print(f"Entwurf Rechtsrahmen → {p}")
        return p
    with_model(llm, [(spec, done)], a.wait_min)
    return 0


def cmd_reading(a, llm) -> int:
    from pipeline.field_watch import measure_sheet
    cust, f = _field(a.customer, a.field)
    logger.info("Sheet-Messung für %s (einige Minuten) …", f["name"])
    d = measure_sheet(f)
    spec = fr.reading_spec(f, fr.sheet_measurement_text(d), llm)
    if a.dry_run:
        return _show(spec)

    def done(out):
        p = field_drafts.save_draft(cust["slug"], f["slug"], "reading", out["report"], _meta(out, llm),
                                    _payload(spec, out) | {"measurement": spec["extra_context"]})
        print(f"Entwurf Einordnung → {p}")
        return p
    with_model(llm, [(spec, done)], a.wait_min)
    return 0


def cmd_movers(a, llm) -> int:
    from pipeline.field_watch import load_customer, measure_week
    cust = load_customer(a.customer)
    if a.week:
        today = date.fromisoformat(a.week)
    else:  # wie scripts/field_watch.py: Default = Vorwoche (die zuletzt abgeschlossene)
        today = date.today()
        today = today - timedelta(days=today.weekday() + 1) if today.weekday() < 6 else today
    d = measure_week(cust["fields"], today)
    moving = fr.movers(d["fields"], min_delta_pct=a.min_delta)
    if not moving:
        print(f"Woche {d['week']}: kein Feld mit deutlicher Bewegung (≥ +{a.min_delta} %, ≥ 5 Signale) — kein Entwurf.")
        return 0
    since = (date.fromisoformat(d["week_start"]) - timedelta(days=14)).isoformat()
    jobs = []
    by_slug = {x["slug"]: x for x in cust["fields"]}
    for m in moving:
        f = {**by_slug.get(m["field"].get("slug"), {}), **m["field"]}
        spec = fr.movers_spec(f, d["week"], fr.week_measurement_text(f, d["week"]), since, llm)
        if a.dry_run:
            _show(spec)
            continue

        def done(out, f=f, spec=spec, tiers=m["tiers"]):
            p = field_drafts.save_draft(cust["slug"], f["slug"], "movers", out["report"],
                                        _meta(out, llm) | {"tiers": tiers}, _payload(spec, out), week=d["week"])
            print(f"Entwurf Bewegung {f['name']} ({', '.join(tiers)}) → {p}")
            return p
        jobs.append((spec, done))
    if jobs:
        with_model(llm, jobs, a.wait_min)
    return 0


def cmd_setup(a, llm) -> int:
    from pipeline import corpus_api
    spec = fr.setup_spec(a.phrase, llm)
    if a.dry_run:
        return _show(spec)

    def done(out):
        parsed = fr.parse_setup(out["report"])
        terms = [a.phrase.lower()] + [t for t in parsed["terms"] if t != a.phrase.lower()]
        counts = corpus_api.term_counts(terms[:25])["terms"]
        body = ("Kandidaten für das Feld (Modell-Vorschlag, deterministisch gezählt). Erst prüfen, dann in "
                "fields/<kunde>.yaml übernehmen und dem Kunden zur Freigabe vorlegen.\n\n"
                + "```yaml\n" + fr.setup_yaml(a.phrase, counts, parsed["cpc_hints"]) + "```\n\n"
                + (f"Hinweis des Modells: {parsed['notes']}\n" if parsed["notes"] else ""))
        p = field_drafts.save_draft(None, None, "setup", body, _meta(out, llm) | {"phrase": a.phrase},
                                    _payload(spec, out) | {"parsed": parsed, "counts": counts})
        print(body)
        print(f"→ {p}")
        return p
    with_model(llm, [(spec, done)], a.wait_min)
    return 0


def cmd_prospect(a, llm) -> int:
    spec = fr.prospect_spec(a.company, llm)
    if a.dry_run:
        return _show(spec)

    def done(out):
        p = field_drafts.save_draft(None, None, "prospect", out["report"], _meta(out, llm) | {"company": a.company},
                                    _payload(spec, out))
        print(f"Briefing → {p}")
        return p
    with_model(llm, [(spec, done)], a.wait_min)
    return 0


def cmd_list(a) -> int:
    from pipeline.field_watch import OUT_DIR
    root = OUT_DIR / a.customer / "drafts" if a.customer else OUT_DIR
    rows = 0
    for p in sorted(root.glob("**/drafts/**/*.md") if not a.customer else root.glob("**/*.md")):
        try:
            d = field_drafts.parse(p)
        except ValueError as exc:
            print(f"FEHLER {exc}")
            continue
        state = d["status"]
        if state == "rewritten":
            try:
                field_drafts.check_rewritten(d)
            except field_drafts.DraftNotRewritten:
                state = "rewritten?! (zu nah am Entwurf)"
        print(f"{state:<34} {d.get('section'):<11} {d.get('created', '')[:16]}  {p.relative_to(OUT_DIR)}")
        rows += 1
    if not rows:
        print("keine Entwürfe")
    return 0


def cmd_purge(a) -> int:
    gone = field_drafts.purge(apply=a.apply)
    print(f"{'gelöscht' if a.apply else 'würde löschen'}: {len(gone)} Dateien (älter als {field_drafts.RETENTION_DAYS} Tage)")
    for g in gone[:20]:
        print("  ", g)
    return 0


def _show(spec: dict) -> int:
    s = dict(spec)
    print(json.dumps(s, ensure_ascii=False, indent=1)[:6000])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", choices=("local", "anthropic"), default=os.environ.get("FIELD_RESEARCH_LLM", "local"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wait-min", type=int, default=0)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("regulatory", "reading"):
        p = sub.add_parser(name)
        p.add_argument("customer")
        p.add_argument("field")
        p.add_argument("--words", type=int, default=None)
    p = sub.add_parser("movers")
    p.add_argument("customer")
    p.add_argument("--week", help="ein Datum der zu berichtenden Woche (Default: Vorwoche)")
    p.add_argument("--min-delta", type=int, default=50)
    p = sub.add_parser("setup")
    p.add_argument("phrase")
    p = sub.add_parser("prospect")
    p.add_argument("company")
    p = sub.add_parser("list")
    p.add_argument("customer", nargs="?")
    p = sub.add_parser("purge")
    p.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s field_research %(levelname)s %(message)s")
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if a.cmd == "list":
        return cmd_list(a)
    if a.cmd == "purge":
        return cmd_purge(a)
    llm = llm_config(a.llm)
    handler = {"regulatory": cmd_regulatory, "reading": cmd_reading, "movers": cmd_movers,
               "setup": cmd_setup, "prospect": cmd_prospect}[a.cmd]
    try:
        if a.dry_run:
            return handler(a, llm)
        with ops_record("field_research"):
            return handler(a, llm)
    except GpuBusy as exc:
        print(f"abgebrochen: {exc} (--wait-min N wartet)", file=sys.stderr)
        return GPU_BUSY
    except Exception as exc:                                        # noqa: BLE001
        logger.exception("field_research %s fehlgeschlagen", a.cmd)
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
