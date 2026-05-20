#!/usr/bin/env bash
# Scheduled Catandary pipeline run for off-hours use on ki-workstation.
#
# Sequence:
#   1. Run full cycle (poll + LLM) with the given batch size (default 600).
#   2. If unprocessed entries remain, run a second cycle (--skip-poll) sized
#      to drain the remaining backlog in one go.
#   3. Always start llama-server.service at the end so the fcc-stack is
#      available again after the off-hours window.
#
# The script stops llama-server.service BEFORE running so Ollama
# (qwen3:14b 9.3 GB + qwen3:8b 5.2 GB) gets the full GPU. The fcc
# llama-server (~22 GB) and Ollama models cannot share VRAM on the
# RTX 3090. llama-server is restarted at the end regardless of outcome.
#
# Usage:
#   scripts/scheduled_cycle.sh [BATCH]    # default BATCH=600
#
# Logs go to ~/logs/catandary-scheduled-<YYYYMMDD-HHMM>.log

set -u

REPO="/home/dirk/projects/catandary-trends"
BATCH="${1:-600}"
LOG="/home/dirk/logs/catandary-scheduled-$(date +%Y%m%d-%H%M).log"
mkdir -p "$(dirname "$LOG")"

{
  echo "================================================================"
  echo "scheduled_cycle.sh start  $(date -Iseconds)"
  echo "  repo  : $REPO"
  echo "  batch : $BATCH"
  echo "  log   : $LOG"
  echo "================================================================"

  cd "$REPO" || { echo "ABORT: cannot cd to $REPO"; exit 1; }
  # shellcheck disable=SC1091
  source .venv/bin/activate

  echo
  echo "----- stopping llama-server.service to free GPU -----"
  systemctl --user stop llama-server.service
  # Give the GPU a moment to release VRAM before Ollama loads qwen3:14b
  for i in 1 2 3 4 5 6 7 8; do
    sleep 2
    USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    echo "  [${i}] VRAM used: ${USED} MiB"
    if [ "${USED:-9999}" -lt 1500 ]; then break; fi
  done

  echo
  echo "----- run 1: full cycle (poll + LLM), batch $BATCH -----"
  python -m pipeline.run_full_cycle --batch "$BATCH"
  RC1=$?
  echo "----- run 1 exit code: $RC1 -----"

  # Check remaining backlog regardless of exit code (Step 3 reads DB state)
  UNPROCESSED=$(python - <<'PY'
from pipeline.db import get_unprocessed_entries, init_db
init_db()
print(len(get_unprocessed_entries(limit=999999)))
PY
)
  echo
  echo "----- backlog after run 1: $UNPROCESSED unprocessed entries -----"

  RC2=0
  if [ "${UNPROCESSED:-0}" -gt 0 ]; then
    echo
    echo "----- run 2: drain backlog (--skip-poll), batch $UNPROCESSED -----"
    python -m pipeline.run_full_cycle --skip-poll --batch "$UNPROCESSED"
    RC2=$?
    echo "----- run 2 exit code: $RC2 -----"
  else
    echo "no backlog → skipping run 2"
  fi

  echo
  echo "----- restarting llama-server.service -----"
  systemctl --user start llama-server.service
  RC3=$?
  echo "----- llama-server start exit code: $RC3 -----"

  echo
  echo "scheduled_cycle.sh end  $(date -Iseconds)  (rc1=$RC1 rc2=$RC2 rc3=$RC3)"
} >> "$LOG" 2>&1
