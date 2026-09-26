#!/usr/bin/env bash
# Diagnose: begrenzt die Grammatik (response_format json_schema, CPU-Sampling je Slot) den
# 8B-Durchsatz? Gleiche Prompts, gleicher Server, einmal mit und einmal ohne Schema.
set -u
cd "$(dirname "$0")/../.." || exit 1
PY=.venv/bin/python; RS=scripts/ctx_eval/run_server.sh; B="$PY -u scripts/ctx_eval/bench_parallel.py"
P=data/ctx_eval/prompts; R=data/ctx_eval/results.jsonl
run() { local label=$1 prompts=$2 conc=$3 n=$4; shift 4
  $B --prompts "$P/$prompts" --concurrency "$conc" --n "$n" --label "$label" --out "$R" "$@" 2>&1 | grep -v httpx; }
$RS start start-qwen3-8b-208k.sh 8b-c96k-p24u-diag -c 98304 --parallel 24 --kv-unified || exit 2
run 8b-c96k-p24u-noschema 8b_stage234.jsonl 24 48 --duration 120 --ramp 30 --offset 200 --no-schema
run 8b-c96k-p24u-noschema-rel rel_hand.jsonl 24 150 --duration 60 --ramp 15 --no-schema
run 8b-c96k-p24u-schema-rel rel_hand.jsonl 24 150 --duration 60 --ramp 15
$RS stop
echo "block_diag fertig $(date -Iseconds)"
