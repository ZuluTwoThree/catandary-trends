#!/usr/bin/env python3
"""Print the mail HTML of one newsletter edition — read only, never sends.

Why a module of its own: the release view (/trends/newsletter/review, owner
mandate 2026-09-06) must show *exactly* what the recipient gets, and the mail
HTML is built in Python (pipeline/newsletter_generator.generate_html). Rather
than re-implementing the template in TypeScript — two renderers drift, and the
one the owner reads would be the wrong one — the page shells out to this CLI
(frontend/src/lib/newsletterMail.ts, execFile, argv only) and shows the result
in an iframe.

It deliberately has no send path at all: it imports the sender only for
render_email_html(), so nothing here can put a mail on the wire.

    python -m pipeline.newsletter_preview --latest
    python -m pipeline.newsletter_preview --year 2026 --week 35 > /tmp/preview.html
"""
from __future__ import annotations

import argparse
import logging
import sys

from pipeline.newsletter_sender import get_edition, render_email_html


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render one newsletter edition as the email HTML (no send)")
    ap.add_argument("--latest", action="store_true", help="the newest edition")
    ap.add_argument("--year", type=int)
    ap.add_argument("--week", type=int)
    args = ap.parse_args()
    if not (args.latest or (args.year and args.week)):
        ap.error("need --latest or --year + --week")

    # Logs to stderr: stdout carries the HTML and nothing else, because the
    # caller pipes it straight into an iframe.
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, force=True)

    edition = get_edition(args.year, args.week)
    if not edition:
        print("no matching edition found", file=sys.stderr)
        return 1
    sys.stdout.write(render_email_html(edition))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
