#!/usr/bin/env python3
"""Volltext-Nachhollauf: geloeschte Artikeltexte erneut holen (#102, 2026-09-10).

Die 14-Tage-Regel hat bis zum 10.09.2026 **17.665 Volltexte** geloescht
(Purge-Log, fuenf Laeufe seit dem 04.09.). Verloren ist davon nichts
Grundsaetzliches: geloescht wurde die Kopie, nicht der Zeiger darauf — die
Quell-URL steht in jeder Zeile. Stichprobe an 30 Eintraegen aus Volltext-Quellen
(15-45 Tage alt): **24 von 30 wieder abrufbar**, kein einziger 404, die
Fehlschlaege waren Paywall-Kurzseiten und ein Timeout.

Rechtlich ist der erneute Abruf genau das, was §44b erlaubt; seit der
Fristverlaengerung auf 60 Monate (2026-09-10) darf das Ergebnis auch bleiben.
Der Fetcher prueft bei JEDEM Abruf robots.txt und TDM-Signale — Quellen, die
inzwischen einen Vorbehalt erklaert haben, liefern dann eben nichts.

Reihenfolge gegenueber dem Embedding-Backfill: **erst hier, dann embedden.**
Sonst entstuenden Vektoren auf 775-Zeichen-Anrissen, die man danach noch einmal
rechnen muesste.

Scope: Eintraege aus Quellen mit `fulltext: true`, `processed`, ohne
`raw_content`, noch nicht nachgeholt — und **mindestens 15 Tage alt**. Der
Altersfilter ist keine Feinheit, sondern der Kern: im 0-14-Tage-Band haben 70 %
der Eintraege ihren Text noch (der Purge hat sie nicht angefasst), und die
uebrigen 30 % sind genau die, bei denen der Abruf schon damals scheiterte —
Paywalls und Bot-Sperren. Ein Lauf ohne den Filter zieht also gezielt die
Fehlschlaege: erster Versuch am 10.09. mit "neueste zuerst" brachte 3 von 60
(5 %), mit dem Filter liegt die Quote bei rund 80 %.

Neueste zuerst innerhalb des Fensters — bei aelteren steigt Link-Rot und
Paywall-Quote.

Jeder Versuch wird gestempelt (`fulltext_refetched_at`), auch der gescheiterte:
sonst wiederholt der naechste Lauf dieselben Fehlschlaege.

    python scripts/refetch_fulltext.py --limit 200               # Dry-Run
    python scripts/refetch_fulltext.py --limit 5000 --apply
    python scripts/refetch_fulltext.py --status published,draft --apply
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from pipeline import article_fetcher as af
from pipeline.db import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

#: Kuerzer ist keine Artikelseite, sondern ein Teaser hinter einer Paywall.
MIN_TEXT = 400
#: Threads. Die Bremse haengt am HOST (article_fetcher._throttle, seit heute mit
#: Schloss je Host) — mehr Threads verteilen sich also ueber verschiedene
#: Quellen, ohne eine einzelne haerter anzufassen.
WORKERS = 8


#: Juenger als das heisst: der Purge hat den Eintrag nie angefasst, ein
#: fehlender Text ist dort ein gescheiterter Abruf und kein geloeschter.
MIN_AGE_DAYS = 15


def candidates(limit: int, status: str = "", since: str = "",
               min_age_days: int = MIN_AGE_DAYS) -> list[dict]:
    names = sorted(af.fulltext_source_names())
    if not names:
        return []
    ph = ",".join("?" * len(names))
    where = [f"s.name IN ({ph})", "re.processed", "re.raw_content IS NULL",
             "re.fulltext_refetched_at IS NULL"]
    params: list = list(names)
    if min_age_days:
        where.append("re.fetched_at < now() - make_interval(days => ?)")
        params.append(min_age_days)
    if status:
        sts = [x.strip() for x in status.split(",") if x.strip()]
        where.append("EXISTS (SELECT 1 FROM trends t WHERE t.raw_entry_id = re.id "
                     f"AND t.status IN ({','.join('?' * len(sts))}))")
        params += sts
    if since:
        where.append("re.fetched_at >= ?")
        params.append(since)
    sql = ("SELECT re.id, re.url, s.name AS source_name "
           "FROM raw_entries re JOIN sources s ON s.id = re.source_id "
           f"WHERE {' AND '.join(where)} ORDER BY re.id DESC")
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _write(entry_id: int, text: str | None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        if text:
            conn.execute("UPDATE raw_entries SET raw_content = ?, fulltext_refetched_at = ? "
                         "WHERE id = ?", (text, now, entry_id))
        else:
            conn.execute("UPDATE raw_entries SET fulltext_refetched_at = ? WHERE id = ?",
                         (now, entry_id))


def run(rows: list[dict], apply: bool, workers: int = WORKERS) -> Counter:
    stat = Counter()
    t0 = time.time()

    def one(r: dict) -> None:
        with httpx.Client(timeout=20, follow_redirects=True,
                          headers={"User-Agent": af.UA}) as cl:
            res = af.fetch_fulltext_result(r["url"], client=cl)
        ok = bool(res.text) and len(res.text) >= MIN_TEXT
        if ok:
            stat["recovered"] += 1
            stat["chars"] += len(res.text)
        else:
            stat["failed"] += 1
            stat[f"reason:{(res.reason or 'too_short').split(':')[0][:20]}"] += 1
        if apply:
            _write(r["id"], res.text if ok else None)
        stat["seen"] += 1
        if stat["seen"] % 100 == 0:
            done, el = stat["seen"], time.time() - t0
            logger.info("%d/%d — %d zurueckgeholt (%.1f/s)", done, len(rows),
                        stat["recovered"], done / max(el, 1e-9))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, rows))
    stat["seconds"] = int(time.time() - t0)
    return stat


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int, default=500, help="0 = alle Kandidaten")
    ap.add_argument("--status", default="", help="nur Eintraege mit Trend in diesem Status")
    ap.add_argument("--since", default="", help="nur ab diesem fetched_at (YYYY-MM-DD)")
    ap.add_argument("--min-age-days", type=int, default=MIN_AGE_DAYS,
                    help="juengere Eintraege auslassen — dort ist ein fehlender Text ein "
                         "gescheiterter Abruf, kein geloeschter (Default 15)")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--apply", action="store_true", help="wirklich schreiben (Default: Dry-Run)")
    args = ap.parse_args(argv)

    rows = candidates(args.limit, args.status, args.since, args.min_age_days)
    logger.info("%d Kandidaten (Volltext-Quelle, verarbeitet, ohne Text, noch nicht nachgeholt)",
                len(rows))
    if not rows:
        return 0
    stat = run(rows, args.apply, args.workers)
    print()
    for k, v in sorted(stat.items()):
        print(f"  {k:24} {v}")
    if stat["recovered"]:
        print(f"  {'avg_chars':24} {stat['chars'] // stat['recovered']}")
        print(f"  {'Quote':24} {100 * stat['recovered'] // stat['seen']} %")
    if not args.apply:
        print("\nDry-Run — nichts geschrieben. Mit --apply ausfuehren.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
