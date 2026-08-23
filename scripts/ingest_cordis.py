#!/usr/bin/env python3
"""Ingest CORDIS SME-Beteiligungen als STARTUP-FUNDING-Signale (#87, Phase 0).

CORDIS publiziert die EU-Forschungsfoerderung (Horizon Europe + H2020) als
monatliche Bulk-Dumps (CC BY 4.0 — Attribution laeuft ueber die Quellen-
nennung „CORDIS/EU" am Signal). Die organization.csv traegt pro Beteiligung
ein SME-Flag, den Firmentyp (PRC = private kommerzielle Organisation), Land,
Stadt, Website und die tatsaechliche EU-Zuwendung (ecContribution); die
project.csv liefert Titel, Abstract (objective) und Daten. Gefiltert wird auf
SME=true UND activityType=PRC — das ist die „gefoerderte Firma", inklusive
aller EIC-Accelerator-Grants.

Eine raw_entry pro SME-Beteiligung. URL = CORDIS-Projektseite + Org-Fragment
(aufloesbar + eindeutig). Dedup via url-Unique.

    python scripts/ingest_cordis.py --dry-run --limit 500
    python scripts/ingest_cordis.py                      # HE + H2020
    python scripts/ingest_cordis.py --programme he --refresh
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_cordis")

UA = {"User-Agent": "CatandaryTrends research (trends@catandary.de)"}
PROGRAMMES = {
    "he": ("Horizon Europe", "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip",
           "cordis-HORIZONprojects-csv.zip"),
    "h2020": ("Horizon 2020", "https://cordis.europa.eu/data/cordis-h2020projects-csv.zip",
              "cordis-h2020projects-csv.zip"),
}
DATA_DIR = Path(__file__).parent.parent / "data"

csv.field_size_limit(10_000_000)


def _eur(s: str | None) -> str:
    try:
        n = float((s or "").replace(",", "."))
    except ValueError:
        return "undisclosed"
    if n <= 0:
        return "undisclosed"
    if n >= 1e6:
        return f"EUR {n/1e6:.1f}M"
    if n >= 1e3:
        return f"EUR {n/1e3:.0f}k"
    return f"EUR {n:.0f}"


def _date(*candidates: str | None) -> str | None:
    """Erstes parsebares Datum aus ecSignatureDate/startDate (ISO oder mit Zeit)."""
    for raw in candidates:
        s = (raw or "").strip().split(" ")[0]
        try:
            return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
        except ValueError:
            continue
    return None


def _projects(z: zipfile.ZipFile) -> dict[str, dict]:
    with z.open("project.csv") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"),
                                delimiter=";")
        return {(p.get("id") or "").strip(): p for p in reader}


def _map_org(org: dict, proj: dict, programme: str) -> tuple[str, str, str, str] | None:
    """(Beteiligungs-Zeile, Projekt-Zeile) -> (url, title, excerpt, date); None = skip.
    Rein funktional (DB-frei), damit testbar."""
    if (org.get("SME") or "").strip().lower() != "true":
        return None
    if (org.get("activityType") or "").strip() != "PRC":
        return None
    name = (org.get("name") or "").strip()
    pid = (org.get("projectID") or "").strip()
    oid = (org.get("organisationID") or "").strip()
    if not name or not pid or not oid:
        return None
    date = _date(proj.get("ecSignatureDate"), proj.get("startDate"))
    if not date:
        return None
    url = f"https://cordis.europa.eu/project/id/{pid}#org-{oid}"
    amt = _eur(org.get("ecContribution") or org.get("netEcContribution"))
    acronym = (proj.get("acronym") or org.get("projectAcronym") or "").strip()
    country = (org.get("country") or "").strip()
    city = (org.get("city") or "").strip()
    website = (org.get("organizationURL") or "").strip()
    objective = (proj.get("objective") or "").strip()
    ptitle = (proj.get("title") or "").strip()

    title = f"{name} secures {amt} {programme} grant ({acronym or 'EU project'})"
    geo = ", ".join(x for x in (city, country) if x) or "EU"
    facts = website if website else ""
    prefix = f"[Funding · {programme} · SME · {geo} · {amt}] "
    body = f"{ptitle}. {name} ({facts}): {objective}" if facts else \
           f"{ptitle}. {name}: {objective}"
    excerpt = (prefix + body)[:2000]
    return (url, title.replace("\x00", "")[:500], excerpt.replace("\x00", ""), date)


def download_zip(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Lade %s -> %s …", url, dest)
    tmp = dest.with_suffix(".part")
    with httpx.Client(headers=UA, timeout=300) as client, \
         client.stream("GET", url, follow_redirects=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.rename(dest)
    logger.info("Download fertig: %.1f MB", dest.stat().st_size / 1e6)


def ingest_programme(key: str, args, src_id: int) -> dict:
    programme, url, fname = PROGRAMMES[key]
    dest = DATA_DIR / fname
    if args.refresh or not dest.exists():
        download_zip(url, dest)
    st = {"programme": programme, "orgs": 0, "kept": 0, "inserted": 0, "dups": 0}
    z = zipfile.ZipFile(dest)
    projects = _projects(z)
    buf: list[tuple] = []
    with z.open("organization.csv") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"),
                                delimiter=";")
        for org in reader:
            st["orgs"] += 1
            proj = projects.get((org.get("projectID") or "").strip(), {})
            mapped = _map_org(org, proj, programme)
            if not mapped:
                continue
            st["kept"] += 1
            if not args.dry_run:
                u, t, e, d = mapped
                buf.append((src_id, u, t, e, d))
                if len(buf) >= 2000:
                    ins = db.insert_raw_entries_market_batch(buf)
                    st["inserted"] += ins
                    st["dups"] += len(buf) - ins
                    buf.clear()
            if args.limit and st["kept"] >= args.limit:
                break
    if buf and not args.dry_run:
        ins = db.insert_raw_entries_market_batch(buf)
        st["inserted"] += ins
        st["dups"] += len(buf) - ins
    logger.info("  %(programme)s: %(orgs)d participations | %(kept)d SME/PRC "
                "| %(inserted)d inserted | %(dups)d dup", st)
    return st


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest CORDIS SME participations (#87 Phase 0)")
    ap.add_argument("--programme", choices=[*PROGRAMMES, "all"], default="all")
    ap.add_argument("--refresh", action="store_true", help="Bulk-ZIPs neu herunterladen")
    ap.add_argument("--limit", type=int, default=0, help="max Eintraege je Programm (0 = alle)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src_id = -1
    if not args.dry_run:
        db.init_db()
        src_id = db.upsert_source(
            name="CORDIS EU Research Projects (SME Participations)",
            feed_url="https://cordis.europa.eu/",
            source_type="api", vertical="CROSS")

    keys = list(PROGRAMMES) if args.programme == "all" else [args.programme]
    total = 0
    for k in keys:
        total += ingest_programme(k, args, src_id)["inserted"]
    logger.info("[cordis] DONE: %d SME funding signals inserted", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
