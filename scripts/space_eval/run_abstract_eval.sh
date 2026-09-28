#!/usr/bin/env bash
# eval_abstract_length.py on the local GPU (#114, owner 28.09.: "stop the 8B, use the GPU").
# Stops llama-server.service (:8090), runs the embedding model on its own port 8095
# (started and stopped by PID — NOT via ~/llama.cpp/start-*.sh, whose pkill would also
# take down the CPU embedder on :8091), and restores :8090 in an EXIT trap, so also
# when the evaluation fails. A Besitzvermerk in the main worktree tells the ops
# sampler that a known job holds the card; the run is logged in ops_events.
set -u
REPO=/home/dirk/projects/ct-dev
MAIN=/home/dirk/projects/catandary-trends
LLAMA=/home/dirk/llama.cpp
PY=$REPO/.venv/bin/python
LOG=${LOG:-/tmp/space_eval_server.log}
MARK=$MAIN/data/llama-server.space_eval.pid
PID=""
RC=0

restore() {
  [ -n "$PID" ] && kill "$PID" 2> /dev/null && wait "$PID" 2> /dev/null
  rm -f "$MARK"
  echo "[$(date +%T)] restoring llama-server.service (start-active.sh -> $(readlink "$LLAMA/start-active.sh"))"
  systemctl --user start llama-server.service
  local m=""
  for _ in $(seq 1 120); do
    m=$(curl -s --max-time 3 http://127.0.0.1:8090/v1/models \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"][0]["id"])' 2> /dev/null) && [ -n "$m" ] && break
    sleep 3
  done
  echo "[$(date +%T)] :8090 serves: ${m:-NOTHING — check llama-server.service}"
  [ -n "${EV:-}" ] && (cd "$REPO" && $PY -m pipeline.ops_events end "$EV" "$RC" "abstract-length eval #114") > /dev/null 2>&1
}
trap restore EXIT

if pgrep -f "scheduled_cycle.sh|full_cycle_cron.sh|weekly_ingesters.sh|signal_batch_embedded" > /dev/null; then
  echo "a GPU cron job is running — not touching the card"; trap - EXIT; exit 75
fi
EV=$(cd "$REPO" && $PY -m pipeline.ops_events start space_eval --pid $$ 2> /dev/null | tail -1)
systemctl --user stop llama-server.service
sleep 3
echo "[$(date +%T)] VRAM after stop: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"
( cd "$LLAMA" && exec ./build/bin/llama-server -m ./models/Qwen3-Embedding-8B-Q4_K_M.gguf --host 127.0.0.1 \
    --port 8095 -ngl 99 --no-mmap --embedding --pooling last -c 65536 -np 16 -ub 8192 -b 8192 ) > "$LOG" 2>&1 &
PID=$!
echo "$PID $$" > "$MARK"
for _ in $(seq 1 120); do
  curl -sf http://127.0.0.1:8095/health > /dev/null && break
  kill -0 "$PID" 2> /dev/null || { echo "embedding server died"; tail -15 "$LOG"; RC=1; exit 1; }
  sleep 2
done
echo "[$(date +%T)] :8095 up (pid $PID)"
(cd "$REPO" && $PY scripts/space_eval/eval_abstract_length.py --host http://127.0.0.1:8095 --batch 32 "$@") || RC=1
echo "[$(date +%T)] eval done, rc=$RC"
