#!/usr/bin/env bash
# Wöchentlicher Research Pulse (#73 Teil 1) — VORSCHLAG, NICHT INSTALLIERT.
# Cron-Vorschlag: 0 12 * * 6 (Samstag 12:00, nach weekly_ingesters.sh 06:00,
# das zuletzt 08:13 endete). Owner entscheidet Cron vs. „Recompute"-Knopf
# (/trends/foresight/research/pulse/<theme>) — die Radar-Regel gilt für
# Radare; die Wochen-Newsletter-Edition läuft per Cron, der Pulse ist vom
# selben Typ (deterministische Datenbasis, datierte Wochen-Edition).
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
# Wächter: data/research_pulse_last.json (finished_at, themes, with_text,
# errors, status) — scripts/cycle_watchdog.py kann darauf prüfen, sobald der
# Cron installiert ist (bis dahin bewusst nicht verdrahtet: ein Samstags-
# „missing" ohne Cron wäre Rauschen).

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

  # Kollisionswächter: der Samstags-Ingester (06:00) hält die GPU mit dem
  # Embedding-Server; läuft er um 12:00 noch (Catch-up-Wochen), warten statt
  # den Modell-Swap unter ihm wegziehen (max 90 min). Dossier-Worker ebenso.
  # Seit #98 der gemeinsame Helfer scripts/lib/gpu_guard.sh.
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/gpu_guard.sh"
  if ! gpu_guard_wait weekly_research_pulse; then
    echo "ABORT: GPU-Lauf nach ${GPU_GUARD_MAX_MIN} min immer noch aktiv — Pulse ${WEEK_ARG} von Hand nachholen"
    echo "weekly_research_pulse.sh end $(date -Iseconds) (gen=blocked)"
    exit 1
  fi

  # Idempotenz: Woche schon gerechnet (alle Themes) → nichts tun.
  DONE=$("$PY" - <<PYEOF
from pipeline.db import get_connection
with get_connection() as c:
    try:
        r = c.execute("SELECT count(DISTINCT theme) AS n FROM research_pulse WHERE year = ? AND week = ? AND text IS NOT NULL", (${YEAR}, ${WEEK})).fetchone()
        print(r["n"] if isinstance(r, dict) else r[0])
    except Exception:
        print(0)
PYEOF
)
  if [ "${DONE:-0}" -ge 20 ]; then
    echo "Pulse ${WEEK_ARG} existiert bereits (${DONE} Themes mit Text) — nichts zu tun."
    echo "weekly_research_pulse.sh end $(date -Iseconds) (gen=exists)"
    exit 0
  fi

  echo "----- research_pulse.py --week ${WEEK_ARG} (alle Themes, Gemma-Texte) -----"
  "$PY" scripts/research_pulse.py --week "$WEEK_ARG"
  RC=$?
  echo "----- Ruhezustand: start-active.sh → $(readlink /home/dirk/llama.cpp/start-active.sh 2>/dev/null), llama-server $(systemctl --user is-active llama-server.service 2>/dev/null) -----"
  echo "weekly_research_pulse.sh end $(date -Iseconds) (gen=$RC)"
  exit "$RC"
} >> "$LOG" 2>&1
