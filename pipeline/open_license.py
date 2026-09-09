"""Lizenzprüfung je Artikel — eine Lizenz sticht den TDM-Vorbehalt (#97, Wege B+C).

§44b Abs. 3 UrhG erlaubt dem Rechteinhaber, Text und Data Mining vorzubehalten.
Der Vorbehalt sperrt eine **Schranke**. Wer für denselben Artikel eine Lizenz
erteilt hat (CC BY, CC0, Public Domain), braucht die Schranke nicht — der
Vorbehalt des Hosts geht für diesen Artikel ins Leere.

Genau diese Konstellation ist bei den 33 am 2026-09-04 abgeschalteten Quellen
der Normalfall: `nature.com` liefert eine site-weite `tdmrep.json`, veröffentlicht
aber laufend Artikel unter CC BY (gemessen 09.09.: Nature 135 von 794 Werken seit
07/2026). An unseren eigenen Einträgen sind es 5 von 40 (12,5 %), bei ~500
Einträgen/Woche aus diesen Quellen also grob 60 Artikel/Woche.

Weg C ist der Lieferweg dazu: vom Vorbehalts-Host wird **nichts** geholt. Der
Feed dient nur als Entdeckungs-Index (dieselbe Regel, die der Owner am
2026-09-03 für Aggregatoren gesetzt hat); der Volltext kommt von der offenen
Fundstelle (`best_oa_location`), die der normale Fetcher mit robots- und
TDM-Prüfung abruft.

Nicht als offen gewertet: alles mit `nc` (nicht-kommerziell) oder `nd` (keine
Bearbeitung) — unsere Artikel entstehen in einem kommerziellen Umfeld und sind
Bearbeitungen im weiteren Sinn. `cc-by-sa` gilt als offen (Präzedenz 2026-09-04:
ITU News CC BY-SA 3.0 IGO, Hochschulforum CC BY-SA 4.0).
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

OPENALEX = "https://api.openalex.org/works"
MAILTO = "trends@catandary.de"
UA = f"CatandaryTrends/1.0 (mailto:{MAILTO})"
REQUEST_DELAY = float(os.getenv("OPENALEX_DELAY", "0.7"))

_OPEN_PREFIXES = ("cc-by", "cc0", "public-domain", "pd")
_CLOSED_TOKENS = ("-nc", "-nd")


def is_open_licence(licence: str | None) -> bool:
    """CC BY / CC BY-SA / CC0 / Public Domain — aber nie NC oder ND."""
    if not licence:
        return False
    lic = licence.strip().lower()
    if any(tok in lic for tok in _CLOSED_TOKENS):
        return False
    return any(lic.startswith(p) for p in _OPEN_PREFIXES)


def doi_from_url(url: str) -> str | None:
    """DOI aus der Artikel-URL, wo der Host sie preisgibt. Spart die Titelsuche
    (die bei Feed-Präfixen wie `[Articles]` oder Sonderzeichen oft danebengreift).

    Nature-News (`d41586-…`) sind Redaktionsbeiträge, keine Aufsätze — sie haben
    zwar einen DOI, sind aber nie offen lizenziert; sie fallen später am
    Lizenz-Check durch, nicht hier."""
    m = re.search(r"nature\.com/articles/([A-Za-z0-9._-]+)", url)
    if m:
        return f"10.1038/{m.group(1)}"
    m = re.search(r"/doi/(?:abs/|full/|pdf/)?(10\.\d{4,9}/[^\s?#]+)", url)
    if m:
        return m.group(1)
    return None


def clean_title(title: str) -> str:
    """Feed-Präfixe der Lancet-/Cell-Feeds entfernen (`[Articles] …`)."""
    return re.sub(r"^\[[^\]]{0,40}\]\s*", "", title or "").strip()


# Datenrepositorien: OpenAlex nennt sie oft als `best_oa_location`, weil dort
# ein Datensatz zum Aufsatz liegt. Der Aufsatztext steht da nicht — solche
# Fundstellen kommen ans Ende der Liste, nicht raus (manchmal sind sie alles,
# was es gibt).
_DEPOSIT_HOSTS = ("zenodo.org", "figshare.com", "dryad", "osf.io", "datadryad.org")


@dataclass
class OpenWork:
    """Auflösung eines raw_entry gegen OpenAlex."""
    doi: str | None = None
    licence: str | None = None
    oa_urls: tuple[str, ...] = ()
    matched_title: str | None = None
    reason: str | None = None          # nohit | http <status> | error <type>

    @property
    def oa_url(self) -> str | None:
        return self.oa_urls[0] if self.oa_urls else None

    @property
    def is_open(self) -> bool:
        return is_open_licence(self.licence) and bool(self.oa_urls)


def _rank_locations(work: dict) -> tuple[str, ...]:
    """Alle offenen Fundstellen des Werks, Datenrepositorien zuletzt, ohne Dubletten."""
    seen: list[str] = []
    for loc in [work.get("best_oa_location"), work.get("primary_location"),
                *(work.get("locations") or [])]:
        if not loc:
            continue
        for u in (loc.get("pdf_url"), loc.get("landing_page_url")):
            if u and u not in seen:
                seen.append(u)
    return tuple(sorted(seen, key=lambda u: any(h in u for h in _DEPOSIT_HOSTS)))


def _get(client: httpx.Client, params: dict) -> dict | None:
    key = os.getenv("OPENALEX_API_KEY", "")
    p = {**params, "per-page": 1, "mailto": MAILTO}
    if key:
        p["api_key"] = key
    r = client.get(OPENALEX, params=p, timeout=40)
    if r.status_code != 200:
        return {"_status": r.status_code}
    return r.json()


def resolve(url: str, title: str, client: httpx.Client | None = None) -> OpenWork:
    """raw_entry → OpenAlex-Werk → Lizenz + offene Fundstelle.

    Erst über den DOI aus der URL, sonst über die Titelsuche. Ein Treffer per
    Titelsuche wird gegen den bereinigten Titel geprüft, damit ein
    Beinahe-Treffer nicht die Lizenz eines fremden Werks erbt."""
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": UA})
    try:
        doi = doi_from_url(url)
        title_clean = clean_title(title)
        if doi:
            data = _get(client, {"filter": f"doi:{doi}"})
        else:
            if not title_clean:
                return OpenWork(reason="nohit")
            data = _get(client, {"filter": "title.search:" + title_clean.replace(",", " ")[:180]})
        if data is None or "_status" in (data or {}):
            return OpenWork(reason=f"http {(data or {}).get('_status')}")
        results = data.get("results") or []
        if not results:
            return OpenWork(doi=doi, reason="nohit")
        w = results[0]
        got_title = (w.get("title") or "").strip()
        if not doi and got_title.lower()[:80] != title_clean.lower()[:80]:
            return OpenWork(reason="nohit")           # Titelsuche traf ein anderes Werk
        loc = w.get("best_oa_location") or {}
        return OpenWork(doi=w.get("doi"), licence=loc.get("license"),
                        oa_urls=_rank_locations(w), matched_title=got_title)
    except Exception as e:                                    # noqa: BLE001
        return OpenWork(reason=f"error {type(e).__name__}")
    finally:
        if own:
            client.close()
        time.sleep(REQUEST_DELAY)
