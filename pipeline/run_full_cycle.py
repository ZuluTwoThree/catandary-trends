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

from pipeline.config import DATA_DIR, LOG_LEVEL, OLLAMA_HOST

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
    parser.add_argument("--dry-run", action="store_true", help="Check Ollama health + show stats, no processing")
    args = parser.parse_args()

    cycle_start = time.time()
    timestamp = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 60)
    logger.info("CYCLE START — %s", timestamp)
    logger.info("=" * 60)

    # Step 1: Ollama health check
    if not args.skip_poll or not args.skip_llm:
        ollama_ok = check_ollama()
        if not ollama_ok and not args.skip_llm:
            logger.error("ABORT: Ollama is not available. Cannot run LLM pipeline.")
            result = {
                "timestamp": timestamp,
                "status": "aborted",
                "reason": "ollama_unavailable",
                "duration_s": round(time.time() - cycle_start, 1),
            }
            write_cycle_log(result)
            sys.exit(1)

    # Step 1b: GPU placement check (only when LLM will run, skip on dry-run)
    if not args.skip_llm and not args.dry_run:
        if not check_gpu():
            logger.error("ABORT: GPU not available — refusing to run LLM pipeline on CPU.")
            result = {
                "timestamp": timestamp,
                "status": "aborted",
                "reason": "gpu_unavailable",
                "duration_s": round(time.time() - cycle_start, 1),
            }
            write_cycle_log(result)
            sys.exit(1)

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
