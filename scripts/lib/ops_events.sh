#!/usr/bin/env bash
# Ereignis-Protokoll der Cron-Wrapper fuer das Ops-Dashboard (#104, Stufe 2).
#
# Zwei Zeilen je Wrapper, nach `cd "$REPO"`:
#     source "$REPO/scripts/lib/ops_events.sh"
#     ops_event_start full_cycle_cron            # ganz am Anfang
#     ...
#     ops_event_end "$RC" "batch=$CYCLE_BATCH"   # vor der end-Zeile, Notiz optional
#
# Schreibt nach ops_events (pipeline/ops_events.py). Grundsatz: das Protokoll
# darf den Lauf nie verhindern — schlaegt der Eintrag fehl, gibt es eine
# Warnung im Log und der Wrapper laeuft weiter. Die id des Laufs steht in
# $OPS_EVENT_ID (leer, wenn der Start scheiterte → end ist ein No-op).
#
# Der Python-Interpreter: $OPS_EVENTS_PY, sonst .venv/bin/python neben dieser
# Datei (Repo-Root/.venv), sonst python3.
#
# Die Zeile traegt die pid des Wrappers (`$$`); stirbt er ohne ops_event_end,
# schliesst der Ops-Sampler die Zeile binnen einer Minute (pipeline/ops_events.py).
#
# OPS_EVENT_ID wird exportiert: ruft der Wrapper ein Python-Skript, das selbst
# `pipeline.ops_events.record()` nutzt, uebernimmt es diese id statt eine zweite
# Zeile anzulegen (Notizen landen dann hier, das Ende schreibt der Wrapper).

_ops_events_repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)"
OPS_EVENTS_PY="${OPS_EVENTS_PY:-$_ops_events_repo/.venv/bin/python}"
[ -x "$OPS_EVENTS_PY" ] || OPS_EVENTS_PY="python3"
OPS_EVENT_ID=""
export OPS_EVENT_ID

ops_event_start() {
  local job="$1" note="${2:-}"
  # --pid $$: die Bash des Wrappers ist der Prozess, dessen Leben den Lauf bedeutet
  # (nicht der kurzlebige Python-Aufruf hier) — der Sampler schliesst die Zeile,
  # wenn diese pid stirbt, ohne dass ops_event_end lief (Stromausfall, kill -9).
  OPS_EVENT_ID=$(cd "$_ops_events_repo" && "$OPS_EVENTS_PY" -m pipeline.ops_events start "$job" --pid "$$" ${note:+--note "$note"} 2>/dev/null) || OPS_EVENT_ID=""
  if [ -n "$OPS_EVENT_ID" ]; then
    echo "[ops_events] $job → #$OPS_EVENT_ID"
  else
    echo "[ops_events] WARN: Start von $job nicht protokolliert (DB?) — Lauf geht weiter"
  fi
}

ops_event_end() {
  local rc="${1:-0}" note="${2:-}"
  [ -n "$OPS_EVENT_ID" ] || return 0
  (cd "$_ops_events_repo" && "$OPS_EVENTS_PY" -m pipeline.ops_events end "$OPS_EVENT_ID" "$rc" ${note:+"$note"} 2>/dev/null) \
    || echo "[ops_events] WARN: Ende von #$OPS_EVENT_ID nicht protokolliert"
}
