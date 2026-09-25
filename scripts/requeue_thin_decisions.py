#!/usr/bin/env python3
"""Einträge zurückholen, deren Schicksal auf einer zu dünnen Textbasis entschieden wurde.

Anlass (2026-09-26): `article_fetcher.fetch_batch` wählte `ORDER BY re.id DESC` (die
neuesten), `db.get_unprocessed_entries` nimmt die ältesten — bei einem Rückstand grösser
als der Batch verfehlten sich die Mengen vollständig (gemessen 0 von 250). Die Läufe vom
25.09. 21:10–23:46 verarbeiteten deshalb 568 Einträge fast ohne Volltext: nur 13 von 331
trugen Text, obwohl der Abrufer 226 geholt hatte und alle Quellen `fulltext: true` sind.

Folge: Relevanz, Extraktion und Artikel entstanden aus zwei Sätzen Teaser. Wer auf dieser
Grundlage als "not_relevant" verworfen wurde, ist endgültig weg (`processed`+`filtered_out`
kommen nie wieder in den Pool). Dieses Skript setzt genau solche Zeilen zurück, damit der
nächste Lauf sie MIT Volltext neu bewertet.

Was zurückgeholt wird (Default):
  * `not_relevant…`          — die Entscheidung hing am Text
  * `insufficient_source_text` — Stage 0b; mit Volltext ist die Textbasis da
  * `embedding_error`/`content_generation_error` nur mit --include-errors
Was NICHT zurückgeholt wird:
  * Duplikate (`duplicate…`, `title_duplicate…`) — dieselbe Meldung bleibt dieselbe
    Meldung, egal wie viel Text sie hat
  * Zeilen, aus denen ein Trend entstanden ist — die würden eine Dublette erzeugen;
    dafür ist der Weg "Write again" (status review + content-Cache löschen), s. --with-trends

Aufruf (Default Dry-Run):
  scripts/requeue_thin_decisions.py --since '2026-09-25 21:10' --until '2026-09-25 23:50'
  scripts/requeue_thin_decisions.py --since … --max-chars 1000 --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.db import get_connection  # noqa: E402

REQUEUE_PREFIXES = ("not_relevant", "insufficient_source_text")
ERROR_REASONS = ("embedding_error", "content_generation_error")


def candidates(conn, since: str, until: str | None, max_chars: int,
               include_errors: bool, with_trends: bool):
    where = ["re.processed = TRUE", "re.filtered_out = TRUE", "re.fetched_at > ?"]
    params: list = [since]
    if until:
        where.append("re.fetched_at < ?")
        params.append(until)
    where.append("length(COALESCE(re.raw_content, re.excerpt, '')) < ?")
    params.append(max_chars)
    # LIKE-Muster als PARAMETER, nicht interpoliert: psycopg2 liest ein '%' im
    # SQL-Text als Platzhalter-Anfang (IndexError beim ersten Versuch).
    clauses = ["re.filter_reason LIKE ?" for _ in REQUEUE_PREFIXES]
    params.extend(f"{p}%" for p in REQUEUE_PREFIXES)
    if include_errors:
        clauses.append(f"re.filter_reason IN ({','.join(['?'] * len(ERROR_REASONS))})")
        params.extend(ERROR_REASONS)
    where.append("(" + " OR ".join(clauses) + ")")
    if not with_trends:
        where.append("NOT EXISTS (SELECT 1 FROM trends t WHERE t.raw_entry_id = re.id)")
    rows = conn.execute(
        "SELECT re.id, re.filter_reason, s.name AS source_name, "
        "       length(COALESCE(re.raw_content, re.excerpt, '')) AS chars, "
        "       (re.raw_content IS NOT NULL) AS has_fulltext "
        "  FROM raw_entries re JOIN sources s ON s.id = re.source_id "
        " WHERE " + " AND ".join(where) + " ORDER BY re.id", tuple(params)).fetchall()
    return [dict(r) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, help="fetched_at > (z. B. '2026-09-25 21:10')")
    ap.add_argument("--until", default=None, help="fetched_at <")
    ap.add_argument("--max-chars", type=int, default=1000,
                    help="nur Zeilen mit weniger Quelltext als dies (Default 1000 — die "
                         "Grenze, unterhalb der die Wort-Untergrenze ausgesetzt ist)")
    ap.add_argument("--include-errors", action="store_true",
                    help="auch embedding_error / content_generation_error zurückholen")
    ap.add_argument("--with-trends", action="store_true",
                    help="auch Zeilen, aus denen ein Trend entstand (Vorsicht: Dubletten)")
    ap.add_argument("--limit", type=int, default=0, help="höchstens so viele (0 = alle)")
    ap.add_argument("--apply", action="store_true", help="schreiben (Default: nur zeigen)")
    a = ap.parse_args()

    with get_connection() as conn:
        rows = candidates(conn, a.since, a.until, a.max_chars, a.include_errors, a.with_trends)
    if a.limit:
        rows = rows[:a.limit]
    if not rows:
        print("keine Kandidaten")
        return 0

    by_reason: dict[str, int] = {}
    for r in rows:
        key = (r["filter_reason"] or "?").split(":")[0]
        by_reason[key] = by_reason.get(key, 0) + 1
    chars = sorted(r["chars"] for r in rows)
    print(f"{len(rows)} Kandidaten, Quelltext-Median {chars[len(chars) // 2]} Zeichen "
          f"(min {chars[0]}, max {chars[-1]}), davon {sum(1 for r in rows if r['has_fulltext'])} "
          f"haben schon Volltext")
    for k, v in sorted(by_reason.items(), key=lambda kv: -kv[1]):
        print(f"  {k:34} {v:>4}")
    src: dict[str, int] = {}
    for r in rows:
        src[r["source_name"]] = src.get(r["source_name"], 0) + 1
    print("  Quellen (Top 5): " + ", ".join(f"{k} {v}" for k, v in
                                            sorted(src.items(), key=lambda kv: -kv[1])[:5]))
    if not a.apply:
        print("\nDRY RUN — mit --apply zurücksetzen (processed=FALSE, filtered_out=FALSE, "
              "filter_reason=NULL). Die Stage-Ergebnisse (relevance/extraction/classification/"
              "content) werden mitgelöscht, sonst liest der neue Lauf den alten Cache.")
        return 0

    ids = [r["id"] for r in rows]
    done = 0
    with get_connection() as conn:
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            ph = ",".join("?" * len(chunk))
            conn.execute(
                "UPDATE raw_entries SET processed = FALSE, filtered_out = FALSE, "
                "    filter_reason = NULL, relevance_json = NULL, extraction_json = NULL, "
                "    classification_json = NULL, content_en_json = NULL "
                f" WHERE id IN ({ph})", tuple(chunk))
            done += len(chunk)
            print(f"  zurückgesetzt: {done}/{len(ids)}")
    print(f"{done} Einträge warten wieder im Pool — der nächste Lauf holt jetzt zuerst den "
          f"Volltext (Fix vom 2026-09-26) und entscheidet dann neu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
