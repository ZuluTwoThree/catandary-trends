"""Anthropic API client for structured classification (backfill backend only).

Mirrors `pipeline.ollama_client.chat_structured` so the classification stages
(relevance / extraction / classification / reclassify) can route to Claude when
`CLASSIFY_BACKEND=anthropic`. This is a deliberate, scoped exception for the
one-time historical Cross-Vertical backfill — the ongoing RSS pipeline stays
fully local (CLAUDE.md "Cloud-APIs nur als Fallback"). Embeddings and
content-generation stay local regardless.

`chat_structured` is the synchronous, drop-in replacement (same signature and
`T | None` contract as the Ollama/llama.cpp clients). `batch_classify` uses the
Message Batches API (−50% cost, prompt-cached system+schema) for the production
full-run.
"""
from __future__ import annotations

import logging
import time
from typing import TypeVar

from pydantic import BaseModel

from pipeline.config import ANTHROPIC_API_KEY, MAX_RETRIES

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_TOKENS = 2048  # structured classification output is small (~300 tokens)
_client = None


def _get_client():
    """Lazily build the Anthropic client. Returns None if key/SDK unavailable."""
    global _client
    if _client is not None:
        return _client
    if not ANTHROPIC_API_KEY:
        return None
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic SDK not installed: pip install anthropic")
        return None
    _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _parse_kwargs(model: str, prompt: str, schema: type[T],
                  system: str | None, temperature: float) -> dict:
    kwargs = {
        "model": model,
        "max_tokens": _MAX_TOKENS,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
        "output_format": schema,
    }
    if system:
        # Cache the (large, stable) system prefix — read at ~0.1x on subsequent
        # calls within the 5-min TTL. The taxonomy/mega-trend block dominates the
        # input, so this is the main cost lever at scale.
        kwargs["system"] = [{"type": "text", "text": system,
                             "cache_control": {"type": "ephemeral"}}]
    return kwargs


def chat_structured(model: str, prompt: str, schema: type[T],
                    system: str | None = None, temperature: float = 0.0,
                    fallback_model: str | None = None) -> T | None:
    """Synchronous structured call to Claude. Returns a validated `schema`
    instance, or `None` on refusal / exhausted retries (callers treat `None` as
    skip/filter, matching the Ollama client contract)."""
    client = _get_client()
    if client is None:
        logger.error("anthropic backend unavailable (no ANTHROPIC_API_KEY or SDK)")
        return None

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.parse(**_parse_kwargs(model, prompt, schema, system, temperature))
            if getattr(resp, "stop_reason", None) == "refusal":
                logger.warning("anthropic refusal for %s", model)
                return None
            out = resp.parsed_output
            if out is not None:
                return out
            raise ValueError("parsed_output is None")
        except Exception as e:  # noqa: BLE001 — mirror ollama_client behaviour
            logger.warning("anthropic attempt %d/%d failed (%s): %s",
                           attempt + 1, MAX_RETRIES, model, e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

    if fallback_model and fallback_model != model:
        logger.info("anthropic falling back to %s", fallback_model)
        try:
            resp = client.messages.parse(
                **_parse_kwargs(fallback_model, prompt, schema, system, temperature))
            return resp.parsed_output
        except Exception as e:  # noqa: BLE001
            logger.error("anthropic fallback %s also failed: %s", fallback_model, e)

    logger.error("anthropic: all attempts exhausted for %s", model)
    return None


# Validation keywords Pydantic emits that Anthropic structured output rejects.
_UNSUPPORTED_SCHEMA_KEYS = frozenset({
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minLength", "maxLength", "pattern", "format",
    "minItems", "maxItems", "uniqueItems",
})


def _strict_schema(node):
    """Make a Pydantic JSON schema acceptable to Anthropic structured output: every
    object needs `additionalProperties: false`, and unsupported validation keywords
    (numeric/length/array constraints, pattern, format) must be removed. The SDK's
    `messages.parse` does this internally; the raw batch path must do it itself.
    Recurses into nested objects, $defs, anyOf/allOf, array items."""
    if isinstance(node, dict):
        for k in list(node):
            if k in _UNSUPPORTED_SCHEMA_KEYS:
                del node[k]
        if node.get("type") == "object":
            node["additionalProperties"] = False
        for v in node.values():
            _strict_schema(v)
    elif isinstance(node, list):
        for v in node:
            _strict_schema(v)
    return node


def batch_classify(items: list[tuple[str, str]], schema: type[T], system: str,
                   model: str, max_tokens: int = _MAX_TOKENS,
                   poll_interval: int = 30, timeout: int = 86_400) -> dict[str, T | None]:
    """Classify many prompts via the Message Batches API (−50% cost).

    `items` = list of (custom_id, prompt). Returns {custom_id: schema-instance | None}.
    Submits one batch, polls to completion, validates each result against `schema`.
    """
    client = _get_client()
    if client is None:
        logger.error("anthropic backend unavailable; batch_classify is a no-op")
        return {cid: None for cid, _ in items}

    schema_json = _strict_schema(schema.model_json_schema())
    requests = []
    for cid, prompt in items:
        params = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"format": {"type": "json_schema", "schema": schema_json}},
        }
        if system:
            params["system"] = [{"type": "text", "text": system,
                                 "cache_control": {"type": "ephemeral"}}]
        requests.append({"custom_id": cid, "params": params})

    batch = client.messages.batches.create(requests=requests)
    logger.info("anthropic batch %s submitted (%d requests, model=%s)",
                batch.id, len(requests), model)

    deadline = time.time() + timeout
    while time.time() < deadline:
        status = client.messages.batches.retrieve(batch.id)
        if status.processing_status == "ended":
            break
        logger.info("anthropic batch %s: %s", batch.id, status.processing_status)
        time.sleep(poll_interval)

    results: dict[str, T | None] = {cid: None for cid, _ in items}
    for r in client.messages.batches.results(batch.id):
        if r.result.type != "succeeded":
            continue
        msg = r.result.message
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            results[r.custom_id] = schema.model_validate_json(text)
        except Exception as e:  # noqa: BLE001
            logger.warning("anthropic batch parse failed for %s: %s", r.custom_id, e)
    return results
