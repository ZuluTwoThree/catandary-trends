#!/usr/bin/env bash
# Abschluss: Produktionskonfiguration 8B im selben Dauerlast-Fenster wie die Varianten, dann
# Phase-3-Sonden (längste erlaubte Anfrage, VRAM unter Last) für die Kandidatenkonfigurationen.
set -u
cd "$(dirname "$0")/../.." || exit 1
PY=.venv/bin/python; RS=scripts/ctx_eval/run_server.sh; B="$PY -u scripts/ctx_eval/bench_parallel.py"
P=data/ctx_eval/prompts; R=data/ctx_eval/results.jsonl
run() { local label=$1 prompts=$2 conc=$3 n=$4; shift 4
  $B --prompts "$P/$prompts" --concurrency "$conc" --n "$n" --label "$label" --out "$R" "$@" 2>&1 | grep -v httpx; }
$RS start start-qwen3-8b-208k.sh 8b-prod-ramp || exit 2
run 8b-prod-c208k-p24-ramp 8b_stage234.jsonl 24 48 --duration 150 --ramp 45 --offset 200
run 8b-prod-probe probe_8b_extraction.jsonl 24 24 --warmup 0 --timeout 1200
$RS stop
$RS start start-qwen3-8b-208k.sh 8b-c143k-p16-ub2048 -c 143360 --parallel 16 -ub 2048 -b 2048 || exit 2
run 8b-c143k-p16-ub2048 8b_stage234.jsonl 16 48 --duration 150 --ramp 45 --offset 200
run 8b-c143k-p16-ub2048-probe probe_8b_extraction.jsonl 16 16 --warmup 0 --timeout 1200
$RS stop
$RS start start-qwen3.8-27b.sh 27b-c16k-q8-probe -c 16384 --parallel 1 -ctk q8_0 -ctv q8_0 || exit 2
run 27b-c16k-q8-probe probe_27b_judge.jsonl 1 2 --warmup 0 --timeout 1200
$RS stop
$RS start start-gemma4-26b.sh gemma-c16k-p1-probe -c 16384 --parallel 1 || exit 2
run gemma-c16k-p1-probe probe_gemma_content.jsonl 1 2 --warmup 0 --timeout 1200
$RS stop
# Gemma mehrere Slots OHNE unified (4 × 8192): skaliert Stufe 6, wenn der Code parallel schickte?
$RS start start-gemma4-26b.sh gemma-c32k-p4 -c 32768 --parallel 4 --no-kv-unified || exit 2
run gemma-c32k-p4 gemma_stage6.jsonl 2,4 24 --duration 90 --ramp 20
$RS stop
echo "block_final fertig $(date -Iseconds)"
