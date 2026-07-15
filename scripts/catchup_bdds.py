#!/usr/bin/env python3
"""Walk the BDDS DOCDB front-file backlog (#49).

The patent corpus is the longest-lead-time signal in the foresight engine, and it
had gone stale in a way that is invisible until you plot it by month:

    2025-11  141,139     normal
    2025-12   48,750     back file's coverage tapers off
    2026-02   19,897
    2026-03        7     <- effectively nothing
    2026-06   15,263     one weekly delivery, fetched by hand on 2026-06-25

Cause: the back file on disk (docdb_xml_bck_202607 = 2026 WEEK 07, mid-February —
the "202607" is a week stamp, not July) is the newest EPO offers, and
ingest_patents.py's BDDS mode only ever fetched `deliveries[0]`, the current week.
So every week between the back file and the last manual run was skipped.

This walks the offered deliveries oldest-first and ingests each one. Idempotent:
raw_entries dedups on url, so re-running a delivery inserts nothing new and it is
safe to resume after an interruption.

    python scripts/catchup_bdds.py --list                    # what's offered vs done
    python scripts/catchup_bdds.py --after 2025-12-01 --dry-run
    python scripts/catchup_bdds.py --after 2025-12-01        # ingest the backlog
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from scripts.ingest_patents import BDDS_API, bdds_token

STATE = Path(__file__).parent.parent / "data" / "bdds_catchup_state.json"
WEEK_RE = re.compile(r"(\d{4})/(\d{3})")


def deliveries(product: int) -> list[dict]:
    with httpx.Client(timeout=120, headers={"User-Agent": "catandary-trends/patents"}) as c:
        tok = bdds_token(c)
        prod = c.get(f"{BDDS_API}/products/{product}",
                     headers={"Authorization": f"Bearer {tok}",
                              "Accept": "application/json"}).json()
    out = []
    for d in prod.get("deliveries", []):
        name = str(d.get("deliveryName") or "")
        m = WEEK_RE.search(name)
        if not m:
            continue  # 'Notifications' and other non-weekly rows
        out.append({"id": int(d["deliveryId"]), "name": name,
                    "week": f"{m.group(1)}/{m.group(2)}",
                    "kind": "amend" if "Amend" in name else "crdel",
                    "files": len(d.get("files", []))})
    out.sort(key=lambda x: (x["week"], x["kind"]))   # oldest first
    return out


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"done": []}


def save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", type=int, default=3, help="3 = DOCDB front file")
    ap.add_argument("--after", default="2025-12-01", help="publication-date floor")
    ap.add_argument("--before", default="2027-01-01")
    ap.add_argument("--list", action="store_true", help="show offered vs done, do nothing")
    ap.add_argument("--kind", choices=["crdel", "amend", "both"], default="crdel",
                    help="Cr-Del carries new publications; Amend only revises existing ones")
    ap.add_argument("--limit", type=int, default=0, help="stop after N deliveries")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ds = deliveries(args.product)
    state = load_state()
    done = set(state["done"])
    todo = [d for d in ds if d["id"] not in done
            and (args.kind == "both" or d["kind"] == args.kind)]

    if args.list:
        print(f"{'WOCHE':<10}{'ART':<8}{'ID':<8}{'DATEIEN':>8}  STATUS")
        print("-" * 52)
        for d in ds:
            print(f"{d['week']:<10}{d['kind']:<8}{d['id']:<8}{d['files']:>8}  "
                  f"{'erledigt' if d['id'] in done else 'offen'}")
        print(f"\n{len(ds)} angeboten · {len(done)} erledigt · {len(todo)} offen ({args.kind})")
        return 0

    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} Lieferungen aufzuholen (kind={args.kind}, ab {args.after})\n")

    t0 = time.time()
    for i, d in enumerate(todo, 1):
        print(f"=== [{i}/{len(todo)}] {d['week']} {d['kind']} (id={d['id']}) ===", flush=True)
        cmd = [sys.executable, "-u", "scripts/ingest_patents.py", "--source", "epo-bdds",
               "--product", str(args.product), "--delivery", str(d["id"]),
               "--after", args.after, "--before", args.before, "--max-files", "0"]
        if args.dry_run:
            cmd.append("--dry-run")
        r = subprocess.run(cmd, cwd=str(Path(__file__).parent.parent))
        if r.returncode != 0:
            print(f"!! Lieferung {d['id']} fehlgeschlagen (rc={r.returncode}) — Abbruch, "
                  f"Stand ist gespeichert, erneuter Aufruf setzt hier auf")
            return 1
        if not args.dry_run:
            done.add(d["id"])
            state["done"] = sorted(done)
            save_state(state)        # persist per delivery so a crash resumes cleanly
        el = (time.time() - t0) / 60
        print(f"--- {i}/{len(todo)} fertig · {el:.0f} min · ETA {el/i*(len(todo)-i):.0f} min\n",
              flush=True)

    print(f"Fertig: {len(todo)} Lieferungen in {(time.time()-t0)/60:.0f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
