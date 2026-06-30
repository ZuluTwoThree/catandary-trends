"""GPU handover between Ollama and llama-server for pipeline stages on llama.cpp.

Two handovers are supported, sharing the same `llama-server.service` on port 8090
via symlink-swap of `start-active.sh`:

  • Stage 6 (Content-Gen, 35B): see `content_gen_on_llamacpp`. The 35B alone
    occupies ~24 GB and cannot coexist with Ollama models. It always swaps the
    symlink to the 35B start script, so content gen uses the 35B regardless of
    which model (or none) was loaded at pipeline start.
  • Stages 2/3/4/8 (8B): see `eight_b_on_llamacpp`. The 8B (~5 GB) coexists
    fine with Ollama embeddings (~5 GB) but uses the same port as the 35B,
    so symlink-swap is required.

Common pattern for each:

  1. save the current symlink target so we can restore it on exit
  2. swap `start-active.sh` to the start script that loads the expected model
  3. free Ollama VRAM (`ollama stop` every running model)
  4. start `llama-server.service` — which now follows the swapped symlink
  5. run the stage(s) against :8090
  6. stop llama-server, restore symlink, VRAM frees for the next phase

A pre-flight check refuses to start if `start-active.sh` does not resolve to a
script that loads the expected model — defense in depth against OOM.
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

# Mapping from GGUF basename to the start script that loads it. Used to swap
# the start-active.sh symlink before bringing the server up. Add new entries
# here when introducing more llama.cpp-backed stages.
LLAMA_CPP_ROOT = Path(os.getenv("LLAMACPP_ROOT", "/home/dirk/llama.cpp"))
MODEL_START_SCRIPTS: dict[str, Path] = {
    "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf":  LLAMA_CPP_ROOT / "start-qwen3.6-35b.sh",
    # Stage-6 content-gen alternative: 30B-A3B MoE (~18 GB, 40K ctx, 2K/4K batch).
    "Qwen3-30B-A3B-Q4_K_M.gguf":        LLAMA_CPP_ROOT / "start-qwen3-30b.sh",
    # Phase 2-4 default: the 208K-context / 24-slot 8B (parallel classification).
    # CLASSIFY_WORKERS=24 fans out across its slots. Swapped out for Stage 5/6.
    "Qwen3-8B-UD-Q4_K_XL.gguf":        LLAMA_CPP_ROOT / "start-qwen3-8b-208k.sh",
    "Qwen3-Embedding-8B-Q4_K_M.gguf":  LLAMA_CPP_ROOT / "start-qwen3-emb.sh",
}

# The 208K classifier is the only valid *resting* state for start-active.sh:
# between handovers and after a cycle, :8090 should serve it. The embedding/30B/35B
# scripts are transient — swapped in for a single stage only. If a handover is
# hard-killed mid-stage (OOM/SIGKILL), its finally-based restore never runs and the
# symlink is left on a transient script; the next handover would then save & "restore"
# that poison value, cascading until the cycle ends on the wrong model. This stranded
# the embedding server on :8090 once (2026-06-30), wasting a 10h BIZ run.
CANONICAL_RESTING_MODEL = "Qwen3-8B-UD-Q4_K_XL.gguf"
CANONICAL_RESTING_SCRIPT = MODEL_START_SCRIPTS[CANONICAL_RESTING_MODEL].name


def _safe_saved_target() -> str:
    """Symlink target to restore to on handover exit — never a transient script.

    If start-active.sh is currently anything but the canonical classifier (e.g. a
    prior handover was hard-killed and left it on emb/30B/35B), fall back to the
    canonical classifier so the poison value cannot cascade through restores."""
    current = _current_symlink_target()
    if current != CANONICAL_RESTING_SCRIPT:
        logger.warning(
            "start-active.sh at handover entry is %r, not the canonical classifier "
            "— will restore to %s (poisoned-symlink guard)",
            current, CANONICAL_RESTING_SCRIPT)
        return CANONICAL_RESTING_SCRIPT
    return current


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


def _current_symlink_target() -> str | None:
    """Return the basename of the current start-active.sh target, or None."""
    if not START_ACTIVE.is_symlink():
        return None
    try:
        return os.readlink(str(START_ACTIVE))
    except OSError:
        return None


def swap_active_symlink(expected_model: str) -> str | None:
    """Point start-active.sh at the registered start script for expected_model.

    Returns the previous symlink target (basename) so it can be restored later.
    Raises RuntimeError if no start script is registered for the model, or if
    the registered script is missing.
    """
    target_script = MODEL_START_SCRIPTS.get(Path(expected_model).name)
    if target_script is None:
        raise RuntimeError(
            f"No start script registered for {expected_model}. "
            f"Known models: {list(MODEL_START_SCRIPTS)}")
    if not target_script.is_file():
        raise RuntimeError(f"Start script missing: {target_script}")

    previous = _current_symlink_target()
    new_target_name = target_script.name
    if previous == new_target_name:
        return previous  # nothing to do, symlink already correct

    logger.info("Swapping start-active.sh: %s → %s", previous, new_target_name)
    if START_ACTIVE.is_symlink() or START_ACTIVE.exists():
        START_ACTIVE.unlink()
    START_ACTIVE.symlink_to(new_target_name)
    return previous


def llama_server_start(expected_model: str, timeout: int = 240,
                       swap_symlink: bool = False) -> None:
    """Free Ollama VRAM, start llama-server via systemd, wait until ready.

    When `swap_symlink=True`, swap start-active.sh to the start script
    registered for `expected_model` before pre-flight. Used by the 8B
    context manager; Stage 6's `content_gen_on_llamacpp` keeps the legacy
    behaviour (assumes scheduled_cycle.sh has set the symlink externally).

    Raises RuntimeError if pre-flight fails or the expected model never appears.
    """
    if _model_ready(expected_model):
        logger.info("llama-server already serving %s", expected_model)
        return

    if swap_symlink:
        swap_active_symlink(expected_model)

    if not _preflight_model_matches(expected_model):
        raise RuntimeError(
            f"start-active.sh does not load {expected_model}; aborting handover")

    # Stop any llama-server already on the GPU FIRST. Without this, a pre-existing
    # server (e.g. an idle gpt-oss/8B from another context) keeps holding VRAM —
    # the VRAM-wait stalls and `systemctl start` on an already-active unit is a
    # no-op, so the expected model never loads. Stopping is idempotent (no-op if
    # already stopped), which keeps the scheduled_cycle path unaffected.
    logger.info("Freeing VRAM before starting llama-server (stop unit + unload Ollama)")
    _run(["systemctl", "--user", "stop", LLAMA_UNIT], timeout=60)
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
    """Context manager: bring llama-server up with the 35B for content gen, tear
    it down after.

    Content generation ALWAYS attempts `expected_model` (the 35B), regardless of
    which model — if any — start-active.sh pointed to at pipeline start. This
    swaps the symlink to the registered start script for `expected_model` on
    entry (saving the previous target) and restores it on exit, mirroring
    `embed_on_llamacpp` / `eight_b_on_llamacpp`. The pre-flight in
    `llama_server_start` then passes because the swap sets the right model.

    If llama-server already serves `expected_model` (e.g. externally managed),
    it is left untouched. On exit, Ollama models reload on demand for the
    subsequent reclassify/publish stages.
    """
    if _model_ready(expected_model):
        logger.info("content-gen handover: llama-server already serving %s — nothing to do",
                    expected_model)
        try:
            yield
        finally:
            pass
        return

    saved_target = _safe_saved_target()
    llama_server_start(expected_model, swap_symlink=True)
    try:
        yield
    finally:
        try:
            llama_server_stop()
        except Exception as e:
            logger.error("llama-server stop failed: %s", e)
        # Restore start-active.sh to its pre-context target so the next handover
        # and scheduled_cycle's final `systemctl start` find it as expected.
        if saved_target and _current_symlink_target() != saved_target:
            try:
                logger.info("Restoring start-active.sh → %s", saved_target)
                if START_ACTIVE.is_symlink() or START_ACTIVE.exists():
                    START_ACTIVE.unlink()
                START_ACTIVE.symlink_to(saved_target)
            except Exception as e:
                logger.error("symlink restore failed: %s", e)


@contextmanager
def embed_on_llamacpp(expected_model: str):
    """Context manager: swap symlink to embedding start script, start server,
    restore on exit. Mirrors `eight_b_on_llamacpp` for Stage 5.

    The embedding server runs in --embedding --pooling last mode, exposing
    POST /v1/embeddings only — chat endpoints are unavailable while it's up.
    `_model_ready` still works because llama-server reports its loaded model
    on GET /v1/models regardless of mode.
    """
    if _model_ready(expected_model):
        logger.info("embed handover: llama-server already serving %s — nothing to do",
                    expected_model)
        try:
            yield
        finally:
            pass
        return

    saved_target = _safe_saved_target()
    llama_server_start(expected_model, swap_symlink=True)
    try:
        yield
    finally:
        try:
            llama_server_stop()
        except Exception as e:
            logger.error("llama-server stop failed: %s", e)
        if saved_target and _current_symlink_target() != saved_target:
            try:
                logger.info("Restoring start-active.sh → %s", saved_target)
                if START_ACTIVE.is_symlink() or START_ACTIVE.exists():
                    START_ACTIVE.unlink()
                START_ACTIVE.symlink_to(saved_target)
            except Exception as e:
                logger.error("symlink restore failed: %s", e)


@contextmanager
def eight_b_on_llamacpp(expected_model: str):
    """Context manager: swap symlink to 8B start script, start server, restore on exit.

    Used to wrap Stages 2/3/4 and Stage 8. The symlink is saved on entry and
    restored on exit so the subsequent Stage 6 35B handover finds start-active.sh
    in its expected state. Also ensures `scheduled_cycle.sh`'s final
    `systemctl start llama-server.service` brings up the right model.
    """
    if _model_ready(expected_model):
        logger.info("8B handover: llama-server already serving %s — nothing to do",
                    expected_model)
        try:
            yield
        finally:
            pass
        return

    saved_target = _safe_saved_target()
    llama_server_start(expected_model, swap_symlink=True)
    try:
        yield
    finally:
        try:
            llama_server_stop()
        except Exception as e:
            logger.error("llama-server stop failed: %s", e)
        # Restore symlink to its pre-context state so the next handover finds
        # start-active.sh as it expects.
        if saved_target and _current_symlink_target() != saved_target:
            try:
                logger.info("Restoring start-active.sh → %s", saved_target)
                if START_ACTIVE.is_symlink() or START_ACTIVE.exists():
                    START_ACTIVE.unlink()
                START_ACTIVE.symlink_to(saved_target)
            except Exception as e:
                logger.error("symlink restore failed: %s", e)
