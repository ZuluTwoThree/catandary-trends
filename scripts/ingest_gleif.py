#!/usr/bin/env python3
"""GLEIF Golden Copy (Level 1) als Entity-Resolution-Backbone laden (#87 Phase 1).

CC0-Daten, ~3,4M LEIs. Wert für die Resolution: LEI <-> Registerbehörde +
lokale Register-ID (ra_id/ra_entity_id) — die Brücke zwischen US-, UK- und
EU-Records ohne Namensvergleich. Fonds und Branches werden übersprungen
(EntityCategory FUND/BRANCH): sie sind keine operativen Firmen und würden
das Namens-Matching mit Vehikel-Namen fluten.

Download (~480 MB) landet auf der Daten-HDD, nicht auf dem 92%-vollen Root-FS.

    python scripts/ingest_gleif.py                  # neuesten Golden Copy laden
    python scripts/ingest_gleif.py --file /pfad.zip # vorhandenes ZIP verwenden
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline.company_norm import norm_company_name
from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_gleif")

PUBLISHES_API = "https://goldencopy.gleif.org/api/v2/golden-copies/publishes"
DOWNLOAD_DIR = Path("/mnt/data-hdd/startup-explorer")
UA = {"User-Agent": "CatandaryTrends research (trends@catandary.de)"}

# CDF-3.x-Spaltennamen (Header wird dynamisch aufgelöst; bricht laut, wenn
# sich das Format ändert).
COLS = {
    "lei": "LEI",
    "name": "Entity.LegalName",
    "country": "Entity.LegalAddress.Country",
    "city": "Entity.LegalAddress.City",
    "hq_country": "Entity.HeadquartersAddress.Country",
    "hq_city": "Entity.HeadquartersAddress.City",
    "ra_id": "Entity.RegistrationAuthority.RegistrationAuthorityID",
    "ra_entity_id": "Entity.RegistrationAuthority.RegistrationAuthorityEntityID",
    "category": "Entity.EntityCategory",
    "status": "Entity.EntityStatus",
}
SKIP_CATEGORIES = {"FUND", "BRANCH"}


def latest_zip_url(client: httpx.Client) -> str:
    r = client.get(PUBLISHES_API, params={"format": "csv", "per_page": 1}, timeout=60)
    r.raise_for_status()
    info = r.json()["data"][0]["lei2"]["full_file"]["csv"]
    logger.info("Golden Copy %s: %s Records, %s",
                r.json()["data"][0]["publish_date"], info["record_count"],
                info["size_human_readable"])
    return info["url"]


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        logger.info("ZIP vorhanden: %s", dest)
        return dest
    logger.info("Lade %s -> %s", url, dest)
    tmp = dest.with_suffix(".part")
    with httpx.Client(headers=UA, follow_redirects=True, timeout=120) as client:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
    tmp.rename(dest)
    logger.info("Download fertig: %.0f MB", dest.stat().st_size / 1e6)
    return dest


def load(zip_path: Path, batch: int = 5000) -> dict:
    st = {"rows": 0, "kept": 0, "skipped_cat": 0}
    t0 = time.time()
    with zipfile.ZipFile(zip_path) as z:
        member = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(member) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            header = next(reader)
            try:
                idx = {k: header.index(v) for k, v in COLS.items()}
            except ValueError as e:
                raise SystemExit(f"GLEIF-CSV-Format geändert: {e} — Header: {header[:12]}…")
            buf: list[tuple] = []
            with get_connection() as conn:
                def flush():
                    nonlocal buf
                    if buf:
                        conn.executemany(
                            "INSERT OR IGNORE INTO gleif_entities "
                            "(lei, name, name_norm, country, city, hq_country, hq_city, "
                            " ra_id, ra_entity_id, category, status) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", buf)
                        buf = []
                for row in reader:
                    st["rows"] += 1
                    cat = row[idx["category"]].strip()
                    if cat in SKIP_CATEGORIES:
                        st["skipped_cat"] += 1
                        continue
                    name = row[idx["name"]].strip()
                    if not name:
                        continue
                    buf.append((
                        row[idx["lei"]].strip(), name[:500], norm_company_name(name)[:500],
                        row[idx["country"]].strip() or None,
                        row[idx["city"]].strip()[:200] or None,
                        row[idx["hq_country"]].strip() or None,
                        row[idx["hq_city"]].strip()[:200] or None,
                        row[idx["ra_id"]].strip() or None,
                        row[idx["ra_entity_id"]].strip()[:200] or None,
                        cat or None, row[idx["status"]].strip() or None,
                    ))
                    st["kept"] += 1
                    if len(buf) >= batch:
                        flush()
                    if st["rows"] % 500_000 == 0:
                        logger.info("  %d Zeilen (%d übernommen, %.0f/s)",
                                    st["rows"], st["kept"], st["rows"] / (time.time() - t0))
                flush()
    logger.info("DONE in %.0fs: %d Zeilen, %d übernommen, %d Fonds/Branches übersprungen",
                time.time() - t0, st["rows"], st["kept"], st["skipped_cat"])
    return st


def main() -> int:
    ap = argparse.ArgumentParser(description="GLEIF Golden Copy laden (#87)")
    ap.add_argument("--file", type=Path, help="vorhandenes Golden-Copy-ZIP statt Download")
    args = ap.parse_args()
    if args.file:
        zip_path = args.file
    else:
        with httpx.Client(headers=UA, timeout=60) as client:
            url = latest_zip_url(client)
        zip_path = download(url, DOWNLOAD_DIR / url.rsplit("/", 1)[-1])
    load(zip_path)
    with get_connection() as conn:
        n = conn.execute("SELECT count(*) c FROM gleif_entities").fetchone()
        logger.info("gleif_entities gesamt: %s", dict(n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
