#!/usr/bin/env bash
# Testlauf des Draft-Richters auf dem umgestellten 16K/q8_0-27B (Stufe 10).
# Bildet den Stage-10-Block aus scripts/scheduled_cycle.sh nach: Unit stoppen, VRAM prüfen,
# Symlink auf das Richter-Skript, starten, Identitätscheck, richten, Ruhezustand herstellen.
#   scripts/ctx_eval/testrun_judge.sh [LIMIT] [--dry-run]
set -u
cd "$(dirname "$0")/../.." || exit 1
LIMIT="${1:-40}"; shift || true
SCRIPT=$(.venv/bin/python -c "import sys;sys.path.insert(0,'.');from pipeline.draft_judge import JUDGE_START_SCRIPT;print(JUDGE_START_SCRIPT)")
OUT=data/ctx_eval/testrun; mkdir -p "$OUT"
STAMP=$(date +%Y%m%d-%H%M); LOG="$OUT/judge-$STAMP.log"; VRAM="$OUT/judge-vram-$STAMP.tsv"

echo "judge testrun start $(date -Iseconds) limit=$LIMIT script=$SCRIPT args=$*" | tee "$LOG"
systemctl --user stop llama-server.service; sleep 3
for i in $(seq 1 8); do
  USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1)
  [ "${USED:-9999}" -lt 1100 ] && break
  echo "  [$i/8] VRAM belegt: $USED MiB — warte" | tee -a "$LOG"; sleep 5
done
ln -sf "$SCRIPT" /home/dirk/llama.cpp/start-active.sh
systemctl --user start llama-server.service
( while true; do printf '%s\t%s\n' "$(date +%H:%M:%S)" \
    "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)"; sleep 2; done ) > "$VRAM" &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null; ln -sf start-qwen3-8b-208k.sh /home/dirk/llama.cpp/start-active.sh; systemctl --user restart llama-server.service' EXIT
UP=0; for i in $(seq 1 40); do sleep 3; curl -sf -m 3 http://127.0.0.1:8090/v1/models >/dev/null 2>&1 && { UP=1; break; }; done
SERVED=$(curl -s -m 3 http://127.0.0.1:8090/v1/models)
echo "up=$UP served=$(echo "$SERVED" | grep -o 'models/[^\"]*' | head -1)" | tee -a "$LOG"
if [ "$UP" = "1" ] && echo "$SERVED" | grep -q "Qwen3.8-27B"; then
  .venv/bin/python -m pipeline.draft_judge --since-hours 4 --limit "$LIMIT" "$@" >> "$LOG" 2>&1
  RC=$?
else
  echo "ABBRUCH: Server nicht bereit oder falsches Modell" | tee -a "$LOG"; RC=1
fi
kill $SAMPLER 2>/dev/null
echo "judge testrun end $(date -Iseconds) rc=$RC" | tee -a "$LOG"
echo "VRAM-Spitze: $(awk -F'\t' 'BEGIN{m=0} $2>m{m=$2} END{print m}' "$VRAM") MiB"
tail -4 "$LOG"
exit $RC
