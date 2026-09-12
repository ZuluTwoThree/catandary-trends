#!/usr/bin/env python3
"""Offen lizenzierte Artikel aus Vorbehalts-Quellen freischalten (#97, Wege B+C).

Eine Lizenz sticht den TDM-Vorbehalt: veröffentlicht ein Verlag denselben
Artikel unter CC BY/CC0, braucht es die Schranke aus §44b nicht mehr, und der
site-weite Vorbehalt des Hosts geht für diesen Artikel ins Leere. Herleitung und
Grenzen: pipeline/open_license.py.

Ablauf je unverarbeitetem Eintrag einer Quelle im Signalbetrieb
(`llm_pipeline = FALSE`, gesetzt für die 33 Vorbehalts-Quellen):

  1. AUFLÖSEN   raw_entry -> OpenAlex-Werk (DOI aus der URL, sonst Titelsuche
                mit Titelabgleich gegen Beinahe-Treffer).
  2. PRÜFEN     `best_oa_location.license` offen? (cc-by / cc-by-sa / cc0 /
                public domain; nie -nc, nie -nd).
  3. HOLEN      Volltext von der OFFENEN Fundstelle — nie vom Vorbehalts-Host.
                Der Fetcher prüft dort robots.txt (immer) — der TDM-Vorbehalt
                des Hosts wird bei belegter offener Lizenz nicht angewandt, denn
                die Lizenz ist eine Erlaubnis, der Vorbehalt sperrt nur die
                Schranke. Zeigt OpenAlex mehrere Fundstellen, werden bis zu zwei
                versucht (Datenrepositorien zuletzt).
  4. SCHREIBEN  raw_content + open_licence + oa_url. `open_licence` ist zugleich
                die Eintrittskarte in den Content-Cycle (get_unprocessed_entries).

Jeder Eintrag wird mit `--apply` genau EINMAL geprueft: `licence_checked_at`
wird bei jedem Ausgang gestempelt (auch bei "nicht offen"). Sonst fragte der
naechtliche Lauf dieselben ~85 % Nicht-Offenen jede Nacht neu ab — die Zeilen
bleiben unverarbeitet, bis der Samstagslauf sie einzieht.

Default ist Dry-Run.

    python scripts/resolve_open_licence.py --limit 50                 # Dry-Run
    python scripts/resolve_open_licence.py --limit 50 --apply
    python scripts/resolve_open_licence.py --source "Nature (main)" --apply
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from pipeline import article_fetcher as af
from pipeline.db import get_connection
from pipeline.open_license import UA, resolve

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MIN_TEXT = 400          # kürzer als das ist kein Artikelvolltext, sondern eine Landing-Page
MAX_LOCATIONS = 2       # höchstens zwei Fundstellen je Eintrag versuchen


def candidates(limit: int, source: str = "", min_id: int = 0) -> list[dict]:
    """Unverarbeitete Einträge von Signalbetriebs-Quellen, noch nicht aufgelöst."""
    where = ["re.processed = FALSE", "re.filtered_out = FALSE",
             "COALESCE(s.llm_pipeline, TRUE) = FALSE", "re.open_licence IS NULL",
             "re.licence_checked_at IS NULL",     # jeder Eintrag wird genau einmal geprueft
             "s.source_type <> 'api'"]
    params: list = []
    if source:
        where.append("s.name = ?")
        params.append(source)
    if min_id:
        where.append("re.id > ?")
        params.append(min_id)
    sql = ("SELECT re.id, re.url, re.title, s.name AS source_name "
           "FROM raw_entries re JOIN sources s ON s.id = re.source_id "
           f"WHERE {' AND '.join(where)} ORDER BY re.id DESC")
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _stamp(entry_id: int) -> None:
    """Geprueft — egal mit welchem Ergebnis. Ohne diese Marke fragt der naechtliche
    Lauf dieselben ~85 % Nicht-Offenen jede Nacht erneut ab (kostenpflichtige API),
    und bei einem Limit kaeme der aeltere Teil des Pools nie an die Reihe."""
    with get_connection() as conn:
        conn.execute("UPDATE raw_entries SET licence_checked_at = ? WHERE id = ?",
                     (datetime.now(timezone.utc).isoformat(), entry_id))


def process(rows: list[dict], apply: bool) -> Counter:
    stat = Counter()
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as oa_client, \
         httpx.Client(timeout=20, follow_redirects=True,
                      headers={"User-Agent": af.UA}) as fetch_client:
        for r in rows:
            stat["seen"] += 1
            work = resolve(r["url"], r["title"] or "", client=oa_client)
            if apply:
                _stamp(r["id"])
            if work.reason:
                stat[f"unresolved:{work.reason.split()[0]}"] += 1
                continue
            if not work.is_open:
                stat["not_open"] += 1
                continue
            text = used = None
            reason = "no_location"
            for cand in work.oa_urls[:MAX_LOCATIONS]:
                res = af.fetch_fulltext_result(cand, client=fetch_client,
                                               open_licence=work.licence)
                if res.text and len(res.text) >= MIN_TEXT:
                    text, used = res.text, cand
                    break
                reason = res.reason or "too_short"
            if not text:
                stat[f"no_text:{reason}"] += 1
                continue
            stat["open_with_text"] += 1
            logger.info("[%d] %s | %s | %d chars from %s",
                        r["id"], r["source_name"], work.licence, len(text), used)
            if apply:
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE raw_entries SET raw_content = ?, open_licence = ?, oa_url = ? "
                        "WHERE id = ?", (text, work.licence, used, r["id"]))
                stat["written"] += 1
    return stat


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int, default=100, help="0 = alle Kandidaten")
    ap.add_argument("--source", default="", help="nur diese Quelle (exakter Name)")
    ap.add_argument("--min-id", type=int, default=0)
    ap.add_argument("--apply", action="store_true", help="wirklich schreiben (Default: Dry-Run)")
    args = ap.parse_args(argv)

    rows = candidates(args.limit, args.source, args.min_id)
    logger.info("%d Kandidaten (unverarbeitet, Signalbetrieb, noch nicht aufgelöst)", len(rows))
    if not rows:
        return 0
    stat = process(rows, args.apply)
    print()
    for k, v in sorted(stat.items()):
        print(f"  {k:28} {v}")
    if not args.apply and stat["open_with_text"]:
        print(f"\nDry-Run — {stat['open_with_text']} Einträge wären freigeschaltet worden. "
              "Mit --apply schreiben.")
    return 0


if __name__ == "__main__":
    try:
        from pipeline.ops_events import record  # Laufprotokoll fuer /trends/ops (#104)
    except ImportError:  # Paket nicht im Pfad (Cron ohne cd, 12.09.: Backup fiel aus) — Protokoll ist optional, der Job nicht
        from contextlib import nullcontext as record
    with record("resolve_open_licence"):
        raise SystemExit(main())
