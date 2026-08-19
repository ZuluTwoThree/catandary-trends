#!/usr/bin/env python3
"""Ingest US SBIR/STTR awards as STARTUP-FUNDING signals (#87, Phase 0).

SBIR/STTR ist das staatliche US-Startup-R&D-Programm: jeder Award geht an eine
Small Business (<500 MA) und traegt Firma, Betrag, Agency, Phase, Mitarbeiter-
zahl, Website, DUNS und Abstract — ein freies, strukturiertes, historisches
(seit 1983) Startup-Signal im FUNDING-Tier neben SEC Form D (privates Kapital)
und den oeffentlichen Forschungs-Grants.

Quelle: der offizielle Bulk-CSV (data.www.sbir.gov/awarddatapublic/
award_data.csv, ~367 MB, alle Awards inkl. Abstracts; Public Domain). Die
Awards-API (api.www.sbir.gov) liefert Stand 2026-08 nur 403 „Forbidden"
(„undergoing maintenance" laut sbir.gov/api) — der CSV ist der stabile Pfad.
Der heruntergeladene CSV bleibt als data/sbir_award_data.csv liegen: Phase 1
(Entity Resolution) liest DUNS/Website/Mitarbeiterzahl daraus erneut.

Eine raw_entry pro Award; URL = Award-Suche per Contract-Nummer (aufloesbar,
eindeutig). Dedup via url-Unique.

    python scripts/ingest_sbir.py --dry-run --limit 500
    python scripts/ingest_sbir.py --since 1983
    python scripts/ingest_sbir.py --refresh            # CSV neu laden
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_sbir")

UA = {"User-Agent": "CatandaryTrends research (trends@catandary.de)"}
CSV_URL = "https://data.www.sbir.gov/awarddatapublic/award_data.csv"
DEFAULT_CSV = Path(__file__).parent.parent / "data" / "sbir_award_data.csv"

# Abstracts koennen sehr lang sein — Default-Limit des csv-Moduls reicht nicht.
csv.field_size_limit(10_000_000)


def _amount(s: str | None) -> str:
    try:
        n = float((s or "").replace(",", "").replace("$", ""))
    except ValueError:
        return "undisclosed"
    if n <= 0:
        return "undisclosed"
    if n >= 1e6:
        return f"${n/1e6:.1f}M"
    if n >= 1e3:
        return f"${n/1e3:.0f}k"
    return f"${n:.0f}"


def _award_date(row: dict) -> str | None:
    """Proposal Award Date (MM/DD/YYYY) — Fallback 1. Januar des Award-Jahrs."""
    raw = (row.get("Proposal Award Date") or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(raw, fmt).date()
            # Quell-Tippfehler wie "07/01/1905" nicht als Datum uebernehmen —
            # SBIR existiert seit 1983; dann greift der Award-Year-Fallback.
            if 1982 <= d.year <= 2100:
                return d.isoformat()
        except ValueError:
            continue
    year = (row.get("Award Year") or "").strip()
    if year.isdigit() and 1982 <= int(year) <= 2100:
        return f"{year}-01-01"
    return None


def _map_row(row: dict) -> tuple[str, str, str, str] | None:
    """Row -> (url, title, excerpt, published_date); None = ueberspringen.
    Rein funktional (DB-frei), damit testbar."""
    company = (row.get("Company") or "").strip().strip('"')
    date = _award_date(row)
    if not company or not date:
        return None
    contract = (row.get("Contract") or "").strip()
    tracking = (row.get("Agency Tracking Number") or "").strip()
    key = contract or tracking
    if not key:
        return None
    url = f"https://www.sbir.gov/awards?keyword={quote(key)}"
    program = (row.get("Program") or "SBIR").strip()
    phase = (row.get("Phase") or "").strip()
    agency = (row.get("Agency") or "").strip()
    amt = _amount(row.get("Award Amount"))
    state = (row.get("State") or "").strip()
    city = (row.get("City") or "").strip()
    n_emp = (row.get("Number Employees") or "").strip()
    website = (row.get("Company Website") or "").strip()
    award_title = (row.get("Award Title") or "").strip()
    abstract = (row.get("Abstract") or "").strip()

    title = f"{company} wins {amt} {program} {phase} award ({agency})"
    geo = ", ".join(x for x in (city, state) if x) or "US"
    facts = "; ".join(x for x in (
        f"{n_emp} employees" if n_emp.isdigit() else "",
        website,
    ) if x)
    prefix = f"[Funding · {program} {phase} · {agency} · {geo} · {amt}] "
    body = f"{award_title}. {company} ({facts}): {abstract}" if facts else \
           f"{award_title}. {company}: {abstract}"
    excerpt = (prefix + body)[:2000]
    # Postgres verweigert NUL-Bytes in Text
    return (url, title.replace("\x00", "")[:500],
            excerpt.replace("\x00", ""), date)


def download_csv(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Lade %s -> %s (~350 MB) …", CSV_URL, dest)
    tmp = dest.with_suffix(".part")
    with httpx.Client(headers=UA, timeout=120) as client, \
         client.stream("GET", CSV_URL, follow_redirects=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    tmp.rename(dest)
    logger.info("Download fertig: %.1f MB", dest.stat().st_size / 1e6)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest SBIR/STTR awards (#87 Phase 0)")
    ap.add_argument("--csv-path", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--refresh", action="store_true", help="CSV neu herunterladen")
    ap.add_argument("--since", type=int, default=1983, help="fruehestes Award-Jahr")
    ap.add_argument("--limit", type=int, default=0, help="max Awards (0 = alle)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.refresh or not args.csv_path.exists():
        download_csv(args.csv_path)

    src_id = -1
    if not args.dry_run:
        db.init_db()
        src_id = db.upsert_source(
            name="SBIR/STTR Awards (US Startup R&D Funding)",
            feed_url="https://www.sbir.gov/data-resources",
            source_type="api", vertical="CROSS")

    st = {"rows": 0, "kept": 0, "inserted": 0, "dups": 0, "skipped": 0}
    buf: list[tuple] = []
    with open(args.csv_path, encoding="utf-8", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            st["rows"] += 1
            year = (row.get("Award Year") or "").strip()
            if year.isdigit() and int(year) < args.since:
                st["skipped"] += 1
                continue
            mapped = _map_row(row)
            if not mapped:
                st["skipped"] += 1
                continue
            st["kept"] += 1
            if not args.dry_run:
                url, title, excerpt, date = mapped
                buf.append((src_id, url, title, excerpt, date))
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
    logger.info("[sbir] DONE: %(rows)d rows | %(kept)d kept | %(inserted)d inserted "
                "| %(dups)d dup | %(skipped)d skipped", st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
