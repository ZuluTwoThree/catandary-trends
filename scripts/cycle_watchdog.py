#!/usr/bin/env python3
"""Alert when the nightly cycle did not finish.

Why this exists: on 2026-08-17 a power cut rebooted the machine at 06:21, in the
middle of the 04:00 run. Ingestion and content generation had completed, but
reclassify and auto-publish never ran — 858 articles stayed drafts and nothing
reached the site. Nobody noticed. The wrapper writes its exit code to the log as
its last act, so when it dies the line is simply absent, and an absent line
raises no alarm. It surfaced only because the owner happened to ask.

The check is deliberately about the END of the run, not its content: a cycle
that finishes with rc=0 is assumed fine (the review-queue mail covers quality).

Since 2026-08-24 the watchdog also checks the nightly 02:45 Postgres backup —
by artifact, not by log: backup_db.py logged "backup OK" for 42 nights
(2026-07-13 .. 2026-08-23) while pg_dump died on its timeout every time, so
the only evidence that counts is the dump directory itself.

Silence means healthy — a mail only ever arrives when something is wrong, which
is what makes it worth reading.

    python -m scripts.cycle_watchdog                # check today, mail if broken
    python -m scripts.cycle_watchdog --dry-run      # print the verdict, never send
    python -m scripts.cycle_watchdog --date 20260817
    python -m scripts.cycle_watchdog --force        # mail even when healthy
"""
from __future__ import annotations

import argparse
import html
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.review_notify import send  # noqa: E402  (same Resend transport)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("cycle_watchdog")

LOG_DIR = Path.home() / "logs"
LOG_GLOB = "catandary-full-cycle-{stamp}-*.log"

# The wrapper's closing line, e.g.
#   full_cycle_cron.sh end  2026-08-14T06:52:46+02:00  (rc=0)
END_RE = re.compile(r"full_cycle_cron\.sh end\s+(\S+)\s+\(rc=(-?\d+)\)")
START_RE = re.compile(r"full_cycle_cron\.sh start\s+(\S+)")

# Processes that mean "the run is still going", so a missing end line is a slow
# run rather than a dead one — a different problem with a different answer.
RUNNING_HINTS = ("scheduled_cycle.sh", "run_full_cycle", "full_cycle_cron.sh")

# Where the 02:45 backup cron writes its Postgres dump (backup_db.py, -Fd).
BACKUP_DIR = Path("/mnt/data-hdd/backups/catandary")
BACKUP_LOG = LOG_DIR / "catandary-backup.log"
# A full dump is ~113 GB (2026-08-23); anything under this is a truncated run.
BACKUP_MIN_BYTES = 1_000_000_000


def cycle_is_running() -> bool:
    """True if a cycle process is alive. Reads /proc directly so the check has
    no dependency on pgrep being installed in a cron environment."""
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmdline = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", "replace")
        except (OSError, PermissionError):
            continue
        if any(h in cmdline for h in RUNNING_HINTS):
            return True
    return False


def db_snapshot() -> list[str]:
    """What the incomplete run cost, in plain numbers. Never raises — a
    database problem must not suppress the alert about the cycle."""
    try:
        from pipeline.db import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS created, "
                "       COUNT(*) FILTER (WHERE status = 'published') AS published, "
                "       COUNT(*) FILTER (WHERE status = 'draft') AS draft "
                "  FROM trends WHERE created_at::date = CURRENT_DATE"
            ).fetchone()
            d = dict(row) if hasattr(row, "keys") else {
                "created": row[0], "published": row[1], "draft": row[2]}
            held = conn.execute(
                "SELECT COUNT(*) AS n FROM trends "
                " WHERE status = 'draft' AND confidence >= 0.85"
            ).fetchone()
            n = dict(held)["n"] if hasattr(held, "keys") else held[0]
        return [
            f"created today: {d['created']}",
            f"published: {d['published']}",
            f"still draft: {d['draft']}",
            f"drafts at/above the publish threshold: {n}",
        ]
    except Exception as e:  # noqa: BLE001
        return [f"(database snapshot unavailable: {e!r})"]


