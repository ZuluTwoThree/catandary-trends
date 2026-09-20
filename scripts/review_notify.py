#!/usr/bin/env python3
"""Morning reminder for the grounding-hold review queue (issue #71).

The nightly gate keeps back high-confidence drafts whose body states a figure
or date the source does not support. Left alone they just pile up — this mails
the owner a short digest so the queue actually gets worked.

Deliberately quiet: NO mail when there is nothing to review. A reminder that
arrives every day regardless is one you stop reading.

    python -m scripts.review_notify --dry-run   # print, never send
    python -m scripts.review_notify             # send if there is anything

Runs after the nightly cycle (see scripts/full_cycle_cron.sh).
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("review_notify")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_ADDR = os.getenv("NEWSLETTER_FROM", "Catandary Trends <trends@send.catandary.de>")
# Where the review UI lives. Localhost by default: the queue is an internal tool
# and the app is not public yet.
REVIEW_URL = os.getenv("REVIEW_URL", "http://localhost:3001/trends/review")
TO_ADDR = os.getenv("REVIEW_NOTIFY_TO", "molkereimeister@web.de")

# Mirrors AUTO_PUBLISH_CONFIDENCE — only drafts the gate actually judged.
CONFIDENCE_MIN = 0.85


def fetch_queue() -> tuple[int, int, str | None, list[dict]]:
    """(today, total, oldest_date, sample_of_todays_titles)"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "       COUNT(*) FILTER (WHERE created_at >= CURRENT_DATE) AS today, "
            "       MIN(created_at)::date::text AS oldest "
            "  FROM trends WHERE status = 'draft' AND confidence >= ?",
            (CONFIDENCE_MIN,),
        ).fetchone()
        r = dict(row) if hasattr(row, "keys") else {
            "total": row[0], "today": row[1], "oldest": row[2]}

        rows = conn.execute(
            "SELECT title_en, source_name FROM trends "
            " WHERE status = 'draft' AND confidence >= ? AND created_at >= CURRENT_DATE "
            " ORDER BY created_at DESC LIMIT 20",
            (CONFIDENCE_MIN,),
        ).fetchall()
    items = [dict(x) if hasattr(x, "keys") else {"title_en": x[0], "source_name": x[1]}
             for x in rows]
    return int(r["today"] or 0), int(r["total"] or 0), r["oldest"], items


def judge_stats() -> dict | None:
    """Last night's draft-judge numbers (pipeline.draft_judge), if fresh.

    The judge writes data/draft_judge_last.json at the end of stage 10; a stale
    file (older than 24h — e.g. the judge was skipped or failed) must not show
    up as if it ran, so freshness gates the section."""
    import datetime
    p = Path("data/draft_judge_last.json")
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        ts = datetime.datetime.fromisoformat(d["date"])
        age = datetime.datetime.now(datetime.timezone.utc) - ts
        if age.total_seconds() > 24 * 3600 or d.get("dry_run"):
            return None
        return d
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def deep_dive_stats() -> dict | None:
    """The last newsletter deep-dive run (#96, scripts/newsletter_deep_dive.py),
    if fresh. Runs Monday after the edition; the Tuesday mail carries it. A
    dry run IS reported — that is the whole point of the dry-run phase."""
    import datetime
    p = Path("data/newsletter_deep_dive_last.json")
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        ts = datetime.datetime.fromisoformat(d["date"])
        age = datetime.datetime.now(datetime.timezone.utc) - ts
        if age.total_seconds() > 36 * 3600:
            return None
        return d
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


# GPU cron wrappers that leave a status note via scripts/lib/gpu_guard.sh
# (gpu_guard_note): data/<job>_last.json. The Saturday ingesters run 06:00 and
# the Research Pulse 12:00 (cron since 2026-09-18); the next review mail goes
# out Monday ~06:00 — 60 h freshness carries both exactly into that one mail
# and not into Tuesday's.
GPU_JOB_NOTES = ("weekly_ingesters", "monthly_startup_sources", "weekly_research_pulse",
                 "weekly_field_watch")   # kein GPU-Job, aber derselbe Notiz-Weg (Sa 12:30)
