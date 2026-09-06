#!/usr/bin/env bash
# Weekly newsletter: generate the current-week edition and SEND it via Resend.
#
# Content engine: Gemma-4-26B, ensured on :8090 below (owner decision 2026-08-02).
# The sender is idempotent (sent_at) and delivers to the confirmed subscribers.
#
# NOT YET A CRON JOB — run manually. Before scheduling this weekly, three things
# must be fixed (see docs/launch/newsletter-doi-php/EINBAU.md):
#   1. PUBLIC_BASE_URL in the pipeline .env still points at localhost:3004, so
#      every unsubscribe link in a sent mail is a dead localhost URL.
#   2. The sender links /trends/newsletter/unsubscribe — a Next.js route that
#      does not exist on the Hetzner webspace. Legally required before mailing
#      anyone but ourselves.
#   3. Confirmed subscribers live in MySQL on Hetzner; this sender reads local
#      Postgres. The export bridge (export.php + sync_subscribers.py) has to run
#      first, or real signups are never mailed.
#
# RELEASE GATE (owner mandate 2026-09-06): the send step below exits 2 and mails
# nothing unless the edition has been released by a person at
# /trends/newsletter/review (newsletter_editions.approved_at). This wrapper
# generates a FRESH edition, which is by definition not released yet — so a run
# of this script ends at `send=2` until the owner has read and released it. That
# is the intended order (generate → read → release → send), not a failure; see
# docs/owner_manual.md § 7.5.
set -u

# cron has no systemd user session — set XDG_RUNTIME_DIR so `systemctl --user`
# (used below to bring up llama-server if :8090 is down) can reach the bus.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

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

  # --- Ensure the CONTENT ENGINE is Gemma-4-26B ---------------------------
  # Owner decision 2026-08-02 after an A/B on the 2026-W31 data: the 26B cites
  # more grounded specifics (5 vs 3), forms cross-cutting theses instead of
  # describing, and produced all 8 verticals in one pass where the 8B needed
  # per-vertical retries. Previously this wrapper simply reused whatever the
  # nightly cycle had left on :8090 — which made the newsletter's quality
  # depend on chance. Same symlink-swap pattern scheduled_cycle.sh uses.
  MODEL_ID() { curl -sf -m 3 http://127.0.0.1:8090/v1/models \
      | "$PY" -c "import json,sys;print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null; }

  WANT="gemma-4-26B"
  CUR="$(MODEL_ID)"
  if [ -n "$CUR" ] && [[ "$CUR" == *"$WANT"* ]]; then
    echo "----- :8090 already serving the content engine: $CUR -----"
  else
    echo "----- :8090 serving '${CUR:-nothing}' — swapping to $WANT -----"
    systemctl --user stop llama-server.service 2>/dev/null
    sleep 3
    ln -sfn start-gemma4-26b.sh /home/dirk/llama.cpp/start-active.sh \
      || echo "  WARN: symlink swap failed — starting whatever is active"
    systemctl --user start llama-server.service
    for i in $(seq 1 30); do
      sleep 3
      CUR="$(MODEL_ID)"
      [ -n "$CUR" ] && { echo "  :8090 up: $CUR (after $((i*3))s)"; break; }
    done
  fi

  if [ -z "$CUR" ]; then
    echo "ABORT: no model serving on :8090 — refusing to generate"
    echo "newsletter_tonight.sh end  $(date -Iseconds)  (gen=skipped send=skipped)"
    exit 1
  fi
  case "$CUR" in
    *"$WANT"*) : ;;
    *) echo "  WARN: generating on '$CUR', not $WANT — quality may differ" ;;
  esac

  echo "----- generating current-week newsletter (saves edition to DB) -----"
  "$PY" -m pipeline.newsletter_generator
  RC_GEN=$?
  echo "----- generator exit code: $RC_GEN -----"

  # Only send if generation succeeded — otherwise `--latest` would ship a STALE
  # edition (as happened 2026-07-22: gen failed, sender mailed the old W29).
  RC_SEND="skipped"
  if [ "$RC_GEN" -eq 0 ]; then
    echo "----- sending latest edition via Resend -----"
    "$PY" -m pipeline.newsletter_sender --latest
    RC_SEND=$?
    echo "----- sender exit code: $RC_SEND -----"
    if [ "$RC_SEND" -eq 2 ]; then
      echo "      (edition not released — read it at /trends/newsletter/review"
      echo "       and press 'Release for sending', then run the sender again:"
      echo "       .venv/bin/python -m pipeline.newsletter_sender --latest)"
    fi
  else
    echo "----- generation FAILED (rc=$RC_GEN) — skipping send (no stale edition) -----"
  fi

  echo "newsletter_tonight.sh end  $(date -Iseconds)  (gen=$RC_GEN send=$RC_SEND)"
} >> "$LOG" 2>&1