def inspect(stamp: str) -> dict:
    """Judge the run for the given YYYYMMDD stamp."""
    logs = sorted(LOG_DIR.glob(LOG_GLOB.format(stamp=stamp)))
    if not logs:
        # The cycle is scheduled Mon-Fri only (crontab: 0 4 * * 1-5), so a
        # missing weekend log is the expected state, not an incident. Without
        # this the watchdog would cry wolf every Saturday and Sunday and be
        # ignored by the time it matters.
        if datetime.strptime(stamp, "%Y%m%d").weekday() >= 5:
            return {"ok": True, "kind": "weekend", "log": None,
                    "headline": "no cycle scheduled (weekend)",
                    "detail": "", "tail": []}
        return {"ok": False, "kind": "missing", "log": None,
                "headline": "The nightly cycle left no log at all",
                "detail": "No file matched "
                          f"{LOG_DIR}/{LOG_GLOB.format(stamp=stamp)} — the cron "
                          "job did not start, or could not write its log.",
                "tail": []}

    log = logs[-1]
    text = log.read_text(errors="replace")
    tail = [ln for ln in text.splitlines() if ln.strip()][-12:]
    started = START_RE.search(text)
    end = END_RE.search(text)

    if end:
        rc = int(end.group(2))
        if rc == 0:
            return {"ok": True, "kind": "clean", "log": log,
                    "headline": f"finished cleanly at {end.group(1)}",
                    "detail": "", "tail": tail}
        return {"ok": False, "kind": "failed", "log": log,
                "headline": f"The nightly cycle finished with exit code {rc}",
                "detail": f"Started {started.group(1) if started else '?'}, "
                          f"ended {end.group(1)}.",
                "tail": tail}

    if cycle_is_running():
        return {"ok": False, "kind": "running", "log": log,
                "headline": "The nightly cycle is still running",
                "detail": f"Started {started.group(1) if started else '?'} and has "
                          "not finished. A normal run takes just under three "
                          "hours, so this is worth a look — but nothing is lost "
                          "yet; it may simply be slow.",
                "tail": tail}

    return {"ok": False, "kind": "aborted", "log": log,
            "headline": "The nightly cycle stopped without finishing",
            "detail": f"Started {started.group(1) if started else '?'}. No exit "
                      "code was ever written and no cycle process is alive, so "
                      "the run was cut off — a reboot, a power cut, or a kill. "
                      "Ingested articles are safe in the database, but the "
                      "closing stages (reclassify, auto-publish) may not have "
                      "run. scripts/resume_cycle.sh replays exactly those.",
            "tail": tail}


def inspect_backup(stamp: str) -> dict:
    """Judge the 02:45 Postgres backup for the given YYYYMMDD stamp.

    The artifact is the evidence, not the log: for 42 nights the log said
    "backup OK" while pg_dump had died on its timeout and no dump existed.
    The backup runs daily at 02:45 and takes ~20 min, so by watchdog time
    (07:45) the dump directory for today must exist, be complete (toc.dat
    present — pg_dump writes it last) and be plausibly sized.
    """
    date_tag = datetime.strptime(stamp, "%Y%m%d").strftime("%Y-%m-%d")
    dump = BACKUP_DIR / f"catandary-pg-{date_tag}.dumpdir"
    tail: list[str] = []
    log_path = BACKUP_LOG if BACKUP_LOG.exists() else None
    if log_path:
        tail = [ln for ln in log_path.read_text(errors="replace").splitlines()
                if ln.strip()][-12:]

    if dump.is_dir() and (dump / "toc.dat").exists():
        size = sum(f.stat().st_size for f in dump.iterdir() if f.is_file())
        if size >= BACKUP_MIN_BYTES:
            return {"ok": True, "kind": "backup", "log": log_path,
                    "headline": f"backup present ({size/1e9:.0f} GB)",
                    "detail": "", "tail": tail}
        return {"ok": False, "kind": "backup", "log": log_path,
                "headline": "The nightly Postgres backup is implausibly small",
                "detail": f"{dump} holds only {size/1e6:.0f} MB — a full dump "
                          "is around 113 GB. The dump directory exists but its "
                          "content does not look like a complete backup.",
                "tail": tail}

    return {"ok": False, "kind": "backup", "log": log_path,
            "headline": "The nightly Postgres backup is missing",
            "detail": f"Expected {dump} — the 02:45 backup_db.py run either "
                      "did not start, failed, or is still unfinished hours "
                      "later. Until a dump for today exists, the newest "
                      "restorable state is the previous day. Run manually: "
                      ".venv/bin/python scripts/backup_db.py --dest "
                      f"{BACKUP_DIR} --skip-sqlite --keep-days 7",
            "tail": tail}


