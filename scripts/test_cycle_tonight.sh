#!/usr/bin/env bash
# One-off TEST wrapper for the full pipeline cycle (2026-07-22, 01:00 via cron).
#
# Why a wrapper instead of calling scheduled_cycle.sh directly: a llama-server was
# started MANUALLY (outside the systemd unit) holding ~19.6 GB VRAM. The in-pipeline
# GPU handover only stops the *systemd* unit + Ollama — it cannot free a manual
# llama-server, so the first stage model-load would OOM (exit 137). This wrapper
# frees ALL VRAM first (systemd unit + any manual `build/bin/llama-server`), waits
# for the card to clear, then runs the production scheduled_cycle. The cycle restores
# the systemd 8B server on :8090 at the end, so the 05:30 newsletter has an LLM.
set -u

REPO="/home/dirk/projects/catandary-trends"
LOG="/home/dirk/logs/catandary-test-cycle-$(date +%Y%m%d-%H%M).log"
mkdir -p "$(dirname "$LOG")"

{
  echo "================================================================"
  echo "test_cycle_tonight.sh start  $(date -Iseconds)"
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

  echo "test_cycle_tonight.sh end  $(date -Iseconds)  (rc=$RC)"
} >> "$LOG" 2>&1
