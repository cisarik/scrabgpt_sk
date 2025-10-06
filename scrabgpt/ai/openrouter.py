"""OpenRouter integration for multi-model AI gameplay.

Allows concurrent calls to multiple AI models and selection of best move.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextlib import contextmanager
from itertools import count
from typing import Any, Iterator

import httpx

from ..logging_setup import TRACE_ID_VAR

log = logging.getLogger("scrabgpt.ai.openrouter")


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return headers with sensitive values redacted for logging."""

    sanitized = dict(headers)
    if "Authorization" in sanitized:
        sanitized["Authorization"] = "***redacted***"
    return sanitized


def _format_json(data: Any) -> str:
    """Safely format JSON payloads for debug logs."""

    try:
        return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:  # noqa: BLE001
        return repr(data)


class OpenRouterClient:
    """Client for OpenRouter API with support for multiple models."""
    
    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout_seconds: int | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        env_timeout = os.getenv("OPENROUTER_TIMEOUT_SECONDS")
        try:
            env_timeout_value = int(env_timeout) if env_timeout is not None else None
        except ValueError:
            env_timeout_value = None
        resolved_timeout = timeout_seconds or env_timeout_value or 120
        self.timeout_seconds = max(5, resolved_timeout)
        self.base_url = "https://openrouter.ai/api/v1"
        timeout_config = httpx.Timeout(
            timeout=self.timeout_seconds,
            connect=min(10.0, max(1.0, self.timeout_seconds / 3)),
        )
        self.client = httpx.AsyncClient(
            timeout=timeout_config,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
        self._call_counter = count(1)
    
    def _next_call_id(self, kind: str) -> str:
        """Return a unique identifier for logging scopes."""

        return f"{kind}-{next(self._call_counter)}"

    @contextmanager
    def _trace_scope(self, call_id: str) -> Iterator[str]:
        """Bind TRACE_ID to include OpenRouter call id for downstream logs."""

        current = TRACE_ID_VAR.get()
        combined = call_id if current in {"", "-"} else f"{current}|{call_id}"
        token = TRACE_ID_VAR.set(combined)
        try:
            yield combined
        finally:
            TRACE_ID_VAR.reset(token)
    
    async def fetch_models(self, *, order: str = "week") -> list[dict[str, Any]]:
        """Fetch available models from OpenRouter.
        
        Args:
            order: Sorting order - 'week' for top weekly, 'created' for newest
        """
        call_id = self._next_call_id("models")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"order": order}

        with self._trace_scope(call_id) as trace_id:
            log.info("[%s] Fetching OpenRouter models order=%s", trace_id, order)
            log.debug(
                "[%s] GET %s/models headers=%s params=%s",
                trace_id,
                self.base_url,
                _sanitize_headers(headers),
                params,
            )

            start = time.perf_counter()

            try:
                response = await self.client.get(
                    f"{self.base_url}/models",
                    headers=headers,
                    params=params,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                models_list: list[dict[str, Any]] = data.get("data", [])

                for model in models_list:
                    pricing = model.get("pricing", {})
                    model["prompt_price"] = float(pricing.get("prompt", 0))
                    model["completion_price"] = float(pricing.get("completion", 0))

                elapsed = time.perf_counter() - start
                log.info(
                    "[%s] Retrieved %d models in %.2fs (HTTP %s)",
                    trace_id,
                    len(models_list),
                    elapsed,
                    response.status_code,
                )
                log.debug("[%s] Models response: %s", trace_id, _format_json(data))

                return models_list
            except httpx.TimeoutException as e:
                elapsed = time.perf_counter() - start
                log.error(
                    "[%s] Timeout fetching models after %.2fs: %s",
                    trace_id,
                    elapsed,
                    e,
                )
                return []
            except Exception as e:
                elapsed = time.perf_counter() - start
                response_data: str | None = None
                if isinstance(e, httpx.HTTPStatusError):
                    response_data = e.response.text
                    status = e.response.status_code
                else:
                    status = "?"
                log.error(
                    "[%s] Failed to fetch models (status=%s, elapsed=%.2fs): %s",
                    trace_id,
                    status,
                    elapsed,
                    e,
                )
                if response_data:
                    log.error("[%s] Error response body: %s", trace_id, response_data)
                log.debug("[%s] Exception detail", trace_id, exc_info=True)
                return []
    
    async def call_model(
        self,
        model_id: str,
        prompt: str,
        max_tokens: int = 3600,
    ) -> dict[str, Any]:
        """Call a specific model via OpenRouter."""
        call_id = self._next_call_id("call")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/cisarik/scrabgpt_sk",
            "X-Title": "ScrabGPT SK",
        }
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }

        with self._trace_scope(call_id) as trace_id:
            log.info(
                "[%s] Calling model %s (max_tokens=%d, prompt_chars=%d)",
                trace_id,
                model_id,
                max_tokens,
                len(prompt),
            )
            log.debug("[%s] Request headers=%s", trace_id, _sanitize_headers(headers))
            log.debug("[%s] Request payload: %s", trace_id, _format_json(payload))
            log.debug("[%s] Prompt body:\n%s", trace_id, prompt)

            start = time.perf_counter()

            try:
                response = await self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()

                elapsed = time.perf_counter() - start
                log.info(
                    "[%s] Model %s responded HTTP %s in %.2fs",
                    trace_id,
                    model_id,
                    response.status_code,
                    elapsed,
                )
                log.debug("[%s] Response headers=%s", trace_id, dict(response.headers))
                log.debug("[%s] Raw response JSON: %s", trace_id, _format_json(data))

                if "choices" not in data or not data["choices"]:
                    log.error(
                        "[%s] Model %s returned unexpected structure: %s",
                        trace_id,
                        model_id,
                        data,
                    )
                    return {
                        "model": model_id,
                        "content": "",
                        "error": "Unexpected response structure",
                        "status": "error",
                        "raw_json": data,
                        "trace_id": trace_id,
                        "call_id": call_id,
                        "elapsed": elapsed,
                        "timeout_seconds": self.timeout_seconds,
                        "request_payload": payload,
                        "request_headers": _sanitize_headers(headers),
                    }

                message = data["choices"][0].get("message", {})
                content = message.get("content", "")

                if not content:
                    reasoning = message.get("reasoning", "")
                    if reasoning:
                        log.info(
                            "[%s] Model %s returned reasoning instead of content", trace_id, model_id
                        )
                        content = reasoning

                if not content:
                    log.warning(
                        "[%s] Model %s returned empty content. Response: %s",
                        trace_id,
                        model_id,
                        data,
                    )
                    return {
                        "model": model_id,
                        "content": "",
                        "error": "Model returned empty response",
                        "status": "error",
                        "raw_json": data,
                        "trace_id": trace_id,
                        "call_id": call_id,
                        "elapsed": elapsed,
                        "timeout_seconds": self.timeout_seconds,
                        "request_payload": payload,
                        "request_headers": _sanitize_headers(headers),
                    }

                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)

                log.info("[%s] Model %s raw content:\n%s", trace_id, model_id, content)
                log.info("[%s] Model %s full JSON:\n%s", trace_id, model_id, _format_json(data))
                log.info(
                    "[%s] Parsed response from %s (prompt_tokens=%d, completion_tokens=%d)",
                    trace_id,
                    model_id,
                    prompt_tokens,
                    completion_tokens,
                )

                return {
                    "model": model_id,
                    "content": content,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "status": "ok",
                    "raw_json": data,
                    "trace_id": trace_id,
                    "call_id": call_id,
                    "elapsed": elapsed,
                    "timeout_seconds": self.timeout_seconds,
                    "request_payload": payload,
                    "request_headers": _sanitize_headers(headers),
                    "response_headers": dict(response.headers),
                }
            except httpx.TimeoutException:
                elapsed = time.perf_counter() - start
                log.warning(
                    "[%s] Call to %s timed out after %.2fs",
                    trace_id,
                    model_id,
                    self.timeout_seconds,
                )
                return {
                    "model": model_id,
                    "content": "",
                    "error": f"Timeout after {self.timeout_seconds}s",
                    "status": "timeout",
                    "trace_id": trace_id,
                    "call_id": call_id,
                    "elapsed": elapsed,
                    "timeout_seconds": self.timeout_seconds,
                    "request_payload": payload,
                    "request_headers": _sanitize_headers(headers),
                }
            except asyncio.CancelledError:
                elapsed = time.perf_counter() - start
                log.warning(
                    "[%s] Call to %s cancelled after %.2fs", trace_id, model_id, elapsed
                )
                raise
            except Exception as e:
                elapsed = time.perf_counter() - start
                error_body: str | None = None
                status: str | int = "?"
                if isinstance(e, httpx.HTTPStatusError):
                    error_body = e.response.text
                    status = e.response.status_code
                log.error(
                    "[%s] Failed to call model %s (status=%s, elapsed=%.2fs): %s",
                    trace_id,
                    model_id,
                    status,
                    elapsed,
                    e,
                )
                if error_body:
                    log.error("[%s] Error response body: %s", trace_id, error_body)
                log.debug("[%s] Exception detail", trace_id, exc_info=True)
                return {
                    "model": model_id,
                    "content": "",
                    "error": str(e),
                    "status": "error",
                    "trace_id": trace_id,
                    "call_id": call_id,
                    "elapsed": elapsed,
                    "timeout_seconds": self.timeout_seconds,
                    "request_payload": payload,
                    "request_headers": _sanitize_headers(headers),
                }
    
    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()


