#!/usr/bin/env python3
"""dossier_source_priors — Erfahrungsbasis je (Feld, Host) für den Dossier-
Rechercheur (Stufe 2 des Plans docs/plan_dossier_agent_2026-09-18.md;
Rechenregeln in pipeline/dossier_priors.py).

Self-contained additive Migration — wie scripts/migrate_dossier_orders.py
NICHT in db.init_db verdrahtet (Dossier-Tabellen sind Owner-Werkzeug).

⚠️  Additive Migrationsskripte laufen NIE automatisch auf der Live-DB. Nach
dem Merge einmal manuell ausführen (auf dem Host mit DATABASE_URL):

    .venv/bin/python scripts/migrate_dossier_source_priors.py             # Tabelle anlegen
    .venv/bin/python scripts/migrate_dossier_source_priors.py --backfill  # + aus allen Läufen rechnen

Ohne Tabelle liest und schreibt der Lauf nichts (Warnung im Log, Lauf endet
normal). Angelegt wird:

  dossier_source_priors — PK (field, host): n_read, n_cited, n_dropped,
                          rank_seen, updated_at. Der Worker addiert am Ende
                          jedes Laufs; --backfill rechnet die Tabelle aus
                          `dossiers.result` NEU (löscht vorher).

Idempotent (CREATE TABLE IF NOT EXISTS) — sicher erneut auszuführen.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod
from pipeline import dossier_priors


def migrate(backfill: bool = False) -> None:
    dossier_priors.ensure_schema()
    backend = "PostgreSQL" if db_mod.USE_POSTGRES else "SQLite"
    print(f"OK: dossier_source_priors vorhanden ({backend}).")
    if backfill:
        from scripts import corpus_research as cr
        out = dossier_priors.backfill(rank_of=lambda s: cr.catalog_rank(s))
        print(f"Backfill: {out['runs']} Lauf/Läufe verrechnet, {len(out['fields'])} Feld(er)")
        for f, s in out["fields"].items():
            print(f"  {f}: {s['runs']} Lauf/Läufe, {s['hosts']} Host(s), "
                  f"Rang 1 aus Erfahrung: {s['rank1']}"
                  + (f" ({', '.join(s['rank1_hosts'][:8])}"
                     f"{' …' if len(s['rank1_hosts']) > 8 else ''})" if s['rank1'] else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--backfill", action="store_true",
                    help="Tabelle aus allen gespeicherten Läufen neu rechnen (löscht vorher)")
    a = ap.parse_args()
    migrate(backfill=a.backfill)
