"""Web-Suche mit Fallback (pipeline/web_search.py, 2026-09-13): Brave zuerst,
SearXNG bei 402/429/5xx/Netzfehler oder fehlendem Schluessel; Treffer in
Brave-Form; erzwungene Backends per WEB_SEARCH_BACKEND."""
from __future__ import annotations

import httpx
import pytest

from pipeline import web_search as ws


class _Resp:
    def __init__(self, status: int, payload: dict, url: str = "https://x"):
        self.status_code = status
        self._payload = payload
        self.request = httpx.Request("GET", url)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=self.request,
                                        response=httpx.Response(self.status_code, request=self.request))

    def json(self):
        return self._payload


BRAVE_OK = {"web": {"results": [{"url": "https://a.example/1", "title": "A", "description": "d"}]}}
SEARX_OK = {"results": [{"url": "https://b.example/2", "title": "B", "content": "c",
                         "publishedDate": "2026-09-01T00:00:00", "engine": "google"}]}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "k")
    monkeypatch.delenv("WEB_SEARCH_BACKEND", raising=False)
    monkeypatch.setattr(ws, "BRAVE_MIN_INTERVAL", 0)


def _route(monkeypatch, brave_status=200, searx_status=200):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        if "brave.com" in url:
            return _Resp(brave_status, BRAVE_OK, url)
        return _Resp(searx_status, SEARX_OK, url)

    monkeypatch.setattr(httpx, "get", fake_get)
    return calls


def test_brave_first(env, monkeypatch):
    calls = _route(monkeypatch)
    res, backend = ws.search_raw("q", 6)
    assert backend == "brave" and res[0]["url"] == "https://a.example/1"
    assert len(calls) == 1


def test_quota_exhausted_falls_back_to_searxng_in_brave_shape(env, monkeypatch):
    calls = _route(monkeypatch, brave_status=402)
    res, backend = ws.search_raw("q", 6)
    assert backend == "searxng"
    assert [c.split("/")[2] for c in calls] == ["api.search.brave.com", "127.0.0.1:8888"]
    r = res[0]
    assert r["url"] == "https://b.example/2" and r["description"] == "c"
    assert r["page_age"] == "2026-09-01" and r["profile"]["name"] == "b.example"


def test_a_bad_request_is_not_papered_over(env, monkeypatch):
    _route(monkeypatch, brave_status=400)
    with pytest.raises(httpx.HTTPStatusError):
        ws.search_raw("q", 6)


def test_missing_key_uses_searxng_in_auto_mode(env, monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY")
    calls = _route(monkeypatch)
    _, backend = ws.search_raw("q", 6)
    assert backend == "searxng" and all("brave.com" not in c for c in calls)


def test_forced_backend_and_total_failure(env, monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_BACKEND", "searxng")
    calls = _route(monkeypatch)
    assert ws.search_raw("q", 6)[1] == "searxng" and "brave.com" not in calls[0]
    monkeypatch.setenv("WEB_SEARCH_BACKEND", "auto")
    _route(monkeypatch, brave_status=503, searx_status=500)
    with pytest.raises(ws.SearchUnavailable):
        ws.search_raw("q", 6)
