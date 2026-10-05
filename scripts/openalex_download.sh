#!/usr/bin/env bash
# OpenAlex-Download — getrennt von der Verarbeitung (Owner 05.10.2026).
# Lädt nachts die offenen Teilstücke am Stück, filtert sie und legt sie auf der HDD ab
# (/mnt/data-hdd/openalex_staging); der Sync (sync_openalex_monthly.sh, 09:00–17:00) verarbeitet
# dann nur noch lokale Dateien und wartet nie auf das Internet.
# Fenster: ab DL_START (Default 17:00) bis DL_UNTIL (Default 01:15, vor dem Backup 01:30);
# ein Start außerhalb tut nichts. DL_STREAMS parallele Downloads (Default 4).
# Einmalig: DL_REDO_SINCE=2026-10-05 lädt auch die am 05.10. mit v1 gelesenen Teilstücke.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$HOME/logs/catandary-openalex-download-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"
DL_START="${DL_START:-17:00}"
DL_UNTIL="${DL_UNTIL:-01:15}"
DL_STREAMS="${DL_STREAMS:-4}"
DL_REDO_SINCE="${DL_REDO_SINCE:-}"
{
  echo "================================================================"
  echo "openalex_download.sh start $(date -Iseconds) (Fenster $DL_START–$DL_UNTIL, $DL_STREAMS parallel${DL_REDO_SINCE:+, redo-since $DL_REDO_SINCE})"
  echo "================================================================"
  NOW=$(date +%H:%M)
  if ! { [ "$NOW" \> "$DL_START" ] || [ "$NOW" = "$DL_START" ] || [ "$NOW" \< "$DL_UNTIL" ]; }; then
    echo "außerhalb des Fensters ($NOW) — nichts gestartet"
    echo "openalex_download.sh end $(date -Iseconds) (rc=0, outside window)"
    exit 0
  fi
  cd "$REPO" || exit 1
  mkdir -p "$HOME/.local/state/catandary"
  exec 9>"$HOME/.local/state/catandary/openalex_download.lock"
  if ! flock -n 9; then
    echo "läuft bereits — Ende"; echo "openalex_download.sh end $(date -Iseconds) (rc=0, locked)"; exit 0
  fi
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/ops_events.sh"
  ops_event_start openalex_download
  nice -n 10 ionice -c 3 "$REPO/.venv/bin/python" -u scripts/download_openalex.py --streams "$DL_STREAMS" \
      --until "$DL_UNTIL" ${DL_REDO_SINCE:+--redo-since "$DL_REDO_SINCE"}
  RC=$?
  [ "$RC" -eq 3 ] && { echo "Fenster zu — Rest in der nächsten Nacht"; RC=0; }
  ops_event_end "$RC"
  echo "openalex_download.sh end $(date -Iseconds) (rc=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
