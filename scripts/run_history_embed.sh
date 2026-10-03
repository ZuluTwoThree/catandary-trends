#!/usr/bin/env bash
# Embed the history queue on BOTH GPUs at once (Owner 2026-10-03: "nutze die 5080, du kannst
# sie heute dafür haben"). One-off, no cron. Re-running continues where it stopped.
#
#   scripts/run_history_embed.sh            # 3090 + 5080
#   NO_REMOTE=1 scripts/run_history_embed.sh   # 3090 only
#
# bequietUbuntu: stops the user unit llama-server.service (Nemotron on :8090), starts
# Qwen3-Embedding-8B on :8095 (same GGUF, vectors cos 0.998 against the workstation's) and
# restarts the unit in an EXIT trap — also on failure. Pattern: scripts/space_eval/run_abstract_eval_bqu.sh.
# Workstation: the worker swaps :8090 to the embedding model via gpu_handover (owner
# record, symlink restore) and starts the resting 8B again afterwards.
set -u
REPO=$(cd "$(dirname "$0")/.." && pwd)
PY=$REPO/.venv/bin/python
LOGDIR=${LOGDIR:-$HOME/logs}
STAMP=$(date +%Y%m%d-%H%M)
SSH="ssh -n -o BatchMode=yes -o ConnectTimeout=10 bqu"
HOST=${BQU_HOST:-100.94.255.57}
export GPU_JOB_NAME=history_embed
mkdir -p "$LOGDIR"
cd "$REPO"
. scripts/lib/gpu_guard.sh
gpu_guard_wait history_embed 30 || exit 75

REMOTE=""
KILL_REMOTE='pkill -f "[l]lama-server .*--port 8095"; sleep 2; pkill -9 -f "[l]lama-server .*--port 8095"; true'
restore_remote() {
  [ -n "$REMOTE" ] || return 0
  $SSH "$KILL_REMOTE"
  echo "[$(date +%T)] restarting llama-server.service on bequietUbuntu"
  $SSH 'systemctl --user start llama-server.service'
  local m=""
  for _ in $(seq 1 120); do
    m=$(curl -s --max-time 3 "http://$HOST:8090/v1/models" \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"][0]["id"])' 2> /dev/null) && [ -n "$m" ] && break
    sleep 3
  done
  echo "[$(date +%T)] bequietUbuntu :8090 serves: ${m:-NOTHING — check llama-server.service there}"
  REMOTE=""
}
trap restore_remote EXIT

if [ -z "${NO_REMOTE:-}" ]; then
  echo "[$(date +%T)] bequietUbuntu before: $(curl -s --max-time 3 "http://$HOST:8090/v1/models" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"][0]["id"])' 2> /dev/null)"
  if $SSH 'systemctl --user stop llama-server.service'; then
    REMOTE=1
    sleep 3
    timeout 20 $SSH 'cd ~/llama.cpp && (nohup ./build/bin/llama-server -m ./models/Qwen3-Embedding-8B-Q4_K_M.gguf \
      --host 0.0.0.0 --port 8095 -ngl 99 -fa on --embedding --pooling last -c 32768 -np 8 -ub 2048 -b 8192 \
      > /tmp/emb8095.log 2>&1 < /dev/null &) ; true'
    for _ in $(seq 1 90); do curl -sf "http://$HOST:8095/health" > /dev/null && break; sleep 2; done
    if curl -sf "http://$HOST:8095/health" > /dev/null; then
      echo "[$(date +%T)] :8095 up on bequietUbuntu"
    else
      echo "[$(date +%T)] remote :8095 did not come up — 3090 only"; $SSH 'tail -15 /tmp/emb8095.log'
      restore_remote
    fi
  else
    echo "[$(date +%T)] could not stop Nemotron on bequietUbuntu — 3090 only"
  fi
fi

PIDS=()
if [ -n "$REMOTE" ]; then
  $PY scripts/history_embed.py work --host "http://$HOST:8095" --name 5080 --threads 3 \
      > "$LOGDIR/history-embed-5080-$STAMP.log" 2>&1 &
  PIDS+=($!)
fi
$PY scripts/history_embed.py work --handover --host http://127.0.0.1:8090 --name 3090 --threads 2 \
    > "$LOGDIR/history-embed-3090-$STAMP.log" 2>&1 &
PIDS+=($!)
echo "[$(date +%T)] workers: ${PIDS[*]} · logs $LOGDIR/history-embed-*-$STAMP.log"
RC=0
for p in "${PIDS[@]}"; do wait "$p" || RC=$?; done
echo "[$(date +%T)] workers finished rc=$RC"
$PY scripts/history_embed.py status
exit $RC
