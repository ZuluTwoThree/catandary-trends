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

  echo "----- freeing GPU: stop systemd unit + any manual llama-server -----"
  systemctl --user stop llama-server.service 2>/dev/null
  if pkill -f 'build/bin/llama-server' 2>/dev/null; then
    echo "  killed manual/leftover llama-server process(es)"
  else
    echo "  no manual llama-server process found"
  fi

  echo "----- waiting for VRAM to clear (<1500 MiB) -----"
  for i in $(seq 1 20); do
    sleep 2
    USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
    echo "  [$i] VRAM used: ${USED} MiB"
    [ "${USED:-9999}" -lt 1500 ] && break
  done

  echo "----- launching production scheduled_cycle.sh 600 -----"
  bash "$REPO/scripts/scheduled_cycle.sh" 600
  RC=$?
  echo "----- scheduled_cycle.sh exit code: $RC -----"

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

  echo "full_cycle_cron.sh end  $(date -Iseconds)  (rc=$RC)"
} >> "$LOG" 2>&1
