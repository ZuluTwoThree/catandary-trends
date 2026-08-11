#!/usr/bin/env python3
"""Newsletter delivery via Resend (Epic W2.5, issue #16).

The generator (newsletter_generator.py) writes editions into newsletter_editions
and the frontend renders them; this module DELIVERS the latest edition to the
confirmed subscribers. Batch send (Resend /emails/batch, <=100/call), a signed
one-click unsubscribe link + List-Unsubscribe header, and idempotency via a
sent_at column so an edition is never mailed twice.

Owner gates: RESEND_API_KEY (present) + a Resend-verified sending domain (SPF/
DKIM) for real delivery. Until then use --dry-run (renders + counts, no send)
or EMAIL_TRANSPORT=console-equivalent via --dry-run.

    python -m pipeline.newsletter_sender --dry-run          # latest edition
    python -m pipeline.newsletter_sender --latest           # send latest
    python -m pipeline.newsletter_sender --year 2026 --week 29
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import logging
import os
import time
from urllib.parse import quote

import httpx

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.newsletter_generator import (
    decode_edition_row,
    get_latest_newsletter,
    generate_html,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("newsletter_sender")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_ADDR = os.getenv("NEWSLETTER_FROM", "Catandary Trends <trends@catandary.de>")
BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://catandary.de")
# Reuse the auth secret so the frontend unsubscribe route can verify the token.
SECRET = os.getenv("AUTH_SECRET", "")
BATCH = 100


def migrate() -> None:
    """Additive: mark editions as sent (idempotency)."""
    with get_connection() as conn:
        for col, typ in [("sent_at", "TIMESTAMP"), ("recipients_count", "INTEGER")]:
            try:
                conn.execute(f"ALTER TABLE newsletter_editions ADD COLUMN {col} {typ}")
            except Exception:
                pass  # already exists


def unsubscribe_token(email: str) -> str:
    return hmac.new(SECRET.encode(), email.lower().encode(), hashlib.sha256).hexdigest()[:32]


def unsubscribe_url(email: str) -> str:
    return (f"{BASE_URL}/trends/newsletter/unsubscribe"
            f"?email={quote(email)}&token={unsubscribe_token(email)}")


def confirmed_subscribers() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT email FROM newsletter_subscribers "
            "WHERE confirmed = TRUE AND unsubscribed_at IS NULL").fetchall()
    return [r["email"] for r in rows]


def _wrap_html(body_html: str, email: str) -> str:
    unsub = unsubscribe_url(email)
    footer = (
        '<hr style="margin-top:32px;border:none;border-top:1px solid #ddd">'
        '<p style="color:#888;font-size:12px">You receive this because you '
        'subscribed to Catandary Trends. '
        f'<a href="{unsub}">Unsubscribe</a>.</p>'
    )
    return body_html + footer


def send_edition(edition: dict, dry_run: bool, force: bool) -> int:
    if edition.get("sent_at") and not force:
        logger.info("edition %s-W%s already sent at %s — skipping (use --force)",
                    edition.get("year"), edition.get("week"), edition["sent_at"])
        return 0
    recipients = confirmed_subscribers()
    subject = f"Catandary Trends — Week {edition.get('week')}/{edition.get('year')}"
    logger.info("edition %s-W%s: %d confirmed subscribers%s",
                edition.get("year"), edition.get("week"), len(recipients),
                " (DRY RUN)" if dry_run else "")
    # Render BEFORE the dry-run exit. A dry run whose whole point is "would this
    # send work?" must exercise the template, otherwise it green-lights an
    # edition that blows up on the real attempt — which is exactly what happened
    # on 2026-08-12 (JSON columns left as strings, generate_html crashed on
    # .items() while the dry run had reported success).
    base_html = generate_html(edition)
    if dry_run:
        logger.info("rendered %d chars of HTML", len(base_html))
        if recipients:
            logger.info("sample unsubscribe link: %s", unsubscribe_url(recipients[0]))
        return len(recipients)
    if not recipients:
        return 0
    if not RESEND_API_KEY:
        logger.error("RESEND_API_KEY not set — cannot send")
        return 0

    sent = 0
    with httpx.Client(timeout=30) as client:
        for i in range(0, len(recipients), BATCH):
            chunk = recipients[i:i + BATCH]
            payload = [{
                "from": FROM_ADDR,
                "to": [email],
                "subject": subject,
                "html": _wrap_html(base_html, email),
                "headers": {
                    "List-Unsubscribe": f"<{unsubscribe_url(email)}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            } for email in chunk]
            try:
                r = client.post("https://api.resend.com/emails/batch",
                                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                                json=payload)
                r.raise_for_status()
                sent += len(chunk)
                logger.info("  batch %d-%d sent", i, i + len(chunk))
            except Exception as e:
                logger.error("  batch %d failed: %r", i, e)
            time.sleep(0.5)  # gentle on the API

    with get_connection() as conn:
        conn.execute(
            "UPDATE newsletter_editions SET sent_at = CURRENT_TIMESTAMP, "
            "recipients_count = ? WHERE id = ?", (sent, edition["id"]))
    logger.info("edition %s-W%s sent to %d recipients",
                edition.get("year"), edition.get("week"), sent)
    return sent


def get_edition(year: int | None, week: int | None) -> dict | None:
    if year and week:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM newsletter_editions WHERE year = ? AND week = ?",
                (year, week)).fetchone()
        # Same decoding as get_latest_newsletter — a raw dict() leaves the JSON
        # columns as strings and generate_html() then fails on .items().
        return decode_edition_row(row) if row else None
    return get_latest_newsletter()


def main() -> int:
    ap = argparse.ArgumentParser(description="Send a newsletter edition via Resend")
    ap.add_argument("--latest", action="store_true", help="send the latest edition")
    ap.add_argument("--year", type=int)
    ap.add_argument("--week", type=int)
    ap.add_argument("--dry-run", action="store_true",
                    help="render + count recipients, do not send")
    ap.add_argument("--force", action="store_true", help="resend even if already sent")
    args = ap.parse_args()

    migrate()
    if not (args.latest or (args.year and args.week) or args.dry_run):
        ap.error("need --latest, --dry-run, or --year+--week")
    edition = get_edition(args.year, args.week)
    if not edition:
        logger.error("no matching edition found")
        return 1
    send_edition(edition, dry_run=args.dry_run, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
