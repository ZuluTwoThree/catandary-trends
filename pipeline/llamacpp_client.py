"""Minimal llama.cpp client (OpenAI-compatible) for newsletter generation.

Drop-in replacement for `pipeline.ollama_client.chat` against a
`llama-server` instance speaking the OpenAI Chat Completions API on
http://127.0.0.1:8090/v1/chat/completions.

Only the `chat()` signature used by the newsletter generator is provided.
"""

import logging
import os
import time
from typing import Callable, TypeVar

import httpx
from pydantic import BaseModel

from pipeline.config import MAX_RETRIES

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

LLAMACPP_HOST = os.getenv("LLAMACPP_HOST", "http://127.0.0.1:8090")
TIMEOUT = float(os.getenv("LLAMACPP_TIMEOUT", "600"))
# Headroom for GeneratedContent (title+summary+150-250w body+attribution).
# Grammar-constrained decoding force-closes JSON when the budget is hit, which
# yields valid-but-truncated output — so give enough room to finish naturally.
MAX_TOKENS = int(os.getenv("LLAMACPP_MAX_TOKENS", "1024"))


def chat(model: str, prompt: str, system: str | None = None,
         temperature: float = 0.0) -> str:
    """Send a chat request to llama-server and return the response text."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }

    url = f"{LLAMACPP_HOST}/v1/chat/completions"
    logger.debug("llama.cpp chat → %s (model=%s, T=%.2f)", url, model, temperature)
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError) as e:
        logger.error("llama.cpp response missing content: %s — body=%s", e, data)
        return ""


def _strip_fences(raw: str) -> str:
    """Remove markdown code fences some models wrap JSON in."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()
    return cleaned


def chat_structured(model: str, prompt: str, schema: type[T],
                    system: str | None = None, temperature: float = 0.0,
                    fallback_model: str | None = None,
                    validate: Callable[[T], bool] | None = None) -> T | None:
    """Structured output against llama-server (OpenAI json_schema response_format).

    Mirrors pipeline.ollama_client.chat_structured: retry loop, markdown fence
    stripping, Pydantic validation. Thinking is disabled to avoid CoT bloat in
    the JSON payload (Qwen3 equivalent of Ollama's think=False).

    `validate`: optional content guard. If it returns False for a parsed result
    (e.g. body too short due to premature grammar string-termination), the call
    is retried like a failed attempt. On the final attempt the last result is
    returned anyway — a short body beats None (which loses the entry).
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
        "max_tokens": MAX_TOKENS,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": True,
            },
        },
        "chat_template_kwargs": {"enable_thinking": False},
    }

    url = f"{LLAMACPP_HOST}/v1/chat/completions"
    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=TIMEOUT) as client:
                r = client.post(url, json=payload)
                r.raise_for_status()
                data = r.json()
            choice = data["choices"][0]
            raw = choice["message"]["content"] or ""
            if not raw.strip():
                raise ValueError("Empty response from model")
            if choice.get("finish_reason") == "length":
                logger.warning("Output truncated (finish_reason=length, "
                               "max_tokens=%d) — consider raising LLAMACPP_MAX_TOKENS",
                               MAX_TOKENS)
            result = schema.model_validate_json(_strip_fences(raw))
            if validate is not None and not validate(result):
                if attempt < MAX_RETRIES - 1:
                    logger.warning("Content guard rejected output for %s "
                                   "(attempt %d/%d) — retrying",
                                   model, attempt + 1, MAX_RETRIES)
                    time.sleep(2 ** attempt)
                    continue
                logger.warning("Content guard still failing on final attempt "
                               "for %s — returning last result", model)
            return result
        except Exception as e:
            logger.warning("Attempt %d/%d failed for %s: %s",
                           attempt + 1, MAX_RETRIES, model, e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            logger.error("All attempts exhausted for %s", model)
            return None
