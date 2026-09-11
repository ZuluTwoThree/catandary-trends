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
# Wikidata-Anreicherung und die Bruecken — on-demand.
#
# Seit #94 (Teil 1) existiert scripts/update_startup_companies.py als
# additiver Ersatz fuer den Rebuild-Schritt (matcht neue Form-D-/SBIR-/
# CORDIS-/Presse-Kandidaten gegen den Bestand statt ihn zu ersetzen, siehe
# den auskommentierten Schritt unten "nach verifiziertem Erstlauf aktivieren").
#
# Kollisionswächter (#98, seit 2026-09-05): der eine GPU-Schritt (Distill der
# Neuzugaenge via signal_batch_embedded) wartet per scripts/lib/gpu_guard.sh
# auf eine freie GPU (max GPU_GUARD_MAX_MIN=90 min), sonst Skip; das
# min_id-Fenster wird dann in data/monthly_startup_sources_pending_min_id
# gemerkt und beim naechsten Lauf nachgeholt. Ergebnis →
# data/monthly_startup_sources_last.json → Morgen-Mail.

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
  source "$REPO/scripts/lib/ops_events.sh"
  ops_event_start monthly_startup_sources
  # shellcheck disable=SC1091
  source .venv/bin/activate

  MIN_ID=$(python -c "from pipeline.db import get_connection
with get_connection() as c:
    print(c.execute('SELECT coalesce(max(id),0) AS m FROM raw_entries').fetchone()['m'])")
  echo "min_id (Wasserstand vor Ingest): $MIN_ID"
  PENDING_MIN_ID_FILE="data/monthly_startup_sources_pending_min_id"
  if [ -s "$PENDING_MIN_ID_FILE" ]; then
    PENDING=$(tr -dc '0-9' < "$PENDING_MIN_ID_FILE")
    if [ -n "$PENDING" ] && [ "$PENDING" -lt "$MIN_ID" ]; then
      echo "Nachholfenster aus übersprungenem Vorlauf: min_id $MIN_ID → $PENDING"
      MIN_ID=$PENDING
    fi
  fi
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/gpu_guard.sh"

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

  # Firmenstamm-Update (additiv, #94 Teil 1): matcht alle bisher unverknuepften
  # Form-D-/SBIR-/CORDIS-/Presse-Kandidaten gegen startup_companies (dieselbe
  # Quellen-Vierheit wie build_startup_companies, Entity-Resolution importiert
  # aus pipeline/startup_resolution.py, aber ohne TRUNCATE) — nicht nur die
  # CORDIS/SBIR-Neuzugaenge von oben, auch der Form-D-/Presse-Rueckstau aus
  # weekly_ingesters.sh, der seit dem Rebuild (23.08.) kein Ziel mehr fand.
  # Erstlauf verifiziert 2026-08-29 (66 neue Firmen, Enrichment-Checksum
  # unveraendert, Idempotenz-Nachlauf = 0). Stufe C (Embedding-Match) bleibt
  # bis zur Schwellen-Kalibrierung aus (#94-Notiz) — Stufe A+B genuegen fuer
  # den Monatsstrom.
  echo; echo "----- Firmenstamm-Update (additiv, #94) -----"
  python -u scripts/update_startup_companies.py --apply --no-embed-match || RC=$?

  # Neuzugaenge ins Signal-Netz (Funding-Quellen laufen unter source_type=api;
  # --no-patents wie im Weekly — Patente teilen sich den source_type).
  echo; echo "----- Verarbeitung der Neuzugaenge (distill, min_id=$MIN_ID) -----"
  GPU_DONE=0; GPU_SKIPPED=0; GPU_BLOCKED_BY=""
  if gpu_guard_wait monthly_startup_sources; then
    python -u scripts/signal_batch_embedded.py --source-type api --no-patents --min-id "$MIN_ID" || RC=$?
    GPU_DONE=1
    rm -f "$PENDING_MIN_ID_FILE"
  else
    GPU_SKIPPED=1
    GPU_BLOCKED_BY="$(gpu_guard_busy | head -3 | tr '\n' ';')"
    echo "$MIN_ID" > "$PENDING_MIN_ID_FILE"
    echo "SKIP (GPU belegt durch: ${GPU_BLOCKED_BY:-?}) — Neuzugaenge bleiben unprocessed, min_id $MIN_ID gemerkt in $PENDING_MIN_ID_FILE"
    [ "$RC" -eq 0 ] && RC=75
  fi

  # Alte Bulk-Downloads auf der HDD aufraeumen (GLEIF ~480 MB + CH ~490 MB
  # pro Monat — nur den juengsten Stand behalten).
  echo; echo "----- Download-Cleanup (>45 Tage) -----"
  find "$DL_DIR" -maxdepth 1 -name '*.zip' -mtime +45 -print -delete 2>/dev/null || true

  if [ "$GPU_SKIPPED" -gt 0 ]; then NOTE_STATUS=blocked
  elif [ "$RC" -ne 0 ]; then NOTE_STATUS=failed
  else NOTE_STATUS=ok; fi
  gpu_guard_note monthly_startup_sources "$NOTE_STATUS" gpu_steps_done="$GPU_DONE" \
    gpu_steps_skipped="$GPU_SKIPPED" "blocked_by=$GPU_BLOCKED_BY" min_id="$MIN_ID" rc="$RC"

  ops_event_end "$RC" "gpu_done=$GPU_DONE gpu_skipped=$GPU_SKIPPED"
  echo; echo "monthly_startup_sources.sh end $(date -Iseconds) (rc=$RC gpu_done=$GPU_DONE gpu_skipped=$GPU_SKIPPED)"
  exit "$RC"
} >> "$LOG" 2>&1
