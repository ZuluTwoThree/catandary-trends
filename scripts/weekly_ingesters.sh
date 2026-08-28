#!/usr/bin/env bash
# Wöchentlicher Nachschub der Nicht-RSS-Ingester (#4). Cron: 0 6 * * 6 (Samstag 06:00)
#
# Vorher waren Preprints/Funding/Form D Einmal-Schnappschüsse, die stillschweigend
# veralteten (Befund 2026-08-09: keiner der Nicht-RSS-Ingester lief per Cron).
# Dieser Wrapper zieht wöchentlich nach und verarbeitet die Neuzugänge sofort
# über den Distill-Pfad (Embeddings via GPU-Handover, Klassifikation CPU) —
# Samstag früh ist die GPU frei (Full Cycle Mo–Fr 04:00, Discovery So 06:00).
#
# Idempotent: alle Ingester dedupen auf raw_entries.url; überlappende Fenster
# (14/45/60 Tage) heilen verpasste Wochen. Die Verarbeitung ist per --min-id auf
# die HEUTE eingefügten Zeilen begrenzt — der 19,5-Mio-Patent-BACKLOG unter
# source_type='api' bleibt unangetastet. Seit 2026-08-28 (Owner) fließen aber
# die LAUFENDEN Patente in den Signalraum: eigener --patents-only-Pass mit
# rollendem 60-Tage-Publikationsfenster + Mengendeckel (ohne --min-id, denn die
# Patente kommen dienstags und liegen damit unter dem Samstags-Wasserstand).
# Ebenfalls seit 2026-08-28: wöchentlicher OpenAlex-Fresh-Sweep (zitationsfrei,
# #51/#81 §6) — seine Neuzugänge sind source_type='research' und laufen über
# den bestehenden research-Verarbeitungsschritt mit.

set -u

REPO="/home/dirk/projects/catandary-trends"
LOG="/home/dirk/logs/catandary-ingesters-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"

SINCE_PREPRINTS=$(date -d '14 days ago' +%F)
SINCE_FUNDING=$(date -d '45 days ago' +%F)
SINCE_OA_FRESH=$(date -d '14 days ago' +%F)
# --before ist Pflicht: der argparse-Default ist 2010er-Ära-bedingt 2020-01-01,
# ein Fenster "2026 bis 2020" wäre leer (Messfehler-Falle, gefunden 2026-08-28).
BEFORE_OA_FRESH=$(date -d '+1 day' +%F)
SINCE_PATENTS=$(date -d '60 days ago' +%F)

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

  # OpenAlex-Fresh-Sweep (zitationsfrei, publikationsdatum-sortiert): die
  # aktuellen Journal-Arbeiten, die der zitationsgegatete Korpus nie sieht
  # (#51). Deckel je Konzept-Shard begrenzt das Volumen; URL-Dedup macht das
  # überlappende Fenster gefahrlos. Neuzugänge = source_type='research' →
  # werden unten vom research-Verarbeitungsschritt mit embedded.
  echo; echo "----- OpenAlex fresh (zitationsfrei) $SINCE_OA_FRESH .. $BEFORE_OA_FRESH -----"
  python -u scripts/ingest_openalex.py --fresh --vertical ALL \
    --after "$SINCE_OA_FRESH" --before "$BEFORE_OA_FRESH" --cap 1500 || RC=$?

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

  # Patent-Signale (Owner 2026-08-28): die dienstags ingestierten Patente in
  # den embeddeten Signalraum. Bewusst OHNE --min-id (sie liegen unter dem
  # Samstags-Wasserstand); Scope = Abstract vorhanden + rollendes 60-Tage-
  # Publikationsfenster; --limit als Mengenbremse gegen Catch-up-Wochen
  # (Rest bleibt unprocessed und heilt in der Folgewoche).
  echo; echo "----- Patent-Signale (distill, published >= $SINCE_PATENTS) -----"
  python -u scripts/signal_batch_embedded.py --source-type api --patents-only \
    --published-after "$SINCE_PATENTS" --limit 60000 || RC=$?

  # Research-Explorer-Index (#72) nach der Verarbeitung neu materialisieren
  echo; echo "----- Research-Index-Rebuild -----"
  python -u scripts/build_research_index.py || RC=$?

  # ---- Startup Explorer (#87): Signal-Nachschub, alles CPU/Netz ----
  # Presse-Runden: nur neue Eintraege (LEFT JOIN in candidates), Regex-Stufe.
  # Die LLM-Nachveredelung (Investoren) bleibt bewusst on-demand — sie braucht
  # den 8B-Chat-Server und gehoert nicht in dieses GPU-Fenster.
  echo; echo "----- Startup-Explorer-Signale (#87) -----"
  python -u scripts/extract_press_rounds.py --mode regex --limit 5000 || RC=$?
  python -u scripts/ingest_hn_launches.py --since-days 30 || RC=$?
  python -u scripts/ingest_clinical_trials.py || RC=$?
  python -u scripts/ingest_fda_510k.py || RC=$?

  echo; echo "weekly_ingesters.sh end $(date -Iseconds) (rc=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
