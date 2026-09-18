#!/usr/bin/env bash
# Wöchentlicher Research Pulse (#73 Teil 1) — INSTALLIERT seit 2026-09-18
# (Owner). Cron: 0 12 * * 6 (Samstag 12:00, nach weekly_ingesters.sh 06:00,
# das zuletzt 08:13 endete). Bis dahin war die Zeile nur ein Vorschlag, und
# die Seite blieb zwei Wochen lang auf W35 stehen — der „Recompute"-Knopf
# (/trends/foresight/research/pulse/<theme>) rechnet nur ein Theme, niemand
# drückte ihn. Die Radar-Regel („nur auf Knopfdruck") gilt für Radare; die
# Wochen-Newsletter-Edition läuft per Cron, der Pulse ist vom selben Typ
# (deterministische Datenbasis, datierte Wochen-Edition).
#
# Rechnet die VORWOCHE (ISO, deterministisch wie weekly_newsletter_publish.sh:
# %G/%V von vor 7 Tagen) für alle 28 Themes: Stats + Cluster (CPU/SQL, ~15 s)
# und je Theme mit ≥5 Papers einen Gemma-Absatz (ein GPU-Handover, ~2 s/Text
# + Modell-Load). Das Skript macht den Handover selbst
# (pipeline.gpu_handover.content_gen_on_llamacpp) und stellt den Ruhezustand
# von :8090 danach wieder her (lief llama-server vorher, wird er neu gestartet;
# start-active.sh zeigt wieder aufs 208K-8B).
#
# Versioniert: jeder Lauf schreibt neue Zeilen in research_pulse; die Seite
# liest je Theme/Woche die jüngste. Doppelläufe sind deshalb harmlos, aber
# nicht nötig — der Existenz-Check unten überspringt eine schon gerechnete
# Woche (Wiederholung ist der Knopf im Frontend oder ein manueller Aufruf).
#
# Wächter: jeder Ausgang (blocked / exists / gelaufen) schreibt per
# gpu_guard_note data/weekly_research_pulse_last.json; scripts/review_notify.py
# nimmt die Notiz in die Montags-Morgen-Mail (60 h Frische), ein Status ≠ ok
# erzwingt die Mail. Das Skript selbst schreibt zusätzlich
# data/research_pulse_last.json (finished_at, themes, with_text, errors).

set -u

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

REPO="/home/dirk/projects/catandary-trends"
PY="$REPO/.venv/bin/python"
LOG="/home/dirk/logs/catandary-research-pulse-$(date +%Y%m%d).log"
mkdir -p "$(dirname "$LOG")"

YEAR=$(date -d '7 days ago' +%G)
WEEK=$(date -d '7 days ago' +%-V)
WEEK_ARG=$(printf '%d-W%02d' "$YEAR" "$WEEK")

{
  echo "================================================================"
  echo "weekly_research_pulse.sh start $(date -Iseconds) — week ${WEEK_ARG}"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/ops_events.sh"
  ops_event_start weekly_research_pulse "week=${WEEK_ARG}"

  # Kollisionswächter: der Samstags-Ingester (06:00) hält die GPU mit dem
  # Embedding-Server; läuft er um 12:00 noch (Catch-up-Wochen), warten statt
  # den Modell-Swap unter ihm wegziehen (max 90 min). Dossier-Worker ebenso.
  # Seit #98 der gemeinsame Helfer scripts/lib/gpu_guard.sh.
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/gpu_guard.sh"
  if ! gpu_guard_wait weekly_research_pulse; then
    echo "ABORT: GPU-Lauf nach ${GPU_GUARD_MAX_MIN} min immer noch aktiv — Pulse ${WEEK_ARG} von Hand nachholen"
    BLOCKED_BY="$(gpu_guard_busy | head -3 | tr '\n' ';')"
    gpu_guard_note weekly_research_pulse blocked gpu_steps_done=0 gpu_steps_skipped=1 \
      "blocked_by=$BLOCKED_BY" week="$WEEK_ARG" rc=75
    ops_event_end 75 "blocked: fremder GPU-Job"
    echo "weekly_research_pulse.sh end $(date -Iseconds) (gen=blocked)"
    exit 1
  fi

  # Idempotenz: Woche schon gerechnet (≥20 der 28 Themes haben eine Zeile) → nichts tun.
  # Bewusst NICHT „mit Text": unter 5 Papers gibt es keinen Absatz, real sind es 19/28 —
  # ein Text-Kriterium ≥20 hätte jede Woche ein zweites Mal gerechnet.
  DONE=$("$PY" - <<PYEOF
from pipeline.db import get_connection
with get_connection() as c:
    try:
        r = c.execute("SELECT count(DISTINCT theme) AS n FROM research_pulse WHERE year = ? AND week = ?", (${YEAR}, ${WEEK})).fetchone()
        print(r["n"] if isinstance(r, dict) else r[0])
    except Exception:
        print(0)
PYEOF
)
  if [ "${DONE:-0}" -ge 20 ]; then
    echo "Pulse ${WEEK_ARG} existiert bereits (${DONE} Themes mit Text) — nichts zu tun."
    gpu_guard_note weekly_research_pulse ok gpu_steps_done=0 gpu_steps_skipped=0 \
      week="$WEEK_ARG" with_text="$DONE" note=exists rc=0
    ops_event_end 0 "exists"
    echo "weekly_research_pulse.sh end $(date -Iseconds) (gen=exists)"
    exit 0
  fi

  echo "----- research_pulse.py --week ${WEEK_ARG} (alle Themes, Gemma-Texte) -----"
  "$PY" scripts/research_pulse.py --week "$WEEK_ARG"
  RC=$?
  # Themenzahlen aus der Skript-Notiz in die Wrapper-Notiz übernehmen.
  read -r P_THEMES P_TEXT P_ERRORS <<<"$("$PY" - <<PYEOF
import json
try:
    d = json.load(open("data/research_pulse_last.json"))
    print(d.get("themes", 0), d.get("with_text", 0), len(d.get("errors") or []))
except Exception:
    print(0, 0, 0)
PYEOF
)"
  if [ "$RC" -ne 0 ] || [ "${P_ERRORS:-0}" -gt 0 ]; then NOTE_STATUS=failed; else NOTE_STATUS=ok; fi
  gpu_guard_note weekly_research_pulse "$NOTE_STATUS" gpu_steps_done=1 gpu_steps_skipped=0 \
    week="$WEEK_ARG" themes="${P_THEMES:-0}" with_text="${P_TEXT:-0}" errors="${P_ERRORS:-0}" rc="$RC"
  echo "----- Ruhezustand: start-active.sh → $(readlink /home/dirk/llama.cpp/start-active.sh 2>/dev/null), llama-server $(systemctl --user is-active llama-server.service 2>/dev/null) -----"
  ops_event_end "$RC"
  echo "weekly_research_pulse.sh end $(date -Iseconds) (gen=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
