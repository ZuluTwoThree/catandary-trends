#!/usr/bin/env python3
"""Förderaufrufe der öffentlichen Hand als Signale (Owner 2026-10-10, Stufe 2).

„Was von öffentlicher Hand gefördert wird, ist ein Trendsignal.“ Neben den bewilligten Projekten
(ingest_funding.py: NSF/NIH/OpenAIRE/UKRI) jetzt die OFFENEN und ANGEKÜNDIGTEN Aufrufe:

  eu_ft       EU Funding & Tenders Portal — Horizon Europe, EIC, Digital Europe, LIFE, CERV …
              (SEDIA-Such-API, Status offen + angekündigt; ~1.200 Aufrufe)
  grants_gov  grants.gov — alle US-Bundesausschreibungen (DOE, DoD, NIH, NSF, USDA …; ~1.500),
              Beschreibung je NEUER Ausschreibung per fetchOpportunity
  nsf         NSF Funding Opportunities (RSS der Programmankündigungen)

Jeder Aufruf wird ein raw_entry einer Quelle mit dem Namenspräfix „Funding call:“ (source_type 'api'):
  * Ebene Förderung in allen Ebenen-Regeln (pipeline/tiers.py FUNDING_PREFIXES und Zwillinge),
  * öffentliche Förderung → kein Relevanzfilter (tiers.is_public_funding), Signaltyp funding,
  * verarbeitet im Samstagslauf über den Signalpfad (signal_batch_embedded --source-type api),
    NICHT als Artikel — allein das EU-Portal hat über tausend offene Aufrufe.
Auszug: „[Funding call · Programm/Behörde · Frist … · Budget …] Beschreibung“. Datum = Öffnung des
Aufrufs, höchstens heute (angekündigte Aufrufe mit Zukunftsdatum würden Zeitreihen verzerren).
Ansprechpartner (Name, E-Mail, Telefon) aus grants.gov werden NICHT übernommen.

    python scripts/ingest_funding_calls.py --backend all [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import db  # noqa: E402
from ingest_funding import HEADERS, SourceDown, _amount, _get_json, _safe_insert  # noqa: E402

logger = logging.getLogger("ingest_funding_calls")

EU_SEARCH = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
EU_TOPIC_URL = "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{}"
EU_STATUS = {"31094501": "forthcoming", "31094502": "open"}
GRANTS_SEARCH = "https://api.grants.gov/v1/api/search2"
GRANTS_FETCH = "https://api.grants.gov/v1/api/fetchOpportunity"
GRANTS_URL = "https://www.grants.gov/search-results-detail/{}"
NSF_RSS = "https://www.nsf.gov/rss/rss_www_funding_pgm_annc_inf.xml"

SOURCES = {
    "eu_ft": ("Funding call: EU Funding & Tenders Portal",
              "https://ec.europa.eu/info/funding-tenders/opportunities/portal/"),
    "grants_gov": ("Funding call: Grants.gov (US Federal)", "https://www.grants.gov/"),
    "nsf": ("Funding call: NSF Funding Opportunities", NSF_RSS),
}
EU_TOPIC_JSON = "https://ec.europa.eu/info/funding-tenders/opportunities/data/topicDetails/{}.json"
TAG = re.compile(r"<[^>]+>")
# Kontaktdaten im Fließtext (grants.gov nennt Ansprechpartner) — nicht übernehmen
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?\d[\d ()./-]{7,}\d)")


def clean(text) -> str:
    """HTML raus, Entities auflösen, E-Mail-Adressen/Telefonnummern raus, Leerraum zusammenziehen."""
    if isinstance(text, list):
        text = " ".join(str(t) for t in text if t)
    t = html.unescape(TAG.sub(" ", str(text or ""))).replace("\xa0", " ")
    t = PHONE.sub(" ", EMAIL.sub(" ", t))
    return " ".join(t.split())


def expired(deadlines: list[str]) -> bool:
    """Alle bekannten Fristen liegen in der Vergangenheit (ohne Frist: nicht abgelaufen)."""
    return bool(deadlines) and max(deadlines) < date.today().isoformat()


def first(v):
    return (v[0] if v else None) if isinstance(v, list) else v


def pub_date(opened: str | None) -> str | None:
    """Öffnungsdatum, höchstens heute."""
    if not opened:
        return None
    d = opened[:10]
    return min(d, date.today().isoformat())


def call_excerpt(kind: str, parts: list[str], body: str) -> str:
    head = " · ".join(p for p in [kind, *parts] if p)
    return (f"[{head}] " + (body or "")).strip()[:2000]


def _known(source_id: int) -> set[str]:
    if source_id < 0:
        return set()
    with db.get_connection() as conn:
        return {r["url"] for r in conn.execute("SELECT url FROM raw_entries WHERE source_id = ?",
                                               (source_id,)).fetchall()}


def _source(backend: str, dry_run: bool) -> int:
    name, url = SOURCES[backend]
    return -1 if dry_run else db.upsert_source(name, url, "api", "CROSS")


def _stats() -> dict:
    return {"seen": 0, "inserted": 0, "duplicates": 0, "skipped": 0}


def _store(stats: dict, source_id: int, known: set[str], url: str, title: str, excerpt: str,
           pub: str | None, dry_run: bool) -> None:
    stats["seen"] += 1
    if not url or not title:
        stats["skipped"] += 1
        return
    if url in known:
        stats["duplicates"] += 1
        return
    known.add(url)
    if dry_run:
        stats["inserted"] += 1
        return
    eid = _safe_insert(source_id, url, title, excerpt, pub)
    stats["duplicates" if eid is None else "inserted"] += 1


# ------------------------------------------------------------------------- EU F&T
def eu_budget(details: dict) -> str:
    """Summe der Jahresbudgets aus budgetOverviewJSONItem (best effort)."""
    try:
        total = 0.0
        for rows in ((details.get("budgetOverviewJSONItem") or {}).get("budgetTopicActionMap") or {}).values():
            for row in rows or []:
                total += sum(float(v) for v in (row.get("budgetYearMap") or {}).values())
        return _amount(total, "€") if total else ""
    except (TypeError, ValueError, AttributeError):
        return ""


def eu_status(m: dict, details: dict | None) -> str:
    """Status laut Topic-Details (verlässlich), sonst laut Suche."""
    for a in (details or {}).get("actions") or []:
        ab = ((a.get("status") or {}).get("abbreviation") or "").lower()
        if ab:
            return ab
    return EU_STATUS.get(str(first(m.get("status")) or ""), "")


def eu_record(m: dict, details: dict | None = None) -> tuple[str, str, str, str | None] | None:
    """SEDIA-Metadaten (+ Topic-Details) → (url, title, excerpt, pub); None = nicht übernehmen
    (ohne Kennung/Titel, geschlossen, alle Fristen abgelaufen). Rein, ohne Netz (getestet)."""
    ident = first(m.get("identifier"))
    title = clean(first(m.get("title")) or first(m.get("callTitle")))
    if not ident or not title:
        return None
    deadlines = sorted({str(d)[:10] for d in (m.get("deadlineDate") or []) if d})
    status = eu_status(m, details)
    if status == "closed" or expired(deadlines):
        return None
    programme = ident.split("-")[0] if "-" in ident else ""
    budget = eu_budget(details or {})
    body = clean((details or {}).get("description")) or clean(m.get("description")) \
        or clean(first(m.get("callTitle")))
    parts = [f"EU {programme}".strip(), ident, status,
             ("deadline " + ", ".join(deadlines[-3:])) if deadlines else "", budget]
    return (EU_TOPIC_URL.format(ident), title, call_excerpt("Funding call", parts, body),
            pub_date(str(first(m.get("startDate")) or "")))


def ingest_eu(limit: int, dry_run: bool) -> dict:
    stats, sid = _stats(), _source("eu_ft", dry_run)
    known = _known(sid)
    query = {"bool": {"must": [{"terms": {"type": ["1", "2", "8"]}},
                               {"terms": {"status": list(EU_STATUS)}}]}}
    with httpx.Client(headers=HEADERS, timeout=60) as client:
        page, fails = 1, 0
        while stats["seen"] < limit:
            try:
                r = client.post(EU_SEARCH, params={"apiKey": "SEDIA", "text": "***", "pageSize": 100,
                                                   "pageNumber": page},
                                files={"query": (None, json.dumps(query), "application/json"),
                                       "languages": (None, '["en"]', "application/json")})
                r.raise_for_status()
                results = r.json().get("results") or []
            except Exception as e:  # noqa: BLE001
                fails += 1
                logger.warning("[eu_ft] page %d: %s (%d/3)", page, e, fails)
                if fails >= 3:
                    raise SourceDown(f"api.tech.ec.europa.eu: {e}")
                time.sleep(5 * fails)
                continue
            fails = 0
            if not results:
                break
            for res in results:
                m = res.get("metadata") or {}
                ident = first(m.get("identifier"))
                details = None
                if ident and EU_TOPIC_URL.format(ident) not in known and not dry_run:
                    try:                                   # Beschreibung + echter Status, nur für NEUE
                        dr = client.get(EU_TOPIC_JSON.format(ident.lower()))
                        details = (dr.json() or {}).get("TopicDetails") if dr.status_code == 200 else None
                    except Exception as e:  # noqa: BLE001
                        logger.warning("[eu_ft] details %s: %s", ident, e)
                    time.sleep(0.2)
                rec = eu_record(m, details)
                if rec is None:
                    stats["seen"] += 1
                    stats["skipped"] += 1
                    continue
                _store(stats, sid, known, *rec, dry_run)
            page += 1
            time.sleep(0.5)
    return stats


# ----------------------------------------------------------------------- grants.gov
def _us_date(s: str | None) -> str | None:
    for fmt in ("%m/%d/%Y", "%b %d, %Y %I:%M:%S %p %Z", "%b %d, %Y"):
        try:
            return datetime.strptime((s or "").strip()[:len("Feb 08, 2024 12:00:00 AM EST")], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def grants_record(hit: dict, syn: dict | None) -> tuple[str, str, str, str | None] | None:
    """Suchtreffer + Synopsis → (url, title, excerpt, pub). Ansprechpartner werden NICHT übernommen."""
    oid, title = hit.get("id"), clean(hit.get("title"))
    if not oid or not title:
        return None
    syn = syn or {}
    close = _us_date(hit.get("closeDate"))
    if close and expired([close]):
        return None
    ceiling = _amount(syn.get("awardCeiling"), "$")
    total = _amount(syn.get("estimatedFunding"), "$")
    parts = [f"US {hit.get('agency') or hit.get('agencyCode') or ''}".strip(), hit.get("number") or "",
             hit.get("oppStatus") or "", f"deadline {close}" if close else "",
             f"up to {ceiling} per award" if ceiling else "", f"total {total}" if total else ""]
    body = clean(syn.get("synopsisDesc"))
    return (GRANTS_URL.format(oid), title, call_excerpt("Funding call", parts, body),
            pub_date(_us_date(hit.get("openDate"))))


def ingest_grants(limit: int, dry_run: bool) -> dict:
    stats, sid = _stats(), _source("grants_gov", dry_run)
    known = _known(sid)
    with httpx.Client(headers={**HEADERS, "Content-Type": "application/json"}, timeout=60) as client:
        start = 0
        while stats["seen"] < limit:
            data = _get_json(client, GRANTS_SEARCH, method="POST",
                             json_body={"rows": 250, "startRecordNum": start, "oppStatuses": "forecasted|posted"})
            hits = ((data or {}).get("data") or {}).get("oppHits") or []
            if not hits:
                break
            for hit in hits:
                url = GRANTS_URL.format(hit.get("id"))
                syn = None
                if url not in known and not dry_run:        # Beschreibung nur für NEUE Ausschreibungen
                    det = _get_json(client, GRANTS_FETCH, method="POST",
                                    json_body={"opportunityId": int(hit["id"])}, tries=3)
                    syn = ((det or {}).get("data") or {}).get("synopsis") \
                        or ((det or {}).get("data") or {}).get("forecast")
                    time.sleep(0.2)
                rec = grants_record(hit, syn)
                if rec is None:
                    stats["seen"] += 1
                    stats["skipped"] += 1
                    continue
                _store(stats, sid, known, *rec, dry_run)
            start += len(hits)
    return stats


# ------------------------------------------------------------------------------ NSF
def ingest_nsf(limit: int, dry_run: bool) -> dict:
    import feedparser
    stats, sid = _stats(), _source("nsf", dry_run)
    known = _known(sid)
    with httpx.Client(headers=HEADERS, timeout=60) as client:
        try:
            r = client.get(NSF_RSS)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            raise SourceDown(f"www.nsf.gov: {e}")
    for e in feedparser.parse(r.content).entries[:limit]:
        pub = None
        if getattr(e, "published_parsed", None):
            pub = pub_date(time.strftime("%Y-%m-%d", e.published_parsed))
        excerpt = call_excerpt("Funding call", ["US NSF"], clean(getattr(e, "summary", "")))
        _store(stats, sid, known, getattr(e, "link", ""), clean(getattr(e, "title", "")), excerpt, pub, dry_run)
    return stats


BACKENDS = {"eu_ft": ingest_eu, "grants_gov": ingest_grants, "nsf": ingest_nsf}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", required=True, choices=["all", *BACKENDS])
    ap.add_argument("--limit", type=int, default=5000, help="höchstens so viele Aufrufe je Quelle")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    down = []
    for b in (list(BACKENDS) if a.backend == "all" else [a.backend]):
        t0 = time.time()
        try:
            s = BACKENDS[b](a.limit, a.dry_run)
        except SourceDown as e:
            logger.error("[%s] source down — skipped: %s", b, e)
            down.append(b)
            continue
        tag = "[dry] would insert" if a.dry_run else "inserted"
        print(f"{b:10s}: seen {s['seen']:5d} | {tag} {s['inserted']:5d} | {s['duplicates']} dup | "
              f"{s['skipped']} skip | {time.time() - t0:.0f}s")
    if down:
        print(f"SOURCE DOWN: {', '.join(down)} (rc 3)")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
