"""Fremde GPU im Tailnet nutzen — aber nur im vereinbarten Zeitfenster.

Stand 2026-09-11: der einzige Nutzer war der Volltext-Embedding-Lauf (#102),
den der Owner zurueckgebaut hat. `window_open()`/`REMOTE_EMBED_HOST` liest noch
der Ops-Sampler (pipeline/ops_probe.probe_remote); `embed_batch_remote()`
bleibt als Baustein fuer einen kuenftigen Nutzer stehen.

Auf `bequiet` (Tailnet `100.119.239.40`, Windows) steckt eine RTX 5080 mit
16 GB. Owner-Regel vom 2026-09-10: **zwischen 01:00 und 17:00 frei nutzbar,
zwischen 17:00 und 01:00 gehoert sie dem Owner.** Dieses Modul haelt sich daran
— alles hier fragt zuerst, ob das Fenster offen ist.

Warum es sich lohnt (gemessen 2026-09-10, warm, Ø 2.013 Zeichen je Text):

    bequiet / RTX 5080 via Ollama    12,4 Texte/s
    lokal   / RTX 3090 via llama.cpp  6,6 Texte/s
    lokal   / CPU-Server :8091        0,05 Texte/s

Und die Vektoren sind austauschbar: derselbe Text, einmal hier und einmal dort
eingebettet, ergab **cos 0,9995** — dasselbe Modell (Qwen3-Embedding-8B Q4_K_M),
derselbe Raum. Ein Backfill kann also ohne Bruch zwischen beiden wechseln.

Zwei Dinge sind bewusst konservativ:

  * **Kaltstart.** Die erste Anfrage nach einer Pause kostet ~35 s (Modell
    laden). Der Aufrufer sollte das einkalkulieren, nicht als Ausfall werten.
  * **Nie verlassen.** `available()` prueft Fenster UND Erreichbarkeit. Ist der
    Rechner aus — er ist ein Arbeitsplatz, kein Server, Laufzeit beim ersten
    Blick 2 h — faellt der Aufrufer auf die lokale Karte zurueck.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, time as dtime

import httpx

# Wichtig: pipeline.config zuerst — dort laeuft load_dotenv(). Ohne diesen Import
# liest os.getenv() unten die blanke Prozessumgebung, und die .env-Werte kommen
# nie an (beobachtet 2026-09-10: REMOTE_EMBED_HOST blieb leer, weil
# scripts/embed_full_text.py remote_gpu VOR pipeline.config importiert).
from pipeline import config as _config  # noqa: F401

logger = logging.getLogger(__name__)

REMOTE_EMBED_HOST = os.getenv("REMOTE_EMBED_HOST", "")
REMOTE_EMBED_MODEL = os.getenv("REMOTE_EMBED_MODEL", "qwen3-embedding")
#: "HH:MM-HH:MM" in lokaler Zeit. Ueber Mitternacht hinweg erlaubt.
REMOTE_GPU_WINDOW = os.getenv("REMOTE_GPU_WINDOW", "01:00-17:00")
REMOTE_TIMEOUT = float(os.getenv("REMOTE_EMBED_TIMEOUT", "300"))


def _parse_window(spec: str) -> tuple[dtime, dtime]:
    lo, hi = spec.split("-")
    h1, m1 = (int(x) for x in lo.split(":"))
    h2, m2 = (int(x) for x in hi.split(":"))
    return dtime(h1, m1), dtime(h2, m2)


def window_open(now: datetime | None = None, spec: str | None = None) -> bool:
    """Liegt `now` im Nutzungsfenster? Ein Fenster ueber Mitternacht (z. B.
    22:00-06:00) wird korrekt behandelt."""
    start, end = _parse_window(spec or REMOTE_GPU_WINDOW)
    t = (now or datetime.now()).time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def available(now: datetime | None = None) -> str | None:
    """Host-URL, wenn konfiguriert UND Fenster offen UND erreichbar — sonst None.

    Die Erreichbarkeitspruefung ist bewusst kurz (2 s): ein ausgeschalteter
    Arbeitsplatzrechner soll den Aufrufer nicht aufhalten, sondern ihn sofort
    auf die lokale Karte zurueckfallen lassen."""
    if not REMOTE_EMBED_HOST:
        return None
    if not window_open(now):
        return None
    try:
        r = httpx.get(f"{REMOTE_EMBED_HOST}/api/version", timeout=2)
        if r.status_code != 200:
            return None
    except Exception:                                               # noqa: BLE001
        logger.info("remote GPU %s nicht erreichbar — lokal weiter", REMOTE_EMBED_HOST)
        return None
    return REMOTE_EMBED_HOST


def embed_batch_remote(texts: list[str], host: str | None = None,
                       model: str | None = None) -> list[list[float]]:
    """Eine Anfrage, viele Texte — Ollamas /api/embed nimmt eine Liste.

    Wirft bei jedem Fehler; der Aufrufer entscheidet, ob er zurueckfaellt. Das
    ist Absicht: ein stiller Wechsel des Backends mitten im Lauf waere genau die
    Art Unsichtbarkeit, die spaeter niemand mehr nachvollziehen kann."""
    url = f"{host or REMOTE_EMBED_HOST}/api/embed"
    r = httpx.post(url, json={"model": model or REMOTE_EMBED_MODEL, "input": texts},
                   timeout=REMOTE_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    vecs = data.get("embeddings")
    if not vecs or len(vecs) != len(texts):
        raise RuntimeError(f"{url}: {len(vecs or [])} Vektoren fuer {len(texts)} Texte")
    return vecs
