#!/usr/bin/env python3
"""ClinicalTrials.gov-Studien als Produktreife-Signal (#87 Phase 2, HEALTH).

API v2 (US-Gov Open Data, keine Auth). Statt 22k Einzel-Sponsor-Abfragen ein
EIN Sweep über alle Studien mit LeadSponsorClass=INDUSTRY (seitenweise,
pageSize 1000) — die Sponsor-Namen werden lokal konservativ gegen den
Firmenstamm gematcht. Event: clinical, Datum = Studienstart, meta = Phase +
Status + NCT-Id.

    python scripts/ingest_clinical_trials.py --dry-run
    python scripts/ingest_clinical_trials.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline.startup_match import (
    insert_events, load_unique_name_index, match, refresh_aggregates,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_clinical_trials")

API = "https://clinicaltrials.gov/api/v2/studies"
UA = {"User-Agent": "CatandaryTrends research (trends@catandary.de)"}
FIELDS = ("NCTId|LeadSponsorName|Phase|OverallStatus|StartDate")
SINCE = "2000-01-01"


def _study_row(s: dict) -> dict:
    proto = s.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    sponsor = proto.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
    design = proto.get("designModule", {})
    status = proto.get("statusModule", {})
    start = (status.get("startDateStruct") or {}).get("date") or ""
    if len(start) == 7:          # "2021-03" -> Monatsanfang
        start += "-01"
    return {"nct": ident.get("nctId"), "sponsor": sponsor.get("name"),
            "phases": design.get("phases") or [],
            "status": status.get("overallStatus"), "start": start}


def main() -> int:
    ap = argparse.ArgumentParser(description="ClinicalTrials-Signale (#87 Phase 2)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-pages", type=int, default=0, help="0 = alle")
    args = ap.parse_args()
    idx = load_unique_name_index()
    st = {"studies": 0, "matched": 0, "pages": 0}
    events: list[tuple] = []
    token = None
    with httpx.Client(headers=UA) as client:
        while True:
            params = {
                "filter.advanced": "AREA[LeadSponsorClass]INDUSTRY",
                "fields": FIELDS, "pageSize": 1000,
            }
            if token:
                params["pageToken"] = token
            r = client.get(API, params=params, timeout=90)
            if r.status_code == 429:
                time.sleep(10)
                continue
            r.raise_for_status()
            data = r.json()
            st["pages"] += 1
            for s in data.get("studies", []):
                st["studies"] += 1
                row = _study_row(s)
                if not row["nct"] or len(row["start"]) != 10 or row["start"] < SINCE:
                    continue
                cid = match(idx, row["sponsor"])
                if not cid:
                    continue
                st["matched"] += 1
                meta = {"nct": row["nct"], "phases": row["phases"],
                        "status": row["status"]}
                events.append((cid, "clinical", row["start"], None, None, None,
                               "[]", json.dumps(meta), "ClinicalTrials.gov",
                               f"https://clinicaltrials.gov/study/{row['nct']}", None))
            if st["pages"] % 25 == 0:
                logger.info("  %(pages)d Seiten, %(studies)d Studien, %(matched)d Matches", st)
            token = data.get("nextPageToken")
            if not token or (args.max_pages and st["pages"] >= args.max_pages):
                break
            time.sleep(1.3)   # ~50 req/min Community-Limit respektieren
    logger.info("CT.gov: %(studies)d Industry-Studien, %(matched)d gematcht "
                "(%(pages)d Seiten)", st)
    if args.dry_run:
        logger.info("DRY-RUN — nichts geschrieben.")
        return 0
    n = insert_events(events)
    refresh_aggregates()
    logger.info("%d clinical-Events geschrieben.", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
