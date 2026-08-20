#!/usr/bin/env python3
"""Ingest SEC Form D filings as a STARTUP-FUNDING signal (issue #4).

Form D = the mandatory notice a company files when raising private capital under
Reg D (the exemption almost every venture/angel round uses). It carries the
issuer, industry, and offering amount — a free, structured, historical (to 2008)
"who's raising money" signal that sits in the FUNDING tier alongside public
grants, but captures PRIVATE / startup capital instead.

Source: the SEC's structured Form D data sets (quarterly TSV ZIPs). We join
FORMDSUBMISSION + primary ISSUER + OFFERING, keep operating-company industries
(dropping the ~60% that are pooled investment funds / real estate), map the SEC
industry group to a vertical, and insert one dated raw_entry per new offering.

    python scripts/ingest_secform_d.py --since 2010 --dry-run
    python scripts/ingest_secform_d.py --since 2010
    python scripts/ingest_secform_d.py --quarter 2024q1
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# SEC requires a descriptive User-Agent with contact info.
UA = {"User-Agent": "CatandaryTrends research (trends@catandary.de)"}
BASE = "https://www.sec.gov/files/structureddata/data/form-d-data-sets"

# SEC INDUSTRYGROUPTYPE -> Catandary vertical. Operating-company industries only;
# anything not mapped (Pooled Investment Fund, REITS, Real Estate, Banking,
# Insurance, Investing …) is dropped — those aren't startup/product signals.
INDUSTRY_VERTICAL = {
    "OTHER TECHNOLOGY": "TECH", "COMPUTERS": "TECH", "TELECOMMUNICATIONS": "TECH",
    "SEMICONDUCTORS": "TECH", "SCIENTIFIC": "TECH",
    "BIOTECHNOLOGY": "HEALTH", "OTHER HEALTH CARE": "HEALTH", "PHARMACEUTICALS": "HEALTH",
    "HEALTH INSURANCE": "HEALTH", "HOSPITALS & PHYSICIANS": "HEALTH",
    "AGRICULTURE": "FOOD",
    "CLEAN TECHNOLOGY": "ECO", "ENVIRONMENTAL SERVICES": "ECO",
    "COAL MINING": "ECO", "ELECTRIC UTILITIES": "ECO", "ENERGY CONSERVATION": "ECO",
    "OIL AND GAS": "ECO", "OTHER ENERGY": "ECO",
    "MANUFACTURING": "BIZ", "RETAILING": "BIZ", "COMMERCIAL": "BIZ",
    "BUSINESS SERVICES": "BIZ", "CONSTRUCTION": "BIZ", "AIRLINES AND AIRPORTS": "BIZ",
    "LODGING AND CONVENTION": "LIFESTYLE", "TOURISM AND TRAVEL SERVICES": "LIFESTYLE",
    "RESTAURANTS": "LIFESTYLE", "TRAVEL": "LIFESTYLE", "ARTS": "LIFESTYLE",
    "OTHER TRAVEL": "LIFESTYLE",
    "APPAREL AND ACCESSORIES": "FASHION",
}


def _quarters(since_year: int):
    now = datetime.now(timezone.utc)
    for y in range(since_year, now.year + 1):
        for q in range(1, 5):
            if datetime(y, q * 3 - 2, 1, tzinfo=timezone.utc) <= now:
                yield f"{y}q{q}"


def _tsv(z: zipfile.ZipFile, name: str) -> list[dict]:
    inner = next((x for x in z.namelist() if x.upper().endswith(name + ".TSV")), None)
    if not inner:
        return []
    text = z.read(inner).decode("utf-8", "ignore")
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


def _filing_date(s: str) -> str | None:
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except (ValueError, AttributeError):
            continue
    return None


def _amount(s: str) -> str:
    try:
        n = float(s)
        return f"${n/1e6:.1f}M" if n >= 1e6 else f"${n:,.0f}"
    except (ValueError, TypeError):
        return "undisclosed"


def ingest_quarter(client: httpx.Client, quarter: str, dry_run: bool) -> dict:
    st = {"quarter": quarter, "filings": 0, "inserted": 0, "dups": 0, "skipped": 0}
    url = f"{BASE}/{quarter}_d.zip"
    try:
        r = client.get(url, timeout=120, follow_redirects=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("  %s: download error %s", quarter, type(e).__name__)
        return st
    if r.status_code != 200 or r.content[:2] != b"PK":
        logger.info("  %s: not available (HTTP %d)", quarter, r.status_code)
        return st
    z = zipfile.ZipFile(io.BytesIO(r.content))
    subs = {s["ACCESSIONNUMBER"]: s for s in _tsv(z, "FORMDSUBMISSION")}
    offers = {o["ACCESSIONNUMBER"]: o for o in _tsv(z, "OFFERING")}
    # primary issuer per accession
    prim: dict[str, dict] = {}
    for iss in _tsv(z, "ISSUERS"):
        if iss.get("IS_PRIMARYISSUER_FLAG") == "true" or iss["ACCESSIONNUMBER"] not in prim:
            prim[iss["ACCESSIONNUMBER"]] = iss

    src_id = -1 if dry_run else db.upsert_source(
        name="SEC Form D (Startup Private Offerings)",
        feed_url="https://www.sec.gov/structureddata/data/form-d-data-sets",
        source_type="api", vertical="CROSS",
        llm_pipeline=False,  # signal-only: funding entries never become articles
    )

    buf: list[tuple] = []
    for acc, sub in subs.items():
        if sub.get("SUBMISSIONTYPE") != "D" or sub.get("TESTORLIVE") == "TEST":
            continue  # only new live offerings (skip amendments + test filings)
        off = offers.get(acc, {})
        industry = (off.get("INDUSTRYGROUPTYPE") or "").upper()
        vert = INDUSTRY_VERTICAL.get(industry)
        if not vert:
            st["skipped"] += 1  # pooled fund / real estate / finance — not a startup signal
            continue
        iss = prim.get(acc, {})
        name = (iss.get("ENTITYNAME") or "").strip()
        cik = (iss.get("CIK") or "").strip()
        if not name or not cik:
            st["skipped"] += 1
            continue
        st["filings"] += 1
        date = _filing_date(sub.get("FILING_DATE", ""))
        amt = _amount(off.get("TOTALOFFERINGAMOUNT", ""))
        geo = ", ".join(x for x in (iss.get("CITY"), iss.get("STATEORCOUNTRYDESCRIPTION")) if x)
        title = f"{name} raises {amt} private round ({off.get('INDUSTRYGROUPTYPE') or industry.title()})"
        excerpt = (f"[Funding · SEC Form D] {name} ({geo}) filed a Reg-D private offering. "
                   f"Industry: {off.get('INDUSTRYGROUPTYPE')}. Total offering {amt}, "
                   f"sold {_amount(off.get('TOTALAMOUNTSOLD',''))}. Filed {date}.")
        edgar = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-','')}/{acc}-index.htm"
        if dry_run:
            st["inserted"] += 1
            continue
        buf.append((src_id, edgar, title[:500], excerpt[:2000], date))
        if len(buf) >= 2000:
            ins = db.insert_raw_entries_market_batch(buf)
            st["inserted"] += ins
            st["dups"] += len(buf) - ins
            buf.clear()
    if buf and not dry_run:
        ins = db.insert_raw_entries_market_batch(buf)
        st["inserted"] += ins
        st["dups"] += len(buf) - ins
    logger.info("  %s: %d startup filings | inserted %d | %d dup | %d skip (funds/RE)",
                quarter, st["filings"], st["inserted"], st["dups"], st["skipped"])
    return st


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest SEC Form D as a startup-funding signal (#4)")
    ap.add_argument("--since", type=int, default=2010, help="start year (Form D electronic from 2008)")
    ap.add_argument("--quarter", help="single quarter, e.g. 2024q1")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.dry_run:
        db.init_db()
    grand = 0
    with httpx.Client(headers=UA) as client:
        quarters = [args.quarter] if args.quarter else list(_quarters(args.since))
        logger.info("[sec-form-d] %d quarters | since=%s | dry=%s",
                    len(quarters), args.since, args.dry_run)
        for q in quarters:
            st = ingest_quarter(client, q, args.dry_run)
            grand += st["inserted"]
            time.sleep(0.5)  # be polite to SEC
    logger.info("[sec-form-d] DONE: %d startup-funding signals inserted", grand)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
