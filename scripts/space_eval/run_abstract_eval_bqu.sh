#!/usr/bin/env bash
# eval_abstract_length.py on the RTX 5080 of bequietUbuntu (owner 28.09.: "use the 5080,
# you may stop Nemotron briefly"). Stops the user unit llama-server.service there
# (Nemotron on :8090), starts Qwen3-Embedding-8B on :8095 (same GGUF, md5-identical to the
# workstation's), runs the evaluation FROM the workstation, and restarts the unit in an
# EXIT trap — also when the evaluation fails. A cross-host check embeds 200 texts on the
# workstation's CPU embedder (:8091) as well: same vector space on both machines?
set -u
REPO=/home/dirk/projects/ct-dev
PY=$REPO/.venv/bin/python
SSH="ssh -n -o BatchMode=yes -o ConnectTimeout=10 bqu"
HOST=${BQU_HOST:-100.94.255.57}
STARTED=""
RC=0
# The remote server is found by its port, not by a remembered PID: on 28.09. `nohup setsid
# ... & echo $!` over ssh returned the PID of the wrapping shell and the ssh session did
# not return until killed (the server kept it open).
# "[l]lama-server": without the brackets pkill -f also matches the ssh shell that carries
# this very pattern in its command line and kills it (28.09.: the restart after it never ran).
KILL_REMOTE='pkill -f "[l]lama-server .*--port 8095"; sleep 2; pkill -9 -f "[l]lama-server .*--port 8095"; true'

restore() {
  [ -n "$STARTED" ] && $SSH "$KILL_REMOTE"
  echo "[$(date +%T)] restarting llama-server.service on bequietUbuntu"
  $SSH 'systemctl --user start llama-server.service'
  local m=""
  for _ in $(seq 1 120); do
    m=$(curl -s --max-time 3 "http://$HOST:8090/v1/models" \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"][0]["id"])' 2> /dev/null) && [ -n "$m" ] && break
    sleep 3
  done
  echo "[$(date +%T)] bequietUbuntu :8090 serves: ${m:-NOTHING — check llama-server.service there}"
}
trap restore EXIT

echo "[$(date +%T)] before: $(curl -s --max-time 3 "http://$HOST:8090/v1/models" | python3 -c 'import sys,json; print(json.load(sys.stdin)["data"][0]["id"])' 2> /dev/null)"
$SSH 'systemctl --user stop llama-server.service' || { RC=1; exit 1; }
sleep 3
echo "[$(date +%T)] VRAM after stop: $($SSH 'nvidia-smi --query-gpu=memory.used --format=csv,noheader')"
STARTED=1
timeout 20 $SSH 'cd ~/llama.cpp && (nohup ./build/bin/llama-server -m ./models/Qwen3-Embedding-8B-Q4_K_M.gguf \
  --host 0.0.0.0 --port 8095 -ngl 99 -fa on --embedding --pooling last -c 32768 -np 8 -ub 2048 -b 8192 \
  > /tmp/emb8095.log 2>&1 < /dev/null &) ; true'
echo "[$(date +%T)] remote embedding server: $($SSH 'pgrep -f "[l]lama-server .*--port 8095"' | tr '\n' ' ')"
for _ in $(seq 1 90); do
  curl -sf "http://$HOST:8095/health" > /dev/null && break
  sleep 2
done
curl -sf "http://$HOST:8095/health" > /dev/null || { echo "remote :8095 not up"; $SSH 'tail -15 /tmp/emb8095.log'; RC=1; exit 1; }
echo "[$(date +%T)] :8095 up on bequietUbuntu"
(cd "$REPO" && $PY scripts/space_eval/eval_abstract_length.py --host "http://$HOST:8095" --batch 32 \
    --label "RTX 5080 bequietUbuntu" --out eval_abstract_length_5080.json \
    --compare-host http://127.0.0.1:8091 "$@") || RC=1
echo "[$(date +%T)] eval done, rc=$RC"
