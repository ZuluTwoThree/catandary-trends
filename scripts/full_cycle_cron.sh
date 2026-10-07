#!/usr/bin/env bash
# Production cron wrapper for the full pipeline cycle (Mon-Fri 04:00).
# Ursprünglich als One-off-Testwrapper gebaut (2026-07-22), seit 2026-07-28 der
# reguläre Einstiegspunkt für den geplanten Full Cycle.
#
# Why a wrapper instead of calling scheduled_cycle.sh directly: a llama-server
# may have been started MANUALLY (outside the systemd unit), holding ~20 GB VRAM.
# The in-pipeline GPU handover only stops the *systemd* unit + Ollama — it cannot
# free a manual llama-server, so the first stage model-load would OOM (exit 137).
# This wrapper frees ALL VRAM first (systemd unit + any manual
# `build/bin/llama-server`), waits for the card to clear, then runs the production
# scheduled_cycle. The cycle restores the systemd 8B server on :8090 at the end.
#
# Kollisionswächter (#98, seit 2026-09-05): das VRAM-Freiräumen killt JEDEN
# manuellen llama-server — auch den eines laufenden Ingester-/Dossier-/Pulse-
# Jobs. Deshalb wartet der Wrapper vorher per scripts/lib/gpu_guard.sh, bis
# kein bekannter GPU-Job mehr läuft (max GPU_GUARD_MAX_MIN=90 min); ist die GPU
# dann immer noch belegt, bricht er mit rc=75 ab, OHNE etwas anzufassen (die
# end-Zeile trägt den rc → der Wächter meldet es). Ein zweiter, von Hand
# gestarteter Cycle fällt unter dieselbe Regel (Vorfall 05.09.: manueller
# Nachtlauf lief in den Samstags-Ingester).
set -u

# cron has no systemd user session — `systemctl --user` fails with
# "Failed to connect to bus" unless XDG_RUNTIME_DIR points at the (lingering)
# user runtime dir. Linger is enabled, so /run/user/<uid> exists; export it so
# the GPU handovers inside the pipeline can start/stop llama-server.service.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

REPO="/home/dirk/projects/catandary-trends"
LOG="/home/dirk/logs/catandary-full-cycle-$(date +%Y%m%d-%H%M).log"
mkdir -p "$(dirname "$LOG")"

