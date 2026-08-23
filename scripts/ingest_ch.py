#!/usr/bin/env python3
"""Companies-House-Snapshot (UK) als Stammdaten-Subset laden (#87 Phase 1).

Free Company Data Product (OGL v3, Attribution "Contains Companies House
data © Crown copyright"), Monats-Snapshot ~5,5M lebende UK-Firmen. Geladen
wird das im Plan §5.6 beschlossene SUBSET, nicht alles: Firmen ab
--since (Default 2000) MIT startup-relevantem SIC-Code. Wert: exaktes
Gründungsdatum + Branche für die Resolution/Anreicherung.

    python scripts/ingest_ch.py                    # Snapshot laden (Subset)
    python scripts/ingest_ch.py --since 2015
    python scripts/ingest_ch.py --file /pfad.zip
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import sys
import time
import zipfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline.company_norm import norm_company_name
from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_ch")

BASE = "https://download.companieshouse.gov.uk"
DOWNLOAD_DIR = Path("/mnt/data-hdd/startup-explorer")
UA = {"User-Agent": "CatandaryTrends research (trends@catandary.de)"}

# Startup-relevante UK-SIC-2007-Präfixe (bewusst großzügig Richtung Tech +
# Fintech + E-Commerce; ein zu enges Subset kostet Matches, ein zu weites
# nur Plattenplatz):
#   20/21 Chemie/Pharma · 26-30 Elektronik/Geräte/Fahrzeuge · 325 Medizintechnik
#   582 Software-Publishing · 61-63 Telecom/IT/Information · 64 Finanzdienste
#   712 Test/Analyse · 72 F&E · 4791 Versandhandel/E-Commerce
SIC_PREFIXES = ("20", "21", "26", "27", "28", "29", "30", "325",
                "582", "61", "62", "63", "64", "712", "72", "4791")


def month_urls() -> list[str]:
    """Kandidaten-URLs: aktueller + Vormonat (Snapshot erscheint zum 1.)."""
    today = date.today()
    urls = []
    for back in (0, 1):
        y, m = today.year, today.month - back
        if m < 1:
            y, m = y - 1, m + 12
        urls.append(f"{BASE}/BasicCompanyDataAsOneFile-{y}-{m:02d}-01.zip")
    return urls


def download(dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=UA, follow_redirects=True, timeout=120) as client:
        for url in month_urls():
            dest = dest_dir / url.rsplit("/", 1)[-1]
            if dest.exists() and dest.stat().st_size > 0:
                logger.info("ZIP vorhanden: %s", dest)
                return dest
            head = client.head(url)
            if head.status_code != 200:
                continue
            logger.info("Lade %s (%.0f MB)", url, int(head.headers.get("content-length", 0)) / 1e6)
            tmp = dest.with_suffix(".part")
            with client.stream("GET", url) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            tmp.rename(dest)
            return dest
    raise SystemExit("Kein Companies-House-Snapshot erreichbar (aktueller + Vormonat geprüft).")


def _sic_codes(row: dict) -> list[str]:
    out = []
    for i in ("1", "2", "3", "4"):
        v = (row.get(f"SICCode.SicText_{i}") or "").strip()
        if v and " - " in v:
            out.append(v.split(" - ", 1)[0].strip())
        elif v and v[:4].isdigit():
            out.append(v.split()[0])
    return out


def _inc_date(s: str | None) -> str | None:
    try:
        return datetime.strptime((s or "").strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def load(zip_path: Path, since_year: int, batch: int = 5000) -> dict:
    import json
    st = {"rows": 0, "kept": 0}
    t0 = time.time()
    since = f"{since_year}-01-01"
    with zipfile.ZipFile(zip_path) as z:
        member = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(member) as raw:
            # Companies House liefert Header mit führenden Leerzeichen
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            reader.fieldnames = [f.strip() for f in (reader.fieldnames or [])]
            buf: list[tuple] = []
            with get_connection() as conn:
                def flush():
                    nonlocal buf
                    if buf:
                        conn.executemany(
                            "INSERT OR IGNORE INTO ch_companies "
                            "(number, name, name_norm, city, postcode, status, "
                            " category, inc_date, sic) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            buf)
                        buf = []
                for row in reader:
                    st["rows"] += 1
                    if st["rows"] % 1_000_000 == 0:
                        logger.info("  %d Zeilen (%d übernommen, %.0f/s)",
                                    st["rows"], st["kept"], st["rows"] / (time.time() - t0))
                    inc = _inc_date(row.get("IncorporationDate"))
                    if not inc or inc < since:
                        continue
                    sics = _sic_codes(row)
                    if not any(c.startswith(SIC_PREFIXES) for c in sics):
                        continue
                    name = (row.get("CompanyName") or "").strip()
                    number = (row.get("CompanyNumber") or "").strip()
                    if not name or not number:
                        continue
                    buf.append((
                        number, name[:500], norm_company_name(name)[:500],
                        (row.get("RegAddress.PostTown") or "").strip()[:200] or None,
                        (row.get("RegAddress.PostCode") or "").strip()[:20] or None,
                        (row.get("CompanyStatus") or "").strip() or None,
                        (row.get("CompanyCategory") or "").strip()[:100] or None,
                        inc, json.dumps(sics),
                    ))
                    st["kept"] += 1
                    if len(buf) >= batch:
                        flush()
                flush()
    logger.info("DONE in %.0fs: %d Zeilen, %d im Subset übernommen",
                time.time() - t0, st["rows"], st["kept"])
    return st


def main() -> int:
    ap = argparse.ArgumentParser(description="Companies-House-Snapshot laden (#87)")
    ap.add_argument("--file", type=Path, help="vorhandenes Snapshot-ZIP statt Download")
    ap.add_argument("--since", type=int, default=2000, help="Gründungsjahr-Untergrenze (Default 2000)")
    args = ap.parse_args()
    zip_path = args.file or download(DOWNLOAD_DIR)
    load(zip_path, args.since)
    with get_connection() as conn:
        n = conn.execute("SELECT count(*) c FROM ch_companies").fetchone()
        logger.info("ch_companies gesamt: %s", dict(n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
