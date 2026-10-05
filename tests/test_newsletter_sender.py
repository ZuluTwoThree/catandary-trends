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


# --- release gate: no edition goes out unread (owner mandate 2026-09-06) --------

class TestReleaseGate:
    """`approved_at` is the human-in-the-loop lock in front of every send.

    The owner reads each issue in /trends/newsletter/review and releases it;
    until then the sender mails nothing. There is deliberately no flag to
    switch this off, so the tests also pin that --force does not open it.
    """

    UNRELEASED = {"id": 9, "year": 2026, "week": 36}
    RELEASED = {"id": 9, "year": 2026, "week": 36,
                "approved_at": "2026-09-06 08:00:00", "approved_by": "owner",
                "approval_note": "read it"}

    def test_approval_of_reports_state(self, monkeypatch):
        m = _mod(monkeypatch)
        ok, state = m.approval_of(self.UNRELEASED)
        assert ok is False
        assert "NOT RELEASED" in state and "/trends/newsletter/review" in state
        ok, state = m.approval_of(self.RELEASED)
        assert ok is True
        assert "owner" in state and "read it" in state

    def test_send_edition_refuses_without_approval(self, monkeypatch):
        m = _mod(monkeypatch)
        with pytest.raises(m.NotReleased, match="approved_at"):
            m.send_edition(dict(self.UNRELEASED), dry_run=False, force=False)

    def test_force_does_not_open_the_gate(self, monkeypatch):
        """--force overrides the already-sent check, never the release."""
        m = _mod(monkeypatch)
        with pytest.raises(m.NotReleased):
            m.send_edition(dict(self.UNRELEASED, sent_at=None), dry_run=False, force=True)

    def test_no_cli_flag_switches_the_gate_off(self, monkeypatch):
        """No opt-out option may exist — a switch would get used."""
        m = _mod(monkeypatch)
        flags = re.findall(r'add_argument\(\s*"(--[a-z-]+)"', Path(m.__file__).read_text())
        assert flags == ["--latest", "--year", "--week", "--dry-run", "--force", "--test-to"]

    def _run_main(self, monkeypatch, edition, argv):
        m = _mod(monkeypatch)
        sent: list = []
        monkeypatch.setattr(m, "migrate", lambda: None)
        monkeypatch.setattr(m, "get_edition", lambda y, w: edition)
        monkeypatch.setattr(m, "send_edition", lambda *a, **k: sent.append(k) or 0)
        monkeypatch.setattr("sys.argv", ["newsletter_sender", *argv])
        return m.main(), sent

    def test_main_exits_nonzero_and_sends_nothing(self, monkeypatch):
        rc, sent = self._run_main(monkeypatch, dict(self.UNRELEASED), ["--latest"])
        assert rc == 2
        assert sent == []

    def test_main_gate_also_applies_to_year_week(self, monkeypatch):
        rc, sent = self._run_main(
            monkeypatch, dict(self.UNRELEASED), ["--year", "2026", "--week", "36"])
        assert rc == 2 and sent == []

    def test_dry_run_stays_allowed_without_release(self, monkeypatch):
        rc, sent = self._run_main(monkeypatch, dict(self.UNRELEASED), ["--dry-run"])
        assert rc == 0
        assert sent and sent[0]["dry_run"] is True

    def test_released_edition_passes(self, monkeypatch):
        rc, sent = self._run_main(monkeypatch, dict(self.RELEASED), ["--latest"])
        assert rc == 0
        assert sent and sent[0]["dry_run"] is False


class TestPreviewRenderer:
    """The release view must show the recipient's mail, not a second render."""

    EDITION = {"id": 1, "year": 2026, "week": 36, "editorial": "A line.",
               "vertical_summaries": {"TECH": "Tech moved."},
               "mega_trend_radar": [], "trend_refs": {}, "total_signals": 7}

    def test_preview_needs_no_secret_and_no_address(self, monkeypatch):
        m = _mod(monkeypatch, secret="")  # unsubscribe not configured at all
        html = m.render_email_html(self.EDITION)
        assert m.PREVIEW_UNSUB_URL in html
        assert "{{UNSUBSCRIBE_URL}}" not in html

    def test_preview_and_recipient_copy_differ_only_in_the_unsub_link(self, monkeypatch):
        m = _mod(monkeypatch)
        preview = m.render_email_html(self.EDITION)
        recipient = m.render_email_html(self.EDITION, EMAIL)
        assert preview.replace(m.PREVIEW_UNSUB_URL, "") == recipient.replace(
            m.unsubscribe_url(EMAIL), "")

    def test_mail_carries_the_ai_disclosure(self, monkeypatch):
        m = _mod(monkeypatch)
        from pipeline.newsletter_generator import AI_DISCLOSURE_EN
        assert AI_DISCLOSURE_EN in m.render_email_html(self.EDITION)


# --- robustness (2026-10-05, issue #16 check) ------------------------------------

class _FakeConn:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.log.append((sql, params))
        return self


