#!/usr/bin/env bash
# Resume the closing stages of a cycle that died before finishing.
#
# Written for 2026-08-17: the machine rebooted uncleanly at 06:21 (no shutdown
# record, log tail truncated to nul bytes) while the 04:00 cycle was still in
# content generation. Ingestion and generation had completed — 858 trends were
# written — but Stage 8 (reclassify) and Stage 9 (auto-publish) never ran, so
# every one of them stayed a draft and nothing reached the site.
#
# Deliberately NOT a full cycle: there were zero unprocessed non-patent entries,
# so polling and the LLM pipeline have nothing to do. Re-running them would cost
# ~3 GPU-hours and risk generating duplicates of articles that already exist.
#
# What it does, in the order the cycle would have:
#   1. put the Stage-8 model (Qwen3-8B, 208K) on :8090, remembering what was
#      there so the owner's model is restored afterwards
#   2. reclassify_drafts()      — Stage 8
#   3. pipeline.auto_publisher  — Stage 9
#   4. scripts.review_notify    — the morning mail the crashed run never sent
#
#   ./scripts/resume_cycle.sh              # run it
#   DEADLINE_HHMM=0345 ./scripts/resume_cycle.sh
#
# The deadline exists because this is scheduled at 02:00 and full_cycle_cron.sh
# fires at 04:00 — that wrapper frees ALL VRAM as its first act, which would
# kill this mid-write. Stopping ourselves cleanly beats being killed.
set -u

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

REPO="/home/dirk/projects/catandary-trends"
PY="$REPO/.venv/bin/python"
LLAMA="/home/dirk/llama.cpp"
STAGE8_START="${LLAMA_8B_WORK_SCRIPT:-start-qwen3-8b-16slot.sh}"
STAGE8_GGUF="Qwen3-8B-UD-Q4_K_XL.gguf"
DEADLINE_HHMM="${DEADLINE_HHMM:-0345}"
LOG="/home/dirk/logs/catandary-resume-$(date +%Y%m%d-%H%M).log"
mkdir -p "$(dirname "$LOG")"

model_id() {
  curl -sf -m 3 http://127.0.0.1:8090/v1/models \
    | "$PY" -c "import json,sys;print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null
}

past_deadline() { [ "$(date +%H%M)" -ge "$DEADLINE_HHMM" ]; }

{
  echo "================================================================"
  echo "resume_cycle.sh start  $(date -Iseconds)   deadline ${DEADLINE_HHMM}"
  echo "================================================================"
  cd "$REPO" || { echo "ABORT: cannot cd $REPO"; exit 1; }

  # config.py reads .env via load_dotenv(), which resolves against the CURRENT
  # directory. Started from anywhere else, DATABASE_URL stays empty and the
  # pipeline silently falls back to the stale local SQLite file — it would run
  # to completion against the wrong database and report success. Verified the
  # hard way while smoke-testing this unit (3,564 drafts there vs 10,105 in
  # production). Fail loudly instead.
  if ! "$PY" -c "import sys; sys.path.insert(0,'.'); from pipeline import db; sys.exit(0 if db.USE_POSTGRES else 1)"; then
    echo "ABORT: not connected to PostgreSQL — refusing to touch the SQLite fallback"
    exit 1
  fi

  echo "----- state before -----"
  "$PY" - <<'STATE'
import sys; sys.path.insert(0, '.')
from pipeline.db import get_connection
with get_connection() as c:
    r = dict(c.execute(
        "SELECT COUNT(*) FILTER (WHERE status='draft') d, "
        "       COUNT(*) FILTER (WHERE status='draft' AND confidence>=0.85) hi "
        "  FROM trends WHERE created_at > NOW() - INTERVAL '3 days'").fetchone())
    print(f"  drafts (last 3 days): {r['d']}, of those conf>=0.85: {r['hi']}")
STATE

  # --- 1. Stage-8 model, remembering what was loaded --------------------
  PREV_TARGET="$(readlink "$LLAMA/start-active.sh" || true)"
  PREV_MODEL="$(model_id)"
  echo "----- :8090 currently serving '${PREV_MODEL:-nothing}' (symlink: ${PREV_TARGET:-?}) -----"

  if [ ! -f "$LLAMA/$STAGE8_START" ] || ! grep -q "$STAGE8_GGUF" "$LLAMA/$STAGE8_START"; then
    echo "ABORT: $STAGE8_START missing or does not reference $STAGE8_GGUF"
    exit 1
  fi

  case "${PREV_MODEL:-}" in
    *"$STAGE8_GGUF"*) echo "  already the Stage-8 model — no swap needed" ;;
    *)
      echo "----- swapping :8090 to $STAGE8_GGUF -----"
      systemctl --user stop llama-server.service 2>/dev/null
      sleep 3
      ln -sfn "$STAGE8_START" "$LLAMA/start-active.sh"
      systemctl --user reset-failed llama-server.service 2>/dev/null || true  # start limit (gpu_handover.unit_start)
      systemctl --user start llama-server.service
      for i in $(seq 1 40); do
        sleep 3
        CUR="$(model_id)"
        [ -n "$CUR" ] && { echo "  up after $((i*3))s: $CUR"; break; }
      done
      [ -z "${CUR:-}" ] && { echo "ABORT: :8090 never came up"; exit 1; }
      ;;
  esac

  export STAGE_8B_BACKEND=llamacpp
  export STAGE_8B_MODEL="$STAGE8_GGUF"
  export LLAMACPP_MAX_TOKENS=2048

  # --- 2. Stage 8: reclassify ------------------------------------------
  RC_RECLASS="skipped"
  if past_deadline; then
    echo "----- past deadline before Stage 8 — skipping -----"
  else
    # Seit 2026-09-24 nur die noch nicht gestempelten Drafts (reclassified_at
    # IS NULL) — genau das, was ein abgebrochener Lauf schuldig geblieben ist.
    # Der ganze Bestand nur mit Absicht: reclassify_drafts(force=True).
    echo "----- Stage 8: reclassify_drafts() -----"
    "$PY" - <<'RECLASS'
