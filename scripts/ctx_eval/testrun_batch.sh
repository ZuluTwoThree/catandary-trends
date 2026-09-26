#!/usr/bin/env bash
# Testlauf der umgestellten Startskripte (16K-Varianten für Gemma/27B) auf dev.
# Setzt dieselbe Umgebung wie scripts/scheduled_cycle.sh und fährt einen echten
# Pipeline-Batch; ein VRAM-Sampler schreibt parallel mit.
#   scripts/ctx_eval/testrun_batch.sh [BATCH] [--skip-poll]
#
# ACHTUNG (gelernt 25.09.2026): `run_full_cycle` arbeitet ZWEI Runden ab — erst den
# Backlog (Phase 1), dann die "neuen" Einträge (Phase 3), jede bis BATCH. Ein Aufruf
# mit 250 verarbeitet also bis zu 500 Einträge. Wer genau N will, ruft
# `python -m pipeline.run_full_cycle --skip-poll --batch N` direkt auf und nimmt
# in Kauf, dass Phase 3 dann leer läuft.
#
# Wie scheduled_cycle.sh stellt dieses Skript am Ende den Ruhezustand wieder her
# (Symlink auf den 208K-Klassifizierer, llama-server gestartet) — auch bei Abbruch,
# per trap. Ohne das lag der Server nach dem ersten Testlauf 10 min tot da.
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

restore_resting_state() {
  # Ruhezustand: derselbe Endzustand, den scheduled_cycle.sh herstellt.
  # Nicht anfassen, wenn ein fremder GPU-Job die Unit hält (der stellt ihn selbst her).
  if BUSY=$(gpu_guard_busy 2>/dev/null); then
    echo "----- Ruhezustand NICHT hergestellt: fremder GPU-Job aktiv -----"
    echo "$BUSY" | sed 's/^/    /'
    return
  fi
  ln -sf start-qwen3-8b-208k.sh /home/dirk/llama.cpp/start-active.sh
  systemctl --user start llama-server.service
  for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 3
    curl -sf -m 3 http://127.0.0.1:8090/v1/models >/dev/null 2>&1 && break
  done
  echo "----- Ruhezustand: $(readlink /home/dirk/llama.cpp/start-active.sh), llama-server $(systemctl --user is-active llama-server.service) -----"
}

# shellcheck disable=SC1091
source scripts/lib/gpu_guard.sh 2>/dev/null || true
# Kollisionswächter wie in scheduled_cycle.sh: läuft ein fremder GPU-Job, nicht starten.
if BUSY=$(gpu_guard_busy 2>/dev/null); then
  echo "ABBRUCH: fremder GPU-Job aktiv — nichts angefasst:"; echo "$BUSY" | sed 's/^/  /'
  exit 75
fi

( while true; do
    printf '%s\t%s\t%s\n' "$(date +%H:%M:%S)" \
      "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" \
      "$(curl -s -m 2 http://127.0.0.1:8090/v1/models 2>/dev/null | grep -o 'models/[^"]*' | head -1)"
    sleep 2
  done ) > "$VRAM" &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null; restore_resting_state' EXIT

echo "testrun start $(date -Iseconds) batch=$BATCH args=$*" | tee "$LOG"
.venv/bin/python -m pipeline.run_full_cycle --batch "$BATCH" "$@" >> "$LOG" 2>&1
RC=$?
kill $SAMPLER 2>/dev/null
echo "testrun end $(date -Iseconds) rc=$RC" | tee -a "$LOG"
echo "--- VRAM je geladenem Modell (MiB) ---"
awk -F'\t' '$3!=""{n[$3]++; if($2>max[$3])max[$3]=$2} END{for(m in max) printf "  %-46s Spitze %s MiB (%d Messungen)\n", m, max[m], n[m]}' "$VRAM"
exit $RC
