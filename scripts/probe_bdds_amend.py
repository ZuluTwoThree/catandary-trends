#!/usr/bin/env python3
"""Read-only probe: do BDDS 'Amend' deliveries carry publications we lack? (#49)

After the Cr-Del catch-up the gap months sit at ~60-70k patents/month against a
~145k historical norm. Two candidate explanations, and they imply opposite
actions:

  (a) DOCDB publication lag — records enter DOCDB over months, so the older
      months read 145k only because they had time to fill. Then the gap months
      will fill themselves via future weekly deliveries and there is nothing
      to do.
  (b) The 28 never-ingested Amend deliveries carry the missing half — then we
      have a real hole and must ingest them.

This decides it WITHOUT writing: parse an Amend delivery, collect the espacenet
URLs of the records in our CPC scope, and ask the DB how many it already knows.
A high already-known share means Amend only revises what we have (a); a high
unknown share means Amend carries publications we are missing (b).

    python scripts/probe_bdds_amend.py --delivery 2993
    python scripts/probe_bdds_amend.py --delivery 2993 --delivery 3116
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from pipeline.db import get_connection
from scripts.ingest_patents import BDDS_API, bdds_token, parse_docdb_document, _EXCH


def probe(delivery_id: int, after: str, before: str, scratch: str) -> dict:
    af, bf = int(after.replace("-", "")), int(before.replace("-", ""))
    urls: set[str] = set()
    docs = matched = 0
    with httpx.Client(timeout=600, headers={"User-Agent": "catandary-trends/patents"}) as client:
        tok = bdds_token(client)
        prod = client.get(f"{BDDS_API}/products/3",
                          headers={"Authorization": f"Bearer {tok}",
                                   "Accept": "application/json"}).json()
        d = next(x for x in prod["deliveries"] if int(x["deliveryId"]) == delivery_id)
        print(f"  {d.get('deliveryName')}")
        for f in d["files"]:
            if not f["fileName"].lower().endswith(".zip"):
                continue
            zpath = os.path.join(scratch, f["fileName"])
            if not (os.path.exists(zpath) and os.path.getsize(zpath) > 1 << 20):
                tok = bdds_token(client)
                with client.stream("GET", f"{BDDS_API}/products/3/delivery/{delivery_id}"
                                          f"/file/{f['fileId']}/download",
                                   headers={"Authorization": f"Bearer {tok}"}) as r:
                    r.raise_for_status()
                    with open(zpath + ".part", "wb") as fh:
                        for chunk in r.iter_bytes(1 << 20):
                            fh.write(chunk)
                os.replace(zpath + ".part", zpath)
            with zipfile.ZipFile(zpath) as z:
                for name in [n for n in z.namelist() if n.endswith(".zip") and "/DOC/" in n]:
                    try:
                        with z.open(name) as innerf, zipfile.ZipFile(innerf) as iz:
                            root = ET.fromstring(iz.read(iz.namelist()[0]))
                    except (zipfile.BadZipFile, ET.ParseError):
                        continue
                    for docu in root.findall(f"{_EXCH}exchange-document"):
                        docs += 1
                        rec = parse_docdb_document(docu)
                        if rec is None or not rec.get("url"):
                            continue
                        pd = (rec.get("pub_date") or "").replace("-", "")
                        if not pd or not (af <= int(pd) < bf):
                            continue
                        matched += 1
                        urls.add(rec["url"])
    known = 0
    ulist = list(urls)
    with get_connection() as c:
        for i in range(0, len(ulist), 5000):
            chunk = ulist[i:i + 5000]
            ph = ",".join(["?"] * len(chunk))
            r = c.execute(f"SELECT COUNT(*) AS n FROM raw_entries WHERE url IN ({ph})",
                          tuple(chunk)).fetchone()
            known += r["n"] if isinstance(r, dict) else r[0]
    return {"docs": docs, "matched": matched, "unique": len(urls),
            "known": known, "new": len(urls) - known}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delivery", type=int, action="append", required=True)
    ap.add_argument("--after", default="2025-12-01")
    ap.add_argument("--before", default="2027-01-01")
    args = ap.parse_args()

    scratch = tempfile.mkdtemp(prefix="bdds-probe-")
    print(f"Read-only Probe · scratch={scratch}\n")
    tot = {"unique": 0, "known": 0, "new": 0}
    for did in args.delivery:
        print(f"=== Lieferung {did} ===")
        r = probe(did, args.after, args.before, scratch)
        print(f"  Dokumente gescannt : {r['docs']:,}")
        print(f"  im CPC-Scope       : {r['matched']:,}  ({r['unique']:,} eindeutige URLs)")
        print(f"  davon SCHON in DB  : {r['known']:,}  ({r['known']/max(r['unique'],1)*100:.1f}%)")
        print(f"  davon NEU          : {r['new']:,}  ({r['new']/max(r['unique'],1)*100:.1f}%)\n")
        for k in tot:
            tot[k] += r[k]
    if len(args.delivery) > 1:
        print(f"=== SUMME über {len(args.delivery)} Lieferungen ===")
        print(f"  eindeutig {tot['unique']:,} · bekannt {tot['known']:,} "
              f"({tot['known']/max(tot['unique'],1)*100:.1f}%) · NEU {tot['new']:,} "
              f"({tot['new']/max(tot['unique'],1)*100:.1f}%)")
    print("\nDeutung: hoher BEKANNT-Anteil → Amend revidiert nur (Lag erklärt die Lücke).")
    print("         hoher NEU-Anteil     → Amend trägt fehlende Publikationen (ingesten).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
