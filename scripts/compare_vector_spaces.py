#!/usr/bin/env python3
"""A/B-Test der beiden Vektorraeume — hilft der Volltext wirklich? (#102)

Owner-Auftrag 2026-09-11: vor jeder Behauptung, der zweite Vektorraum sei
besser, messen statt glauben.

Der Test: zu einem zufaelligen Ausgangseintrag die naechsten Nachbarn einmal
ueber `embedding_1024` (Titel + 500 Zeichen) und einmal ueber
`embedding_full_1024` (voller Quelltext) holen und nebeneinander legen.

Warum gerade Patente der harte Fall sind: ihre Abstracts beginnen fast alle
gleich ("The embodiment of the invention discloses a … method and device,
equipment and a storage medium"). Der alte Vektor sieht bei einem
1.603-Zeichen-Abstract 31 % — und der Schnitt faellt mitten in die
Eroeffnungsformel, bevor das Verfahren ueberhaupt beschrieben wird. Wenn der
zweite Raum irgendwo etwas bringen muss, dann hier.

Zu pruefen ist auch die Gegenrichtung: Patentsprache ist AUCH jenseits der
500 Zeichen formelhaft. Ob der Vektor am Verfahren haengt oder weiter am Stil,
zeigt erst der Vergleich.

    python scripts/compare_vector_spaces.py --kind patent -n 3
    python scripts/compare_vector_spaces.py --kind openalex -n 3
    python scripts/compare_vector_spaces.py --kind article --neighbours 8
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.db import get_connection

KINDS = {
    "patent":   "re.pub_number IS NOT NULL",
    "openalex": "re.openalex_id IS NOT NULL",
    "funding":  "s.source_type = 'api' AND re.pub_number IS NULL AND re.openalex_id IS NULL",
    "research": "s.source_type = 'research'",
    "article":  "t.status = 'published'",
}


def neighbours(conn, col: str, vec: str, seed_id: int, scope: str, n: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        f"SELECT t.title_en, (t.{col} <=> ?::vector) d "
        f"  FROM trends t JOIN raw_entries re ON re.id = t.raw_entry_id "
        f"  JOIN sources s ON s.id = re.source_id "
        f" WHERE {scope} AND t.id <> ? AND t.{col} IS NOT NULL "
        f" ORDER BY t.{col} <=> ?::vector LIMIT ?", (vec, seed_id, vec, n)).fetchall()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--kind", default="patent", choices=sorted(KINDS))
    ap.add_argument("-n", "--seeds", type=int, default=3)
    ap.add_argument("--neighbours", type=int, default=6)
    args = ap.parse_args(argv)
    scope = KINDS[args.kind]

    with get_connection() as conn:
        seeds = [dict(r) for r in conn.execute(
            f"SELECT t.id, t.title_en, re.excerpt, re.raw_content, "
            f"       t.embedding_1024::text v_old, t.embedding_full_1024::text v_new, "
            f"       t.full_embedded_chars "
            f"  FROM trends t JOIN raw_entries re ON re.id = t.raw_entry_id "
            f"  JOIN sources s ON s.id = re.source_id "
            f" WHERE {scope} AND t.embedding_1024 IS NOT NULL "
            f"   AND t.embedding_full_1024 IS NOT NULL "
            f" ORDER BY random() LIMIT ?", (args.seeds,)).fetchall()]
        if not seeds:
            print(f"Kein {args.kind}-Eintrag hat BEIDE Vektoren — Backfill noch nicht gelaufen?")
            return 1

        for s in seeds:
            full = len((s.get("raw_content") or s.get("excerpt") or ""))
            print("=" * 78)
            print(f"AUSGANG  {(s['title_en'] or '')[:70]}")
            print(f"         Quelltext {full} Zeichen · alter Vektor sah 500 "
                  f"({100 * 500 // max(full, 1)} %) · neuer sah {s['full_embedded_chars']}")
            old = neighbours(conn, "embedding_1024", s["v_old"], s["id"], scope, args.neighbours)
            new = neighbours(conn, "embedding_full_1024", s["v_new"], s["id"], scope, args.neighbours)
            print(f"\n  {'ALT (Titel + 500)':<44} {'NEU (voller Quelltext)'}")
            for a, b in zip(old, new):
                print(f"  {a['d']:.3f} {(a['title_en'] or '')[:38]:<38} "
                      f"{b['d']:.3f} {(b['title_en'] or '')[:38]}")
            same = len({x["title_en"] for x in old} & {x["title_en"] for x in new})
            print(f"\n  Überlappung: {same} von {args.neighbours} — "
                  f"je weniger, desto mehr aendert der zweite Raum.")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
