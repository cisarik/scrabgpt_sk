"""Vertex AI integration for Scrabble AI.

Wraps google-genai library to provide an interface compatible with OpenRouterClient.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import inspect
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from itertools import count
from typing import Any, Callable, Iterator

from google import genai
from google.genai import types

from ..logging_setup import TRACE_ID_VAR

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
    ) -> None:
        # Load credentials and project_id from file if present
        creds_path = os.path.abspath("vertexaccount.json")
        loaded_project_id = None
        
        if os.path.exists(creds_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
            try:
                with open(creds_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    loaded_project_id = data.get("project_id")
            except Exception as e:
                log.warning("Failed to parse project_id from %s: %s", creds_path, e)

        self.project_id = project_id or loaded_project_id or "vertexaccount"
        # Prefer argument, then env var, then default
        self.location = location or os.getenv("VERTEX_LOCATION") or "us-central1"
            
        self.client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location
        )
        
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
            "gemini-3-pro": "gemini-2.5-pro",
            "gemini-3-pro-preview": "gemini-2.5-pro",
            "gemini-2.5-pro": "gemini-2.5-flash",
        }
        return chain.get(normalized)
    
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
        tools: list[types.Tool] | None = None,
        tool_config: types.ToolConfig | None = None,
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
                    if hasattr(t, "function_declarations"):
                        tool_count += len(t.function_declarations)
                    else:
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
                contents = []
                
                # If messages are provided, convert them
                if messages:
                    for msg in messages:
                        role = "user" if msg["role"] == "user" else "model"
                        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
                
                # If prompt is provided and no messages, treat it as user message
                if prompt and not messages:
                    contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
                    
                config_args = {
                    "max_output_tokens": resolved_max_tokens,
                    "temperature": 0.7,
                }
                    
                if thinking_mode:
                    config_args["thinking_config"] = types.ThinkingConfig(include_thoughts=True)
                    
                config = types.GenerateContentConfig(**config_args)
                
                if tools:
                    config.tools = tools
                if tool_config:
                    config.tool_config = tool_config
                
                kwargs = {
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
                    if "system_instruction" in kwargs:
                        del kwargs["system_instruction"]
                
                # --- Tool Execution Loop ---
                from .tool_adapter import execute_tool
                
                while True:
                    # Run blocking call via dedicated executor.
                    # Avoid asyncio default executor lifecycle issues in nested worker threads.
                    if self._executor_closed:
                        raise RuntimeError("Vertex client executor is closed")
                    loop = asyncio.get_running_loop()
                    response = await loop.run_in_executor(
                        self._executor,
                        partial(self.client.models.generate_content, **kwargs),
                    )
                    
                    # Check for tool calls
                    tool_calls = []
                    if response.candidates and response.candidates[0].content.parts:
                        for part in response.candidates[0].content.parts:
                            if part.function_call:
                                tool_calls.append(part.function_call)
                    
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
                            for tc in tool_calls:
                                args_dict = {}
                                if tc.args:
                                    # Convert MapComposite to dict
                                    try:
                                        # Depending on SDK version, it might be dict or MapComposite
                                        if hasattr(tc.args, "items"):
                                            args_dict = dict(tc.args.items())
                                        else:
                                            args_dict = dict(tc.args)
                                    except Exception:
                                        args_dict = {"raw": str(tc.args)}
                                tool_calls_data.append({"name": tc.name, "args": args_dict})

                            res = progress_callback({
                                "status": "tool_use",
                                "model": model_id,
                                "tool_calls": [tc.name for tc in tool_calls],
                                "tool_calls_data": tool_calls_data,
                                "message": f"🛠️ Volám nástroje: {', '.join(tc.name for tc in tool_calls)}"
                            })
                            if inspect.isawaitable(res):
                                await res
                        except Exception:  # noqa: BLE001
                            log.warning("Progress callback failed in tool loop", exc_info=True)
                    
                    # Append model's response (with tool calls) to history
                    kwargs["contents"].append(response.candidates[0].content)
                    
                    # Execute each tool and append result
                    tool_outputs = []
                    for tc in tool_calls:
                        log.info("[%s] Executing tool: %s", trace_id, tc.name)
                        result = execute_tool(tc.name, tc.args)
                        
                        # Report result via progress callback
                        if progress_callback:
                            try:
                                res = progress_callback({
                                    "status": "tool_result",
                                    "model": model_id,
                                    "tool_name": tc.name,
                                    "result": result,
                                    "message": f"✅ Výsledok {tc.name}"
                                })
                                if inspect.isawaitable(res):
                                    await res
                            except Exception:
                                log.warning("Progress callback failed for tool result", exc_info=True)
                        
                        tool_outputs.append(
                            types.Part.from_function_response(
                                name=tc.name,
                                response=result
                            )
                        )
                    
                    # Append tool outputs as a single 'user' message (or 'function' role if supported)
                    # For Gemini 2.0, we send back a Content with role='tool' containing the function responses
                    kwargs["contents"].append(types.Content(role="tool", parts=tool_outputs))
                    
                    # Loop continues to send tool outputs back to model
                
                # --- End Loop ---
                
                elapsed = time.perf_counter() - start
                
                text_content = ""
                if response.text:
                    text_content = response.text
                
                usage = response.usage_metadata
                prompt_tokens = usage.prompt_token_count if usage else 0
                completion_tokens = usage.candidates_token_count if usage else 0
                
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
                    "trace_id": trace_id,
                    "call_id": call_id,
                    "elapsed": elapsed,
                    "timeout_seconds": self.timeout_seconds,
                }
                
            except Exception as e:
                fallback_model = None
                if _fallback_depth < 2:
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
                return {
                    "model": model_id,
                    "content": "",
                    "error": str(e),
                    "status": "error",
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
