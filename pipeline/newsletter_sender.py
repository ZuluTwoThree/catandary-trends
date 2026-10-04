#!/usr/bin/env python3
"""Newsletter delivery via Resend (Epic W2.5, issue #16).

The generator (newsletter_generator.py) writes editions into newsletter_editions
and the frontend renders them; this module DELIVERS the latest edition to the
confirmed subscribers. Batch send (Resend /emails/batch, <=100/call), a signed
unsubscribe link + RFC 8058 List-Unsubscribe headers, and idempotency via a
sent_at column so an edition is never mailed twice.

Unsubscribe (owner decision 2026-09-02: the public site is a static export on
the Hetzner webspace, so the Next.js route /trends/newsletter/unsubscribe does
not exist publicly): every mail links
    https://catandary.de/newsletter/unsubscribe.php?t=<token>
served by the PHP DOI package (docs/launch/newsletter-doi-php/unsubscribe.php).
The token is HMAC-SHA256 over the address with NEWSLETTER_UNSUB_SECRET — the
SAME value as `unsub_secret` (block 5) in nl_config.php on the webspace — and
never expires; see unsubscribe_token() for the exact format. Fail closed: with
the secret missing nothing is rendered or sent (a newsletter without a working
withdrawal link is a legal defect, § 7 UWG / Art. 7 Abs. 3 DSGVO).

Owner gates: RESEND_API_KEY (present) + a Resend-verified sending domain (SPF/
DKIM) for real delivery. Until then use --dry-run (renders + counts, no send)
or EMAIL_TRANSPORT=console-equivalent via --dry-run.

Release gate (owner mandate 2026-09-06): an edition is only sent once a person
has read it and released it — `newsletter_editions.approved_at`, set by the
release view /trends/newsletter/review. Without it a send attempt exits 2 and
mails nothing; --dry-run stays allowed and says that the release is missing.
There is no flag to switch the gate off, by design. --force only overrides the
already-sent check, never the release.

    python -m pipeline.newsletter_sender --dry-run          # latest edition
    python -m pipeline.newsletter_sender --latest           # send latest
    python -m pipeline.newsletter_sender --year 2026 --week 29
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import logging
import os
import time

import httpx

from pipeline import db as db_mod
from pipeline.db import get_connection
from pipeline.newsletter_generator import (
    decode_edition_row,
    ensure_approval_columns,
    get_latest_newsletter,
    generate_html,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("newsletter_sender")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_ADDR = os.getenv("NEWSLETTER_FROM", "Catandary Trends <trends@catandary.de>")
# Where unsubscribe.php lives: the public webspace, NOT the local Next instance
# (PUBLIC_BASE_URL is the app's base and may legitimately be localhost).
UNSUB_BASE = os.getenv("NEWSLETTER_PUBLIC_BASE", "https://catandary.de").rstrip("/")
# Must equal `unsub_secret` (block 5) in nl_config.php on the webspace.
UNSUB_SECRET = os.getenv("NEWSLETTER_UNSUB_SECRET", "")
# The mailto: half of List-Unsubscribe — the address named in the consent text.
UNSUB_MAILTO = os.getenv("NEWSLETTER_UNSUB_MAILTO", "contact@catandary.de")
MIN_SECRET_LEN = 16  # same bar as frontend/src/lib/unsubscribe.ts
BATCH = 100


def migrate() -> None:
    """Additive: mark editions as sent (idempotency) + carry the approval columns.

    The approval columns are what the release gate below reads, so they are
    ensured here as well: a missing column must never let the gate fail open
    (scripts/migrate_newsletter_approval.py is the visible, by-hand run).
    """
    with get_connection() as conn:
        for col, typ in [("sent_at", "TIMESTAMP"), ("recipients_count", "INTEGER")]:
            try:
                conn.execute(f"ALTER TABLE newsletter_editions ADD COLUMN {col} {typ}")
            except Exception:
                pass  # already exists
    ensure_approval_columns()


def _b64url(raw: bytes) -> str:
    """Base64 with -_ and no = padding (RFC 4648 §5) — URL-safe, no quoting needed."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _normalize_email(email: str) -> bytes:
    # bytes.lower() is ASCII-only — bit-identical to PHP 8.2's locale-free
    # strtolower(), which is what subscribe.php stored and unsubscribe.php looks up.
    return email.strip().encode("utf-8").lower()


