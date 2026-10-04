#!/usr/bin/env bash
# Food pilot (#114), full run — one-off, on demand, NOT a cron. Runs from this worktree.
#   1. waits for a free GPU (scripts/lib/gpu_guard.sh), logs to ops_events (job food_pilot)
#   2. takes the selected research works over into raw_entries (idempotent: known URLs are
#      reused, already processed rows are skipped) — data/food_pilot/{patents.ids,research.jsonl}
#      come from `scripts/food_pilot.py select`
#   3. embeds + distill-classifies exactly that list: signal_batch_embedded --ids-file --clean-text
#   4. restores the resting state (8B on :8090) — the embedding handover only restores the
#      symlink and leaves the unit stopped (seen 29.09. after the 1,000-entry test run)
#   5. rebuilds research_signals so search and the research explorer see the new papers
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
LOG="/home/dirk/logs/food-pilot-$(date +%Y%m%d-%H%M).log"
{
  echo "food pilot start $(date -Iseconds)"
  cd "$REPO" || exit 1
  source "$REPO/scripts/lib/ops_events.sh"
  ops_event_start food_pilot "issue #114"
  source "$REPO/scripts/lib/gpu_guard.sh"
  if ! gpu_guard_wait food_pilot; then
    ops_event_end 75 "blocked: fremder GPU-Job"; echo "food pilot end $(date -Iseconds) (blocked)"; exit 75
  fi
  "$PY" -u scripts/food_pilot.py takeover --apply; RC_T=$?
  RC_E=skipped
  if [ "$RC_T" -eq 0 ]; then
    "$PY" -u scripts/signal_batch_embedded.py --ids-file data/food_pilot/embed.ids --clean-text; RC_E=$?
  fi
  if BUSY=$(gpu_guard_busy); then
    echo "----- resting state NOT restored: another GPU job holds the card -----"; RC_REST=busy
  else
    ln -sfn "$LLAMA_REST_SCRIPT" /home/dirk/llama.cpp/start-active.sh
    systemctl --user start llama-server.service; RC_REST=$?
    for i in $(seq 1 40); do sleep 3; curl -sf -m 3 http://127.0.0.1:8090/v1/models > /dev/null && break; done
    echo "----- resting state: $(readlink /home/dirk/llama.cpp/start-active.sh), llama-server $(systemctl --user is-active llama-server.service) -----"
  fi
  "$PY" -u scripts/build_research_index.py; RC_I=$?
  "$PY" -u scripts/food_pilot.py status
  RC=0; [ "$RC_T" -ne 0 ] && RC=1; [ "$RC_E" != 0 ] && RC=1; [ "$RC_I" -ne 0 ] && RC=1
  ops_event_end "$RC" "takeover=$RC_T embed=$RC_E index=$RC_I rest=$RC_REST"
  echo "food pilot end $(date -Iseconds) (rc=$RC takeover=$RC_T embed=$RC_E index=$RC_I rest=$RC_REST)"
  exit "$RC"
} >> "$LOG" 2>&1
