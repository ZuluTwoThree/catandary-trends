"""Unsubscribe link + RFC 8058 headers of the newsletter sender (#16, 2026-09-02).

The public site is a static export on the Hetzner webspace, so the withdrawal
link in every mail must point at the PHP endpoint there
(docs/launch/newsletter-doi-php/unsubscribe.php), not at the Next.js route.
The token has to be reproducible by _lib.php::nl_unsub_token() with the same
secret — VECTOR below is the shared fixture; tests/test_newsletter_doi_php.py
runs the real PHP against it whenever a php CLI is available.
"""
from __future__ import annotations

import importlib
import importlib.util
import re
from pathlib import Path

import pytest

SECRET = "unsub-test-secret-0123456789"
EMAIL_RAW = " Alice@Example.com "
EMAIL = "alice@example.com"
VECTOR = "YWxpY2VAZXhhbXBsZS5jb20.PJOENDIrCGd1sSH0sF3nXjKLc6NBV3j04aeaklwoQ7I"
PHP_URL = "https://catandary.de/newsletter/unsubscribe.php?t="


def _mod(monkeypatch, secret: str = SECRET, base: str | None = None):
    """Re-import the sender with the env this test wants (constants are module-level)."""
    monkeypatch.setenv("NEWSLETTER_UNSUB_SECRET", secret)
    if base is None:
        monkeypatch.delenv("NEWSLETTER_PUBLIC_BASE", raising=False)
    else:
        monkeypatch.setenv("NEWSLETTER_PUBLIC_BASE", base)
    monkeypatch.delenv("NEWSLETTER_UNSUB_MAILTO", raising=False)
    import pipeline.newsletter_sender as m
    return importlib.reload(m)


class TestToken:
    def test_matches_shared_vector(self, monkeypatch):
        m = _mod(monkeypatch)
        assert m.unsubscribe_token(EMAIL_RAW) == VECTOR

    def test_normalizes_case_and_whitespace(self, monkeypatch):
        m = _mod(monkeypatch)
        assert m.unsubscribe_token(EMAIL) == m.unsubscribe_token(EMAIL_RAW)
        assert m.unsubscribe_token("ALICE@EXAMPLE.COM") == VECTOR

    def test_is_urlsafe_and_carries_the_address(self, monkeypatch):
        """PHP finds the subscriber by decoding the first half — no ?email= param."""
        m = _mod(monkeypatch)
        tok = m.unsubscribe_token(EMAIL)
        assert re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}", tok)
        first, _ = tok.split(".")
        pad = "=" * (-len(first) % 4)
        import base64
        assert base64.urlsafe_b64decode(first + pad) == EMAIL.encode()

    def test_secret_changes_token(self, monkeypatch):
        a = _mod(monkeypatch).unsubscribe_token(EMAIL)
        b = _mod(monkeypatch, secret="another-secret-0123456789").unsubscribe_token(EMAIL)
        assert a != b


class TestFailClosed:
    """No secret -> nothing signed, nothing sent (mirror of frontend E-7 fix)."""

    @pytest.mark.parametrize("secret", ["", "short", "CHANGE_ME_same_as_NEWSLETTER_UNSUB_SECRET"])
    def test_unconfigured_secret_raises(self, monkeypatch, secret):
        m = _mod(monkeypatch, secret=secret)
        assert m.unsubscribe_configured() is False
        with pytest.raises(RuntimeError, match="NEWSLETTER_UNSUB_SECRET"):
            m.unsubscribe_token(EMAIL)
        with pytest.raises(RuntimeError, match="NEWSLETTER_UNSUB_SECRET"):
            m.unsubscribe_url(EMAIL)

    def test_send_edition_refuses_even_dry_run(self, monkeypatch):
        m = _mod(monkeypatch, secret="")
        with pytest.raises(RuntimeError, match="refusing"):
            m.send_edition({"id": 1, "year": 2026, "week": 36}, dry_run=True, force=False)


