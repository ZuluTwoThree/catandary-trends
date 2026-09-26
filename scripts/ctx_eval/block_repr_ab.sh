#!/usr/bin/env bash
# Repräsentativer A/B über 150 Content-Prompts: neues 16K-Skript gegen das alte 262144er.
# Prüft Wortzahl-Verteilung UND erfundene Spezifika bei gleicher Eingabe.
set -u
cd "$(dirname "$0")/../.." || exit 1
PY=.venv/bin/python; RS=scripts/ctx_eval/run_server.sh; B="$PY -u scripts/ctx_eval/bench_parallel.py"
run() { local label=$1 script=$2 dump=$3
  $RS start "$script" "$label" || exit 2
  $B --prompts data/ctx_eval/prompts/repr_ab.jsonl --concurrency 1 --n 150 --warmup 0 \
     --label "$label" --out data/ctx_eval/results.jsonl --dump "data/ctx_eval/$dump" 2>&1 | grep -v httpx
  $RS stop; }
run repr-c16k  start-gemma4-26b-ctx16k.sh repr_c16k.jsonl
run repr-c256k start-gemma4-26b.sh        repr_c256k.jsonl
echo "block_repr_ab fertig $(date -Iseconds)"
