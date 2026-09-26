#!/usr/bin/env bash
# 8B ohne --kv-unified, weniger Slots bei gleichem Slot-Kontext (Vergleich zum 96K-Pool):
# unified teilt EINEN Puffer über alle Sequenzen — die Attention läuft dann über alle belegten
# Zellen, nicht nur die eigene Sequenz. Deshalb hier die klassische Variante.
set -u
cd "$(dirname "$0")/../.." || exit 1
PY=.venv/bin/python; RS=scripts/ctx_eval/run_server.sh; B="$PY -u scripts/ctx_eval/bench_parallel.py"
P=data/ctx_eval/prompts; R=data/ctx_eval/results.jsonl
run() { local label=$1 prompts=$2 conc=$3 n=$4; shift 4
  $B --prompts "$P/$prompts" --concurrency "$conc" --n "$n" --label "$label" --out "$R" "$@" 2>&1 | grep -v httpx; }
$RS start start-qwen3-8b-208k.sh 8b-c143k-p16 -c 143360 --parallel 16 || exit 2
run 8b-c143k-p16 8b_stage234.jsonl 16,24 48 --duration 150 --ramp 45 --offset 200
$RS stop
$RS start start-qwen3-8b-208k.sh 8b-c215k-p24-ub2048 -c 215040 --parallel 24 -ub 2048 -b 2048 || exit 2
run 8b-c215k-p24-ub2048 8b_stage234.jsonl 24 48 --duration 150 --ramp 45 --offset 200
$RS stop
echo "block_8b_extra fertig $(date -Iseconds)"