class TestUrl:
    def test_points_at_the_php_endpoint(self, monkeypatch):
        m = _mod(monkeypatch)
        url = m.unsubscribe_url(EMAIL)
        assert url == PHP_URL + VECTOR
        assert "/trends/newsletter/unsubscribe" not in url
        assert "email=" not in url

    def test_base_override_strips_trailing_slash(self, monkeypatch):
        m = _mod(monkeypatch, base="https://staging.example/")
        assert m.unsubscribe_url(EMAIL).startswith("https://staging.example/newsletter/unsubscribe.php?t=")

    def test_public_base_url_of_the_app_is_ignored(self, monkeypatch):
        """PUBLIC_BASE_URL may be localhost (the app's base); the link must not follow it."""
        monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:3004")
        m = _mod(monkeypatch)
        assert m.unsubscribe_url(EMAIL).startswith("https://catandary.de/")


class TestHeaders:
    def test_rfc8058_pair(self, monkeypatch):
        m = _mod(monkeypatch)
        h = m.unsubscribe_headers(EMAIL)
        assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        targets = re.findall(r"<([^>]+)>", h["List-Unsubscribe"])
        assert targets == [
            "mailto:contact@catandary.de?subject=unsubscribe",
            PHP_URL + VECTOR,
        ]
        assert targets[1].startswith("https://")   # RFC 8058 requires https

    def test_message_carries_headers_and_footer_link(self, monkeypatch):
        m = _mod(monkeypatch)
        msg = m.build_message(EMAIL, "Subject", "<p>x</p>{{UNSUBSCRIBE_URL}}")
        assert msg["to"] == [EMAIL]
        assert msg["headers"] == m.unsubscribe_headers(EMAIL)
        assert PHP_URL + VECTOR in msg["html"]
        assert "{{UNSUBSCRIBE_URL}}" not in msg["html"]

    def test_fallback_footer_when_template_lacks_placeholder(self, monkeypatch):
        m = _mod(monkeypatch)
        html = m._wrap_html("<p>no placeholder</p>", EMAIL)
        assert PHP_URL + VECTOR in html


# --- sync bridge: export.php row -> local newsletter_subscribers ----------------

SYNC_PY = Path(__file__).resolve().parent.parent / "docs" / "launch" / "newsletter-doi-php" / "sync_subscribers.py"


def _sync_mod(monkeypatch):
    monkeypatch.setenv("NL_EXPORT_TOKEN", "t")
    spec = importlib.util.spec_from_file_location("nl_sync_subscribers", SYNC_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSyncCarriesUnsubscribeStatus:
    def test_confirmed_row(self, monkeypatch):
        s = _sync_mod(monkeypatch)
        params = s.row_to_params({
            "email": "Bob@Example.com", "status": "confirmed", "verticals": '["TECH"]',
            "confirmed_at": "2026-09-01 10:00:00", "signup_at": "2026-09-01 09:00:00",
            "unsubscribed_at": None, "updated_at": "2026-09-01 10:00:00",
        })
        assert params == ("bob@example.com", '["TECH"]', True, "2026-09-01 10:00:00", None)

    def test_unsubscribed_row_is_excluded_from_delivery(self, monkeypatch):
        """confirmed=False AND unsubscribed_at set — either alone keeps the
        sender's `confirmed = TRUE AND unsubscribed_at IS NULL` filter from
        picking the address up again."""
        s = _sync_mod(monkeypatch)
        params = s.row_to_params({
            "email": "bob@example.com", "status": "unsubscribed", "verticals": "[]",
            "confirmed_at": "2026-09-01 10:00:00", "signup_at": "2026-09-01 09:00:00",
            "unsubscribed_at": "2026-09-02 08:00:00", "updated_at": "2026-09-02 08:00:00",
        })
        assert params[2] is False
        assert params[4] == "2026-09-02 08:00:00"

    def test_upsert_keeps_newer_local_unsubscribe_but_honours_resubscribe(self, monkeypatch):
        s = _sync_mod(monkeypatch)
        sql = s.UPSERT_SQL
        assert "ON CONFLICT (email) DO UPDATE" in sql
        assert "newsletter_subscribers.unsubscribed_at > EXCLUDED.subscribed_at" in sql
        assert "ELSE EXCLUDED.unsubscribed_at" in sql
