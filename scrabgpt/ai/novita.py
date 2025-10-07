"""Novita integration for multi-model AI gameplay.

Allows concurrent calls to multiple AI models via Novita API.
API is OpenAI-compatible with additional reasoning_content field.
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

log = logging.getLogger("scrabgpt.ai.novita")


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


class NovitaClient:
    """Client for Novita API with support for multiple reasoning models."""
    
    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout_seconds: int | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("NOVITA_API_KEY", "")
        env_timeout = os.getenv("NOVITA_TIMEOUT_SECONDS")
        try:
            env_timeout_value = int(env_timeout) if env_timeout is not None else None
        except ValueError:
            env_timeout_value = None
        resolved_timeout = timeout_seconds or env_timeout_value or 120
        self.timeout_seconds = max(5, resolved_timeout)
        self.base_url = "https://api.novita.ai/openai"
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
        """Bind TRACE_ID to include Novita call id for downstream logs."""

        current = TRACE_ID_VAR.get()
        combined = call_id if current in {"", "-"} else f"{current}|{call_id}"
        token = TRACE_ID_VAR.set(combined)
        try:
            yield combined
        finally:
            TRACE_ID_VAR.reset(token)
    
    async def fetch_models(self) -> list[dict[str, Any]]:
        """Fetch available models from Novita API.
        
        Returns:
            List of model dicts with id, name, context_length, category, etc.
        """
        call_id = self._next_call_id("models")
        headers = {"Authorization": f"Bearer {self.api_key}"}

        with self._trace_scope(call_id) as trace_id:
            log.info("[%s] Fetching Novita models", trace_id)
            log.debug("[%s] GET %s/v1/models headers=%s", trace_id, self.base_url, _sanitize_headers(headers))

            start = time.perf_counter()

            try:
                response = await self.client.get(
                    f"{self.base_url}/v1/models",
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                
                # Novita returns OpenAI-compatible format: {"object": "list", "data": [...]}
                models_list: list[dict[str, Any]] = data.get("data", [])

                # Process each model
                processed_models = []
                for model in models_list:
                    model_id = model.get("id", "")
                    
                    # Categorize by prefix
                    category = "other"
                    if model_id.startswith("deepseek/"):
                        category = "deepseek"
                    elif model_id.startswith("qwen/"):
                        category = "qwen"
                    elif model_id.startswith("zai-org/glm") or model_id.startswith("thudm/glm"):
                        category = "glm"
                    elif model_id.startswith("meta-llama/"):
                        category = "llama"
                    
                    # Extract context length (max_model_len or context_window)
                    context_length = model.get("max_model_len") or model.get("context_window", 0)
                    
                    processed_models.append({
                        "id": model_id,
                        "name": model_id.split("/")[-1].replace("-", " ").title(),  # Extract readable name
                        "context_length": context_length,
                        "category": category,
                        "owned_by": model.get("owned_by", ""),
                        "created": model.get("created", 0),
                    })

                elapsed = time.perf_counter() - start
                log.info(
                    "[%s] Retrieved %d Novita models in %.2fs (HTTP %s)",
                    trace_id,
                    len(processed_models),
                    elapsed,
                    response.status_code,
                )
                log.debug("[%s] Models response: %s", trace_id, _format_json(data))

                return processed_models
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
                status: str | int = "?"
                if isinstance(e, httpx.HTTPStatusError):
                    response_data = e.response.text
                    status = e.response.status_code
                log.error(
                    "[%s] Failed to fetch Novita models (status=%s, elapsed=%.2fs): %s",
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
        max_tokens: int = 4096,
        *,
        temperature: float = 0.6,
        top_p: float = 0.95,
    ) -> dict[str, Any]:
        """Call a specific model via Novita API.
        
        Args:
            model_id: Model identifier (e.g., "deepseek/deepseek-r1")
            prompt: User prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.5-0.7 recommended for reasoning)
            top_p: Nucleus sampling parameter (0.95 recommended)
        
        Returns:
            Dict with model response including content and reasoning_content
        """
        call_id = self._next_call_id("call")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }

        with self._trace_scope(call_id) as trace_id:
            log.info(
                "[%s] Calling Novita model %s (max_tokens=%d, prompt_chars=%d, temp=%.2f)",
                trace_id,
                model_id,
                max_tokens,
                len(prompt),
                temperature,
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
                    "[%s] Novita model %s responded HTTP %s in %.2fs",
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
                        "reasoning_content": "",
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
                reasoning_content = message.get("reasoning_content", "")

                # Some models may return reasoning in content field instead
                if not content and reasoning_content:
                    log.info(
                        "[%s] Model %s returned only reasoning_content, using as content",
                        trace_id,
                        model_id,
                    )
                    content = reasoning_content
                    reasoning_content = ""

                if not content and not reasoning_content:
                    log.warning(
                        "[%s] Model %s returned empty content. Response: %s",
                        trace_id,
                        model_id,
                        data,
                    )
                    return {
                        "model": model_id,
                        "content": "",
                        "reasoning_content": "",
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

                log.info("[%s] Model %s content:\n%s", trace_id, model_id, content)
                if reasoning_content:
                    log.info(
                        "[%s] Model %s reasoning:\n%s",
                        trace_id,
                        model_id,
                        reasoning_content[:500],
                    )
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
                    "reasoning_content": reasoning_content,
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
                    "reasoning_content": "",
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
                    "[%s] Failed to call Novita model %s (status=%s, elapsed=%.2fs): %s",
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
                    "reasoning_content": "",
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
