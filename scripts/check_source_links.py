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

from pipeline.db import get_connection, _now_iso

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/125.0 Safari/537.36")

# 403/429 = the publisher blocks non-browser clients (Cloudflare et al). The
# link is almost certainly fine for a real visitor, so counting it as "dead"
# would manufacture a defect that does not exist. Only 404/410 (and hard
# connection errors) mean the target is actually gone.
DEAD_CODES = {404, 410}

# A link only counts as *confirmed* dead (what the frontend shows a badge
# for) once dead_links.check_count reaches this — a single blip (a flaky
# publisher, a transient timeout) must never flag a healthy link. See #48.
DEAD_STATUS_THRESHOLD = 2


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


def classify_dead_status(code: int | None, err: str) -> str | None:
    """Map one check result to the dead_links.status value, or None if the
    link should be treated as alive. Mirrors the "really_dead" gate used for
    the console report: only 404/410 and hard connection errors are dead —
    403/429 (bot-block) is presumed alive and must never be marked."""
    if code in DEAD_CODES:
        return str(code)
    if code is None:
        return "conn_error"
    return None


def apply_marks(conn, results: list[tuple]) -> dict[str, int]:
    """Upsert/resurrect dead_links rows from a batch of (row, code, err) results.

    2-strike rule: a fresh dead result inserts (or bumps) check_count; a link
    only becomes *confirmed* dead — the state the frontend badges — once
    check_count reaches DEAD_STATUS_THRESHOLD. A result that resolves alive
    (2xx/3xx, or a 403/429 bot-block) deletes any existing dead_links row for
    that URL ("resurrection") — including a fresh 403 clearing a prior
    conn_error/404 strike, since a bot-block is presumed alive.
    """
    stats = {"first_strike": 0, "confirmed": 0, "resurrected": 0}
    for r, code, err in results:
        url = r["source_url"]
        status = classify_dead_status(code, err)
        existing = conn.execute(
            "SELECT check_count FROM dead_links WHERE url = ?", (url,)).fetchone()
        if status is None:
            if existing is not None:
                conn.execute("DELETE FROM dead_links WHERE url = ?", (url,))
                stats["resurrected"] += 1
            continue
        now = _now_iso()
        if existing is None:
            conn.execute(
                "INSERT INTO dead_links (url, status, first_seen, last_checked, check_count) "
                "VALUES (?, ?, ?, ?, 1)", (url, status, now, now))
            stats["first_strike"] += 1
        else:
            new_count = existing["check_count"] + 1
            conn.execute(
                "UPDATE dead_links SET status = ?, last_checked = ?, check_count = ? "
                "WHERE url = ?", (status, now, new_count, url))
            if new_count >= DEAD_STATUS_THRESHOLD:
                stats["confirmed"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-source", type=int, default=15)
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--show", type=int, default=15, help="list N dead links")
    ap.add_argument("--mark", action="store_true",
                     help="persist dead links into dead_links (2-strike confirm; "
                          "requires scripts/migrate_dead_links.py to have run)")
    args = ap.parse_args()

    rows = sample(args.per_source)
    print(f"Prüfe {len(rows):,} Links aus {len({r['source_name'] for r in rows})} Quellen "
          f"(max {args.per_source}/Quelle)…\n")

    res = asyncio.run(run(rows, args.concurrency))

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

    if args.mark:
        try:
            with get_connection() as conn:
                stats = apply_marks(conn, res)
        except Exception as e:  # noqa: BLE001 — e.g. dead_links missing on this DB
            print(f"\n--mark ÜBERSPRUNGEN: {type(e).__name__}: {e}\n"
                  "(dead_links existiert vermutlich noch nicht — "
                  "scripts/migrate_dead_links.py manuell ausführen)")
            return 0
        print(f"\n--mark: {stats['first_strike']} erster Fehlschlag, "
              f"{stats['confirmed']} bestätigt tot (check_count>=2), "
              f"{stats['resurrected']} wieder lebendig entfernt.")
    return 0


if __name__ == "__main__":
    from pipeline.ops_events import record  # Laufprotokoll fuer /trends/ops (#104)
    with record("check_source_links"):
        raise SystemExit(main())
