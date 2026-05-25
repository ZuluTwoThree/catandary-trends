"""GPU handover between Ollama and llama-server for the content-generation stage.

On the shared GPU the llama.cpp 35B (~24 GB) cannot coexist with the Ollama
pipeline models (qwen3:8b + nuextract + qwen3-embedding ≈ 12 GB). To run Stage-6
content generation on llama-server we must:

  1. free Ollama's VRAM (`ollama stop` every running model),
  2. start llama-server via its **existing systemd unit** — so it loads with the
     EXACT tuned flags from `start-active.sh` that are known to fit VRAM; we never
     invent our own llama-server invocation,
  3. run the stage against :8090,
  4. stop llama-server again so Ollama can reload for later stages (reclassify).

A pre-flight check refuses to start if `start-active.sh` does not resolve to a
script that loads the expected model — this prevents accidentally loading a
larger model that would OOM the card.
"""

import logging
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

LLAMA_UNIT = os.getenv("LLAMA_SERVER_UNIT", "llama-server.service")
LLAMACPP_HEALTH = os.getenv("LLAMACPP_HOST", "http://127.0.0.1:8090") + "/v1/models"
START_ACTIVE = Path(os.getenv("LLAMA_START_ACTIVE",
                              "/home/dirk/llama.cpp/start-active.sh"))
VRAM_FREE_THRESHOLD_MIB = int(os.getenv("VRAM_FREE_THRESHOLD_MIB", "3000"))


def _ollama_bin() -> str:
    return shutil.which("ollama") or "/home/dirk/.local/bin/ollama"


def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    logger.debug("run: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, check=False)


def _vram_used_mib() -> int | None:
    try:
        r = _run(["nvidia-smi", "--query-gpu=memory.used",
                  "--format=csv,noheader,nounits"], timeout=15)
        return int(r.stdout.strip().splitlines()[0])
    except Exception as e:
        logger.warning("nvidia-smi read failed: %s", e)
        return None


def _wait_vram_below(mib: int, timeout: int = 90) -> bool:
    """Poll until VRAM usage drops below `mib`. Returns True if reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        used = _vram_used_mib()
        if used is None:
            return True  # can't measure → don't block
        logger.info("  VRAM used: %d MiB (target < %d)", used, mib)
        if used < mib:
            return True
        time.sleep(3)
    return False


def ollama_unload() -> None:
    """Unload every running Ollama model to free VRAM."""
    ob = _ollama_bin()
    try:
        ps = _run([ob, "ps"], timeout=30)
    except Exception as e:
        logger.warning("`ollama ps` failed (%s) — skipping unload", e)
        return
    lines = ps.stdout.strip().splitlines()
    models = [ln.split()[0] for ln in lines[1:] if ln.strip()]  # skip header
    if not models:
        logger.info("Ollama: no models loaded")
        return
    for m in models:
        logger.info("Ollama: stopping %s", m)
        _run([ob, "stop", m], timeout=30)


def _served_model() -> str | None:
    """Return the model name llama-server currently serves, or None if down."""
    try:
        r = httpx.get(LLAMACPP_HEALTH, timeout=3)
        r.raise_for_status()
        data = r.json()
        return (data.get("data") or data.get("models") or [{}])[0].get("id") \
            or data["models"][0]["name"]
    except Exception:
        return None


def _preflight_model_matches(expected_model: str) -> bool:
    """Verify start-active.sh resolves to a script that loads expected_model."""
    try:
        target = START_ACTIVE.resolve()
        text = target.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Cannot read %s: %s", START_ACTIVE, e)
        return False
    basename = Path(expected_model).name
    if basename in text:
        logger.info("Pre-flight OK: %s loads %s", target.name, basename)
        return True
    logger.error("Pre-flight FAIL: %s does not reference %s — refusing to start "
                 "(would risk loading a model that does not fit VRAM)",
                 target.name, basename)
    return False


def _model_ready(expected_model: str) -> bool:
    served = _served_model()
    return served is not None and Path(expected_model).name in served


def llama_server_start(expected_model: str, timeout: int = 240) -> None:
    """Free Ollama VRAM, start llama-server via systemd, wait until ready.

    Raises RuntimeError if pre-flight fails or the expected model never appears.
    """
    if _model_ready(expected_model):
        logger.info("llama-server already serving %s", expected_model)
        return
    if not _preflight_model_matches(expected_model):
        raise RuntimeError(
            f"start-active.sh does not load {expected_model}; aborting handover")

    logger.info("Freeing Ollama VRAM before starting llama-server")
    ollama_unload()
    _wait_vram_below(VRAM_FREE_THRESHOLD_MIB, timeout=90)

    logger.info("Starting %s", LLAMA_UNIT)
    _run(["systemctl", "--user", "start", LLAMA_UNIT], timeout=60)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _model_ready(expected_model):
            logger.info("llama-server ready: %s", expected_model)
            return
        time.sleep(4)
    raise RuntimeError(
        f"llama-server did not serve {expected_model} within {timeout}s")


def llama_server_stop(timeout: int = 60) -> None:
    """Stop llama-server and wait for the GPU to release its VRAM."""
    logger.info("Stopping %s", LLAMA_UNIT)
    _run(["systemctl", "--user", "stop", LLAMA_UNIT], timeout=60)
    _wait_vram_below(VRAM_FREE_THRESHOLD_MIB, timeout=timeout)


@contextmanager
def content_gen_on_llamacpp(expected_model: str):
    """Context manager: bring llama-server up for content gen, tear it down after.

    Only stops the server on exit if WE started it (so an externally-managed
    server is left untouched). On exit, Ollama models reload on demand for the
    subsequent reclassify/publish stages.
    """
    already_up = _model_ready(expected_model)
    llama_server_start(expected_model)
    try:
        yield
    finally:
        if not already_up:
            try:
                llama_server_stop()
            except Exception as e:
                logger.error("llama-server stop failed: %s", e)
