"""robots.txt that cannot be read means "do not crawl" (RFC 9309 §2.3.1.4).

Until 2026-10-04 a 503 or a timeout on robots.txt was cached as "no rules" and
the article was fetched. Only a 4xx (no robots.txt) means everything is allowed.
"""
from __future__ import annotations

import httpx
import pytest

import pipeline.article_fetcher as af


class _Resp:
    def __init__(self, status: int, text: str = ""):
        self.status_code = status
        self.text = text


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(af, "_robots", {})
    yield


def test_server_error_on_robots_means_disallow(monkeypatch):
    monkeypatch.setattr(af.httpx, "get", lambda *a, **k: _Resp(503))
    assert af._robots_ok("https://host.example/article") is False
    assert af._robots["host.example"] is af._ROBOTS_UNREACHABLE


def test_network_error_on_robots_means_disallow(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectTimeout("slow")
    monkeypatch.setattr(af.httpx, "get", boom)
    assert af._robots_ok("https://host.example/article") is False


def test_missing_robots_means_allowed(monkeypatch):
    monkeypatch.setattr(af.httpx, "get", lambda *a, **k: _Resp(404))
    assert af._robots_ok("https://host.example/article") is True
    assert af._robots["host.example"] is None


def test_real_rules_are_applied(monkeypatch):
    monkeypatch.setattr(af.httpx, "get",
                        lambda *a, **k: _Resp(200, "User-agent: *\nDisallow: /private/\n"))
    assert af._robots_ok("https://host.example/private/x") is False
    assert af._robots_ok("https://host.example/public/x") is True