{
  echo "================================================================"
  echo "full_cycle_cron.sh start  $(date -Iseconds)"
  echo "================================================================"

  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/gpu_guard.sh"
  # shellcheck disable=SC1091
  source "$REPO/scripts/lib/ops_events.sh"
  ops_event_start full_cycle_cron
  if ! gpu_guard_wait full_cycle_cron; then
    echo "ABORT: fremder GPU-Job nach ${GPU_GUARD_MAX_MIN} min immer noch aktiv — VRAM NICHT freigeräumt, Cycle nicht gestartet"
    ops_event_end 75 "blocked: fremder GPU-Job"
    echo "full_cycle_cron.sh end  $(date -Iseconds)  (rc=75)"
    exit 75
  fi

  echo "----- freeing GPU: stop systemd unit + any llama-server HOLDING VRAM -----"
  systemctl --user stop llama-server.service 2>/dev/null
  # Nur toeten, was wirklich VRAM haelt. `pkill -f build/bin/llama-server` traf
  # auch den CPU-Embedder auf :8091 (CUDA_VISIBLE_DEVICES="", 0 MiB VRAM), der
  # die Vektorsuche des Rechercheurs bedient — er lag am 10.09. nach dem ersten
  # Nachtlauf tot da. Der Zweck dieses Blocks ist die Karte, nicht der Name des
  # Prozesses: die PID-Liste kommt deshalb aus nvidia-smi.
  GPU_PIDS=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader,nounits 2>/dev/null | tr -d ' ')
  KILLED=0
  for pid in $(pgrep -f 'build/bin/llama-server' 2>/dev/null); do
    if printf '%s\n' "$GPU_PIDS" | grep -qx "$pid"; then
      kill "$pid" 2>/dev/null && KILLED=$((KILLED + 1))
    else
      echo "  leaving PID $pid alone — holds no VRAM (CPU server, e.g. the :8091 embedder)"
    fi
  done
  if [ "$KILLED" -gt 0 ]; then
    echo "  killed $KILLED llama-server process(es) that held VRAM"
  else
    echo "  no VRAM-holding llama-server process found"
  fi
  # Fremde Tagesanwendungen (Owner 04.10.: nemo-speech, whisper-server) werden fuer den
  # Nachtlauf beendet — das 24-Slot-8B der Stufen 2-4 braucht ~22 GB und passt nicht
  # neben ihre ~4,8 GB. Nur Prozesse, die laut nvidia-smi VRAM halten UND auf
  # GPU_EVICT_PATTERNS (scripts/lib/gpu_guard.sh) passen; alles andere bleibt stehen.
  if [ -n "${GPU_EVICT_PATTERNS:-}" ]; then
    EVICTED=0
    while IFS=, read -r epid ename emem; do
      epid=$(echo "$epid" | tr -d ' '); ename=$(echo "$ename" | tr -d ' ')
      [ -n "$epid" ] || continue
      if printf '%s' "$ename" | grep -Eq "$GPU_EVICT_PATTERNS"; then
        echo "  evicting PID $epid ($ename, ${emem} MiB) — not needed during the cycle (GPU_EVICT_PATTERNS)"
        gpu_evict_pid "$epid" && EVICTED=$((EVICTED + 1))
      fi
    done < <(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>/dev/null)
    [ "$EVICTED" -gt 0 ] && echo "  evicted $EVICTED day-time GPU process(es)"
  fi

  echo "----- waiting for VRAM to clear (<1500 MiB) -----"
  for i in $(seq 1 20); do
    sleep 2
    USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
    echo "  [$i] VRAM used: ${USED} MiB"
    [ "${USED:-9999}" -lt 1500 ] && break
  done

  # Batchgroesse: so bemessen, dass ein normaler Tag in EINEM Lauf durchgeht.
  #
  # Mit 600 sprang run 2 an JEDEM Tag an (Cycle-Logs 02.-09.09.) und kostete
  # jedes Mal einen kompletten zweiten Stage-8-Pass — Reclassify laeuft ueber
  # ALLE Drafts, ~28 min, fuer dasselbe Ergebnis.
  #
  # Gemessener Anfall in die Pipeline: 1.509-1.619/Tag mit 474 Quellen,
  # 3.565 am 10.09. mit 560 Quellen — davon rund 1.107 der Einmaleffekt der
  # 53 erstmals ziehenden Quellen. Stationaer also ~2.460. 3000 deckt das mit
  # gut 20 % Luft.
  #
  # Zu hoch kostet nichts: run_full_cycle nimmt min(batch, vorhandene), ein
  # groesserer Wert verarbeitet also nie mehr als da ist. Gegen einen
  # Massen-Ingest schuetzen ohnehin CYCLE_MAX_PER_SOURCE (200/Quelle/Lauf) und
  # die 50k-Sanity-Zaehlung in scheduled_cycle.sh, nicht diese Zahl.
  #
  # CYCLE_BATCH in der Crontab-Zeile hebt ihn fuer EINE Nacht weiter an.
  CYCLE_BATCH="${CYCLE_BATCH:-3000}"
  echo "----- launching production scheduled_cycle.sh $CYCLE_BATCH -----"
  bash "$REPO/scripts/scheduled_cycle.sh" "$CYCLE_BATCH"
  RC=$?
  echo "----- scheduled_cycle.sh exit code: $RC -----"

  # Vor dem Lauf gestoppte Tagesanwendungen (Docker, s. gpu_evict_pid) wieder starten —
  # auch nach einem Fehlschlag. Laeuft inzwischen ein fremder GPU-Job, bleiben sie aus
  # (Hinweis im Log, der Vermerk data/gpu_evicted_containers bleibt stehen).
  echo "----- day-time GPU apps -----"
  gpu_evict_restore || true

  # Morning reminder for the grounding-hold review queue (#71). Stays silent
  # when nothing was held, so a mail only ever arrives with real work in it.
  # Never fails the cycle — the run itself already succeeded at this point.
  # `-m scripts.review_notify` resolves the package from the CURRENT directory,
  # and cron starts in $HOME — so this failed with "No module named scripts" in
  # every run from 2026-08-04 to 2026-08-10 and no mail was ever sent. The `||`
  # made it non-fatal, which is why it stayed invisible. Run it from the repo.
  echo "----- review queue notification -----"
  ( cd "$REPO" && "$REPO/.venv/bin/python" -m scripts.review_notify ) \
    || echo "  (notification failed — non-fatal)"

  ops_event_end "$RC" "batch=${CYCLE_BATCH:-?}"
  echo "full_cycle_cron.sh end  $(date -Iseconds)  (rc=$RC)"
} >> "$LOG" 2>&1
