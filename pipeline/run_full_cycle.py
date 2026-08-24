#!/usr/bin/env python3
"""Full pipeline cycle orchestrator for Catandary Trends.

Runs the complete automated pipeline:
  1. Ollama health check (abort early if LLM server is down)
  2. Backlog processing (unprocessed entries from previous cycles)
  3. Feed poll (all verticals + cross-industry)
  4. LLM processing batch (newly polled entries)
  5. Summary report

Usage:
    python -m pipeline.run_full_cycle              # Full cycle, batch 400
    python -m pipeline.run_full_cycle --batch 500  # Larger batch
    python -m pipeline.run_full_cycle --skip-poll  # Only LLM processing
    python -m pipeline.run_full_cycle --skip-llm   # Only feed polling
    python -m pipeline.run_full_cycle --dry-run    # Check Ollama + report unprocessed count

Crontab (every 4 hours):
    30 */4 * * *  cd /path/to/catandary-trends && python -m pipeline.run_full_cycle --batch 400 >> data/cycle.log 2>&1
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from pipeline.config import (
    DATA_DIR, LOG_LEVEL, OLLAMA_HOST,
    STAGE_8B_BACKEND, STAGE5_BACKEND, EMBED_BACKEND,
)

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pipeline.cycle")


def check_ollama() -> bool:
    """Verify Ollama is running and responsive."""
    try:
        resp = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m["name"] for m in models]
            logger.info("Ollama OK — %d models loaded: %s", len(models), ", ".join(model_names))
            return True
        logger.error("Ollama responded with HTTP %d", resp.status_code)
        return False
    except httpx.ConnectError:
        logger.error("Ollama not reachable at %s — is the server running?", OLLAMA_HOST)
        return False
    except Exception as e:
        logger.error("Ollama health check failed: %s", e)
        return False


MIN_GPU_FRACTION = 0.80


def check_gpu(model: str = "qwen3:14b") -> bool:
    """Verify the heaviest model is fully loaded on GPU. Force-loads via a tiny
    generate request, then reads /api/ps and asserts size_vram >= 80% of size.

    Why: a broken Ollama install or hijacked VRAM lets the model silently fall
    back to CPU, which makes Stage 6 ~10x slower without any visible error.
    Healthy load is ~84% (rest is KV-cache headroom); partial offloads drop to
    ~40% and trigger the slowdown. See feedback_pipeline_gpu_check.md.
    """
    try:
        httpx.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": model, "prompt": "hi", "stream": False,
                  "keep_alive": "5m", "think": False},
            timeout=120,
        )
    except Exception as e:
        logger.error("GPU check: test-generate on %s failed: %s", model, e)
        return False

    try:
        resp = httpx.get(f"{OLLAMA_HOST}/api/ps", timeout=10)
        ps = resp.json().get("models", [])
    except Exception as e:
        logger.error("GPU check: /api/ps failed: %s", e)
        return False

    target = next((m for m in ps if m.get("name") == model or m.get("model") == model), None)
    if target is None:
        logger.error("GPU check: %s not present in /api/ps after test-generate", model)
        return False

    vram = target.get("size_vram", 0)
    size = target.get("size", 0)
    if size <= 0:
        logger.error("GPU check FAIL: %s reported size=0 in /api/ps", model)
        return False

    fraction = vram / size
    if fraction < MIN_GPU_FRACTION:
        logger.error(
            "GPU check FAIL: %s only %.0f%% on GPU (vram=%.2f GB / size=%.2f GB, "
            "threshold=%.0f%%). Partial CPU offload makes the LLM pipeline 5-10x "
            "slower and triggers reclassify timeouts. Free VRAM (close other "
            "models, browser WebGPU, Open WebUI) and retry.",
            model, fraction * 100, vram / 1e9, size / 1e9, MIN_GPU_FRACTION * 100,
        )
        return False

    logger.info(
        "GPU check OK: %s on GPU (vram=%.2f GB / size=%.2f GB, %.0f%%)",
        model, vram / 1e9, size / 1e9, fraction * 100,
    )
    return True


MIN_GPU_TOTAL_GB = 20.0


def check_gpu_nvidia_smi(min_total_gb: float = MIN_GPU_TOTAL_GB) -> bool:
    """GPU-health preflight for the llama.cpp path — loads NO model and needs NO
    Ollama. Confirms via `nvidia-smi` that a healthy CUDA GPU with enough total
    VRAM is present. The per-stage llama-server (started by the GPU handovers)
    loads with fixed GPU layers and has its own ready-check + OOM guard, so a
    heavyweight canary load here is unnecessary — unlike the Ollama path, which
    must load qwen3:14b to detect silent CPU-offload.
    """
    import subprocess
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode != 0 or not out.stdout.strip():
            logger.error("GPU check (nvidia-smi) FAIL: rc=%d %s",
                         out.returncode, (out.stderr or "").strip()[:200])
            return False
        name, total, used = [x.strip() for x in out.stdout.strip().splitlines()[0].split(",")]
        total_gb, used_gb = float(total) / 1024, float(used) / 1024
        if total_gb < min_total_gb:
            logger.error("GPU check FAIL: %s has %.1f GB total (< %.0f GB required)",
                         name, total_gb, min_total_gb)
            return False
        logger.info("GPU check OK (nvidia-smi, no model load): %s — %.0f GB total, %.1f GB used",
                    name, total_gb, used_gb)
        return True
    except FileNotFoundError:
        logger.error("GPU check FAIL: nvidia-smi not found — no NVIDIA GPU?")
        return False
    except Exception as e:  # noqa: BLE001
        logger.error("GPU check (nvidia-smi) error: %s", e)
        return False


def run_poll() -> dict:
    """Run feed polling and return stats."""
    from pipeline.feed_poller import run_poll as _poll
    return _poll()


def run_llm(batch: int, min_id: int = 0) -> dict:
    """Run LLM processing pipeline and return stats."""
    from pipeline.llm_processor import run_pipeline_batch
    return run_pipeline_batch(limit=batch, min_id=min_id)


def get_unprocessed_count(min_id: int = 0) -> int:
    """Get number of entries waiting for LLM processing (id > min_id)."""
    from pipeline.db import get_unprocessed_entries, init_db
    init_db()
    entries = get_unprocessed_entries(limit=99999, min_id=min_id)
    return len(entries)


def write_cycle_log(result: dict):
    """Append cycle result to data/cycle_log.jsonl for monitoring."""
    log_path = DATA_DIR / "cycle_log.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Catandary Trends — Full Pipeline Cycle")
    parser.add_argument("--batch", type=int, default=400, help="Max entries to process (default: 400)")
    parser.add_argument("--skip-poll", action="store_true", help="Skip feed polling, only run LLM")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM processing, only poll feeds")
    parser.add_argument("--min-id", type=int, default=0,
                        help="only process raw_entries with id > MIN_ID — scope to a fresh poll "
                             "so a run never picks up a large unrelated backfill backlog")
    parser.add_argument("--dry-run", action="store_true", help="Show unprocessed stats, no processing (no backend/GPU checks)")
    args = parser.parse_args()

    cycle_start = time.time()
    timestamp = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 60)
    logger.info("CYCLE START — %s", timestamp)
    logger.info("=" * 60)

    # Which GPU backend(s) do the LLM stages use? (STAGE_8B = stages 2/3/4/8,
    # STAGE5 = content-gen, EMBED = embeddings.) When all are on llama.cpp, the
    # whole cycle runs on the llama-server — Ollama is not needed at all. Ollama
    # is only required when some GPU stage is still routed to it (the defaults).
    gpu_backends = {STAGE_8B_BACKEND, STAGE5_BACKEND, EMBED_BACKEND}
    uses_ollama = "ollama" in gpu_backends

    def _abort(reason: str):
        logger.error("ABORT: %s", reason)
        write_cycle_log({
            "timestamp": timestamp, "status": "aborted", "reason": reason,
            "duration_s": round(time.time() - cycle_start, 1),
        })
        sys.exit(1)

    # Step 1: LLM backend health check (only matters when LLM will run)
    if not args.skip_llm:
        if uses_ollama:
            if not check_ollama():
                _abort("ollama_unavailable")
        else:
            logger.info("LLM stages on llama.cpp (backends=%s) — Ollama not required "
                        "(managed by GPU handovers)", sorted(gpu_backends))

    # Step 1b: GPU health check (skip on dry-run). Ollama path loads qwen3:14b as
    # a CPU-offload canary; llama.cpp path checks nvidia-smi only (no model load).
    if not args.skip_llm and not args.dry_run:
        gpu_ok = check_gpu() if uses_ollama else check_gpu_nvidia_smi()
        if not gpu_ok:
            _abort("gpu_unavailable")

    # Dry run: just report status
    if args.dry_run:
        unprocessed = get_unprocessed_count()
        logger.info("DRY RUN — Unprocessed entries: %d", unprocessed)
        logger.info("Would process up to %d entries", min(args.batch, unprocessed))
        return

    # Step 2: Process backlog (unprocessed entries from previous cycles)
    backlog_stats = None
    if not args.skip_llm:
        backlog_count = get_unprocessed_count(min_id=args.min_id)
        if backlog_count > 0:
            logger.info("-" * 40)
            logger.info("PHASE 1: Backlog (%d unprocessed entries, min_id=%d)",
                        backlog_count, args.min_id)
            logger.info("-" * 40)
            t0 = time.time()
            backlog_stats = run_llm(min(args.batch, backlog_count), min_id=args.min_id)
            backlog_duration = time.time() - t0
            logger.info(
                "Backlog done in %.1fs — %d processed, %d trends created, %d filtered, %d errors",
                backlog_duration,
                backlog_stats.get("processed", 0),
                backlog_stats.get("created", 0),
                backlog_stats.get("filtered", 0),
                backlog_stats.get("errors", 0),
            )
        else:
            logger.info("No backlog — all entries already processed")

    # Step 3: Feed polling
    poll_stats = None
    if not args.skip_poll:
        logger.info("-" * 40)
        logger.info("PHASE 2: Feed Polling")
        logger.info("-" * 40)
        t0 = time.time()
        poll_stats = run_poll()
        poll_duration = time.time() - t0
        logger.info(
            "Poll done in %.1fs — %d new entries, %d duplicates skipped",
            poll_duration, poll_stats.get("new", 0), poll_stats.get("duplicate", 0),
        )
    else:
        logger.info("SKIP: Feed polling (--skip-poll)")

    # Step 3b: Full-text enrichment (#11) — fill raw_content for opt-in sources
    # before the LLM stages, so classification + content-gen work from the real
    # article, not the RSS teaser. Only opt-in sources (sources.yaml fulltext:true),
    # robots-respecting; no-op if none pending. Non-fatal on error.
    # Runs in --skip-poll drain runs too (2026-08-25): the backlog drains were
    # exactly the runs whose entries reached content-gen text-less — 84% of the
    # first judge night's candidates had an empty raw_content because of this.
    if not args.skip_llm:
        try:
            from pipeline.article_fetcher import fetch_batch
            filled = fetch_batch(limit=args.batch)
            if filled:
                logger.info("Full-text: enriched %d entries before LLM", filled)
        except Exception as e:  # noqa: BLE001
            logger.warning("Full-text enrichment skipped (non-fatal): %r", e)

    # Step 4: LLM processing (newly polled entries)
    llm_stats = None
    if not args.skip_llm:
        new_count = get_unprocessed_count(min_id=args.min_id)
        if new_count > 0:
            logger.info("-" * 40)
            logger.info("PHASE 3: LLM Pipeline (%d new entries, batch=%d, min_id=%d)",
                        new_count, args.batch, args.min_id)
            logger.info("-" * 40)
            t0 = time.time()
            llm_stats = run_llm(min(args.batch, new_count), min_id=args.min_id)
            llm_duration = time.time() - t0
            logger.info(
                "LLM done in %.1fs — %d processed, %d trends created, %d filtered, %d errors",
                llm_duration,
                llm_stats.get("processed", 0),
                llm_stats.get("created", 0),
                llm_stats.get("filtered", 0),
                llm_stats.get("errors", 0),
            )
        else:
            logger.info("No new entries to process after polling")
    else:
        logger.info("SKIP: LLM processing (--skip-llm)")

    # Step 5: Summary
    total_duration = time.time() - cycle_start
    logger.info("=" * 60)
    logger.info("CYCLE COMPLETE — %.1fs total", total_duration)
    if backlog_stats:
        logger.info("  Backlog: %d trends created, %d filtered, %d errors",
                    backlog_stats.get("created", 0), backlog_stats.get("filtered", 0), backlog_stats.get("errors", 0))
    if poll_stats:
        logger.info("  Poll: %d new entries from feeds", poll_stats.get("new", 0))
    if llm_stats:
        logger.info("  LLM:  %d trends created, %d filtered, %d errors",
                    llm_stats.get("created", 0), llm_stats.get("filtered", 0), llm_stats.get("errors", 0))
    logger.info("=" * 60)

    # Write cycle log
    result = {
        "timestamp": timestamp,
        "status": "ok",
        "duration_s": round(total_duration, 1),
        "backlog": backlog_stats,
        "poll": poll_stats,
        "llm": llm_stats,
    }
    write_cycle_log(result)

    # Exit with error code if LLM had errors
    if llm_stats and llm_stats.get("errors", 0) > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
