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
# Ceiling for the truncation retry below: an attempt that hit the length
# limit gets a bigger budget, but never an unbounded one — a runaway
# enumeration must fail loudly rather than generate for minutes.
TRUNCATION_MAX_TOKENS = int(os.getenv("LLAMACPP_TRUNCATION_MAX_TOKENS", "8192"))


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


def _json_schema(schema, require_all_fields: bool):
    """The schema sent to llama-server.

    Pydantic marks only fields WITHOUT a default as required, and every field of
    ExtractionResult has one — so `required` was absent entirely and the grammar
    happily let the model omit brand_name, key_claims and quotes. It did:
    measured 0/14 brands and 0 claims across 14 articles. Listing every property
    as required forces a value for each (an empty list is still a legal value,
    so nothing is fabricated by construction).

    Opt-in per call: relevance and classification are unaffected, since forcing
    fields there would change decisions rather than fill in evidence.
    """
    js = schema.model_json_schema()
    if require_all_fields and "properties" in js:
        js["required"] = list(js["properties"].keys())
    return js


def chat_structured(model: str, prompt: str, schema: type[T],
                    system: str | None = None, temperature: float = 0.0,
                    fallback_model: str | None = None,
                    validate: Callable[[T], bool] | None = None,
                    max_validate_retries: int | None = None,
                    require_all_fields: bool = False) -> T | None:
    """Structured output against llama-server (OpenAI json_schema response_format).

    Mirrors pipeline.ollama_client.chat_structured: retry loop, markdown fence
    stripping, Pydantic validation. Thinking is disabled to avoid CoT bloat in
    the JSON payload (Qwen3 equivalent of Ollama's think=False).

    `validate`: optional content guard. If it returns False for a parsed result
    the call is retried. The last result is returned anyway once the retry budget
    is exhausted — a flagged body beats None (which loses the entry).
    `max_validate_retries`: cap on *content-guard* retries (separate from HTTP/JSON
    error retries, which keep the full MAX_RETRIES budget). Defaults to MAX_RETRIES-1.
    Set low (e.g. 1) for soft guards like the cliché check: one quick re-roll, then
    accept — avoids burning 3× GPU on output the model keeps producing anyway.
    Content-guard retries skip the exponential backoff (the server is healthy)."""
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
                "schema": _json_schema(schema, require_all_fields),
                "strict": True,
            },
        },
        "chat_template_kwargs": {"enable_thinking": False},
    }

    url = f"{LLAMACPP_HOST}/v1/chat/completions"
    vcap = max_validate_retries if max_validate_retries is not None else MAX_RETRIES - 1
    vfails = 0
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
                # Give the NEXT attempt more room instead of replaying the same
                # request. At temperature 0 an identical payload should yield an
                # identical truncation — that retries succeeded at all was down
                # to llama.cpp not being bit-deterministic (batch composition
                # shifts float reduction order). Hoping for numerical noise is
                # not error handling. Doubling is capped so one pathological
                # input cannot drag the whole run into huge generations.
                grown = min(MAX_TOKENS * (2 ** (attempt + 1)), TRUNCATION_MAX_TOKENS)
                if grown > payload["max_tokens"]:
                    logger.warning("Output truncated (finish_reason=length at "
                                   "max_tokens=%d) — retrying with %d",
                                   payload["max_tokens"], grown)
                    payload["max_tokens"] = grown
                else:
                    logger.warning("Output truncated at the %d-token ceiling — "
                                   "the prompt or schema is the problem, not the limit",
                                   payload["max_tokens"])
            result = schema.model_validate_json(_strip_fences(raw))
            if validate is not None and not validate(result):
                vfails += 1
                if vfails <= vcap and attempt < MAX_RETRIES - 1:
                    logger.warning("Content guard rejected output for %s "
                                   "(cliché retry %d/%d) — re-rolling", model, vfails, vcap)
                    continue  # no backoff: server is healthy, just re-roll
                return result  # validate budget spent → accept the last result
            return result
        except Exception as e:
            logger.warning("Attempt %d/%d failed for %s: %s",
                           attempt + 1, MAX_RETRIES, model, e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            logger.error("All attempts exhausted for %s", model)
            return None


def generate_embedding(text: str, model: str | None = None) -> list[float] | None:
    """Generate an embedding vector via llama-server's OpenAI-compatible endpoint.

    Drop-in replacement for `pipeline.ollama_client.generate_embedding`. Hits
    POST {LLAMACPP_HOST}/v1/embeddings. `model` is included in the payload but
    llama-server ignores it (the loaded model is whatever start-active.sh
    brought up); callers can pass it for logging clarity.
    """
    payload: dict = {"input": text}
    if model is not None:
        payload["model"] = model
    url = f"{LLAMACPP_HOST}/v1/embeddings"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        logger.error("llama.cpp embedding failed: %s", e)
        return None
