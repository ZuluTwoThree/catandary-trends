#!/usr/bin/env python3
"""Admin override for a user's subscription tier (Epic W2.2, issue #17).

Lets us grant pilot customers / friends a paid tier before Stripe is live, and
inspect / reset accounts. No auth of its own — it's a local operator tool.

    python scripts/set_user_tier.py --list
    python scripts/set_user_tier.py --email a@b.com --tier pro
    python scripts/set_user_tier.py --email a@b.com --tier free
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.db import get_connection

TIERS = ("free", "starter", "pro", "superpro")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list all accounts + tiers")
    ap.add_argument("--email", help="account email")
    ap.add_argument("--tier", choices=TIERS, help="tier to set")
    args = ap.parse_args()

    with get_connection() as conn:
        if args.list or not args.email:
            rows = conn.execute(
                "SELECT email, tier, newsletter_opt_in, last_login_at "
                "FROM app_users ORDER BY id").fetchall()
            if not rows:
                print("no accounts yet")
                return 0
            for r in rows:
                print(f"  {r['email']:<40} {r['tier']:<10} "
                      f"{'nl' if r['newsletter_opt_in'] else '  '}  {r['last_login_at']}")
            return 0

        if not args.tier:
            ap.error("--tier required with --email (unless --list)")
        email = args.email.lower().strip()
        exists = conn.execute(
            "SELECT 1 FROM app_users WHERE email = ?", (email,)).fetchone()
        if not exists:
            print(f"no such account: {email}")
            return 1
        conn.execute("UPDATE app_users SET tier = ? WHERE email = ?",
                     (args.tier, email))
        print(f"{email} → {args.tier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
