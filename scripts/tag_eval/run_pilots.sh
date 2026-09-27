#!/usr/bin/env bash
# Pilots C (reranker assigns CPC / OpenAlex labels) and A (small LLMs tag like the 8B)
# on the local GPU. 2026-09-27, Owner-Go: the model on :8090 may pause for about an
# hour and is restored afterwards — by the EXIT trap, so also when a pilot fails.
#
# Test servers run on their own ports (8093 reranker, 8094 LLM, 8095 embedder) and
# are started and stopped by PID. Deliberately NOT via ~/llama.cpp/start-*.sh: those
# `pkill -f build/bin/llama-server`, which would also take down the CPU embedder on
# :8091. While the card is held, a Besitzvermerk data/llama-server.tag_eval.pid in
# the main worktree tells the ops sampler that a known job owns it (otherwise the
# gpu_foreign alarm fires), and the run is logged in ops_events.
set -u
REPO=/home/dirk/projects/ct-dev
MAIN=/home/dirk/projects/catandary-trends
LLAMA=/home/dirk/llama.cpp
PY=$REPO/.venv/bin/python
LOGD=${LOGD:-/tmp/tag_eval}
MARK=$MAIN/data/llama-server.tag_eval.pid
mkdir -p "$LOGD"
PIDS=()
RC=0

start_server() {  # port model [llama-server args...]
  local port=$1 model=$2
  shift 2
  ( cd "$LLAMA" && exec ./build/bin/llama-server -m "./models/$model" --host 127.0.0.1 \
      --port "$port" -ngl 99 --no-mmap "$@" ) > "$LOGD/server-$port.log" 2>&1 &
  local pid=$!
  PIDS+=("$pid")
  echo "$pid $$" > "$MARK"
  for _ in $(seq 1 240); do
    if curl -sf "http://127.0.0.1:$port/health" > /dev/null; then
      echo "[$(date +%T)] :$port up — $model (pid $pid)"
      return 0
    fi
    if ! kill -0 "$pid" 2> /dev/null; then
      echo "[$(date +%T)] :$port died while loading $model"
      tail -15 "$LOGD/server-$port.log"
      return 1
    fi
    sleep 2
  done
  echo "[$(date +%T)] :$port not ready after 8 min"
  return 1
}

stop_servers() {
  local p
  for p in "${PIDS[@]}"; do kill "$p" 2> /dev/null; done
  for p in "${PIDS[@]}"; do wait "$p" 2> /dev/null; done
  PIDS=()
}

restore() {
  stop_servers
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
  [ -n "${EV:-}" ] && (cd "$REPO" && $PY -m pipeline.ops_events end "$EV" "$RC" "tag-eval pilots A+C") > /dev/null 2>&1
}
trap restore EXIT

EV=$(cd "$REPO" && $PY -m pipeline.ops_events start tag_eval --pid $$ 2> /dev/null | tail -1)
echo "[$(date +%T)] :8090 before: $(curl -s --max-time 3 http://127.0.0.1:8090/v1/models | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"][0]["id"])' 2> /dev/null)"
systemctl --user stop llama-server.service
sleep 3
echo "[$(date +%T)] VRAM after stop: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"

# ---------------------------------------------------------------- pilot C
if start_server 8095 Qwen3-Embedding-8B-Q4_K_M.gguf --embedding --pooling last -c 8192 -ub 8192 -b 8192 \
   && start_server 8093 qwen3-reranker-0.6b-q8_0.gguf --reranking --pooling rank -c 16384 -ub 2048 -b 2048 -np 8; then
  # Sanity first: community GGUFs of this reranker are known to return garbage scores.
  if $PY - << 'PYEOF'
import httpx, sys
r = httpx.post("http://127.0.0.1:8093/v1/rerank", timeout=60, json={
    "query": "Which classification label describes the subject of this patent? Solar charging circuit. "
             "A charging circuit that converts sunlight collected by a photovoltaic panel into current for a battery.",
    "documents": ["H02S: Generation of electric power by conversion of infrared radiation, visible light "
                  "or ultraviolet light, e.g. using photovoltaic [PV] modules.",
                  "A23L: Foods, foodstuffs, or non-alcoholic beverages; their preparation or treatment."]}).json()
s = {x["index"]: x["relevance_score"] for x in r["results"]}
print(f"reranker sanity: H02S {s[0]:.4f}  A23L {s[1]:.4f}")
sys.exit(0 if s[0] > s[1] and abs(s[0] - s[1]) > 1e-3 else 1)
PYEOF
  then
    (cd "$REPO" && $PY scripts/tag_eval/pilot_vocab_rerank.py --rerank-host http://127.0.0.1:8093 \
        --embed-host http://127.0.0.1:8095 --n 1000 --k 20 --workers 8) || RC=1
  else
    echo "[$(date +%T)] reranker sanity FAILED — pilot C skipped"
    RC=1
  fi
else
  RC=1
fi
stop_servers

# ---------------------------------------------------------------- pilot A
for spec in "qwen3-8b|Qwen3-8B-UD-Q4_K_XL.gguf" "qwen3.5-4b|Qwen3.5-4B-UD-Q4_K_XL.gguf" \
            "gemma4-e4b|gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf"; do
  label=${spec%%|*}
  model=${spec#*|}
  if start_server 8094 "$model" -c 32768 -np 8 -fa on --jinja --reasoning off -ctk q8_0 -ctv q8_0; then
    (cd "$REPO" && LLAMACPP_HOST=http://127.0.0.1:8094 $PY scripts/tag_eval/pilot_small_llm_tags.py \
        --label "$label" --n 500 --workers 8) || RC=1
  else
    RC=1
  fi
  stop_servers
done
(cd "$REPO" && $PY scripts/tag_eval/pilot_small_llm_tags.py --compare) || RC=1
echo "[$(date +%T)] pilots done, rc=$RC"
