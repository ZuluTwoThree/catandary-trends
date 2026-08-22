#!/usr/bin/env python3
"""FDA-510(k)-Clearances als Produktreife-Signal (#87 Phase 2, HEALTH).

openFDA-Bulk-Download (Public Data, kein Key nötig; der openFDA-Disclaimer
„not validated for clinical use" gehört auf die Methodik-Seite). Der
Download-Index (api.fda.gov/download.json) listet die device/510k-
Partitionen; wir laden alle, matchen `applicant` konservativ gegen den
Firmenstamm und schreiben fda_clearance-Events (decision_date).

    python scripts/ingest_fda_510k.py --dry-run
    python scripts/ingest_fda_510k.py
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from pipeline.startup_match import (
    insert_events, load_unique_name_index, match, refresh_aggregates,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("ingest_fda_510k")

DOWNLOAD_INDEX = "https://api.fda.gov/download.json"
UA = {"User-Agent": "CatandaryTrends research (trends@catandary.de)"}
SINCE = "1995-01-01"  # Clearances aelter als das Korpus-Segment lohnen nicht


def partitions(client: httpx.Client) -> list[str]:
    r = client.get(DOWNLOAD_INDEX, timeout=60)
    r.raise_for_status()
    info = r.json()["results"]["device"]["510k"]
    urls = [p["file"] for p in info["partitions"]]
    logger.info("openFDA 510(k): %s Records in %d Partition(en)",
                info.get("total_records"), len(urls))
    return urls


def main() -> int:
    ap = argparse.ArgumentParser(description="FDA-510(k)-Signale (#87 Phase 2)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    idx = load_unique_name_index()
    st = {"records": 0, "dated": 0, "matched": 0}
    events: list[tuple] = []
    with httpx.Client(headers=UA, follow_redirects=True) as client:
        for url in partitions(client):
            r = client.get(url, timeout=300)
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                member = z.namelist()[0]
                data = json.loads(z.read(member))
            for rec in data.get("results", []):
                st["records"] += 1
                date = (rec.get("decision_date") or "").strip()
                if len(date) != 10 or date < SINCE:
                    continue
                st["dated"] += 1
                cid = match(idx, rec.get("applicant"))
                if not cid:
                    continue
                st["matched"] += 1
                k = (rec.get("k_number") or "").strip()
                meta = {"device": (rec.get("device_name") or "")[:200],
                        "k_number": k,
                        "product_code": rec.get("product_code"),
                        "decision": rec.get("decision_code")}
                src = f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpmn/pmn.cfm?ID={k}"
                events.append((cid, "fda_clearance", date, None, None, None,
                               "[]", json.dumps(meta), "openFDA 510(k)", src, None))
            time.sleep(1)
    logger.info("510(k): %(records)d Records, %(dated)d datiert, %(matched)d gematcht", st)
    if args.dry_run:
        logger.info("DRY-RUN — nichts geschrieben.")
        return 0
    n = insert_events(events)
    refresh_aggregates()
    logger.info("%d fda_clearance-Events geschrieben.", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
