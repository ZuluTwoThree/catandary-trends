"""Web-Cache des Rechercheurs (pipeline/web_cache.py, 2026-09-12): Brave-Treffer
und Seitentexte werden je Haltefrist einmal geholt — auch ueber Laeufe hinweg."""
from __future__ import annotations

import time

import pytest

from pipeline import web_cache as wc


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_CACHE_PATH", str(tmp_path / "wc.sqlite"))
    monkeypatch.delenv("WEB_CACHE", raising=False)
    return wc


def test_put_get_and_ttl(cache, monkeypatch):
    k = cache.make_key("brave", "LFP price", 6)
    assert cache.cache_get("brave", k) is None
    assert cache.cache_put("brave", k, [{"url": "https://a"}])
    assert cache.cache_get("brave", k) == [{"url": "https://a"}]
    monkeypatch.setenv("WEB_CACHE_SEARCH_TTL_HOURS", "0")     # sofort abgelaufen
    assert cache.cache_get("brave", k) is None
    assert cache.make_key("brave", "  LFP Price ", 6) == k     # normalisiert


def test_disabled_cache_never_stores(cache, monkeypatch):
    monkeypatch.setenv("WEB_CACHE", "0")
    k = cache.make_key("page", "https://x")
    assert cache.cache_put("page", k, {"text": "t", "status": "fetched"}) is False
    assert cache.cache_get("page", k) is None


def test_purge_and_stats(cache):
    cache.cache_put("page", "a", {"text": "t", "status": "fetched"})
    st = cache.stats()
    assert st["page"]["rows"] == 1
    assert cache.purge(all_rows=True) == 1
    assert cache.stats() == {}


class TestResearcherUsesTheCache:

    @pytest.fixture
    def cr(self, cache, monkeypatch):
        import importlib
        import scripts.corpus_research as cr
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "k")
        for k in cr._web_stats:
            cr._web_stats[k] = 0
        return cr

    def test_brave_search_hits_the_api_once_per_query(self, cr, monkeypatch):
        import httpx
        calls = []

        class _R:
            def raise_for_status(self): pass
            def json(self): return {"web": {"results": [
                {"url": "https://example.org/a", "title": "A", "description": "d"}]}}

        monkeypatch.setattr(httpx, "get", lambda *a, **kw: calls.append(kw["params"]["q"]) or _R())
        monkeypatch.setattr(cr, "_BRAVE_MIN_INTERVAL", 0)
        first = cr.brave_search("lfp pack price 2025", 6)
        second = cr.brave_search("lfp pack price 2025", 6)
        assert calls == ["lfp pack price 2025"]
        assert [x["url"] for x in first] == [x["url"] for x in second] == ["https://example.org/a"]
        assert cr.web_stats()["brave_api"] == 1 and cr.web_stats()["brave_cached"] == 1

    def test_page_fetch_caches_stable_outcomes_only(self, cr, monkeypatch):
        seen = []

        class _Res:
            def __init__(self, text, reason): self.text, self.reason = text, reason

        outcomes = {"https://ok/x": _Res("The SPC runs to March 2031.", None),
                    "https://slow/y": _Res("", "error: timeout")}
        monkeypatch.setattr(cr, "fetch_fulltext_result", lambda u: seen.append(u) or outcomes[u])
        assert cr.fetch_web_page_status("https://ok/x")[1] == "fetched"
        assert cr.fetch_web_page_status("https://ok/x")[1] == "fetched"
        assert cr.fetch_web_page_status("https://slow/y")[1] == "timeout"
        assert cr.fetch_web_page_status("https://slow/y")[1] == "timeout"
        assert seen == ["https://ok/x", "https://slow/y", "https://slow/y"]
        assert cr.web_stats()["page_cached"] == 1