# Optional note fields the line shows verbatim when present (pulse: which ISO
# week was computed and how many themes got a Gemma paragraph).
GPU_JOB_NOTE_EXTRAS = ("week", "themes", "with_text", "errors", "note", "customers")
GPU_JOB_NOTE_MAX_AGE_H = 60


def gpu_job_notes() -> list[dict]:
    """Fresh status notes of the GPU cron wrappers (#98): whether their GPU
    steps ran, were skipped because another GPU job held :8090 (status
    'blocked'), or failed. A blocked/failed note forces a mail even when the
    review queue is empty — the skipped signals stay unprocessed until the
    next run, and that is worth one line in the morning."""
    import datetime
    notes = []
    for job in GPU_JOB_NOTES:
        p = Path(f"data/{job}_last.json")
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text())
            ts = datetime.datetime.fromisoformat(d["date"])
            age = datetime.datetime.now(datetime.timezone.utc) - ts
            if age.total_seconds() <= GPU_JOB_NOTE_MAX_AGE_H * 3600:
                notes.append(d)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
    return notes


def _gpu_job_line(n: dict) -> str:
    line = (f"GPU cron {n.get('job')}: {n.get('status')} — "
            f"{n.get('gpu_steps_done', 0)} GPU step(s) done, "
            f"{n.get('gpu_steps_skipped', 0)} skipped")
    if n.get("blocked_by"):
        line += f" (blocked by: {n['blocked_by']})"
    if n.get("status") == "blocked":
        line += "; skipped signals stay unprocessed and are caught up by the next run"
    extras = [f"{k}={n[k]}" for k in GPU_JOB_NOTE_EXTRAS if n.get(k) not in (None, "")]
    if extras:
        line += "; " + ", ".join(extras)
    line += f"; rc={n.get('rc')}"
    return line


def _deep_dive_line(dd: dict) -> str:
    audit = dd.get("audit") or {}
    gates = dd.get("gates") or {}
    failed = [k for k, v in gates.items() if not v]
    tag = "dry-run" if dd.get("dry_run", True) else "LIVE"
    head = (f"Newsletter deep dive ({tag}) W{dd.get('week')}/{dd.get('year')}: "
            f"{dd.get('status')} — theme {dd.get('theme_name') or dd.get('theme') or '—'}")
    if dd.get("status") == "disabled":
        # Der Rechercheur (Scouting-Dossiers) ist seit 2026-09-19 entfernt;
        # der Schritt protokolliert nur noch, dass er nichts getan hat.
        head += "; researcher removed 2026-09-19 — edition unchanged"
    elif dd.get("theme"):
        head += (f"; audit {audit.get('supported', '?')} supported / "
                 f"{audit.get('contradictions', '?')} contradictions / "
                 f"{audit.get('dossier_ungrounded', '?')} ungrounded; "
                 f"{dd.get('words') or 0} words; gate "
                 f"{'passed' if dd.get('gate_passed') else 'failed: ' + (', '.join(failed) or 'n/a')}")
    if dd.get("error"):
        head += f"; error: {dd['error']}"
    return head


