#!/usr/bin/env python3
"""Ingest public research/innovation *funding* records as dated raw_entries.

Funding awards are an early foresight signal: a grant is committed years before
the product, paper or market move it enables. This ingester pulls grant/award
records from open, public funding databases and stores, for each award, **what
is concretely funded** (project title + objective/abstract), plus the funder,
the country/region (for technology-hotspot clustering) and the amount and date.

All sources are free, public, dated primary sources (no scraping, no aggregator
resale). Each award becomes a raw_entry (processed=0) under a per-source row
(source_type='api', vertical='CROSS'); the normal signal pipeline then classifies
the real vertical/PESTEL/mega-trend and embeds it.

Backends (verified working 2026-06-30):
  nsf       NSF Awards API (US)            — abstractText + awardee state + amount
  nih       NIH RePORTER (US biomed)       — abstract_text + org state/country
  openaire  OpenAIRE (EU + national)       — summary + funder + jurisdiction(country)
            covers Horizon Europe/CORDIS AND dozens of national funders ("all
            countries") with the funder's jurisdiction = country hotspot tag
  ukri      UKRI Gateway to Research (UK)  — abstractText + lead funder (opt-in;
            no server-side date filter, so client-filtered by start year)

The excerpt is prefixed with `[Funding · <funder> · <geo> · <amount>]` so the
funder, country and scale survive into the embedding and the classifier's
`regions` field — that is what makes the later cluster/trajectory hotspot view
possible.

Usage:
    python scripts/ingest_funding.py --backend all --since 2024-01-01 --dry-run
    python scripts/ingest_funding.py --backend nsf --since 2025-01-01 --limit 5000
    python scripts/ingest_funding.py --backend openaire --since 2024-01-01
    python scripts/ingest_funding.py --backend ukri --since 2024-01-01 --limit 4000
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_funding")

MAILTO = "trends@catandary.de"
UA = f"CatandaryTrends/1.0 (mailto:{MAILTO})"
HEADERS = {"User-Agent": UA}

# Technology shards for the OpenAIRE breadth pull. Each shard stays well under the
# API's 10k deep-paging window and doubles as a technology-cluster seed: the same
# query returns projects from every funder/country, so jurisdiction reveals where
# each technology is being funded (the hotspot map).
TECH_SHARDS = [
    "artificial intelligence", "machine learning", "quantum", "semiconductor",
    "battery energy storage", "hydrogen", "photovoltaic solar", "carbon capture",
    "biotechnology", "gene therapy", "vaccine", "synthetic biology",
    "robotics", "autonomous vehicles", "6G wireless", "cybersecurity",
    "circular economy", "sustainable materials", "alternative protein",
    "microbiome", "longevity ageing", "space satellite", "fusion energy",
    "green hydrogen", "neuromorphic", "digital twin", "advanced manufacturing",
    # 2026-08-09, Paket A (#4): Funding-Abdeckung fuer die neuen Themes
    "digital health", "telemedicine", "health informatics",
    "education technology", "lifelong learning",
    "remote work", "future of work",
    "spacecraft", "satellite constellation", "space launch",
    "quantum communication", "photonics",
]


def _amount(val, currency: str = "") -> str:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    cur = currency or "$"
    if n >= 1e6:
        return f"{cur}{n/1e6:.1f}M"
    if n >= 1e3:
        return f"{cur}{n/1e3:.0f}k"
    return f"{cur}{n:.0f}"


def _safe_insert(source_id: int, url: str, title: str, excerpt: str,
                 pub: str | None, tries: int = 6) -> int | None:
    """db.insert_raw_entry with retry on transient SQLite write-lock contention
    (the signal pipeline may be writing the same DB). Duplicates return None and
    are handled inside insert_raw_entry."""
    # Postgres rejects NUL (0x00) in text — some NIH/OpenAIRE abstracts carry them.
    title = (title or "").replace("\x00", "")
    excerpt = (excerpt or "").replace("\x00", "")
    for i in range(tries):
        try:
            return db.insert_raw_entry(source_id, url, title, excerpt, pub)
        except Exception as e:  # noqa: BLE001
            if "locked" in str(e).lower() and i < tries - 1:
                time.sleep(0.5 * (i + 1))
                continue
            raise


def _excerpt(funder: str, geo: str, amount: str, abstract: str) -> str:
    bits = [b for b in (funder, geo, amount) if b]
    prefix = f"[Funding · {' · '.join(bits)}] " if bits else ""
    return (prefix + (abstract or "").strip())[:2000]


class SourceDown(RuntimeError):
    """Eine Quelle antwortet gar nicht mehr — der Rest ihres Laufs wird übersprungen."""


# Abbruch für tote Quellen (seit 2026-10-10, Owner): am 10.10. antwortete die alte OpenAIRE-
# Suchschnittstelle nicht mehr; jeder der 39 Suchbegriffe lief sechsmal in 45-s-Timeouts mit
# Backoff — 142 Zeitüberschreitungen, der Samstagslauf stand drei statt 1,3 Stunden und hielt den
# Research Pulse auf. Jetzt zählt jede Quelle (Host) ihre Netzfehler IN FOLGE über alle Anfragen;
# ab DEAD_AFTER ohne eine einzige Antwort dazwischen gilt sie als tot (SourceDown), ihr Backend
# endet, die anderen laufen weiter, der Lauf endet mit rc 3 (→ Ops-Alarm job_failed).
DEAD_AFTER = int(os.getenv("FUNDING_DEAD_AFTER", "8"))
_FAIL_STREAK: dict[str, int] = {}


def _get_json(client: httpx.Client, url: str, *, params=None, method="GET",
              json_body=None, tries: int = 6, timeout: int = 45):
    """HTTP GET/POST returning parsed JSON, with exponential backoff on 429/5xx.
    Raises SourceDown after DEAD_AFTER consecutive network errors against the same host."""
    host = httpx.URL(url).host
    for i in range(tries):
        try:
            if method == "POST":
                r = client.post(url, json=json_body, timeout=timeout)
            else:
                r = client.get(url, params=params, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — transient network
            _FAIL_STREAK[host] = _FAIL_STREAK.get(host, 0) + 1
            if _FAIL_STREAK[host] >= DEAD_AFTER:
                raise SourceDown(f"{host}: {_FAIL_STREAK[host]} network errors in a row ({e})")
            logger.warning("request error (%s), retry %d/%d", e, i + 1, tries)
            time.sleep(2 ** i)
            continue
        _FAIL_STREAK[host] = 0
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                logger.warning("non-JSON 200 from %s", url)
                return None
        if r.status_code in (429, 500, 502, 503, 504):
            logger.warning("HTTP %d, backoff retry %d/%d", r.status_code, i + 1, tries)
            time.sleep(2 ** i)
            continue
        logger.error("HTTP %d from %s", r.status_code, url)
        return None
    return None


# ----------------------------------------------------------------------------- NSF
def ingest_nsf(since: str, limit: int, dry_run: bool) -> dict:
    stats = {"seen": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    start_mdy = datetime.strptime(since, "%Y-%m-%d").strftime("%m/%d/%Y")
    end_mdy = date.today().strftime("%m/%d/%Y")
    source_id = -1 if dry_run else db.upsert_source(
        "NSF Awards (US Federal Research Funding)",
        "https://api.nsf.gov/services/v1/awards.json", "api", "CROSS")
    fields = ("id,title,abstractText,awardeeStateCode,awardeeName,date,startDate,"
              "fundsObligatedAmt,fundProgramName")
    rpp, offset = 25, 1
    with httpx.Client(headers=HEADERS) as client:
        while stats["seen"] < limit:
            data = _get_json(client, "https://api.nsf.gov/services/v1/awards.json",
                             params={"dateStart": start_mdy, "dateEnd": end_mdy,
                                     "rpp": rpp, "offset": offset, "printFields": fields})
            awards = ((data or {}).get("response") or {}).get("award") or []
            if not awards:
                break
            for a in awards:
                stats["seen"] += 1
                aid = a.get("id")
                title = (a.get("title") or "").strip()
                if not aid or not title:
                    stats["skipped"] += 1
                    continue
                url = f"https://www.nsf.gov/awardsearch/showAward?AWD_ID={aid}"
                geo = f"US-{a.get('awardeeStateCode')}" if a.get("awardeeStateCode") else "US"
                funder = "NSF" + (f"/{a['fundProgramName']}" if a.get("fundProgramName") else "")
                excerpt = _excerpt(funder, geo, _amount(a.get("fundsObligatedAmt")),
                                   a.get("abstractText") or "")
                pub = _nsf_date(a.get("startDate") or a.get("date"))
                if dry_run:
                    stats["inserted"] += 1
                    continue
                eid = _safe_insert(source_id, url, title, excerpt, pub)
                stats["duplicates" if eid is None else "inserted"] += 1
            offset += rpp
            if len(awards) < rpp:
                break
    return stats


def _nsf_date(s: str | None) -> str | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


# ----------------------------------------------------------------------------- NIH
def ingest_nih(since: str, limit: int, dry_run: bool) -> dict:
    stats = {"seen": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    since_year = int(since[:4])
    years = list(range(since_year, date.today().year + 1))
    source_id = -1 if dry_run else db.upsert_source(
        "NIH RePORTER (US Biomedical Funding)",
        "https://api.reporter.nih.gov/v2/projects/search", "api", "CROSS")
    include = ["ProjectTitle", "AbstractText", "Organization", "FiscalYear",
               "ApplId", "ProjectStartDate", "AwardAmount", "AgencyIcAdmin"]
    with httpx.Client(headers=HEADERS) as client:
        for yr in years:
            offset, page_limit = 0, 500
            while stats["seen"] < limit and offset < 15000:
                body = {"criteria": {"fiscal_years": [yr]},
                        "include_fields": include,
                        "offset": offset, "limit": page_limit,
                        "sort_field": "project_start_date", "sort_order": "desc"}
                data = _get_json(client, "https://api.reporter.nih.gov/v2/projects/search",
                                 method="POST", json_body=body)
                results = (data or {}).get("results") or []
                if not results:
                    break
                for p in results:
                    stats["seen"] += 1
                    appl = p.get("appl_id")
                    title = (p.get("project_title") or "").strip()
                    if not appl or not title:
                        stats["skipped"] += 1
                        continue
                    url = f"https://reporter.nih.gov/project-details/{appl}"
                    org = p.get("organization") or {}
                    st, country = org.get("org_state"), org.get("org_country")
                    geo = f"US-{st}" if st else (country or "US")
                    ic = (p.get("agency_ic_admin") or {}).get("abbreviation") or ""
                    funder = "NIH" + (f"/{ic}" if ic else "")
                    excerpt = _excerpt(funder, geo, _amount(p.get("award_amount")),
                                       p.get("abstract_text") or "")
                    pub = (p.get("project_start_date") or "")[:10] or f"{yr}-01-01"
                    if dry_run:
                        stats["inserted"] += 1
                        continue
                    eid = _safe_insert(source_id, url, title, excerpt, pub)
                    stats["duplicates" if eid is None else "inserted"] += 1
                offset += page_limit
                if len(results) < page_limit:
                    break
    return stats


# ------------------------------------------------------------------------ OpenAIRE
def _oa(node, *path):
    """Walk OpenAIRE's verbose `{"$": value}` JSON safely."""
    cur = node
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    if isinstance(cur, dict) and "$" in cur:
        return cur["$"]
    return cur


