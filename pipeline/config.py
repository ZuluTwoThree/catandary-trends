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

# Ollama
# OLLAMA_HOST env var is often set to 0.0.0.0 for the server bind address.
# For the client, we always connect to 127.0.0.1.
OLLAMA_HOST = os.getenv("OLLAMA_CLIENT_HOST", "http://127.0.0.1:11434")

# Models
MODEL_FILTER = "qwen3:8b"
MODEL_EXTRACT = "nuextract"
MODEL_CLASSIFY = "qwen3:8b"
MODEL_GENERATE = "qwen3:14b"
MODEL_EMBEDDING = "qwen3-embedding"

# Pipeline
RELEVANCE_THRESHOLD = 0.6
DUPLICATE_SIMILARITY_THRESHOLD = 0.92
AUTO_PUBLISH_CONFIDENCE = 0.9
MAX_RETRIES = 3

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def load_sources() -> dict:
    """Load sources configuration from sources.yaml."""
    sources_path = PROJECT_ROOT / "sources.yaml"
    with open(sources_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
