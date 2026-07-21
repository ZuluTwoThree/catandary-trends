#!/usr/bin/env bash
# One-off TEST wrapper: generate the current-week newsletter and SEND it via Resend
# (2026-07-22, 05:30 via cron). Runs after the 01:00 test cycle, which leaves the
# systemd 8B llama-server on :8090 — the generator reuses it (NEWSLETTER_LLM_BACKEND
# =llamacpp), so no VRAM juggling. Defensive: if :8090 is down (cycle failed/overran),
# start the systemd unit first. The sender is idempotent (sent_at) and delivers to
# the confirmed subscribers (currently: molkereimeister@web.de).
set -u

REPO="/home/dirk/projects/catandary-trends"
PY="$REPO/.venv/bin/python"
LOG="/home/dirk/logs/catandary-newsletter-test-$(date +%Y%m%d-%H%M).log"
mkdir -p "$(dirname "$LOG")"
export NEWSLETTER_LLM_BACKEND=llamacpp

{
  echo "================================================================"
  echo "newsletter_tonight.sh start  $(date -Iseconds)"
  echo "================================================================"

  cd "$REPO" || { echo "ABORT: cannot cd $REPO"; exit 1; }

  # Ensure an LLM is serving on :8090 (the generator needs it).
  if ! curl -sf -m 3 http://127.0.0.1:8090/v1/models >/dev/null 2>&1; then
    echo "----- :8090 down — starting llama-server.service -----"
    systemctl --user start llama-server.service
    for i in $(seq 1 15); do
      sleep 2
      curl -sf -m 3 http://127.0.0.1:8090/v1/models >/dev/null 2>&1 && { echo "  :8090 up"; break; }
    done
  else
    MODEL=$(curl -sf -m 3 http://127.0.0.1:8090/v1/models | "$PY" -c "import json,sys;print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null)
    echo "----- :8090 already serving: ${MODEL:-unknown} -----"
  fi

  echo "----- generating current-week newsletter (saves edition to DB) -----"
  "$PY" -m pipeline.newsletter_generator
  RC_GEN=$?
  echo "----- generator exit code: $RC_GEN -----"

  echo "----- sending latest edition via Resend -----"
  "$PY" -m pipeline.newsletter_sender --latest
  RC_SEND=$?
  echo "----- sender exit code: $RC_SEND -----"

  echo "newsletter_tonight.sh end  $(date -Iseconds)  (gen=$RC_GEN send=$RC_SEND)"
} >> "$LOG" 2>&1
