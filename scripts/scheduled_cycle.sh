#!/usr/bin/env bash
# Scheduled Catandary pipeline run for off-hours use on ki-workstation.
#
# Sequence:
#   0. Capture a watermark (max raw_entries.id) BEFORE polling. Both runs below
#      are scoped to id > WATERMARK (--min-id), so the cycle only processes the
#      freshly-polled entries and never drains an unrelated backfill backlog that
#      shares the unprocessed pool (the multi-year signal backfill is classified
#      separately by signal_batch).
#   1. Run full cycle (poll + LLM) with the given batch size (default 600).
#   2. If fresh entries remain (id > WATERMARK), run a second cycle (--skip-poll)
#      sized to drain that fresh backlog in one go.
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

  # >>> Stage-6 content generation on llama.cpp 35B — `git revert` this commit to disable >>>
  # Activates the llama.cpp backend ONLY if start-active.sh actually loads the
  # expected GGUF (so the mid-pipeline GPU handover reloads exactly that model and
  # fits VRAM). Otherwise fall back to Ollama 14B — no crash, no symlink mutation.
  # Content gen ALWAYS attempts the 35B, regardless of which model (or none) is
  # loaded at pipeline start: content_gen_on_llamacpp swaps start-active.sh to the
  # 35B start script for the duration of Stage 6 and restores it afterwards. We
  # therefore gate only on the 35B START SCRIPT existing and referencing the
  # expected GGUF — not on start-active.sh's current target. Fall back to Ollama
  # only if that start script is missing/misconfigured (avoids a hard crash).
  export STAGE5_MODEL="Qwen3-30B-A3B-Q4_K_M.gguf"
  STAGE5_START="/home/dirk/llama.cpp/start-qwen3-30b.sh"
  if [ -f "$STAGE5_START" ] && grep -q "$STAGE5_MODEL" "$STAGE5_START" 2>/dev/null; then
    export STAGE5_BACKEND=llamacpp
    echo "----- Stage-6 backend: llamacpp ($STAGE5_MODEL), handover swaps symlink to 30B -----"
  else
    export STAGE5_BACKEND=ollama
    echo "----- Stage-6 backend: ollama (fallback — $STAGE5_START missing or wrong GGUF) -----"
  fi
  # <<< Stage-6 activation <<<

  # >>> Stages 2/3/4/8 on llama.cpp 8B — `git revert` this commit to disable >>>
  # Activates the llama.cpp 8B backend for the four qwen3:8b stages ONLY if the
  # 8B start script exists and references the expected GGUF. The pipeline's
  # in-run eight_b_on_llamacpp handover swaps the symlink to the 208K/24-slot
  # start script (start-qwen3-8b-208k.sh) before Stages 2-4 and Stage 8 and
  # restores it afterwards — phase 2-4 then runs parallel (CLASSIFY_WORKERS=24).
  # Fail-safe: missing script or wrong GGUF reference → fall back to Ollama.
  export STAGE_8B_MODEL="Qwen3-8B-UD-Q4_K_XL.gguf"
  ACTIVE_8B="/home/dirk/llama.cpp/start-qwen3-8b-208k.sh"
  if [ -f "$ACTIVE_8B" ] && grep -q "$STAGE_8B_MODEL" "$ACTIVE_8B" 2>/dev/null; then
    export STAGE_8B_BACKEND=llamacpp
    echo "----- Stages 2/3/4/8 backend: llamacpp ($STAGE_8B_MODEL) -----"
  else
    export STAGE_8B_BACKEND=ollama
    echo "----- Stages 2/3/4/8 backend: ollama (fallback — $ACTIVE_8B missing or wrong GGUF) -----"
  fi
  # <<< Stage 8B activation <<<

  # >>> Stage 5 Embedding on llama.cpp — `git revert` this commit to disable >>>
  # Activates the llama.cpp embedding backend ONLY if the embedding start
  # script exists and references the expected GGUF. The in-pipeline
  # embed_on_llamacpp handover swaps the symlink to start-qwen3-emb.sh
  # for Stage 5 and restores it afterwards.
  # Fail-safe: missing script or wrong GGUF reference → fall back to Ollama.
  export EMBED_MODEL="Qwen3-Embedding-8B-Q4_K_M.gguf"
  ACTIVE_EMB="/home/dirk/llama.cpp/start-qwen3-emb.sh"
  if [ -f "$ACTIVE_EMB" ] && grep -q "$EMBED_MODEL" "$ACTIVE_EMB" 2>/dev/null; then
    export EMBED_BACKEND=llamacpp
    echo "----- Stage 5 backend: llamacpp ($EMBED_MODEL) -----"
  else
    export EMBED_BACKEND=ollama
    echo "----- Stage 5 backend: ollama (fallback — $ACTIVE_EMB missing or wrong GGUF) -----"
  fi
  # <<< Stage 5 Embed activation <<<

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

  # Watermark: max raw_entries.id BEFORE the poll. Both runs are scoped to
  # id > WATERMARK so the cycle only processes freshly-polled entries and never
  # picks up an unrelated backfill backlog that shares the unprocessed pool
  # (the multi-year signal backfill is classified separately by signal_batch).
  echo
  WATERMARK=$(python - <<'PY'
from pipeline.db import get_connection
with get_connection() as c:
    print(c.execute("SELECT COALESCE(MAX(id), 0) FROM raw_entries").fetchone()[0])
PY
)
  WATERMARK="${WATERMARK:-0}"
  echo "----- watermark before poll: $WATERMARK (only entries polled after this are processed) -----"

  echo
  echo "----- run 1: full cycle (poll + LLM), batch $BATCH, min_id $WATERMARK -----"
  python -m pipeline.run_full_cycle --batch "$BATCH" --min-id "$WATERMARK"
  RC1=$?
  echo "----- run 1 exit code: $RC1 -----"

  # Remaining backlog = freshly-polled entries (id > WATERMARK) not yet done in
  # run 1 — NOT the backfill. Drained by run 2, still scoped to the watermark.
  UNPROCESSED=$(WATERMARK="$WATERMARK" python - <<'PY'
import os
from pipeline.db import get_unprocessed_entries, init_db
init_db()
print(len(get_unprocessed_entries(limit=999999, min_id=int(os.environ["WATERMARK"]))))
PY
)
  echo
  echo "----- backlog after run 1 (id > $WATERMARK): $UNPROCESSED unprocessed entries -----"

  RC2=0
  if [ "${UNPROCESSED:-0}" -gt 0 ]; then
    echo
    echo "----- run 2: drain fresh backlog (--skip-poll), batch $UNPROCESSED, min_id $WATERMARK -----"
    python -m pipeline.run_full_cycle --skip-poll --batch "$UNPROCESSED" --min-id "$WATERMARK"
    RC2=$?
    echo "----- run 2 exit code: $RC2 -----"
  else
    echo "no fresh backlog → skipping run 2"
  fi

  echo
  echo "----- restarting llama-server.service -----"
  systemctl --user start llama-server.service
  RC3=$?
  echo "----- llama-server start exit code: $RC3 -----"

  echo
  echo "scheduled_cycle.sh end  $(date -Iseconds)  (rc1=$RC1 rc2=$RC2 rc3=$RC3)"
} >> "$LOG" 2>&1
