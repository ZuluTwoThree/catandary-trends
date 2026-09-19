"""Web-Suche des Rechercheurs mit Fallback (2026-09-13).

Brave Search ist die erste Wahl (bezahltes Kontingent, gute Frische). Faellt
sie aus — 402 (Kontingent erschoepft, 12.09.), 429, 5xx, Netzfehler, fehlender
Schluessel — springt eine lokale SearXNG-Instanz ein (Metasuche ueber Brave,
Google CSE u. a.; Docker `searxng`, 127.0.0.1:8888, Einstellungen in
deploy/searxng/settings.yml, JSON-Format an, Limiter aus).

    from pipeline.web_search import search_raw
    results, backend = search_raw("lfp pack price 2025", count=6)

`results` ist die ROHE Trefferliste in Brave-Form ({url, title, description,
page_age, profile.name}) — SearXNG-Treffer werden dorthin umgeformt, damit der
Aufrufer nichts unterscheiden muss.

Umgebung: WEB_SEARCH_BACKEND = auto (Default) | brave | searxng;
SEARXNG_URL (Default http://127.0.0.1:8888); BRAVE_SEARCH_API_KEY.
"""
from __future__ import annotations

import logging
import os
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
BRAVE_MIN_INTERVAL = 1.05          # Brave free/base tier: 1 request per second
_brave_last_call = 0.0


class SearchUnavailable(RuntimeError):
    """Kein Backend konnte die Anfrage beantworten."""


def backend_mode() -> str:
    m = (os.getenv("WEB_SEARCH_BACKEND") or "auto").strip().lower()
    return m if m in ("auto", "brave", "searxng") else "auto"


def searxng_url() -> str:
    return (os.getenv("SEARXNG_URL") or "http://127.0.0.1:8888").rstrip("/")


def _brave(query: str, count: int) -> list[dict]:
    global _brave_last_call
    import httpx
    key = os.environ.get("BRAVE_SEARCH_API_KEY", "").strip()
    if not key:
        raise SearchUnavailable("BRAVE_SEARCH_API_KEY is not set (.env)")
    wait = BRAVE_MIN_INTERVAL - (time.time() - _brave_last_call)
    if wait > 0:
        time.sleep(wait)
    r = httpx.get(BRAVE_ENDPOINT, params={"q": query, "count": min(count, 20)},
                  headers={"X-Subscription-Token": key, "Accept": "application/json"},
                  timeout=20)
    _brave_last_call = time.time()
    r.raise_for_status()
    return list((r.json().get("web") or {}).get("results", []))


def _searxng(query: str, count: int) -> list[dict]:
    import httpx
    r = httpx.get(f"{searxng_url()}/search",
                  params={"q": query, "format": "json", "language": "en", "safesearch": 0},
                  headers={"Accept": "application/json", "X-Forwarded-For": "127.0.0.1",
                           "X-Real-IP": "127.0.0.1"},
                  timeout=30)
    r.raise_for_status()
    out: list[dict] = []
    for x in (r.json().get("results") or []):
        url = str(x.get("url") or "").strip()
        if not url.startswith("http"):
            continue
        host = urlparse(url).netloc.lower().removeprefix("www.")
        out.append({
            "url": url,
            "title": str(x.get("title") or url),
            "description": str(x.get("content") or ""),
            "page_age": str(x.get("publishedDate") or "")[:10],
            "profile": {"name": host},
            "meta_url": {"hostname": host},
            "engine": x.get("engine"),
        })
        if len(out) >= min(count, 20):
            break
    return out


def _brave_failure_is_fallback_worthy(exc: Exception) -> bool:
    """402/429/5xx/Netz → SearXNG; ein 400 (kaputte Anfrage) nicht."""
    try:
        import httpx
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            return code in (401, 402, 403, 408, 429) or code >= 500
        if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
            return True
    except Exception:                                               # noqa: BLE001
        pass
    return isinstance(exc, SearchUnavailable)


def search_raw(query: str, count: int = 6) -> tuple[list[dict], str]:
    """(rohe Treffer, benutztes Backend). Wirft SearchUnavailable, wenn kein
    Backend antwortet — der Aufrufer protokolliert das wie bisher je Anfrage."""
    mode = backend_mode()
    if mode == "searxng":
        return _searxng(query, count), "searxng"
    if mode == "brave":
        return _brave(query, count), "brave"
    try:
        return _brave(query, count), "brave"
    except Exception as exc:                                        # noqa: BLE001
        if not _brave_failure_is_fallback_worthy(exc):
            raise
        logger.warning("brave search failed (%s) — falling back to searxng at %s",
                       str(exc)[:80], searxng_url())
        try:
            return _searxng(query, count), "searxng"
        except Exception as exc2:                                   # noqa: BLE001
            raise SearchUnavailable(f"brave: {str(exc)[:80]}; searxng: {str(exc2)[:80]}") from exc2


def healthy(backend: str = "searxng") -> bool:
    """Kurzer Erreichbarkeitstest (fuer Wächter/Handbuch)."""
    try:
        import httpx
        if backend == "searxng":
            return httpx.get(f"{searxng_url()}/healthz", timeout=5).status_code == 200
        return bool(os.environ.get("BRAVE_SEARCH_API_KEY", "").strip())
    except Exception:                                               # noqa: BLE001
        return False