OPENAIRE_GRAPH = "https://api.openaire.eu/graph/v1/projects"


def _oa_text(t: str | None) -> str:
    """OpenAIRE-Texte tragen Excel-Reste (`_x000D_`) und Mehrfach-Leerraum."""
    return " ".join((t or "").replace("_x000D_", " ").split())


def ingest_openaire(since: str, limit: int, dry_run: bool) -> dict:
    """OpenAIRE-Projekte über die Graph API v1 (seit 2026-10-10).

    Die alte Suchschnittstelle (api.openaire.eu/search/projects) antwortete am 10.10. nicht mehr.
    Die Graph API filtert das Startdatum serverseitig (fromStartDate/toStartDate) — die frühere
    Krücke „absteigend sortieren und clientseitig abbrechen" entfällt (startYear/endYear der alten
    API schnitten auf das Projekt-ENDE). Projekt-IDs haben dasselbe Format wie vorher
    (`<quelle>::<hash>`), die URL und damit die Dubletten-Erkennung bleiben gleich."""
    stats = {"seen": 0, "inserted": 0, "duplicates": 0, "skipped": 0, "old": 0, "future": 0}
    future_cap = f"{date.today().year + 3}-12-31"
    source_id = -1 if dry_run else db.upsert_source(
        "OpenAIRE Projects (EU + National Funders)",
        "https://api.openaire.eu/search/projects", "api", "CROSS")   # unverändert: dieselbe Quellzeile
    per_shard = max(300, limit // max(1, len(TECH_SHARDS)))
    with httpx.Client(headers=HEADERS) as client:
        for kw in TECH_SHARDS:
            got, page, size = 0, 1, 50
            while got < per_shard and page * size <= 10000 and stats["seen"] < limit:
                data = _get_json(client, OPENAIRE_GRAPH,
                                 params={"search": kw, "fromStartDate": since, "toStartDate": future_cap,
                                         "sortBy": "startDate DESC", "pageSize": size, "page": page})
                results = (data or {}).get("results") or []
                if not results:
                    break
                for item in results:
                    stats["seen"] += 1
                    got += 1
                    obj_id, title = item.get("id"), _oa_text(item.get("title"))
                    if not obj_id or not title:
                        stats["skipped"] += 1
                        continue
                    pub = (item.get("startDate") or "")[:10]
                    url = f"https://explore.openaire.eu/search/project?projectId={obj_id}"
                    f0 = (item.get("fundings") or [{}])[0] or {}
                    funder = f0.get("name") or f0.get("shortName") or "—"
                    juris = f0.get("jurisdiction") or ""
                    g = item.get("granted") or {}
                    cur = g.get("currency") or "€"
                    cur = "€" if cur in ("EUR", "€") else cur
                    amt = _amount(g.get("fundedAmount") or g.get("totalCost") or None, cur)
                    excerpt = _excerpt(funder, juris, amt, _oa_text(item.get("summary")))
                    if dry_run:
                        stats["inserted"] += 1
                        continue
                    eid = _safe_insert(source_id, url, title, excerpt, pub or None)
                    stats["duplicates" if eid is None else "inserted"] += 1
                page += 1
                if len(results) < size:
                    break
            logger.info("[openaire] '%s': seen=%d inserted=%d", kw, stats["seen"], stats["inserted"])
    return stats


# ---------------------------------------------------------------------------- UKRI
def _ukri_date(p: dict) -> str | None:
    """GtR `start`/`end` are ISO strings (often null in list view); `created`/
    `updated` are epoch-millisecond ints. Return the best available ISO date."""
    for v in (p.get("start"), p.get("end")):
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    for v in (p.get("created"), p.get("updated")):
        if isinstance(v, (int, float)) and v > 0:
            return datetime.utcfromtimestamp(v / 1000).strftime("%Y-%m-%d")
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    return None


def ingest_ukri(since: str, limit: int, dry_run: bool) -> dict:
    stats = {"seen": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    since_year = int(since[:4])
    source_id = -1 if dry_run else db.upsert_source(
        "UKRI Gateway to Research (UK)",
        "https://gtr.ukri.org/gtr/api/projects", "api", "CROSS")
    page, size, max_pages = 1, 100, 400  # bounded: no server-side date filter
    with httpx.Client(headers={**HEADERS, "Accept": "application/json"}) as client:
        while stats["inserted"] < limit and page <= max_pages:
            data = _get_json(client, "https://gtr.ukri.org/gtr/api/projects",
                             params={"q": "", "p": page, "s": size})
            projects = (data or {}).get("project") or []
            if not projects:
                break
            for p in projects:
                pub = _ukri_date(p)
                if pub and int(pub[:4]) < since_year:
                    continue
                stats["seen"] += 1
                pid = p.get("id")
                title = (p.get("title") or "").strip()
                if not pid or not title:
                    stats["skipped"] += 1
                    continue
                url = f"https://gtr.ukri.org/project/{pid}"
                funder = "UKRI" + (f"/{p['leadFunder']}" if p.get("leadFunder") else "")
                abstract = p.get("abstractText") or p.get("techAbstractText") or ""
                excerpt = _excerpt(funder, "UK", "", abstract)
                if dry_run:
                    stats["inserted"] += 1
                    continue
                eid = _safe_insert(source_id, url, title, excerpt, pub)
                stats["duplicates" if eid is None else "inserted"] += 1
            page += 1
    return stats


BACKENDS = {"nsf": ingest_nsf, "nih": ingest_nih, "openaire": ingest_openaire, "ukri": ingest_ukri}
DEFAULT_ALL = ["nsf", "nih", "openaire"]  # clean recent-date windows; ukri opt-in


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest public funding awards as raw_entries")
    ap.add_argument("--backend", required=True,
                    choices=["all", *BACKENDS.keys()],
                    help="all = nsf+nih+openaire (ukri is opt-in)")
    ap.add_argument("--since", default="2024-01-01", help="YYYY-MM-DD (default 2024-01-01)")
    ap.add_argument("--limit", type=int, default=10000, help="max records per backend")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    backends = DEFAULT_ALL if args.backend == "all" else [args.backend]
    grand = {"seen": 0, "inserted": 0, "duplicates": 0, "skipped": 0}
    down: list[str] = []
    for b in backends:
        logger.info("=== backend=%s since=%s limit=%d dry=%s ===",
                    b, args.since, args.limit, args.dry_run)
        try:
            s = BACKENDS[b](args.since, args.limit, args.dry_run)
        except SourceDown as e:
            logger.error("[%s] source down — skipped the rest of this backend: %s", b, e)
            down.append(b)
            continue
        for k in grand:
            grand[k] += s.get(k, 0)
        tag = "[dry] would insert" if args.dry_run else "inserted"
        print(f"{b:9s}: seen {s['seen']:6d} | {tag} {s['inserted']:6d} | "
              f"{s['duplicates']} dup | {s['skipped']} skip")
    print(f"{'TOTAL':9s}: seen {grand['seen']:6d} | inserted {grand['inserted']:6d} | "
          f"{grand['duplicates']} dup | {grand['skipped']} skip")
    if down:
        print(f"SOURCE DOWN: {', '.join(down)} (rc 3)")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