def _wired(monkeypatch, recipients, delivered=(), fail_batches=0, sync_ok=True):
    """Sender with every outside effect replaced by a recorder."""
    m = _mod(monkeypatch)
    monkeypatch.setattr(m, "RESEND_API_KEY", "re_test")
    calls = {"posts": [], "recorded": [], "sql": [], "sync": 0}
    state = {"delivered": set(delivered), "fail": fail_batches}

    def sync():
        calls["sync"] += 1
        if not sync_ok:
            raise m.SyncFailed("export.php unreachable")

    def post(client, path, payload, key):
        calls["posts"].append((path, [x["to"][0] for x in payload] if isinstance(payload, list) else payload["to"], key))
        if state["fail"]:
            state["fail"] -= 1
            raise RuntimeError("Resend down")
        return {"data": [{"id": f"id{n}"} for n in range(len(payload))]} if isinstance(payload, list) else {"id": "t1"}

    def record(eid, emails, ids, err):
        calls["recorded"].append((list(emails), err))
        if not err:
            state["delivered"].update(emails)

    monkeypatch.setattr(m, "sync_recipients", sync)
    monkeypatch.setattr(m, "confirmed_subscribers", lambda: list(recipients))
    monkeypatch.setattr(m, "delivered_to", lambda eid: set(state["delivered"]))
    monkeypatch.setattr(m, "record_deliveries", record)
    monkeypatch.setattr(m, "post_resend", post)
    monkeypatch.setattr(m, "generate_html", lambda ed: "<p>{{UNSUBSCRIBE_URL}}</p>")
    monkeypatch.setattr(m, "get_connection", lambda: _FakeConn(calls["sql"]))
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    return m, calls


RELEASED = {"id": 40, "year": 2026, "week": 40, "approved_at": "2026-10-06 08:00:00", "approved_by": "owner"}


class TestRobustDelivery:
    def test_sync_runs_before_send_and_failure_blocks_it(self, monkeypatch):
        m, calls = _wired(monkeypatch, ["a@x.de"], sync_ok=False)
        with pytest.raises(m.SyncFailed):
            m.send_edition(dict(RELEASED), dry_run=False, force=False)
        assert calls["posts"] == [] and calls["sync"] == 1

    def test_partial_failure_does_not_mark_sent_and_rerun_sends_only_the_rest(self, monkeypatch):
        many = [f"u{n}@x.de" for n in range(150)]          # zwei Batches
        m, calls = _wired(monkeypatch, many, fail_batches=0)
        # erster Batch klappt, zweiter scheitert
        orig = m.post_resend

        def flaky(client, path, payload, key, _n=[0]):
            _n[0] += 1
            if _n[0] == 2:
                calls["posts"].append((path, [x["to"][0] for x in payload], key))
                raise RuntimeError("Resend down")
            return orig(client, path, payload, key)
        monkeypatch.setattr(m, "post_resend", flaky)
        m.send_edition(dict(RELEASED), dry_run=False, force=False)
        assert not any("sent_at" in sql for sql, _ in calls["sql"])
        calls["posts"].clear()
        monkeypatch.setattr(m, "post_resend", orig)
        m.send_edition(dict(RELEASED), dry_run=False, force=False)
        assert [len(p[1]) for p in calls["posts"]] == [50]               # nur die 50 fehlenden
        assert any("sent_at" in sql for sql, _ in calls["sql"])

    def test_idempotency_key_is_stable_per_batch(self, monkeypatch):
        m = _mod(monkeypatch)
        k1 = m.idempotency_key("batch", 40, ["b@x.de", "a@x.de"])
        assert k1 == m.idempotency_key("batch", 40, ["a@x.de", "b@x.de"])
        assert k1 != m.idempotency_key("batch", 41, ["a@x.de", "b@x.de"])

    def test_post_resend_retries_transport_errors_with_the_same_key(self, monkeypatch):
        m = _mod(monkeypatch)
        import httpx
        monkeypatch.setattr(m.time, "sleep", lambda s: None)
        seen = []

        class Client:
            def __init__(self):
                self.n = 0

            def post(self, url, json, headers):
                seen.append(headers["Idempotency-Key"])
                self.n += 1
                if self.n < 3:
                    raise httpx.ConnectError("Connection reset by peer")
                return httpx.Response(200, json={"id": "ok"}, request=httpx.Request("POST", url))
        assert m.post_resend(Client(), "/emails", {"to": ["a@x.de"]}, "k-1") == {"id": "ok"}
        assert seen == ["k-1", "k-1", "k-1"]

    def test_test_to_needs_no_release_marks_nothing_and_only_allowlisted(self, monkeypatch):
        monkeypatch.setenv("REVIEW_NOTIFY_TO", "owner@x.de")
        monkeypatch.delenv("NEWSLETTER_TEST_TO", raising=False)
        m, calls = _wired(monkeypatch, ["a@x.de", "b@x.de"])
        unreleased = {"id": 40, "year": 2026, "week": 40}
        assert m.send_test(unreleased, "Owner@X.de ") == "t1"
        path, to, _ = calls["posts"][0]
        assert path == "/emails" and to == ["owner@x.de"]
        assert calls["sql"] == [] and calls["recorded"] == []
        with pytest.raises(ValueError):
            m.send_test(unreleased, "a@x.de")                             # Abonnent, nicht freigegeben
