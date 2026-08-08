#!/usr/bin/env bash
# Wöchentlicher Nachschub der Nicht-RSS-Ingester (#4). Cron: 0 5 * * 6 (Samstag 05:00)
#
# Vorher waren Preprints/Funding/Form D Einmal-Schnappschüsse, die stillschweigend
# veralteten (Befund 2026-08-09: keiner der Nicht-RSS-Ingester lief per Cron).
# Dieser Wrapper zieht wöchentlich nach und verarbeitet die Neuzugänge sofort
# über den Distill-Pfad (Embeddings via GPU-Handover, Klassifikation CPU) —
# Samstag früh ist die GPU frei (Full Cycle Mo–Fr 04:00, Discovery So 06:00).
#
# Idempotent: alle Ingester dedupen auf raw_entries.url; überlappende Fenster
# (14/45 Tage) heilen verpasste Wochen. Die Verarbeitung ist per --min-id auf
# die HEUTE eingefügten Zeilen begrenzt — der 19,5-Mio-Patent-Backlog unter
# source_type='api' bleibt unangetastet (zusätzlich --no-patents, siehe
# signal_batch-Caveat: Funding und Patente teilen sich source_type='api').

set -u

REPO="/home/dirk/projects/catandary-trends"
LOG="/home/dirk/logs/catandary-ingesters-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"

SINCE_PREPRINTS=$(date -d '14 days ago' +%F)
SINCE_FUNDING=$(date -d '45 days ago' +%F)

{
  echo "================================================================"
  echo "weekly_ingesters.sh start $(date -Iseconds)"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd to $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source .venv/bin/activate

  # Wasserstand VOR den Ingests — begrenzt die Verarbeitung auf Neuzugänge
  MIN_ID=$(python -c "from pipeline.db import get_connection
with get_connection() as c:
    print(c.execute('SELECT coalesce(max(id),0) AS m FROM raw_entries').fetchone()['m'])")
  echo "min_id (Wasserstand vor Ingest): $MIN_ID"

  RC=0
  echo; echo "----- Preprints (arXiv/bioRxiv/medRxiv) seit $SINCE_PREPRINTS -----"
  python -u scripts/ingest_preprints.py --backend all --since "$SINCE_PREPRINTS" || RC=$?

  echo; echo "----- Funding (NSF/NIH/OpenAIRE/UKRI) seit $SINCE_FUNDING -----"
  python -u scripts/ingest_funding.py --backend all --since "$SINCE_FUNDING" || RC=$?

  # Form D: Quartals-Datasets erscheinen NACH Quartalsende → nur im jeweils
  # ersten Quartalsmonat das Vorquartal ziehen (idempotent bei Wiederholung).
  M=$(date +%m); Y=$(date +%Y)
  case "$M" in
    01) Q="$((Y-1))q4" ;;
    04) Q="${Y}q1" ;;
    07) Q="${Y}q2" ;;
    10) Q="${Y}q3" ;;
    *)  Q="" ;;
  esac
  if [ -n "$Q" ]; then
    echo; echo "----- SEC Form D Vorquartal $Q -----"
    python -u scripts/ingest_secform_d.py --quarter "$Q" || RC=$?
  else
    echo; echo "----- SEC Form D: kein Quartalsmonat, übersprungen -----"
  fi

  # Neuzugänge verarbeiten: research (Preprints) + api ohne Patente (Funding/Form D).
  # Läuft auch bei Teil-Fehlern oben (was ingestiert wurde, soll ins Signal-Netz).
  echo; echo "----- Verarbeitung der Neuzugänge (distill, min_id=$MIN_ID) -----"
  python -u scripts/signal_batch_embedded.py --source-type research --min-id "$MIN_ID" || RC=$?
  python -u scripts/signal_batch_embedded.py --source-type api --no-patents --min-id "$MIN_ID" || RC=$?

  echo; echo "weekly_ingesters.sh end $(date -Iseconds) (rc=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
