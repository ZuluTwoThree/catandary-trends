#!/usr/bin/env bash
# Monatlicher Nachschub der Startup-Explorer-Quellen (#87). Cron: 0 12 6 * *
# (6. des Monats, 12:00 — nach dem OpenAlex-Sync am 5. und ausserhalb aller
# GPU-Fenster; faellt der 6. auf einen Samstag, ist weekly_ingesters um 12:00
# laengst durch).
#
# Zieht die Bulk-Quellen mit Monats-Rhythmus nach und verarbeitet die
# Neuzugaenge sofort ueber den Distill-Pfad (eigenes min_id-Fenster wie
# weekly_ingesters — sonst blieben Monats-Neuzugaenge unverarbeitet liegen):
#   - CORDIS (CC BY, Dumps erscheinen monatlich; --refresh laedt neu)
#   - SBIR-Bulk-CSV (--refresh; Frische-Lag der Quelle bleibt ~2 Jahre,
#     solange die Awards-API 403 liefert)
#   - GLEIF Golden Copy (CC0; INSERT OR IGNORE ergaenzt nur neue LEIs)
#   - Companies-House-Snapshot (OGL; neuer Monatsstand, neue Firmen)
#   - Enrichment-Lauf (GLEIF/CH, nur eindeutige Treffer mit Laender-Gate)
#
# BEWUSST NICHT hier: der Firmenstamm-Rebuild (build_startup_companies
# TRUNCATEt und wuerde Wikidata-/Embedding-Enrichment verwerfen), die
# Wikidata-Anreicherung und die Bruecken — on-demand, bis ein inkrementeller
# Update-Pfad existiert (siehe #87).

set -u

REPO="/home/dirk/projects/catandary-trends"
LOG="/home/dirk/logs/catandary-startup-sources-$(date +%Y%m%d).log"
DL_DIR="/mnt/data-hdd/startup-explorer"
mkdir -p "$(dirname "$LOG")"

{
  echo "================================================================"
  echo "monthly_startup_sources.sh start $(date -Iseconds)"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd to $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source .venv/bin/activate

  MIN_ID=$(python -c "from pipeline.db import get_connection
with get_connection() as c:
    print(c.execute('SELECT coalesce(max(id),0) AS m FROM raw_entries').fetchone()['m'])")
  echo "min_id (Wasserstand vor Ingest): $MIN_ID"

  RC=0
  echo; echo "----- CORDIS (HE + H2020, --refresh) -----"
  python -u scripts/ingest_cordis.py --programme all --refresh || RC=$?

  echo; echo "----- SBIR-Bulk (--refresh) -----"
  python -u scripts/ingest_sbir.py --refresh || RC=$?

  echo; echo "----- GLEIF Golden Copy -----"
  python -u scripts/ingest_gleif.py || RC=$?

  echo; echo "----- Companies-House-Snapshot -----"
  python -u scripts/ingest_ch.py || RC=$?

  echo; echo "----- Enrichment (GLEIF/CH) -----"
  python -u scripts/enrich_startup_companies.py || RC=$?

  # Neuzugaenge ins Signal-Netz (Funding-Quellen laufen unter source_type=api;
  # --no-patents wie im Weekly — Patente teilen sich den source_type).
  echo; echo "----- Verarbeitung der Neuzugaenge (distill, min_id=$MIN_ID) -----"
  python -u scripts/signal_batch_embedded.py --source-type api --no-patents --min-id "$MIN_ID" || RC=$?

  # Alte Bulk-Downloads auf der HDD aufraeumen (GLEIF ~480 MB + CH ~490 MB
  # pro Monat — nur den juengsten Stand behalten).
  echo; echo "----- Download-Cleanup (>45 Tage) -----"
  find "$DL_DIR" -maxdepth 1 -name '*.zip' -mtime +45 -print -delete 2>/dev/null || true

  echo; echo "monthly_startup_sources.sh end $(date -Iseconds) (rc=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