def get_top_models(models: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """Get top N models sorted by context length and performance.
    
    Prioritizes models with good balance of:
    - High context length
    - Reasonable pricing
    - Popular providers (OpenAI, Anthropic, Google, Meta, etc.)
    """
    scored_models = []
    
    for model in models:
        model_id = model.get("id", "")
        context_length = model.get("context_length", 0)
        prompt_price = model.get("prompt_price", 999.0)
        completion_price = model.get("completion_price", 999.0)
        
        if context_length < 4000:
            continue
        
        if prompt_price == 0 or completion_price == 0:
            continue
        
        score = 0.0
        
        if "gpt" in model_id.lower():
            score += 100
        elif "claude" in model_id.lower():
            score += 95
        elif "gemini" in model_id.lower():
            score += 90
        elif "llama" in model_id.lower():
            score += 85
        elif "mistral" in model_id.lower():
            score += 80
        
        score += min(context_length / 1000, 50)
        
        avg_price = (prompt_price + completion_price) / 2
        if avg_price < 0.001:
            score += 30
        elif avg_price < 0.01:
            score += 20
        elif avg_price < 0.1:
            score += 10
        
        model["_score"] = score
        scored_models.append(model)
    
    scored_models.sort(key=lambda m: m["_score"], reverse=True)
    return scored_models[:limit]


def calculate_estimated_cost(
    models: list[dict[str, Any]],
    prompt_tokens: int,
    max_completion_tokens: int,
) -> float:
    """Calculate estimated cost for calling multiple models."""
    total_cost = 0.0
    
    for model in models:
        prompt_price = model.get("prompt_price", 0)
        completion_price = model.get("completion_price", 0)
        
        prompt_cost = (prompt_tokens / 1_000_000) * prompt_price
        completion_cost = (max_completion_tokens / 1_000_000) * completion_price
        
        total_cost += prompt_cost + completion_cost
    
    return total_cost