def unsubscribe_configured() -> bool:
    return len(UNSUB_SECRET) >= MIN_SECRET_LEN and not UNSUB_SECRET.startswith("CHANGE_ME")


def unsubscribe_token(email: str) -> str:
    """`<b64url(email)>.<b64url(HMAC-SHA256(secret, "unsub:" + email))>`.

    Mirror of nl_unsub_token() in docs/launch/newsletter-doi-php/_lib.php — the
    PHP side decodes the first half to find the subscriber and recomputes the
    second half with hash_equals(). No expiry by design: the link at the end of
    a three-year-old mail must still withdraw consent. Shared test vector in
    tests/test_newsletter_sender.py and tests/test_newsletter_doi_php.py.
    """
    if not unsubscribe_configured():
        raise RuntimeError(
            "NEWSLETTER_UNSUB_SECRET missing or shorter than 16 chars — unsubscribe "
            "links cannot be signed (must equal unsub_secret in nl_config.php)")
    addr = _normalize_email(email)
    mac = hmac.new(UNSUB_SECRET.encode("utf-8"), b"unsub:" + addr, hashlib.sha256).digest()
    return f"{_b64url(addr)}.{_b64url(mac)}"


def unsubscribe_url(email: str) -> str:
    return f"{UNSUB_BASE}/newsletter/unsubscribe.php?t={unsubscribe_token(email)}"


def unsubscribe_headers(email: str) -> dict[str, str]:
    """RFC 2369 + RFC 8058: mailto AND https target, plus the One-Click marker.

    Gmail/Yahoo bulk-sender rules require both headers; the mailbox provider
    then POSTs `List-Unsubscribe=One-Click` to the https URL, which
    unsubscribe.php answers with 200 and no form.
    """
    return {
        "List-Unsubscribe": f"<mailto:{UNSUB_MAILTO}?subject=unsubscribe>, <{unsubscribe_url(email)}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def confirmed_subscribers() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT email FROM newsletter_subscribers "
            "WHERE confirmed = TRUE AND unsubscribed_at IS NULL").fetchall()
    return [r["email"] for r in rows]


UNSUB_TOKEN = "{{UNSUBSCRIBE_URL}}"
# Stand-in for the per-recipient link in a preview render (no address, no
# secret needed). Everything else in the preview is byte-identical to the mail.
PREVIEW_UNSUB_URL = "https://catandary.de/newsletter/unsubscribe.php?t=PREVIEW"


def _substitute_unsub(body_html: str, unsub: str) -> str:
    """Put the recipient's unsubscribe link into the template's own footer.

    The template carries a {{UNSUBSCRIBE_URL}} placeholder so the link sits
    inside the design. It used to be appended as a light-styled block AFTER
    </html> — malformed, and it hung under the dark email as a white slab.

    The append path is kept as a fallback: an older stored edition, or any
    future template that forgets the placeholder, must still ship a working
    unsubscribe link. Dropping it silently would be a legal problem, not a
    cosmetic one (§ 7 UWG, Art. 21 DSGVO).
    """
    if UNSUB_TOKEN in body_html:
        return body_html.replace(UNSUB_TOKEN, unsub)
    logger.warning("template has no %s placeholder — appending plain footer",
                   UNSUB_TOKEN)
    footer = (
        '<hr style="margin-top:32px;border:none;border-top:1px solid #2a2d25">'
        '<p style="color:#8a8d82;font-size:12px;font-family:sans-serif">'
        'You receive this because you subscribed to Catandary Trends. '
        f'<a href="{unsub}" style="color:#8a8d82">Unsubscribe</a>.</p>'
    )
    return body_html + footer


