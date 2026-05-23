"""Minimal llama.cpp client (OpenAI-compatible) for newsletter generation.

Drop-in replacement for `pipeline.ollama_client.chat` against a
`llama-server` instance speaking the OpenAI Chat Completions API on
http://127.0.0.1:8090/v1/chat/completions.

Only the `chat()` signature used by the newsletter generator is provided.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

LLAMACPP_HOST = os.getenv("LLAMACPP_HOST", "http://127.0.0.1:8090")
TIMEOUT = float(os.getenv("LLAMACPP_TIMEOUT", "600"))


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
