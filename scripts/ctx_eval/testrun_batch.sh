#!/usr/bin/env bash
# Testlauf der umgestellten Startskripte (16K-Varianten für Gemma/27B) auf dev.
# Setzt dieselbe Umgebung wie scripts/scheduled_cycle.sh und fährt einen echten
# Pipeline-Batch; ein VRAM-Sampler schreibt parallel mit.
#   scripts/ctx_eval/testrun_batch.sh [BATCH] [--skip-poll]
set -u
cd "$(dirname "$0")/../.." || exit 1
BATCH="${1:-100}"; shift || true
OUT=data/ctx_eval/testrun; mkdir -p "$OUT"
STAMP=$(date +%Y%m%d-%H%M)
LOG="$OUT/cycle-$STAMP.log"; VRAM="$OUT/vram-$STAMP.tsv"

export DISTILL_SIGNAL_TYPE=1
export STAGE5_MODEL="gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"
export STAGE5_BACKEND=llamacpp
export STAGE_8B_MODEL="Qwen3-8B-UD-Q4_K_XL.gguf"
export STAGE_8B_BACKEND=llamacpp
export EMBED_MODEL="Qwen3-Embedding-8B-Q4_K_M.gguf"
export EMBED_BACKEND=llamacpp
export LLAMACPP_MAX_TOKENS=2048
export GPU_JOB_NAME=ctx_eval_testrun

( while true; do
    printf '%s\t%s\t%s\n' "$(date +%H:%M:%S)" \
      "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" \
      "$(curl -s -m 2 http://127.0.0.1:8090/v1/models 2>/dev/null | grep -o 'models/[^"]*' | head -1)"
    sleep 2
  done ) > "$VRAM" &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT

echo "testrun start $(date -Iseconds) batch=$BATCH args=$*" | tee "$LOG"
.venv/bin/python -m pipeline.run_full_cycle --batch "$BATCH" "$@" >> "$LOG" 2>&1
RC=$?
kill $SAMPLER 2>/dev/null
echo "testrun end $(date -Iseconds) rc=$RC" | tee -a "$LOG"
echo "--- VRAM je geladenem Modell (MiB) ---"
awk -F'\t' '$3!=""{n[$3]++; if($2>max[$3])max[$3]=$2} END{for(m in max) printf "  %-46s Spitze %s MiB (%d Messungen)\n", m, max[m], n[m]}' "$VRAM"
exit $RC
