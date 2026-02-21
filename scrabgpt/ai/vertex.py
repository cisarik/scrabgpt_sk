"""Vertex AI integration for Scrabble AI.

Wraps google-genai library to provide an interface compatible with OpenRouterClient.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import inspect
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from itertools import count
from typing import Any, Callable, Iterator

from google.genai import types

from ..logging_setup import TRACE_ID_VAR
from .vertex_genai_client import (
    build_client,
    is_gemini_3_preview_model,
    vertex_error_hint,
)

log = logging.getLogger("scrabgpt.ai.vertex")


def _format_json(data: Any) -> str:
    """Safely format JSON payloads for debug logs."""
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:  # noqa: BLE001
        return repr(data)


class VertexClient:
    """Client for Google Vertex AI via google-genai library."""

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
        *,
        timeout_seconds: int | None = None,
        allow_model_fallback: bool = True,
    ) -> None:
        configured_model = (
            os.getenv("GEMINI_MODEL")
            or os.getenv("GOOGLE_GEMINI_MODEL")
            or "gemini-2.5-pro"
        )
        self.client, client_config = build_client(
            project_id=project_id,
            location=location,
            model=configured_model,
            verbose=True,
        )
        self.project_id = client_config.project_id
        self.location = client_config.location
        self.default_model = client_config.model

        env_timeout = (
            os.getenv("AI_MOVE_TIMEOUT_SECONDS")
            or os.getenv("VERTEX_TIMEOUT_SECONDS")
        )
        try:
            env_timeout_value = int(env_timeout) if env_timeout is not None else None
        except ValueError:
            env_timeout_value = None
        resolved_timeout = timeout_seconds or env_timeout_value or 120
        self.timeout_seconds = max(5, resolved_timeout)
        self.allow_model_fallback = allow_model_fallback
        
        self._call_counter = count(1)
        self.ai_move_max_output_tokens = self._resolve_ai_move_max_tokens()
        self._executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="vertex-ai",
        )
        self._executor_closed = False

    @staticmethod
    def _parse_positive_int(value: Any) -> int | None:
        """Return a positive integer parsed from value or None."""
        if value is None:
            return None
        try:
            tokens = int(str(value))
        except (TypeError, ValueError):
            return None
        return tokens if tokens > 0 else None

    def _resolve_ai_move_max_tokens(self) -> int:
        """Resolve the per-move token cap from environment with sane defaults."""
        env_tokens = self._parse_positive_int(os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS"))
        if env_tokens is not None:
            return max(500, min(env_tokens, 20000))
        return 8192  # Higher default for Gemini 1.5/2.0

    @staticmethod
    def _is_model_unavailable_error(error_text: str) -> bool:
        lowered = error_text.lower()
        markers = (
            "404",
            "not_found",
            "not found",
            "publisher model",
            "does not have access",
            "invalid model version",
        )
        return any(marker in lowered for marker in markers)

    @classmethod
    def _fallback_model_for_error(cls, model_id: str, error_text: str) -> str | None:
        if not cls._is_model_unavailable_error(error_text):
            return None
        normalized = model_id.replace("google/", "").strip().lower()
        chain = {
            "gemini-3.1-pro-preview": "gemini-2.5-pro",
            "gemini-3-pro": "gemini-2.5-pro",
            "gemini-3-pro-preview": "gemini-2.5-pro",
            "gemini-3-flash-preview": "gemini-2.5-flash",
            "gemini-3-pro-image-preview": "gemini-2.5-pro",
            "gemini-2.5-pro": "gemini-2.5-flash",
        }
        return chain.get(normalized)

    def _ensure_client_location_for_model(self, model_id: str) -> None:
        """Rebuild client on global endpoint when Gemini 3.x preview is requested."""
        if not is_gemini_3_preview_model(model_id):
            return
        if self.location == "global":
            return

        previous_location = self.location
        self.client, client_config = build_client(
            project_id=self.project_id,
            location="global",
            model=model_id,
            verbose=True,
        )
        self.location = client_config.location
        log.warning(
            "Switched Vertex client location %s -> %s for model %s",
            previous_location,
            self.location,
            model_id,
        )

    @staticmethod
    def _is_resource_exhausted_error(error_text: str) -> bool:
        lowered = str(error_text or "").lower()
        markers = (
            "429",
            "resource_exhausted",
            "too many requests",
            "rate limit",
            "quota",
        )
        return any(marker in lowered for marker in markers)
    
    def _next_call_id(self, kind: str) -> str:
        """Return a unique identifier for logging scopes."""
        return f"{kind}-{next(self._call_counter)}"

    @contextmanager
    def _trace_scope(self, call_id: str) -> Iterator[str]:
        """Bind TRACE_ID to include call id for downstream logs."""
        current = TRACE_ID_VAR.get()
        combined = call_id if current in {"", "-"} else f"{current}|{call_id}"
        token = TRACE_ID_VAR.set(combined)
        try:
            yield combined
        finally:
            TRACE_ID_VAR.reset(token)
    
    async def call_model(
        self, 
        model_id: str, 
        prompt: str = "", 
        *, 
        messages: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        thinking_mode: bool = False,
        tools: list[Any] | None = None,
        tool_config: Any | None = None,
        tool_context: dict[str, Any] | None = None,
        progress_callback: Callable[[dict[str, Any]], Any] | None = None,
        _fallback_depth: int = 0,
    ) -> dict[str, Any]:
        """
        Call the Vertex AI model.
        
        Args:
            model_id: The model ID to use.
            prompt: The system prompt or initial user message.
            messages: A list of messages in the format [{"role": "user/model", "content": "..."}].
            max_tokens: Max output tokens.
            thinking_mode: Whether to enable thinking/reasoning mode.
            tools: List of tools to provide to the model.
            tool_config: Tool configuration.
            progress_callback: Optional callback for progress updates (e.g. tool use).
            
        Returns:
            A dictionary with the response, compatible with OpenRouter response format.
        """
        call_id = self._next_call_id("vertex")

        # Ensure model_id is valid for Vertex
        # If it contains "google/", strip it as Vertex client uses bare IDs or full paths
        if model_id.startswith("google/"):
            model_id = model_id.replace("google/", "")

        self._ensure_client_location_for_model(model_id)
            
        resolved_max_tokens = (
            max_tokens
            if isinstance(max_tokens, int) and max_tokens > 0
            else self.ai_move_max_output_tokens
        )
        
        # Cap at 20000 (consistent with OpenRouter) but allow user env var to drive it up to that point
        if resolved_max_tokens > 20000:
            log.warning("Capping max_tokens from %d to 20000 for safety", resolved_max_tokens)
            resolved_max_tokens = 20000
        
        with self._trace_scope(call_id) as trace_id:
            tool_count = 0
            if tools:
                # Vertex tools are wrappers; count actual function declarations
                for t in tools:
                    declarations = getattr(t, "function_declarations", None)
                    if isinstance(declarations, list):
                        tool_count += len(declarations)
                        continue
                    tool_count += 1

            log.info(
                "[%s] Calling Vertex model %s (max_tokens=%d, thinking=%s, tools=%d)",
                trace_id,
                model_id,
                resolved_max_tokens,
                thinking_mode,
                tool_count
            )
            
            start = time.perf_counter()
            
            try:
                # Construct contents
                contents: list[Any] = []
                
                # If messages are provided, convert them
                if messages:
                    for msg in messages:
                        role = "user" if msg["role"] == "user" else "model"
                        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
                
                # If prompt is provided and no messages, treat it as user message
                if prompt and not messages:
                    contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
                    
                config_args: dict[str, Any] = {
                    "max_output_tokens": resolved_max_tokens,
                    "temperature": 0.7,
                }
                    
                if thinking_mode:
                    config_args["thinking_config"] = types.ThinkingConfig(include_thoughts=True)
                    
                config: Any = types.GenerateContentConfig(**config_args)
                
                if tools:
                    config.tools = tools
                if tool_config:
                    config.tool_config = tool_config
                
                request_kwargs: dict[str, Any] = {
                    "model": model_id,
                    "contents": contents,
                    "config": config
                }
                
                if prompt and messages:
                    # Construct system prompt from prompt string
                    # Note: If messages are provided, prompt is treated as system instruction by our convention
                    # in multi_model.py/openrouter.py logic.
                    
                    # Pass system instruction in config
                    config.system_instruction = [types.Part(text=prompt)]
                    
                    # IMPORTANT: Ensure system_instruction is NOT in kwargs, as it was removed
                    # from GenerateContentConfig but generate_content signature might not accept it directly
                    if "system_instruction" in request_kwargs:
                        del request_kwargs["system_instruction"]
                
                # --- Tool Execution Loop ---
                from .tool_adapter import execute_tool
                tool_calls_executed: list[str] = []
                
                while True:
                    # Run blocking call via dedicated executor.
                    # Avoid asyncio default executor lifecycle issues in nested worker threads.
                    if self._executor_closed:
                        raise RuntimeError("Vertex client executor is closed")
                    loop = asyncio.get_running_loop()
                    max_retry_attempts = 4
                    response: Any = None
                    for attempt in range(1, max_retry_attempts + 1):
                        try:
                            response = await loop.run_in_executor(
                                self._executor,
                                partial(self.client.models.generate_content, **request_kwargs),
                            )
                            break
                        except Exception as retry_exc:
                            if (
                                attempt >= max_retry_attempts
                                or not self._is_resource_exhausted_error(str(retry_exc))
                            ):
                                raise

                            backoff_seconds = min(
                                12.0,
                                (2 ** (attempt - 1)) + random.uniform(0.0, 0.9),
                            )
                            log.warning(
                                "[%s] Vertex model %s throttled (attempt %d/%d): %s. Backoff %.2fs",
                                trace_id,
                                model_id,
                                attempt,
                                max_retry_attempts,
                                retry_exc,
                                backoff_seconds,
                            )
                            if progress_callback:
                                try:
                                    retry_payload = {
                                        "status": "retry",
                                        "model": model_id,
                                        "model_name": model_id,
                                        "error": (
                                            "429 RESOURCE_EXHAUSTED. "
                                            f"Retry {attempt}/{max_retry_attempts}"
                                        ),
                                        "attempt": attempt,
                                        "max_attempts": max_retry_attempts,
                                    }
                                    maybe_retry = progress_callback(retry_payload)
                                    if inspect.isawaitable(maybe_retry):
                                        await maybe_retry
                                except Exception:
                                    log.warning(
                                        "Progress callback failed for retry notification",
                                        exc_info=True,
                                    )
                            await asyncio.sleep(backoff_seconds)
                    if response is None:
                        raise RuntimeError("Vertex response missing after retries")
                    
                    # Check for tool calls
                    tool_calls: list[tuple[str, dict[str, Any]]] = []
                    candidate_content: Any = None
                    candidates = getattr(response, "candidates", None)
                    if isinstance(candidates, list) and candidates:
                        candidate = candidates[0]
                        candidate_content = getattr(candidate, "content", None)
                        parts = getattr(candidate_content, "parts", None)
                        if isinstance(parts, list):
                            for part in parts:
                                function_call = getattr(part, "function_call", None)
                                if function_call is None:
                                    continue
                                tool_name_raw = getattr(function_call, "name", None)
                                if not isinstance(tool_name_raw, str) or not tool_name_raw:
                                    continue

                                raw_args = getattr(function_call, "args", None)
                                args_dict: dict[str, Any] = {}
                                if isinstance(raw_args, dict):
                                    args_dict = dict(raw_args)
                                elif raw_args is not None and hasattr(raw_args, "items"):
                                    try:
                                        args_dict = dict(raw_args.items())
                                    except Exception:
                                        args_dict = {"raw": str(raw_args)}
                                tool_calls.append((tool_name_raw, args_dict))
                    
                    if not tool_calls:
                        # No tool calls, we are done
                        break
                        
                    # Execute tools
                    log.info("[%s] Model requested %d tool calls", trace_id, len(tool_calls))
                    
                    # Notify progress
                    if progress_callback:
                        try:
                            # Extract args for display
                            tool_calls_data = []
                            tool_names = [tool_name for tool_name, _ in tool_calls]
                            for tool_name, args_dict in tool_calls:
                                tool_calls_data.append({"name": tool_name, "args": args_dict})

                            res = progress_callback({
                                "status": "tool_use",
                                "model": model_id,
                                "tool_calls": tool_names,
                                "tool_calls_data": tool_calls_data,
                                "message": f"🛠️ Volám nástroje: {', '.join(tool_names)}"
                            })
                            if inspect.isawaitable(res):
                                await res
                        except Exception:  # noqa: BLE001
                            log.warning("Progress callback failed in tool loop", exc_info=True)
                    
                    # Append model's response (with tool calls) to history
                    if candidate_content is not None:
                        contents.append(candidate_content)
                    
                    # Execute each tool and append result
                    tool_outputs: list[Any] = []
                    for tool_name, tool_args in tool_calls:
                        log.info("[%s] Executing tool: %s", trace_id, tool_name)
                        result = execute_tool(tool_name, tool_args, context=tool_context)
                        tool_calls_executed.append(tool_name)
                        
                        # Report result via progress callback
                        if progress_callback:
                            try:
                                res = progress_callback({
                                    "status": "tool_result",
                                    "model": model_id,
                                    "tool_name": tool_name,
                                    "tool_args": tool_args,
                                    "result": result,
                                    "message": f"✅ Výsledok {tool_name}"
                                })
                                if inspect.isawaitable(res):
                                    await res
                            except Exception:
                                log.warning("Progress callback failed for tool result", exc_info=True)
                        
                        tool_outputs.append(
                            types.Part.from_function_response(
                                name=tool_name,
                                response=result
                            )
                        )
                    
                    # Append tool outputs as a single 'user' message (or 'function' role if supported)
                    # For Gemini 2.0, we send back a Content with role='tool' containing the function responses
                    contents.append(types.Content(role="tool", parts=tool_outputs))
                    
                    # Loop continues to send tool outputs back to model
                
                # --- End Loop ---
                
                elapsed = time.perf_counter() - start
                
                text_content = ""
                if response.text:
                    text_content = response.text
                
                usage = getattr(response, "usage_metadata", None)
                prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
                completion_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) if usage else 0
                
                log.info(
                    "[%s] Vertex model %s responded in %.2fs (tokens: %d/%d)",
                    trace_id,
                    model_id,
                    elapsed,
                    prompt_tokens,
                    completion_tokens
                )
                
                return {
                    "model": model_id,
                    "content": text_content,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "status": "ok",
                    "tool_calls_executed": tool_calls_executed,
                    "trace_id": trace_id,
                    "call_id": call_id,
                    "elapsed": elapsed,
                    "timeout_seconds": self.timeout_seconds,
                }
                
            except Exception as e:
                fallback_model = None
                if self.allow_model_fallback and _fallback_depth < 2:
                    fallback_model = self._fallback_model_for_error(model_id, str(e))
                if fallback_model and fallback_model != model_id:
                    log.warning(
                        "[%s] Model %s unavailable (%s). Retrying with fallback %s",
                        trace_id,
                        model_id,
                        e,
                        fallback_model,
                    )
                    fallback_result = await self.call_model(
                        fallback_model,
                        prompt,
                        messages=messages,
                        max_tokens=resolved_max_tokens,
                        thinking_mode=thinking_mode,
                        tools=tools,
                        tool_config=tool_config,
                        tool_context=tool_context,
                        progress_callback=progress_callback,
                        _fallback_depth=_fallback_depth + 1,
                    )
                    if fallback_result.get("status") == "ok":
                        fallback_result["fallback_from"] = model_id
                    return fallback_result

                elapsed = time.perf_counter() - start
                log.error(
                    "[%s] Failed to call Vertex model %s (elapsed=%.2fs): %s",
                    trace_id,
                    model_id,
                    elapsed,
                    e,
                )
                log.debug("[%s] Exception detail", trace_id, exc_info=True)
                hint = vertex_error_hint(
                    str(e),
                    model_id=model_id,
                    location=self.location,
                )
                if hint:
                    log.error("[%s] Vertex troubleshooting hint: %s", trace_id, hint)
                error_message = str(e) if not hint else f"{e} | Hint: {hint}"
                return {
                    "model": model_id,
                    "content": "",
                    "error": error_message,
                    "status": "error",
                    "tool_calls_executed": [],
                    "trace_id": trace_id,
                    "call_id": call_id,
                    "elapsed": elapsed,
                    "timeout_seconds": self.timeout_seconds,
                }
    
    async def close(self) -> None:
        """Release resources tied to the client executor."""
        if self._executor_closed:
            return
        self._executor_closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
