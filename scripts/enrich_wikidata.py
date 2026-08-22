#!/usr/bin/env python3
"""Wikidata-Enrichment für den Startup-Firmenstamm (#87 Phase 1, Plan §5.7).

CC0-Daten, anonymer SPARQL-Endpoint, keine Registrierung. Füllt die Lücken,
die die Funding-Quellen nicht schließen können: exaktes Gründungsdatum (P571),
Gründer (P112 — einzige freie Quelle), Website (P856), plus die QID als
weitere harte ID. Wikidata überschreibt NIE härtere Quellen (nur COALESCE).

Zwei Match-Pfade, konservativ nach Plan §4:
  Stufe A: LEI-Querverweis (P1278) für Firmen mit gesetzter LEI — Register-
           abgleich statt Namensvergleich.
  Stufe B: Bulk-Abzug der Firmen-Items MIT Gründungsdatum (Jahres-Slices
           1985+), lokal gematcht über name_norm; Länder-Gate (P17→ISO)
           wenn unsere Firma ein Land hat, sonst nur bei beidseitig
           eindeutigem Schlüssel >= 5 Zeichen (Presse-Regel).

Erwartung ehrlich: Wikidata kennt nur "notable" Firmen — Anreicherung der
Spitze, kein Basiskorpus.

    python scripts/enrich_wikidata.py --dry-run
    python scripts/enrich_wikidata.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline.company_norm import norm_company_name
from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("enrich_wikidata")

ENDPOINT = "https://query.wikidata.org/sparql"
# Projekt-Kontakt im UA ist die bestehende Ingester-Konvention (keine
# persönlichen Daten; Owner-Regel 2026-08-21 beachtet).
HEADERS = {"User-Agent": "CatandaryTrends research (trends@catandary.de)",
           "Accept": "application/sparql-results+json"}
SLEEP = 1.5          # WDQS-Fairness zwischen Queries
MIN_KEY_LEN = 5
SINCE_YEAR = 1985    # Startup-Korpus; ältere Gründungen sind kein Zielsegment

# Firmen-Klassen (direkte P31) — bewusst Liste statt P279*-Pfad (Timeouts)
COMPANY_CLASSES = ("Q4830453", "Q6881511", "Q783794", "Q2993680", "Q891723")


def sparql(client: httpx.Client, query: str, tries: int = 3) -> list[dict] | None:
    for attempt in range(tries):
        try:
            r = client.post(ENDPOINT, data={"query": query}, timeout=90)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "10"))
                logger.warning("429 — warte %ds", wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()["results"]["bindings"]
        except Exception as e:  # noqa: BLE001
            logger.warning("SPARQL-Fehler (%s), Versuch %d/%d", type(e).__name__,
                           attempt + 1, tries)
            time.sleep(5 * (attempt + 1))
    return None


def _val(b: dict, key: str) -> str | None:
    v = b.get(key, {}).get("value")
    return v.strip() if v else None


def _qid(b: dict, key: str = "item") -> str | None:
    v = _val(b, key)
    return v.rsplit("/", 1)[-1] if v else None


def _date(v: str | None) -> str | None:
    # Wikidata-Zeitwerte: "2013-04-01T00:00:00Z"; Jahres-Präzision kommt als
    # -01-01 — für unser DATE-Feld akzeptabel.
    return v[:10] if v and len(v) >= 10 and not v.startswith("-") else None


ITEM_FIELDS = """
  OPTIONAL { ?item wdt:P571 ?inception . }
  OPTIONAL { ?item wdt:P856 ?website . }
  OPTIONAL { ?item wdt:P17 ?c . ?c wdt:P297 ?ctry . }
