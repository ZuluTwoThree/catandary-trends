#!/usr/bin/env bash
# A/B: erzeugt der kleinere Kontext kürzere Bodies? Gleiche 39 Prompts dünner Quellen,
# einmal auf dem neuen 16K-Skript, einmal auf dem alten 262144er. Testserver :8190.
set -u
cd "$(dirname "$0")/../.." || exit 1
PY=.venv/bin/python; RS=scripts/ctx_eval/run_server.sh; B="$PY -u scripts/ctx_eval/bench_parallel.py"
P=data/ctx_eval/prompts; R=data/ctx_eval/results.jsonl
run() { local label=$1 script=$2 dump=$3; shift 3
  $RS start "$script" "$label" "$@" || exit 2
  $B --prompts "$P/thin_ab.jsonl" --concurrency 1 --n 39 --warmup 0 --label "$label" \
     --out "$R" --dump "data/ctx_eval/$dump" 2>&1 | grep -v httpx
  $RS stop; }
run thin-c16k  start-gemma4-26b-ctx16k.sh thin_c16k.jsonl
run thin-c256k start-gemma4-26b.sh        thin_c256k.jsonl
echo "block_thin_ab fertig $(date -Iseconds)"