import logging, sys, time
sys.path.insert(0, '.')
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
from pipeline.reclassify import reclassify_drafts
t0 = time.time()
stats = reclassify_drafts()
logging.getLogger("resume").info("Stage 8 done in %.1fs: %s", time.time() - t0, stats)
RECLASS
    RC_RECLASS=$?
    echo "----- Stage 8 exit code: $RC_RECLASS -----"
  fi

  # --- 3. Stage 9: auto-publish ----------------------------------------
  # Runs even if reclassify failed: the drafts are already generated and
  # classified well enough to judge, and leaving them unpublished for another
  # day is the worse outcome. The publish gate still applies per article.
  RC_PUB="skipped"
  if past_deadline; then
    echo "----- past deadline before Stage 9 — skipping (drafts stay for tonight) -----"
  else
    echo "----- Stage 9: auto_publisher -----"
    "$PY" -m pipeline.auto_publisher
    RC_PUB=$?
    echo "----- Stage 9 exit code: $RC_PUB -----"
  fi

  # --- 4. the morning mail the crashed run never sent -------------------
  echo "----- review queue notification -----"
  ( cd "$REPO" && "$PY" -m scripts.review_notify ) \
    || echo "  (notification failed — non-fatal)"

  # --- 5. give the card back exactly as we found it ---------------------
  if [ -n "$PREV_TARGET" ] && [ "$PREV_TARGET" != "$STAGE8_START" ]; then
    echo "----- restoring :8090 to $PREV_TARGET -----"
    systemctl --user stop llama-server.service 2>/dev/null
    sleep 3
    ln -sfn "$PREV_TARGET" "$LLAMA/start-active.sh"
    systemctl --user reset-failed llama-server.service 2>/dev/null || true  # start limit (gpu_handover.unit_start)
    systemctl --user start llama-server.service
    for i in $(seq 1 40); do
      sleep 3
      CUR="$(model_id)"
      [ -n "$CUR" ] && { echo "  restored: $CUR"; break; }
    done
  else
    echo "----- symlink already at $STAGE8_START — nothing to restore -----"
  fi

  echo "----- state after -----"
  "$PY" - <<'STATE'
import sys; sys.path.insert(0, '.')
from pipeline.db import get_connection
with get_connection() as c:
    r = dict(c.execute(
        "SELECT COUNT(*) FILTER (WHERE status='draft') d, "
        "       COUNT(*) FILTER (WHERE status='published') p "
        "  FROM trends WHERE created_at > NOW() - INTERVAL '3 days'").fetchone())
    print(f"  last 3 days: {r['p']} published, {r['d']} still draft")
STATE

  echo "resume_cycle.sh end  $(date -Iseconds)  (reclass=$RC_RECLASS publish=$RC_PUB)"
} >> "$LOG" 2>&1