"""


def pass_lei(client: httpx.Client, dry: bool) -> dict:
    """Stufe A: P1278 = LEI."""
    st = {"queries": 0, "matched": 0}
    with get_connection() as conn:
        rows = conn.execute(
            "select id, lei from startup_companies "
            "where lei is not null and wikidata_qid is null").fetchall()
    by_lei = {x["lei"]: x["id"] for x in rows}
    leis = list(by_lei)
    logger.info("LEI-Pass: %d Kandidaten", len(leis))
    for i in range(0, len(leis), 300):
        chunk = leis[i:i + 300]
        values = " ".join(f'"{lei}"' for lei in chunk)
        q = f"""SELECT ?item ?lei ?inception ?website ?ctry WHERE {{
          VALUES ?lei {{ {values} }}
          ?item wdt:P1278 ?lei .
          {ITEM_FIELDS}
        }}"""
        st["queries"] += 1
        res = sparql(client, q)
        time.sleep(SLEEP)
        if res is None:
            continue
        updates = {}
        for b in res:
            lei = _val(b, "lei")
            if lei in by_lei and lei not in updates:
                updates[lei] = (_qid(b), _date(_val(b, "inception")),
                                _val(b, "website"))
        if not dry:
            with get_connection() as conn:
                for lei, (qid, founded, website) in updates.items():
                    conn.execute(
                        "update startup_companies set wikidata_qid = ?, "
                        "founded_date = coalesce(founded_date, ?), "
                        "website = coalesce(website, ?) where id = ?",
                        (qid, founded, website, by_lei[lei]))
        st["matched"] += len(updates)
    logger.info("LEI-Pass fertig: %(matched)d Matches aus %(queries)d Queries", st)
    return st


def pass_name(client: httpx.Client, dry: bool) -> dict:
    """Stufe B: Bulk-Abzug (Items mit Gründungsdatum, Jahres-Slices) →
    lokales Matching über name_norm + Länder-Gate."""
    st = {"slices": 0, "wd_items": 0, "matched": 0, "geo_gated": 0}
    # Wikidata-Seite einsammeln
    wd_by_norm: dict[str, list[dict]] = defaultdict(list)
    from datetime import date
    for year in range(SINCE_YEAR, date.today().year + 1):
        classes = " ".join(f"wd:{c}" for c in COMPANY_CLASSES)
        q = f"""SELECT ?item ?itemLabel ?inception ?website ?ctry WHERE {{
          VALUES ?cls {{ {classes} }}
          ?item wdt:P31 ?cls .
          ?item wdt:P571 ?inception .
          FILTER(YEAR(?inception) = {year})
          OPTIONAL {{ ?item wdt:P856 ?website . }}
          OPTIONAL {{ ?item wdt:P17 ?c . ?c wdt:P297 ?ctry . }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
        }}"""
        res = sparql(client, q)
        time.sleep(SLEEP)
        st["slices"] += 1
        if res is None:
            logger.warning("Slice %d übersprungen (Timeout)", year)
            continue
        for b in res:
            label = _val(b, "itemLabel") or ""
            nn = norm_company_name(label)
            if len(nn) < MIN_KEY_LEN:
                continue
            wd_by_norm[nn].append({
                "qid": _qid(b), "founded": _date(_val(b, "inception")),
                "website": _val(b, "website"), "country": _val(b, "ctry")})
            st["wd_items"] += 1
        if year % 10 == 0:
            logger.info("  bis %d: %d Items", year, st["wd_items"])
    logger.info("Wikidata-Seite: %d Items, %d Schlüssel", st["wd_items"], len(wd_by_norm))

    # Unsere Seite
    with get_connection() as conn:
        ours = conn.execute(
            "select id, name_norm, country from startup_companies "
            "where wikidata_qid is null and length(name_norm) >= ?",
            (MIN_KEY_LEN,)).fetchall()
    ours_by_norm: dict[str, list[dict]] = defaultdict(list)
    for x in ours:
        ours_by_norm[x["name_norm"]].append(dict(x))

    updates: list[tuple] = []
    for nn, wd_items in wd_by_norm.items():
        cands = ours_by_norm.get(nn)
        if not cands:
            continue
        # dedupe Wikidata-Seite (mehrere P31-Klassen -> mehrere Zeilen pro Item)
        uniq = {w["qid"]: w for w in wd_items}.values()
        for c in cands:
            if c["country"]:
                hits = [w for w in uniq if w["country"] == c["country"]]
                if len(hits) != 1:
                    st["geo_gated"] += len(hits) > 1
                    continue
            else:
                # Presse-Regel: nur bei beidseitiger Eindeutigkeit
                if len(uniq) != 1 or len(cands) != 1:
                    continue
                hits = list(uniq)
            w = hits[0]
            updates.append((w["qid"], w["founded"], w["website"], c["id"]))
    if not dry:
        with get_connection() as conn:
            for qid, founded, website, cid in updates:
                conn.execute(
                    "update startup_companies set wikidata_qid = ?, "
                    "founded_date = coalesce(founded_date, ?), "
                    "website = coalesce(website, ?) where id = ?",
                    (qid, founded, website, cid))
    st["matched"] = len(updates)
    logger.info("Namens-Pass fertig: %(matched)d Matches (%(geo_gated)d mehrdeutig verworfen)", st)
    return st


def pass_founders(client: httpx.Client, dry: bool) -> dict:
    """Gründer (P112) für alle gematchten Firmen nachladen."""
    st = {"queries": 0, "with_founders": 0}
    with get_connection() as conn:
        rows = conn.execute(
            "select id, wikidata_qid from startup_companies "
            "where wikidata_qid is not null and founders = '[]'::jsonb").fetchall()
    by_qid = {x["wikidata_qid"]: x["id"] for x in rows}
    qids = list(by_qid)
    logger.info("Gründer-Pass: %d Firmen", len(qids))
    for i in range(0, len(qids), 300):
        chunk = qids[i:i + 300]
        values = " ".join(f"wd:{q}" for q in chunk)
        q = f"""SELECT ?item ?founderLabel WHERE {{
          VALUES ?item {{ {values} }}
          ?item wdt:P112 ?founder .
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
        }}"""
        st["queries"] += 1
        res = sparql(client, q)
        time.sleep(SLEEP)
        if res is None:
            continue
        founders: dict[str, list[str]] = defaultdict(list)
        for b in res:
            qid, f = _qid(b), _val(b, "founderLabel")
            # Q-IDs als Label = Person ohne engl. Label -> auslassen
            if qid and f and not f.startswith("Q"):
                founders[qid].append(f[:200])
        if not dry:
            with get_connection() as conn:
                for qid, names in founders.items():
                    conn.execute(
                        "update startup_companies set founders = ? where id = ?",
                        (json.dumps(sorted(set(names))[:10]), by_qid[qid]))
        st["with_founders"] += len(founders)
    logger.info("Gründer-Pass fertig: %(with_founders)d Firmen mit Gründern "
                "aus %(queries)d Queries", st)
    return st


def main() -> int:
    ap = argparse.ArgumentParser(description="Wikidata-Enrichment (#87 Phase 1)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        pass_lei(client, args.dry_run)
        pass_name(client, args.dry_run)
        if not args.dry_run:
            pass_founders(client, args.dry_run)
    with get_connection() as conn:
        r = conn.execute(
            "select count(wikidata_qid) qid, count(founded_date) founded, "
            "count(*) filter (where founders != '[]'::jsonb) with_founders, "
            "count(website) website from startup_companies").fetchone()
        logger.info("Stand nach Enrichment: %s (%.0fs)", dict(r), time.time() - t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