def build_mail(today: int, total: int, oldest: str | None,
               items: list[dict], judge: dict | None = None,
               deep_dive: dict | None = None,
               gpu_jobs: list[dict] | None = None) -> tuple[str, str, str]:
    subject = (f"Review: {today} article{'s' if today != 1 else ''} held overnight"
               if today else f"Review queue: {total} waiting")

    lines = [f"{today} article(s) were held by the quality gate last night."]
    if total > today:
        lines.append(f"{total} in the queue in total"
                     + (f", oldest from {oldest}." if oldest else "."))
    lines.append("")
    lines.append("Each states a figure or date its source does not support, or")
    lines.append("breaks off mid-sentence. Publish or reject — either way it")
    lines.append("leaves the queue.")
    lines.append("")
    for it in items:
        src = f"  [{it.get('source_name')}]" if it.get("source_name") else ""
        lines.append(f"  - {it.get('title_en', '')}{src}")
    if today > len(items):
        lines.append(f"  … and {today - len(items)} more")
    lines.append("")
    if judge:
        cats = ", ".join(f"{k}={v}" for k, v in sorted(judge.get("categories", {}).items()))
        lines.append(f"Draft judge (Qwen3.8-27B, sub-threshold drafts): "
                     f"{judge.get('judged', 0)} judged, {judge.get('released', 0)} released, "
                     f"{judge.get('held', 0)} held, {judge.get('gate_blocked', 0)} gate-blocked, "
                     f"{judge.get('dup_blocked', 0)} duplicates.")
        if cats:
            lines.append(f"  Categories: {cats}")
        lines.append("")
    if deep_dive:
        lines.append(_deep_dive_line(deep_dive))
        lines.append("")
    for n in gpu_jobs or []:
        lines.append(_gpu_job_line(n))
    if gpu_jobs:
        lines.append("")
    lines.append(f"Review: {REVIEW_URL}")
    text = "\n".join(lines)

    rows_html = "".join(
        f'<li style="margin-bottom:6px">{html.escape(str(it.get("title_en","")))}'
        + (f' <span style="color:#888">— {html.escape(str(it.get("source_name")))}</span>'
           if it.get("source_name") else "")
        + "</li>"
        for it in items
    )
    body_html = (
        '<div style="font-family:system-ui,sans-serif;font-size:15px;line-height:1.6">'
        f"<p><strong>{today}</strong> article(s) were held by the quality gate last night."
        + (f" {total} in the queue in total"
           + (f", oldest from {html.escape(oldest)}." if oldest else ".")
           if total > today else "")
        + "</p>"
        "<p style=\"color:#666;font-size:13px\">Each states a figure or date its source "
        "does not support, or breaks off mid-sentence. Publish or reject — either way it "
        "leaves the queue.</p>"
        f'<ul style="font-size:14px;padding-left:18px">{rows_html}</ul>'
        + (f'<p style="color:#666;font-size:13px">… and {today - len(items)} more</p>'
           if today > len(items) else "")
        + (f'<p style="color:#666;font-size:13px">{html.escape(_deep_dive_line(deep_dive))}</p>'
           if deep_dive else "")
        + "".join(f'<p style="color:#666;font-size:13px">{html.escape(_gpu_job_line(n))}</p>'
                  for n in gpu_jobs or [])
        + f'<p><a href="{html.escape(REVIEW_URL)}">Open the review queue</a></p></div>'
    )
    return subject, body_html, text


def send(subject: str, body_html: str, text: str) -> bool:
    if not RESEND_API_KEY:
        logger.error("RESEND_API_KEY not set — cannot send")
        return False
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={"from": FROM_ADDR, "to": [TO_ADDR], "subject": subject,
                  "html": body_html, "text": text},
            timeout=20,
        )
        r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("send failed: %r", e)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Mail the grounding-hold review queue")
    ap.add_argument("--dry-run", action="store_true", help="print, never send")
    ap.add_argument("--force", action="store_true",
                    help="send even when nothing was held (for testing the wiring)")
    args = ap.parse_args()

    today, total, oldest, items = fetch_queue()
    judge = judge_stats()
    deep_dive = deep_dive_stats()
    gpu_jobs = gpu_job_notes()
    gpu_trouble = [n for n in gpu_jobs if n.get("status") != "ok"]
    logger.info("queue: %d held today, %d total, oldest %s | judge: %s | deep dive: %s | gpu crons: %s",
                today, total, oldest,
                f"{judge['released']} released / {judge['held']} held" if judge else "no fresh run",
                deep_dive.get("status") if deep_dive else "no fresh run",
                ", ".join(f"{n.get('job')}={n.get('status')}" for n in gpu_jobs) or "no fresh note")

    # Quiet only when there is truly nothing to report: no held articles AND no
    # judge run AND no deep-dive run AND no blocked/failed GPU cron. A night
    # where the judge released 200 articles deserves a mail even if the >=0.85
    # gate held nothing.
    if today == 0 and judge is None and deep_dive is None and not gpu_trouble and not args.force:
        logger.info("nothing held today, no judge run, no deep dive, GPU crons fine — no mail sent")
        return 0

    subject, body_html, text = build_mail(today, total, oldest, items, judge, deep_dive, gpu_jobs)
    if args.dry_run:
        print(f"--- Subject: {subject}\n\n{text}")
        return 0
    ok = send(subject, body_html, text)
    logger.info("mail %s to %s", "sent" if ok else "FAILED", TO_ADDR)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
