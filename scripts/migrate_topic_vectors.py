#!/usr/bin/env python3
"""topic_vectors — Suchtabelle der Themensuche: Ebene + 1024er-Vektor je Trend,
vier HNSW-Teilindizes (2026-09-17).

Additiv und idempotent. Die Tabelle legt `db.init_db` an
(`_migrate_topic_vectors`); dieses Skript füllt sie und baut auf Wunsch die
Indizes. Warum eine Nebentabelle und keine Spalte auf `trends`, steht in
pipeline/topic_vectors.py.

    .venv/bin/python scripts/migrate_topic_vectors.py            # Tabelle füllen
    .venv/bin/python scripts/migrate_topic_vectors.py --indexes  # zusätzlich die Indizes
    .venv/bin/python scripts/migrate_topic_vectors.py --status   # nur zählen

Füllen: 1,76 Mio. Zeilen in Batches à 100.000 mit je einem Commit (Kopie der
Vektoren, ~7 GB). Indizes: CREATE INDEX CONCURRENTLY, ~100 s je 124k Zeilen,
zusammen rund 8 Minuten und 14 GB (Live-DB 17.09.: Forschung 4,8 GB, Markt 4,9 GB, Förderung 3,1 GB, Patente 1 GB); der nächtliche Dump wächst um die Tabelle (7 GB)
(Indexinhalte sichert pg_dump nicht).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline import db as db_mod  # noqa: E402
from pipeline import topic_vectors as tv  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("migrate_topic_vectors")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--indexes", action="store_true", help="auch die vier HNSW-Teilindizes bauen")
    ap.add_argument("--status", action="store_true", help="nur Zählung und Indexstand ausgeben")
    ap.add_argument("--reconcile", action="store_true", help="Nachzügler per Anti-Join einsammeln")
    ap.add_argument("--drop", metavar="INDEX", help="einen Index entfernen")
    ap.add_argument("--batch", type=int, default=tv.BATCH)
    args = ap.parse_args()

    if args.drop:
        tv.drop_index(args.drop)
        logger.info("dropped %s", args.drop)
        return 0

    db_mod._migrate_topic_vectors()
    db_mod._migrate_topic_reports()
    if not args.status:
        def prog(done, hi, n, el):
            logger.info("fill id<=%d of %d — %d rows (%.0fs)", done, hi, n, el)
        n = tv.backfill(batch=args.batch, progress=prog)
        logger.info("fill done: %d rows", n)
        if args.reconcile:
            logger.info("reconcile: %d late rows", tv.reconcile())
        if args.indexes:
            took = tv.build_indexes(progress=lambda t, s: logger.info("index %s built in %.0fs", t, s))
            logger.info("indexes: %s", {k: round(v) for k, v in took.items()})
    logger.info("rows per tier: %s", tv.counts())
    logger.info("tier indexes: %s", tv.index_status())
    return 0


if __name__ == "__main__":
    sys.exit(main())
