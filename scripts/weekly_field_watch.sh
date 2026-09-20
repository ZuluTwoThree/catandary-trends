#!/usr/bin/env bash
# Wöchentliche Field-Watch-Blätter (Pivot 2026-09-20, docs/commercialization_plan_2026-09-20.md §7).
# Cron-VORSCHLAG: 30 12 * * 6 (Samstag 12:30, nach dem Research Pulse 12:00) —
# Zeile in deploy/crontab.txt, scharf erst mit dem Merge nach main (Owner-Vorlage).
#
# Rechnet für jede Kundendatei fields/<kunde>.yaml (example.yaml ausgenommen)
# das Wochenblatt der VORWOCHE (scripts/field_watch.py --all: Mo–So der Woche
# vor dem letzten Sonntag), schreibt PDF/HTML/JSON nach data/field_watch/<kunde>/
# und eine Zeile je Blatt nach field_watch_runs. Reine SQL-Messung, KEINE GPU —
# deshalb kein Kollisionswächter; ~40 s je Kunde mit drei Feldern.
# Die Kundenseite (--export) wird bewusst NICHT automatisch hochgeladen:
# der Owner sichtet das Blatt und legt es per SFTP nach trends/clients/<kunde>/.
#
# Wächter: gpu_guard_note data/weekly_field_watch_last.json → Montags-Morgen-Mail
# (scripts/review_notify.py, 60 h Frische); rc=2 = keine Kundendateien (kein Fehler).

set -u

REPO="/home/dirk/projects/catandary-trends"
PY="$REPO/.venv/bin/python"
LOG="/home/dirk/logs/catandary-field-watch-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"

{
  echo "================================================================"
  echo "weekly_field_watch.sh start $(date -Iseconds)"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/ops_events.sh"
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/gpu_guard.sh"
  ops_event_start weekly_field_watch
  N=$(ls fields/*.yaml 2>/dev/null | grep -vc 'fields/example')
  if [ "${N:-0}" -eq 0 ]; then
    echo "keine Kundendateien in fields/ — nichts zu tun."
    gpu_guard_note weekly_field_watch ok gpu_steps_done=0 gpu_steps_skipped=0 note=no_customers customers=0 rc=0
    ops_event_end 0 "no customers"
    echo "weekly_field_watch.sh end $(date -Iseconds) (gen=0)"
    exit 0
  fi
  "$PY" scripts/field_watch.py --all
  RC=$?
  if [ "$RC" -ne 0 ]; then NOTE_STATUS=failed; else NOTE_STATUS=ok; fi
  gpu_guard_note weekly_field_watch "$NOTE_STATUS" gpu_steps_done=0 gpu_steps_skipped=0 customers="$N" rc="$RC"
  ops_event_end "$RC"
  echo "weekly_field_watch.sh end $(date -Iseconds) (gen=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
