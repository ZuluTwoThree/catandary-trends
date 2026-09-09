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
#
# Kollisionswächter (#98, seit 2026-09-05): jeder GPU-Schritt (die drei
# signal_batch_embedded-Läufe) wartet vorher per scripts/lib/gpu_guard.sh, bis
# kein fremder GPU-Job mehr läuft (Full Cycle, Dossier-Worker, Pulse, Deep
# Dive …; max GPU_GUARD_MAX_MIN=90 min). Danach wird der GPU-Schritt
# ÜBERSPRUNGEN — die Ingests und alle CPU-/Netz-Schritte laufen trotzdem. Das
# min_id-Fenster eines übersprungenen Laufs wird in
# data/weekly_ingesters_pending_min_id gemerkt und beim nächsten Lauf
# nachgeholt (sonst blieben die Neuzugänge dieser Woche für immer unprocessed).
# Ergebnis → data/weekly_ingesters_last.json → Morgen-Mail (review_notify.py).
# Vorfall: 05.09. ersetzte dieser Lauf den Gemma-Server eines noch laufenden
# Cycles durch den Embedding-Server.

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
  # Nachholfenster: hat ein Vorlauf seine GPU-Schritte übersprungen, liegt sein
  # (kleinerer) Wasserstand hier — die damaligen Neuzugänge sind noch unprocessed.
  PENDING_MIN_ID_FILE="data/weekly_ingesters_pending_min_id"
  if [ -s "$PENDING_MIN_ID_FILE" ]; then
    PENDING=$(tr -dc '0-9' < "$PENDING_MIN_ID_FILE")
    if [ -n "$PENDING" ] && [ "$PENDING" -lt "$MIN_ID" ]; then
      echo "Nachholfenster aus übersprungenem Vorlauf: min_id $MIN_ID → $PENDING"
      MIN_ID=$PENDING
    fi
  fi

  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/gpu_guard.sh"
  GPU_DONE=0; GPU_SKIPPED=0; GPU_BLOCKED_BY=""
  # run_gpu_step <Label> <Kommando…>: wartet auf freie GPU, sonst Skip.
  # Nach dem ersten Skip warten die weiteren Schritte nicht noch einmal 90 min,
  # sondern prüfen nur (ohne Warten), ob die GPU inzwischen frei ist.
  run_gpu_step() {
    local label="$1"; shift
    echo; echo "----- $label -----"
    local ok=0
    if [ "$GPU_SKIPPED" -gt 0 ]; then
      gpu_guard_busy >/dev/null || ok=1
    elif gpu_guard_wait weekly_ingesters; then
      ok=1
    fi
    if [ "$ok" = "1" ]; then
      "$@" || RC=$?
      GPU_DONE=$((GPU_DONE + 1))
    else
      GPU_SKIPPED=$((GPU_SKIPPED + 1))
      [ -z "$GPU_BLOCKED_BY" ] && GPU_BLOCKED_BY="$(gpu_guard_busy | head -3 | tr '\n' ';')"
      echo "SKIP (GPU belegt): $label — Neuzugänge bleiben unprocessed, nächster Lauf holt sie nach"
    fi
  }

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
  # GPU-Schritte — jeder hinter dem Kollisionswächter (s. Kopf).
  run_gpu_step "Verarbeitung der Neuzugänge research (distill, min_id=$MIN_ID)" \
    python -u scripts/signal_batch_embedded.py --source-type research --min-id "$MIN_ID"
  run_gpu_step "Verarbeitung der Neuzugänge api/no-patents (distill, min_id=$MIN_ID)" \
    python -u scripts/signal_batch_embedded.py --source-type api --no-patents --min-id "$MIN_ID"

  # Signalbetriebs-Quellen (#97, 2026-09-09): die 33 Quellen mit TDM-Vorbehalt
  # laufen mit llm_pipeline=false — der Content-Cycle sieht sie nie. 30 davon
  # sind source_type=research und liefen oben schon mit; die drei trade_media
  # (Lebensmittelzeitung, Horizont, Robb Report) faenden sonst keinen Lauf.
  # Ihre Eintraege tragen nur Titel/URL/Datum (store_excerpt: false).
  # BEWUSST OHNE --min-id: der Wasserstand oben wird SAMSTAG frueh genommen, die
  # Eintraege dieser Quellen entstehen aber beim Poll von Montag bis Freitag und
  # liegen damit darunter — mit --min-id faende der Schritt konsequent 0 Zeilen
  # (Befund 2026-09-09, vor dem ersten Lauf). Der Scope ist von sich aus eng
  # (nur llm_pipeline=false, ~1.300 Zeilen/Woche + der stehende Form-D-Rest);
  # --limit ist nur die Mengenbremse gegen einen pathologischen Fall.
  run_gpu_step "Verarbeitung der Signalbetriebs-Quellen (distill, ohne min_id)" \
    python -u scripts/signal_batch_embedded.py --signal-only --limit 20000

  # Patent-Signale (Owner 2026-08-28): die dienstags ingestierten Patente in
  # den embeddeten Signalraum. Bewusst OHNE --min-id (sie liegen unter dem
  # Samstags-Wasserstand); Scope = Abstract vorhanden + rollendes 60-Tage-
  # Publikationsfenster; --limit als Mengenbremse gegen Catch-up-Wochen
  # (Rest bleibt unprocessed und heilt in der Folgewoche).
  run_gpu_step "Patent-Signale (distill, published >= $SINCE_PATENTS)" \
    python -u scripts/signal_batch_embedded.py --source-type api --patents-only \
      --published-after "$SINCE_PATENTS" --limit 60000

  # Nachholfenster pflegen: übersprungen → Wasserstand merken; alles gelaufen → löschen.
  if [ "$GPU_SKIPPED" -gt 0 ]; then
    echo "$MIN_ID" > "$PENDING_MIN_ID_FILE"
    echo "GPU-Schritte übersprungen: $GPU_SKIPPED (blockiert durch: ${GPU_BLOCKED_BY:-?}) — min_id $MIN_ID gemerkt in $PENDING_MIN_ID_FILE"
    [ "$RC" -eq 0 ] && RC=75
  else
    rm -f "$PENDING_MIN_ID_FILE"
  fi

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

  # LLM-Investoren-Nachveredelung (#94 Teil 2) — VORBEREITET, NICHT aktiv.
  # Braucht den 8B-Chat-Server auf :8090; dieser Samstagslauf haelt an dieser
  # Stelle aber schon den EMBEDDING-Server (signal_batch_embedded oben lief
  # via GPU-Handover mit Qwen3-Embedding-8B, nicht dem 8B-Chat-Modell) — ein
  # 8B-Chat-Lauf braeuchte danach einen eigenen Modell-Swap. Baustein dafuer:
  # pipeline.gpu_handover.eight_b_on_llamacpp(STAGE_8B_MODEL) (Symlink-Swap
  # + Ollama-Unload + Start + Restore-on-exit — dasselbe Muster wie Stages
  # 2/3/4/8 im Full-Cycle), NICHT content_gen_on_llamacpp (laedt den
  # Content-Gen-GGUF, nicht das 8B). Aktivierung erst nach --eval-Pruefung
  # der Qualitaet (#94 Teil 2); vorher migrate_press_investor_enrichment.py
  # manuell gegen die Live-DB laufen lassen (additive Migration, nicht in
  # ensure_table()).
  # echo; echo "----- Investoren-Nachveredelung (#94 Teil 2) -----"
  # python -u scripts/extract_press_rounds.py --mode investors --apply --limit 2000 || RC=$?

  # Statusnotiz für die Morgen-Mail (review_notify.py liest sie, solange sie
  # < 60 h alt ist — der Samstagslauf erscheint damit in der Montags-Mail).
  if [ "$GPU_SKIPPED" -gt 0 ]; then NOTE_STATUS=blocked
  elif [ "$RC" -ne 0 ]; then NOTE_STATUS=failed
  else NOTE_STATUS=ok; fi
  gpu_guard_note weekly_ingesters "$NOTE_STATUS" gpu_steps_done="$GPU_DONE" \
    gpu_steps_skipped="$GPU_SKIPPED" "blocked_by=$GPU_BLOCKED_BY" min_id="$MIN_ID" rc="$RC"

  echo; echo "weekly_ingesters.sh end $(date -Iseconds) (rc=$RC gpu_done=$GPU_DONE gpu_skipped=$GPU_SKIPPED)"
  exit "$RC"
} >> "$LOG" 2>&1
