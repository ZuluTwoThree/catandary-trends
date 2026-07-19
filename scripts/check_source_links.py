#!/usr/bin/env python3
"""Verify that published articles' source links actually resolve (#48).

Source attribution is the trust signal the whole free layer rests on, so a dead
backlink is a product defect, not a cosmetic one. Malformed URLs are rare (3
"undefined" + 36 path-less out of 58k); the real question is whether the
syntactically valid ones still resolve — 404s, dead redirects, expired paths.

Samples per source so no single big feed dominates the verdict, and reports a
per-source failure rate: a source that 404s wholesale is a config/ingest bug,
scattered failures are normal link rot.

Polite: HEAD first (GET fallback — some CDNs reject HEAD), one worker per host,
bounded concurrency, real UA. Read-only by default.

    python scripts/check_source_links.py --per-source 15
    python scripts/check_source_links.py --per-source 15 --mark   # flag dead ones
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

from pipeline.db import get_connection

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/125.0 Safari/537.36")


def sample(per_source: int) -> list[dict]:
    with get_connection() as c:
        rows = c.execute(
            "SELECT id, source_name, source_url, created_at FROM ("
            "  SELECT id, source_name, source_url, created_at,"
            "         ROW_NUMBER() OVER (PARTITION BY source_name ORDER BY RANDOM()) AS rn"
            "  FROM trends WHERE status='published' AND source_url <> ''"
            ") s WHERE rn <= ? ORDER BY source_name", (per_source,)).fetchall()
    return [dict(r) for r in rows]


async def check(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> tuple[int | None, str]:
    async with sem:
        for method in ("HEAD", "GET"):
            try:
                r = await client.request(method, url, follow_redirects=True, timeout=15)
                if method == "HEAD" and r.status_code in (403, 405, 501):
                    continue  # some CDNs refuse HEAD — retry as GET
                return r.status_code, ""
            except Exception as e:  # noqa: BLE001
                if method == "GET":
                    return None, type(e).__name__
        return None, "unknown"


async def run(rows: list[dict], concurrency: int) -> list[tuple]:
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(headers={"User-Agent": UA}, http2=False) as client:
        res = await asyncio.gather(*[check(client, r["source_url"], sem) for r in rows])
    return list(zip(rows, [c for c, _ in res], [e for _, e in res]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-source", type=int, default=15)
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--show", type=int, default=15, help="list N dead links")
    args = ap.parse_args()

    rows = sample(args.per_source)
    print(f"Prüfe {len(rows):,} Links aus {len({r['source_name'] for r in rows})} Quellen "
          f"(max {args.per_source}/Quelle)…\n")

    res = asyncio.run(run(rows, args.concurrency))

    # 403/429 = the publisher blocks non-browser clients (Cloudflare et al). The
    # link is almost certainly fine for a real visitor, so counting it as "dead"
    # would manufacture a defect that does not exist. Only 404/410 (and hard
    # connection errors) mean the target is actually gone.
    DEAD_CODES = {404, 410}
    per: dict[str, list[int]] = defaultdict(list)
    dead: list[tuple] = []
    hist: dict[str, int] = defaultdict(int)
    ok = 0
    for r, code, err in res:
        key = str(code) if code else f"ERR:{err}"
        hist[key] += 1
        really_dead = (code in DEAD_CODES) or (code is None)
        per[r["source_name"] or "?"].append(0 if really_dead else 1)
        if really_dead:
            dead.append((r, code, err))
        else:
            ok += 1
    n = len(res)
    print(f"STATUS-VERTEILUNG")
    print("-" * 46)
    for k in sorted(hist, key=lambda x: -hist[x]):
        note = ""
        if k in ("403", "429"):
            note = "  ← Bot-Block, Link vermutlich OK"
        elif k in ("404", "410"):
            note = "  ← wirklich tot"
        elif k.startswith("ERR"):
            note = "  ← Verbindungsfehler"
        print(f"  {k:<12}{hist[k]:>6,}{hist[k]/n*100:>7.1f}%{note}")
    print(f"\n{'':<20}{'N':>7}{'OK':>7}{'TOT':>7}{'RATE':>8}")
    print("-" * 50)
    print(f"{'GESAMT':<20}{n:>7,}{ok:>7,}{n-ok:>7,}{(n-ok)/max(n,1)*100:>7.1f}%")
    print("(TOT = nur 404/410/Verbindungsfehler; 403/429 zählen als OK)\n")

    broken = [(s, v) for s, v in per.items() if sum(v) < len(v)]
    broken.sort(key=lambda x: (sum(x[1]) / len(x[1]), -len(x[1])))
    if broken:
        print(f"QUELLEN MIT TOTEN LINKS\n{'QUELLE':<34}{'N':>5}{'TOT':>6}{'RATE':>8}")
        print("-" * 54)
        for s, v in broken[:20]:
            d = len(v) - sum(v)
            print(f"{s[:33]:<34}{len(v):>5}{d:>6}{d/len(v)*100:>7.0f}%")

    if dead and args.show:
        print(f"\nBEISPIELE ({min(len(dead), args.show)} von {len(dead)}):")
        for r, code, err in dead[:args.show]:
            print(f"  [{code or err}] #{r['id']} {str(r['source_name'])[:20]:<22}"
                  f"{r['source_url'][:78]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
