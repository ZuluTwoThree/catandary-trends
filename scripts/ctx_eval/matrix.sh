#!/usr/bin/env bash
# Messblöcke je Modell (Phase 2/3/4). Jeder Block: Testserver :8190 starten → Lastprofil →
# stoppen. Aufruf: matrix.sh <block>   (gemma | 27b | emb | 8b-variants)
# Voraussetzung: Produktivserver gestoppt (Fenster vom Owner bestätigt).
set -u
cd "$(dirname "$0")/../.." || exit 1
PY=.venv/bin/python; RS=scripts/ctx_eval/run_server.sh; B="$PY -u scripts/ctx_eval/bench_parallel.py"
P=data/ctx_eval/prompts; R=data/ctx_eval/results.jsonl
run() { # label prompts conc n [extra bench args]
  local label=$1 prompts=$2 conc=$3 n=$4; shift 4
  $B --prompts "$P/$prompts" --concurrency "$conc" --n "$n" --label "$label" --out "$R" "$@" 2>&1 | grep -v httpx
}
case "$1" in
  gemma)
    $RS start start-gemma4-26b.sh gemma-prod || exit 2
    run gemma-prod-c256k-p4u gemma_stage6.jsonl 1,2,4,8 24 --duration 120 --ramp 30 --dump data/ctx_eval/dump_gemma_prod.jsonl
    # Phase 4 Arm A: KV q8_0 (Produktion) — 70 A/B-Prompts, T=0.7, sequentiell
    run gemma-q8kv-ab gemma_ab.jsonl 1 70 --warmup 0 --dump data/ctx_eval/q_gemma_q8.jsonl
    $RS stop
    $RS start start-gemma4-26b.sh gemma-c16k-p1 -c 16384 --parallel 1 || exit 2
    run gemma-c16k-p1 gemma_stage6.jsonl 1 24 --duration 90 --ramp 15
    $RS stop
    $RS start start-gemma4-26b.sh gemma-c32k-p4u -c 32768 --parallel 4 --kv-unified || exit 2
    run gemma-c32k-p4u gemma_stage6.jsonl 2,4 24 --duration 90 --ramp 20
    $RS stop
    # Phase 4 Arm B: KV f16 bei kleinem Kontext
    $RS start start-gemma4-26b.sh gemma-c16k-p1-f16 -c 16384 --parallel 1 -ctk f16 -ctv f16 || exit 2
    run gemma-f16kv-ab gemma_ab.jsonl 1 70 --warmup 0 --dump data/ctx_eval/q_gemma_f16.jsonl
    $RS stop
    ;;
  27b)
    $RS start start-qwen3.8-27b.sh 27b-prod || exit 2
    run 27b-prod-c256k-p1-q4 27b_judge.jsonl 1 24 --duration 90 --ramp 15
    # Phase 4 Arm A: KV q4_0 (Produktion), Handentscheidungen
    run 27b-q4kv-hand judge_hand.jsonl 1 150 --warmup 0 --dump data/ctx_eval/q_judge_q4.jsonl
    $RS stop
    $RS start start-qwen3.8-27b.sh 27b-c16k-q8 -c 16384 --parallel 1 -ctk q8_0 -ctv q8_0 || exit 2
    run 27b-c16k-p1-q8 27b_judge.jsonl 1 24 --duration 90 --ramp 15
    run 27b-q8kv-hand judge_hand.jsonl 1 150 --warmup 0 --dump data/ctx_eval/q_judge_q8.jsonl
    $RS stop
    $RS start start-qwen3.8-27b.sh 27b-c32k-p4u-q8 -c 32768 --parallel 4 --kv-unified -ctk q8_0 -ctv q8_0 || exit 2
    run 27b-c32k-p4u-q8 27b_judge.jsonl 2,4 24 --duration 90 --ramp 20
    $RS stop
    ;;
  emb)
    $RS start start-qwen3-emb.sh emb-prod || exit 2
    run emb-prod-c8k-p4u emb.jsonl 1,2,4,8,16,24 200 --duration 25 --ramp 5
    $RS stop
    $RS start start-qwen3-emb.sh emb-c16k-p16u -c 16384 --parallel 16 --kv-unified -ub 2048 -b 2048 || exit 2
    run emb-c16k-p16u emb.jsonl 4,8,16,24 200 --duration 25 --ramp 5
    $RS stop
    $RS start start-qwen3-emb.sh emb-c8k-p8 -c 8192 --parallel 8 -ub 1024 -b 1024 || exit 2
    run emb-c8k-p8 emb.jsonl 4,8,16,24 200 --duration 25 --ramp 5
    $RS stop
    ;;
  8b-variants) echo "→ scripts/ctx_eval/block_8b.sh (läuft direkt nach der 8B-Baseline auf dem noch offenen Server)"; exit 0;;
  *) echo "usage: $0 gemma|27b|emb|8b-variants"; exit 1;;
esac
echo "matrix $1 fertig $(date -Iseconds)"
