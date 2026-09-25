#!/usr/bin/env bash
# 8B-Block nach der Produktions-Baseline (Server 8b-prod läuft noch auf :8190).
set -u
cd "$(dirname "$0")/../.." || exit 1
PY=.venv/bin/python; RS=scripts/ctx_eval/run_server.sh; B="$PY -u scripts/ctx_eval/bench_parallel.py"
P=data/ctx_eval/prompts; R=data/ctx_eval/results.jsonl
run() { local label=$1 prompts=$2 conc=$3 n=$4; shift 4
  $B --prompts "$P/$prompts" --concurrency "$conc" --n "$n" --label "$label" --out "$R" "$@" 2>&1 | grep -v httpx; }
# Phase 4 Arm A (KV q8_0, Produktionskonfiguration): Relevanz gegen Handentscheidungen
run 8b-q8kv-hand rel_hand.jsonl 24 150 --warmup 0 --dump data/ctx_eval/q_rel_q8.jsonl
# Stage 8 (in Produktion sequentiell): was brächte Parallelität?
run 8b-prod-reclassify 8b_reclassify.jsonl 1,8,24 96 --duration 40 --ramp 10
$RS stop
# Gemeinsamer Pool 96K (24 × p99 ≈ 72K + Marge), 24 Slots
$RS start start-qwen3-8b-208k.sh 8b-c96k-p24u -c 98304 --parallel 24 --kv-unified || exit 2
run 8b-c96k-p24u 8b_stage234.jsonl 24 48 --duration 150 --ramp 45 --offset 200
run 8b-c96k-p24u-burst 8b_stage234.jsonl 48 48 --burst --offset 600 --warmup 0
$RS stop
# Gleicher Pool, 48 Slots — steigt der Durchsatz weiter?
$RS start start-qwen3-8b-208k.sh 8b-c96k-p48u -c 98304 --parallel 48 --kv-unified || exit 2
run 8b-c96k-p48u 8b_stage234.jsonl 24,48 48 --duration 150 --ramp 45 --offset 200
$RS stop
# Größere Prefill-Chunks
$RS start start-qwen3-8b-208k.sh 8b-c96k-p24u-ub2048 -c 98304 --parallel 24 --kv-unified -ub 2048 -b 2048 || exit 2
run 8b-c96k-p24u-ub2048 8b_stage234.jsonl 24 48 --duration 150 --ramp 45 --offset 200
$RS stop
# Phase 4 Arm B: KV f16 (8 Slots à 9K → 72K f16 ≈ 10,6 GB KV)
$RS start start-qwen3-8b-208k.sh 8b-c72k-p8-f16 -c 73728 --parallel 8 -ctk f16 -ctv f16 || exit 2
run 8b-f16kv-hand rel_hand.jsonl 8 150 --warmup 0 --dump data/ctx_eval/q_rel_f16.jsonl
$RS stop
echo "block_8b fertig $(date -Iseconds)"
