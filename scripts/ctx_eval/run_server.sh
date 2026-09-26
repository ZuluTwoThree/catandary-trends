#!/usr/bin/env bash
# Testserver für den Kontext-/Parallelitätstest auf Port 8190 — NIE über die
# start-*.sh-Skripte (die enthalten `pkill -f build/bin/llama-server` und binden
# :8090), sondern ~/llama.cpp/build/bin/llama-server direkt mit den Argumenten
# aus dem jeweiligen Produktivskript, --host 127.0.0.1 --port 8190, plus Overrides.
#
#   run_server.sh start <start-script-name> <label> [llama-server overrides...]
#       z. B. run_server.sh start start-gemma4-26b.sh gemma-c32k-p4 -c 32768 --parallel 4
#       Bei llama.cpp gewinnt das letzte Vorkommen eines Flags — Overrides hinten anhängen.
#       Wartet auf /health, schreibt PID nach data/ctx_eval/server.pid, Log nach
#       data/ctx_eval/server-<label>.log, druckt VRAM des Serverprozesses im Leerlauf.
#   run_server.sh stop        beendet NUR den Prozess aus server.pid (SIGTERM, dann wartet
#                             es auf die VRAM-Freigabe). Kein pkill -f.
#   run_server.sh vram        VRAM des Testserverprozesses (MiB)
set -u
LLAMA_DIR="${LLAMA_DIR:-/home/dirk/llama.cpp}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUTDIR="$ROOT/data/ctx_eval"; mkdir -p "$OUTDIR"
PIDFILE="$OUTDIR/server.pid"
PORT="${TEST_PORT:-8190}"

proc_vram() {  # MiB des Prozesses $1 laut nvidia-smi
  nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits 2>/dev/null \
    | awk -F', *' -v p="$1" '$1==p {print $2}' | head -1
}

case "${1:-}" in
  start)
    SCRIPT="$2"; LABEL="$3"; shift 3
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "Testserver läuft schon (PID $(cat "$PIDFILE")) — erst stop"; exit 1; fi
    # exec-Block des Produktivskripts → Argumentliste (ohne den Binärpfad, ohne "$@")
    ARGS=$(sed -n '/exec .\/build\/bin\/llama-server/,/"\$@"/p' "$LLAMA_DIR/$SCRIPT" \
           | sed -e '1s/.*llama-server//' -e '$d' | tr -d '\\' | tr '\n' ' ')
    export LLAMA_REASONING="${LLAMA_REASONING:-off}" LLAMA_REASONING_EFFORT="${LLAMA_REASONING_EFFORT:-default}"
    eval "set -- $ARGS \"\$@\""
    # --port/--host der Produktion durch den Testport ersetzen
    NEW=(); skip=0
    for a in "$@"; do
      if [ $skip = 1 ]; then skip=0; continue; fi
      case "$a" in --port|--host) skip=1; continue;; esac
      NEW+=("$a")
    done
    LOG="$OUTDIR/server-$LABEL.log"
    echo "# $(date -Iseconds) $SCRIPT → llama-server --host 127.0.0.1 --port $PORT ${NEW[*]}" | tee "$LOG"
    ( cd "$LLAMA_DIR" && exec ./build/bin/llama-server --host 127.0.0.1 --port "$PORT" "${NEW[@]}" ) >>"$LOG" 2>&1 &
    PID=$!; echo "$PID" > "$PIDFILE"
    for i in $(seq 1 120); do
      sleep 3
      if ! kill -0 "$PID" 2>/dev/null; then echo "SERVER GESTORBEN — Log $LOG"; tail -5 "$LOG"; rm -f "$PIDFILE"; exit 2; fi
      curl -sf -m 3 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
    done
    sleep 2
    echo "PID $PID  VRAM idle: $(proc_vram "$PID") MiB  (gesamt $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB)"
    grep -E 'n_slots|n_ctx_slot|kv_unified|KV self size|CUDA0 compute buffer|CUDA0 model buffer|rounding' "$LOG" | sed 's/^/   /' | head -12
    ;;
  stop)
    [ -f "$PIDFILE" ] || { echo "kein server.pid"; exit 0; }
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
      kill -TERM "$PID"
      for i in $(seq 1 30); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
      kill -0 "$PID" 2>/dev/null && { kill -KILL "$PID"; sleep 2; }
    fi
    rm -f "$PIDFILE"
    sleep 2; echo "gestoppt; VRAM gesamt jetzt $(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) MiB"
    ;;
  vram)
    [ -f "$PIDFILE" ] && proc_vram "$(cat "$PIDFILE")"
    ;;
  *) echo "usage: $0 start <script> <label> [overrides] | stop | vram"; exit 1;;
esac