def build_mail(v: dict, stamp: str) -> tuple[str, str, str]:
    nice = datetime.strptime(stamp, "%Y%m%d").strftime("%d.%m.%Y")
    subject = f"Catandary: {v['headline'].lower()} ({nice})"
    lines = [v["headline"], "", v["detail"], ""]
    if v["kind"] in ("aborted", "failed", "running"):
        lines += ["Where things stand:"] + [f"  - {s}" for s in db_snapshot()] + [""]
    if v["log"]:
        lines += [f"Log: {v['log']}", "", "Last lines:"] + [f"  {ln}" for ln in v["tail"]]
    text = "\n".join(lines)

    esc = html.escape
    tail_html = "".join(
        f"<div>{esc(ln)}</div>" for ln in v["tail"]) or "<div>—</div>"
    snap_html = ""
    if v["kind"] in ("aborted", "failed", "running"):
        snap_html = ("<ul style='margin:0 0 16px;padding-left:18px;color:#d8d5c8'>"
                     + "".join(f"<li>{esc(s)}</li>" for s in db_snapshot())
                     + "</ul>")
    body_html = f"""<div style="background:#0a0c0a;padding:24px;
  font-family:'IBM Plex Sans',-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;color:#d8d5c8">
  <div style="max-width:620px;margin:0 auto;border:1px solid #2a2d25;border-left:3px solid #ff6b3a;padding:22px">
    <div style="font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10px;
      letter-spacing:.16em;text-transform:uppercase;color:#ff6b3a">Pipeline alert &middot; {esc(nice)}</div>
    <h1 style="font-family:Georgia,serif;font-weight:normal;font-size:22px;
      line-height:1.25;color:#f4f1e8;margin:10px 0 14px">{esc(v['headline'])}</h1>
    <p style="font-size:14px;line-height:1.6;margin:0 0 16px">{esc(v['detail'])}</p>
    {snap_html}
    <div style="font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10px;
      letter-spacing:.12em;text-transform:uppercase;color:#8a8d82;margin-bottom:6px">Last lines</div>
    <div style="font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:11px;
      line-height:1.6;color:#8a8d82;background:#111310;border:1px solid #2a2d25;
      padding:12px;overflow-x:auto;white-space:pre">{tail_html}</div>
    <div style="font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10px;
      color:#8a8d82;margin-top:14px">{esc(str(v['log'] or '—'))}</div>
  </div>
</div>"""
    return subject, body_html, text


def main() -> int:
    ap = argparse.ArgumentParser(description="Alert when the nightly cycle did not finish")
    ap.add_argument("--date", help="YYYYMMDD to inspect (default: today)")
    ap.add_argument("--dry-run", action="store_true", help="print the verdict, never send")
    ap.add_argument("--force", action="store_true", help="send even when the run was clean")
    args = ap.parse_args()

    stamp = args.date or date.today().strftime("%Y%m%d")
    cycle_v = inspect(stamp)
    backup_v = inspect_backup(stamp)
    logger.info("%s: cycle: %s (%s)", stamp, cycle_v["headline"], cycle_v["kind"])
    logger.info("%s: backup: %s", stamp, backup_v["headline"])

    problems = [v for v in (cycle_v, backup_v) if not v["ok"]]
    if not problems:
        if not args.force:
            return 0  # silence means healthy
        problems = [cycle_v]

    sent_ok = True
    for v in problems:
        subject, body_html, text = build_mail(v, stamp)
        if args.dry_run:
            print(f"\nSubject: {subject}\n\n{text}\n")
        else:
            sent_ok = send(subject, body_html, text) and sent_ok
    return 0 if sent_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
