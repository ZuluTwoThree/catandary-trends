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