def _wrap_html(body_html: str, email: str) -> str:
    """The recipient's copy: their signed unsubscribe link in the footer."""
    return _substitute_unsub(body_html, unsubscribe_url(email))


def render_email_html(edition: dict, recipient: str | None = None) -> str:
    """THE mail HTML of one edition — the single source for send AND preview.

    `recipient=None` renders the preview: identical bytes except the
    per-recipient unsubscribe link, which becomes PREVIEW_UNSUB_URL (so a
    preview needs neither an address nor NEWSLETTER_UNSUB_SECRET). The release
    view at /trends/newsletter/review shows exactly this, via the read-only
    CLI in pipeline/newsletter_preview.py — the owner reads what the recipient
    will read, not a second implementation of it.
    """
    base_html = generate_html(edition)
    return _substitute_unsub(
        base_html,
        unsubscribe_url(recipient) if recipient else PREVIEW_UNSUB_URL)


def build_message(email: str, subject: str, base_html: str) -> dict:
    """One Resend /emails(/batch) item; `headers` is Resend's custom-header field."""
    return {
        "from": FROM_ADDR,
        "to": [email],
        "subject": subject,
        "html": _wrap_html(base_html, email),
        "headers": unsubscribe_headers(email),
    }


def approval_of(edition: dict) -> tuple[bool, str]:
    """(released?, one-line state) — the human-in-the-loop fact of an edition.

    Owner mandate 2026-09-06: the owner reads every issue and releases it
    before it goes out. `approved_at` is that release; there is deliberately
    NO flag to switch this off (no --require-approval=0): a switch would be
    used, and the point of the gate is that it cannot be.
    """
    at = edition.get("approved_at")
    if not at:
        return False, "NOT RELEASED (no approved_at) — release it at /trends/newsletter/review"
    who = edition.get("approved_by") or "unknown"
    note = edition.get("approval_note")
    return True, f"released {at} by {who}" + (f" — note: {note}" if note else "")


class NotReleased(RuntimeError):
    """Raised instead of sending an edition no person has released."""


def send_edition(edition: dict, dry_run: bool, force: bool) -> int:
    if not unsubscribe_configured():
        # Refuse even the dry run: its whole point is "would this send work?"
        raise RuntimeError(
            "NEWSLETTER_UNSUB_SECRET not set — refusing to render/send: every mail "
            "needs a signed unsubscribe link (set it to the unsub_secret from nl_config.php)")
    released, state = approval_of(edition)
    logger.info("edition %s-W%s approval: %s",
                edition.get("year"), edition.get("week"), state)
    if not released and not dry_run:
        # Second lock (main() checks first): send_edition is importable, so the
        # gate lives where the sending happens, not only in the CLI. --force
        # does NOT open it — it only overrides the already-sent check.
        raise NotReleased(
            f"edition {edition.get('year')}-W{edition.get('week')} has no approved_at — "
            "refusing to send. Read and release it at /trends/newsletter/review.")
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
        if not released:
            logger.warning("DRY RUN ONLY — a real send of this edition is refused "
                           "until it is released at /trends/newsletter/review")
        if recipients:
            # The token is b64url(email).hmac — a real address would be readable in
            # the log. A placeholder exercises the URL builder just as well.
            logger.info("sample unsubscribe link: %s", unsubscribe_url("subscriber@example.invalid"))
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
            payload = [build_message(email, subject, base_html) for email in chunk]
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
    if not unsubscribe_configured():
        logger.error("NEWSLETTER_UNSUB_SECRET missing/short — cannot sign unsubscribe "
                     "links; nothing rendered or sent (see NEWSLETTER_GOLIVE.md step 3)")
        return 1
    edition = get_edition(args.year, args.week)
    if not edition:
        logger.error("no matching edition found")
        return 1
    released, state = approval_of(edition)
    if not released and not args.dry_run:
        logger.error("edition %s-W%s: %s", edition.get("year"), edition.get("week"), state)
        logger.error("nothing sent. Open /trends/newsletter/review, read the "
                     "edition and press Release; --dry-run works meanwhile.")
        return 2
    send_edition(edition, dry_run=args.dry_run, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
