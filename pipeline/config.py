"""Configuration loader for Catandary Trends pipeline."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "catandary.db"))
DATABASE_URL = os.getenv("DATABASE_URL", "")  # PostgreSQL connection string for production

# Ollama
# OLLAMA_HOST env var is often set to 0.0.0.0 for the server bind address.
# For the client, we always connect to 127.0.0.1.
OLLAMA_HOST = os.getenv("OLLAMA_CLIENT_HOST", "http://127.0.0.1:11434")

# Models — override via environment variables for testing
MODEL_FILTER = os.getenv("MODEL_FILTER", "qwen3:8b")
MODEL_EXTRACT = os.getenv("MODEL_EXTRACT", "nuextract")
MODEL_CLASSIFY = os.getenv("MODEL_CLASSIFY", "qwen3:8b")
MODEL_GENERATE = os.getenv("MODEL_GENERATE", "qwen3:14b")
MODEL_EMBEDDING = os.getenv("MODEL_EMBEDDING", "qwen3-embedding")

# Content-generation backend (pipeline Stage 6 / "Stage 5" in the foresight doc).
# "ollama" (default) uses MODEL_GENERATE on Ollama. "llamacpp" routes content
# generation to a llama-server (GGUF in STAGE5_MODEL) with a mid-pipeline GPU
# handover — see pipeline.gpu_handover. Other stages stay on Ollama.
STAGE5_BACKEND = os.getenv("STAGE5_BACKEND", "ollama")
STAGE5_MODEL = os.getenv("STAGE5_MODEL", "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf")
# Minimum body word count before the llama.cpp content guard retries (premature
# grammar string-termination at temp>0 occasionally yields a stub body).
STAGE5_MIN_BODY_WORDS = int(os.getenv("STAGE5_MIN_BODY_WORDS", "100"))

# qwen3:8b stages backend (pipeline Stages 2 Relevance, 3 Extraction,
# 4 Classification, 8 Reclassify).
# "ollama" (default) uses MODEL_FILTER/MODEL_CLASSIFY on Ollama. "llamacpp" routes
# all four stages to a llama-server serving STAGE_8B_MODEL, sharing the same
# port 8090 with Stage 6's 35B server via symlink-swap (see pipeline.gpu_handover).
STAGE_8B_BACKEND = os.getenv("STAGE_8B_BACKEND", "ollama")
STAGE_8B_MODEL = os.getenv("STAGE_8B_MODEL", "Qwen3-8B-UD-Q4_K_XL.gguf")

# Stages 2/3/4 classification concurrency. Dispatches the pure step_* LLM calls
# via a thread pool against the llama-server's parallel slots. Default 24 matches
# the 208K/24-slot 8B server the handover brings up (see MODEL_START_SCRIPTS).
# Set 0/1 for sequential (e.g. Ollama single-stream). Validated sweet spot: 24.
CLASSIFY_WORKERS = int(os.getenv("CLASSIFY_WORKERS", "24"))

# Stage 5 (Embeddings + Dedup) backend.
# "ollama" (default) uses MODEL_EMBEDDING on Ollama. "llamacpp" routes embedding
# generation to a llama-server in --embedding mode serving EMBED_MODEL on
# port 8090, sharing the symlink with the other llama.cpp stages.
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "ollama")
EMBED_MODEL = os.getenv("EMBED_MODEL", "Qwen3-Embedding-8B-Q4_K_M.gguf")

# Pipeline
RELEVANCE_THRESHOLD = 0.6
DUPLICATE_SIMILARITY_THRESHOLD = 0.92
AUTO_PUBLISH_CONFIDENCE = 0.85
MAX_RETRIES = 3

# Brave Search (radar discovery layer, pipeline/radar_discovery.py)
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")

# Firecrawl (backfill script, scripts/backfill_sources.py)
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

# Anthropic API — classification backend for the one-time historical backfill.
# CLASSIFY_BACKEND="anthropic" routes Stages 2/3/4/8 (relevance/extraction/
# classification/reclassify) to Claude (off-GPU); embeddings + content-gen stay
# local. The ongoing RSS pipeline stays fully local (CLAUDE.md). Takes precedence
# over STAGE_8B_BACKEND when set to "anthropic".
CLASSIFY_BACKEND = os.getenv("CLASSIFY_BACKEND", "ollama")  # ollama | llamacpp | anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL_CLASSIFY = os.getenv("ANTHROPIC_MODEL_CLASSIFY", "claude-haiku-4-5")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def load_sources() -> dict:
    """Load sources configuration from sources.yaml."""
    sources_path = PROJECT_ROOT / "sources.yaml"
    with open(sources_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_mega_trends() -> list[dict]:
    """Load canonical mega-trends taxonomy from mega_trends.yaml."""
    path = PROJECT_ROOT / "mega_trends.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("mega_trends", [])


def get_mega_trend_keys() -> list[str]:
    """Get list of canonical mega-trend keys for LLM prompt."""
    return [mt["key"] for mt in load_mega_trends()]


def get_mega_trend_prompt_block() -> str:
    """Build the mega-trend section for the classification prompt."""
    trends = load_mega_trends()
    lines = []
    for mt in trends:
        momentum = mt.get("momentum", "stable")
        lines.append(f'- {mt["key"]} [{momentum}]: {mt["description"]}')
    return "\n".join(lines)
