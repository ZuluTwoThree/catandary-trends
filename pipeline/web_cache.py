"""Persistenter Cache fuer Web-Suche und Seitenabrufe des Rechercheurs.

Anlass (2026-09-12): drei Dossier-Laeufe zum selben Thema machten 340
Brave-Aufrufe, davon nur 156 verschiedene — die festen Suchmuster (Regulatorik,
Katalysator-Kalender, Foerderung) fragen bei jeder Version dasselbe, und jede
Seite wurde je Lauf neu geholt. Das Brave-Kontingent war am Nachmittag
erschoepft (402). Ein Cache mit kurzer Haltefrist nimmt den Wiederholungsanteil
heraus, ohne die Frische zu opfern.

    from pipeline.web_cache import cache_get, cache_put
    hit = cache_get("brave", key)          # None oder der gespeicherte Wert
    cache_put("brave", key, value)         # value: JSON-faehig

Eine SQLite-Datei (`data/web_cache.sqlite`, WEB_CACHE_PATH), eine Zeile je
(kind, key). Haltefristen je Art: WEB_CACHE_SEARCH_TTL_HOURS (Default 72 —
Suchergebnisse altern schneller) und WEB_CACHE_PAGE_TTL_HOURS (Default 168 =
7 Tage). WEB_CACHE=0 schaltet alles ab (jeder Aufruf geht ins Netz). Abgelaufene
Zeilen werden beim Schreiben geloescht; `purge()` raeumt von Hand.

Gecachte Seitentexte sind fluechtige Arbeitskopien fuer die laufende Analyse
(§44b UrhG: Vervielfaeltigung zum Zweck des TDM, Loeschung, sobald nicht mehr
erforderlich) — die 7 Tage sind die Obergrenze, nicht der Regelfall.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from pathlib import Path

from pipeline.config import DATA_DIR

logger = logging.getLogger(__name__)

DEFAULT_TTL_HOURS = {"brave": 72.0, "page": 168.0}


def enabled() -> bool:
    return os.getenv("WEB_CACHE", "1").strip().lower() not in ("0", "false", "no", "off")


def cache_path() -> Path:
    return Path(os.getenv("WEB_CACHE_PATH") or (DATA_DIR / "web_cache.sqlite"))


def ttl_hours(kind: str) -> float:
    env = {"brave": "WEB_CACHE_SEARCH_TTL_HOURS", "page": "WEB_CACHE_PAGE_TTL_HOURS"}.get(kind)
    raw = os.getenv(env, "") if env else ""
    try:
        return float(raw) if raw else DEFAULT_TTL_HOURS.get(kind, 72.0)
    except ValueError:
        return DEFAULT_TTL_HOURS.get(kind, 72.0)


def make_key(*parts: object) -> str:
    """Stabiler Schluessel aus beliebigen Teilen (Query + count, URL …)."""
    raw = "\x1f".join(str(p).strip().lower() for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    p = cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS web_cache ("
                 " kind TEXT NOT NULL, key TEXT NOT NULL, created REAL NOT NULL,"
                 " payload TEXT NOT NULL, PRIMARY KEY (kind, key))")
    return conn


def cache_get(kind: str, key: str):
    """Der gespeicherte Wert oder None (fehlt, abgelaufen, Cache aus, Fehler)."""
    if not enabled():
        return None
    try:
        with _connect() as conn:
            row = conn.execute("SELECT created, payload FROM web_cache WHERE kind = ? AND key = ?",
                               (kind, key)).fetchone()
        if not row:
            return None
        created, payload = row
        if time.time() - float(created) > ttl_hours(kind) * 3600:
            return None
        return json.loads(payload)
    except Exception as e:                                          # noqa: BLE001
        logger.warning("web_cache.get(%s): %s", kind, e)
        return None


def cache_put(kind: str, key: str, value) -> bool:
    """Wert speichern (JSON). Raeumt dabei abgelaufene Zeilen derselben Art ab.
    Ein Fehler hier darf einen Lauf nie kosten."""
    if not enabled():
        return False
    try:
        now = time.time()
        with _connect() as conn:
            conn.execute("DELETE FROM web_cache WHERE kind = ? AND created < ?",
                         (kind, now - ttl_hours(kind) * 3600))
            conn.execute("INSERT OR REPLACE INTO web_cache (kind, key, created, payload) "
                         "VALUES (?, ?, ?, ?)", (kind, key, now, json.dumps(value, ensure_ascii=False)))
        return True
    except Exception as e:                                          # noqa: BLE001
        logger.warning("web_cache.put(%s): %s", kind, e)
        return False


def purge(all_rows: bool = False) -> int:
    """Abgelaufene Zeilen loeschen (oder alle). Gibt die Zahl zurueck."""
    try:
        with _connect() as conn:
            if all_rows:
                cur = conn.execute("DELETE FROM web_cache")
            else:
                now = time.time()
                n = 0
                for kind in DEFAULT_TTL_HOURS:
                    n += conn.execute("DELETE FROM web_cache WHERE kind = ? AND created < ?",
                                      (kind, now - ttl_hours(kind) * 3600)).rowcount
                return n
            return cur.rowcount
    except Exception as e:                                          # noqa: BLE001
        logger.warning("web_cache.purge: %s", e)
        return 0


def stats() -> dict:
    try:
        with _connect() as conn:
            rows = conn.execute("SELECT kind, count(*), min(created) FROM web_cache GROUP BY kind").fetchall()
        return {k: {"rows": n, "oldest_hours": round((time.time() - (old or time.time())) / 3600, 1)}
                for k, n, old in rows}
    except Exception as e:                                          # noqa: BLE001
        return {"error": str(e)}


if __name__ == "__main__":                                          # pragma: no cover
    import argparse
    ap = argparse.ArgumentParser(description="Web-Cache des Rechercheurs")
    ap.add_argument("cmd", choices=["stats", "purge", "clear"])
    a = ap.parse_args()
    if a.cmd == "stats":
        print(json.dumps(stats(), indent=2))
    else:
        print(purge(all_rows=(a.cmd == "clear")))
