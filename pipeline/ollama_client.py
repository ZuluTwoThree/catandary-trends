"""Ollama client wrapper with retry logic and structured output support."""

import logging
import time
from typing import TypeVar

import ollama
from pydantic import BaseModel

from pipeline.config import OLLAMA_HOST, MAX_RETRIES

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Initialize the Ollama client with generous timeout for inference
client = ollama.Client(host=OLLAMA_HOST, timeout=300)  # 5 min timeout


def chat(model: str, prompt: str, system: str | None = None,
         temperature: float = 0.0) -> str:
    """Send a chat request to Ollama and return the response text."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat(
        model=model,
        messages=messages,
        options={"temperature": temperature},
        think=False,
    )
    return response.message.content or ""


def chat_structured(model: str, prompt: str, schema: type[T],
                    system: str | None = None, temperature: float = 0.0,
                    fallback_model: str | None = None) -> T | None:
    """Send a chat request and parse the response into a Pydantic model.

    Uses structured output (JSON schema) with retry and optional model fallback.
    Disables Qwen3 thinking mode to get direct JSON output.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat(
                model=model,
                messages=messages,
                format=schema.model_json_schema(),
                options={"temperature": temperature},
                think=False,
            )
            raw = response.message.content or ""
            if not raw.strip():
                raise ValueError("Empty response from model")
            result = schema.model_validate_json(raw)
            logger.debug("Structured output from %s (attempt %d): %s", model, attempt + 1, result)
            return result
        except Exception as e:
            logger.warning("Attempt %d/%d failed for %s: %s", attempt + 1, MAX_RETRIES, model, e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue

            # Fallback to alternative model
            if fallback_model and fallback_model != model:
                logger.info("Falling back to %s", fallback_model)
                try:
                    response = client.chat(
                        model=fallback_model,
                        messages=messages,
                        format=schema.model_json_schema(),
                        options={"temperature": temperature},
                        think=False,
                    )
                    raw = response.message.content or ""
                    return schema.model_validate_json(raw)
                except Exception as e2:
                    logger.error("Fallback model %s also failed: %s", fallback_model, e2)

            logger.error("All attempts exhausted for %s", model)
            return None


def generate_embedding(model: str, text: str) -> list[float] | None:
    """Generate an embedding vector for the given text."""
    try:
        response = client.embed(model=model, input=text)
        return response.embeddings[0]
    except Exception as e:
        logger.error("Embedding generation failed: %s", e)
        return None


def check_model_available(model: str) -> bool:
    """Check if a model is available locally in Ollama."""
    try:
        models = client.list()
        available = [m.model for m in models.models]
        return any(model in name or name.startswith(model) for name in available)
    except Exception as e:
        logger.error("Failed to check model availability: %s", e)
        return False
