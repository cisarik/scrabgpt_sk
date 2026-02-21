"""OpenAI chat-completions client with iterative local tool execution."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import time
from contextlib import contextmanager
from itertools import count
from typing import Any, Callable, Iterator

from openai import APITimeoutError, BadRequestError, OpenAI

from ..logging_setup import TRACE_ID_VAR
from .tool_adapter import execute_tool, get_openai_tools

log = logging.getLogger("scrabgpt.ai.openai_tools")


class OpenAIToolClient:
    """Async-friendly OpenAI client that supports function/tool calling loops."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        resolved_api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("LLMSTUDIO_BASE_URL")
        env_timeout = os.getenv("AI_MOVE_TIMEOUT_SECONDS") or os.getenv("OPENAI_TIMEOUT_SECONDS")
        try:
            env_timeout_value = int(env_timeout) if env_timeout is not None else None
        except ValueError:
            env_timeout_value = None
        resolved_timeout = timeout_seconds or env_timeout_value or 120
        self.timeout_seconds = max(5, resolved_timeout)

        client_kwargs: dict[str, Any] = {}
        if resolved_base_url:
            client_kwargs["base_url"] = resolved_base_url.rstrip("/")
            log.info("OpenAI tool client base_url override: %s", client_kwargs["base_url"])

        self.client = OpenAI(
            api_key=resolved_api_key if resolved_api_key else None,
            timeout=self.timeout_seconds,
            max_retries=0,
            **client_kwargs,
        )
        self.ai_move_max_output_tokens = self._resolve_ai_move_max_tokens()
        self._call_counter = count(1)

    @staticmethod
    def _parse_positive_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _resolve_ai_move_max_tokens(self) -> int:
        env_tokens = self._parse_positive_int(os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS"))
        if env_tokens is not None:
            return max(500, min(env_tokens, 20000))
        return 3600

    def _next_call_id(self, kind: str) -> str:
        return f"{kind}-{next(self._call_counter)}"

    @contextmanager
    def _trace_scope(self, call_id: str) -> Iterator[str]:
        current = TRACE_ID_VAR.get()
        combined = call_id if current in {"", "-"} else f"{current}|{call_id}"
        token = TRACE_ID_VAR.set(combined)
        try:
            yield combined
        finally:
            TRACE_ID_VAR.reset(token)

    @staticmethod
    def _tool_unsupported(error_text: str) -> bool:
        lowered = str(error_text or "").lower()
        markers = (
            "tool",
            "function",
            "unsupported",
            "not supported",
            "unknown parameter",
            "invalid parameter",
        )
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _parse_tool_arguments(arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return dict(arguments)
        if isinstance(arguments, str):
            text = arguments.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
                return {"value": parsed}
            except json.JSONDecodeError:
                return {"raw": text}
        return {}

    @staticmethod
    def _message_content(message: Any) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                else:
                    text = getattr(item, "text", None)
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return str(content or "")

    async def _emit_progress(
        self,
        callback: Callable[[dict[str, Any]], Any] | None,
        payload: dict[str, Any],
    ) -> None:
        if callback is None:
            return
        try:
            maybe = callback(payload)
            if inspect.isawaitable(maybe):
                await maybe
        except RuntimeError as cb_err:
            if "Signal source has been deleted" in str(cb_err):
                log.debug("Progress callback ignored: %s", cb_err)
            else:
                log.warning("Progress callback runtime error: %s", cb_err, exc_info=True)
        except Exception:
            log.warning("Progress callback failed", exc_info=True)

    def _build_initial_messages(
        self,
        prompt: str,
        messages: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if messages:
            conversation = list(messages)
            if prompt:
                conversation.insert(0, {"role": "system", "content": prompt})
            return conversation
        return [{"role": "user", "content": prompt}]

    def _create_chat_completion(
        self,
        *,
        model_id: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        tools: list[dict[str, Any]] | None,
        request_timeout_seconds: float | None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
        }
        if request_timeout_seconds is not None:
            kwargs["timeout"] = max(1.0, float(request_timeout_seconds))
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        try:
            return self.client.chat.completions.create(
                max_completion_tokens=max_tokens,
                **kwargs,
            )
        except APITimeoutError:
            raise
        except Exception:
            return self.client.chat.completions.create(
                max_tokens=max_tokens,
                **kwargs,
            )

    async def call_model(
        self,
        model_id: str,
        prompt: str = "",
        *,
        messages: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        thinking_mode: bool = False,
        tools: list[Any] | None = None,
        tool_context: dict[str, Any] | None = None,
        progress_callback: Callable[[dict[str, Any]], Any] | None = None,
        request_timeout_seconds: int | None = None,
        round_timeout_seconds: int | None = None,
        min_word_validations: int = 0,
        min_scored_candidates: int = 0,
    ) -> dict[str, Any]:
        del thinking_mode  # Reserved for parity with provider interface.

        call_id = self._next_call_id("openai")
        resolved_max_tokens = (
            max_tokens
            if isinstance(max_tokens, int) and max_tokens > 0
            else self.ai_move_max_output_tokens
        )
        resolved_max_tokens = min(20000, max(500, resolved_max_tokens))
        openai_tools: list[dict[str, Any]] | None = None
        if tools:
            openai_tools = [dict(tool) for tool in tools if isinstance(tool, dict)]
        if openai_tools is None and tools is None:
            openai_tools = get_openai_tools()

        with self._trace_scope(call_id) as trace_id:
            log.info(
                "[%s] Calling OpenAI model %s (max_tokens=%d, tools=%d)",
                trace_id,
                model_id,
                resolved_max_tokens,
                len(openai_tools or []),
            )
            start = time.perf_counter()
            conversation = self._build_initial_messages(prompt, messages)
            tool_calls_executed: list[str] = []
            tools_disabled = False
            max_rounds = 24
            round_index = 0
            active_tools = openai_tools
            session_timeout = max(
                5,
                int(request_timeout_seconds if request_timeout_seconds is not None else self.timeout_seconds),
            )
            round_timeout = max(
                5,
                int(round_timeout_seconds if round_timeout_seconds is not None else min(25, self.timeout_seconds)),
            )
            session_deadline = time.monotonic() + session_timeout
            consecutive_timeouts = 0
            validated_word_calls = 0
            scored_candidates: set[str] = set()
            best_content_so_far: str | None = None

            while round_index < max_rounds:
                round_index += 1
                remaining_session = session_deadline - time.monotonic()
                if remaining_session <= 0:
                    break
                request_timeout = min(float(round_timeout), max(2.0, remaining_session))
                try:
                    response = await asyncio.to_thread(
                        self._create_chat_completion,
                        model_id=model_id,
                        messages=conversation,
                        max_tokens=resolved_max_tokens,
                        tools=active_tools,
                        request_timeout_seconds=request_timeout,
                    )
                    consecutive_timeouts = 0
                except APITimeoutError:
                    consecutive_timeouts += 1
                    remaining_after_timeout = session_deadline - time.monotonic()
                    if remaining_after_timeout > 6 and consecutive_timeouts < 4:
                        await self._emit_progress(
                            progress_callback,
                            {
                                "status": "retry",
                                "model": model_id,
                                "model_name": model_id,
                                "error": (
                                    f"OpenAI round timeout ({int(request_timeout)}s). "
                                    "Pokračujem v ďalšom kole hľadania."
                                ),
                                "attempt": round_index,
                                "max_attempts": max_rounds,
                                "remaining": int(max(0, remaining_after_timeout)),
                            },
                        )
                        conversation.append(
                            {
                                "role": "user",
                                "content": (
                                    "Continue searching for better scoring legal moves. "
                                    "Use tools again and avoid repeating already invalid ideas."
                                ),
                            }
                        )
                        continue
                    elapsed = time.perf_counter() - start
                    if best_content_so_far:
                        return {
                            "model": model_id,
                            "content": best_content_so_far,
                            "status": "ok",
                            "tool_calls_executed": tool_calls_executed,
                            "tools_unsupported": tools_disabled,
                            "trace_id": trace_id,
                            "call_id": call_id,
                            "elapsed": elapsed,
                            "timeout_seconds": self.timeout_seconds,
                        }
                    return {
                        "model": model_id,
                        "content": "",
                        "error": "Timeout during OpenAI tool workflow",
                        "status": "timeout",
                        "tool_calls_executed": tool_calls_executed,
                        "tools_unsupported": tools_disabled,
                        "trace_id": trace_id,
                        "call_id": call_id,
                        "elapsed": elapsed,
                        "timeout_seconds": self.timeout_seconds,
                    }
                except BadRequestError as exc:
                    if active_tools and self._tool_unsupported(str(exc)):
                        tools_disabled = True
                        active_tools = None
                        log.warning(
                            "[%s] Model %s rejected tools, retrying without tools: %s",
                            trace_id,
                            model_id,
                            exc,
                        )
                        await self._emit_progress(
                            progress_callback,
                            {
                                "status": "retry",
                                "model": model_id,
                                "model_name": model_id,
                                "error": "Model/provider nepodporuje tool calls, retry bez tools.",
                                "attempt": round_index,
                                "max_attempts": max_rounds,
                            },
                        )
                        continue
                    elapsed = time.perf_counter() - start
                    return {
                        "model": model_id,
                        "content": "",
                        "error": str(exc),
                        "status": "error",
                        "tool_calls_executed": tool_calls_executed,
                        "tools_unsupported": tools_disabled,
                        "trace_id": trace_id,
                        "call_id": call_id,
                        "elapsed": elapsed,
                        "timeout_seconds": self.timeout_seconds,
                    }
                except Exception as exc:  # noqa: BLE001
                    elapsed = time.perf_counter() - start
                    return {
                        "model": model_id,
                        "content": "",
                        "error": str(exc),
                        "status": "error",
                        "tool_calls_executed": tool_calls_executed,
                        "tools_unsupported": tools_disabled,
                        "trace_id": trace_id,
                        "call_id": call_id,
                        "elapsed": elapsed,
                        "timeout_seconds": self.timeout_seconds,
                    }

                try:
                    choice = response.choices[0]
                    message = choice.message
                except Exception as exc:  # noqa: BLE001
                    elapsed = time.perf_counter() - start
                    return {
                        "model": model_id,
                        "content": "",
                        "error": f"Invalid OpenAI response structure: {exc}",
                        "status": "error",
                        "tool_calls_executed": tool_calls_executed,
                        "tools_unsupported": tools_disabled,
                        "trace_id": trace_id,
                        "call_id": call_id,
                        "elapsed": elapsed,
                        "timeout_seconds": self.timeout_seconds,
                    }

                raw_tool_calls = list(getattr(message, "tool_calls", []) or [])
                if raw_tool_calls:
                    tool_calls_data: list[dict[str, Any]] = []
                    assistant_tool_calls: list[dict[str, Any]] = []
                    for tool_call in raw_tool_calls:
                        function = getattr(tool_call, "function", None)
                        if function is None:
                            continue
                        tool_name = str(getattr(function, "name", "") or "").strip()
                        if not tool_name:
                            continue
                        args = self._parse_tool_arguments(getattr(function, "arguments", None))
                        tool_calls_data.append({"name": tool_name, "args": args})
                        assistant_tool_calls.append(
                            {
                                "id": str(getattr(tool_call, "id", "") or f"call_{len(assistant_tool_calls)}"),
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": getattr(function, "arguments", "{}") or "{}",
                                },
                            }
                        )

                    if assistant_tool_calls:
                        await self._emit_progress(
                            progress_callback,
                            {
                                "status": "tool_use",
                                "model": model_id,
                                "tool_calls": [item["name"] for item in tool_calls_data],
                                "tool_calls_data": tool_calls_data,
                                "message": "🛠️ OpenAI volá nástroje",
                            },
                        )
                        conversation.append(
                            {
                                "role": "assistant",
                                "content": self._message_content(message),
                                "tool_calls": assistant_tool_calls,
                            }
                        )

                        for idx, call_info in enumerate(assistant_tool_calls):
                            tool_name = call_info["function"]["name"]
                            args = tool_calls_data[idx]["args"] if idx < len(tool_calls_data) else {}
                            result = execute_tool(tool_name, args, context=tool_context)
                            tool_calls_executed.append(tool_name)
                            if tool_name in {"validate_word_slovak", "validate_word_english"}:
                                validated_word_calls += 1
                            elif tool_name in {"calculate_move_score", "scoring_score_words"}:
                                total_score_raw = result.get("total_score") if isinstance(result, dict) else None
                                words_payload = result.get("words") if isinstance(result, dict) else None
                                if not isinstance(words_payload, list):
                                    words_payload = args.get("words")
                                words: list[str] = []
                                if isinstance(words_payload, list):
                                    for item in words_payload:
                                        if isinstance(item, str):
                                            word = item.strip().upper()
                                            if word:
                                                words.append(word)
                                        elif isinstance(item, dict):
                                            word = str(item.get("word") or "").strip().upper()
                                            if word:
                                                words.append(word)
                                try:
                                    total_score = int(total_score_raw)
                                except (TypeError, ValueError):
                                    total_score = -1
                                if words and total_score >= 0:
                                    placement_bits: list[str] = []
                                    placements_payload = args.get("placements")
                                    if isinstance(placements_payload, list):
                                        for placement in placements_payload:
                                            if not isinstance(placement, dict):
                                                continue
                                            row = placement.get("row")
                                            col = placement.get("col")
                                            letter = str(placement.get("letter") or "").strip().upper()
                                            if not isinstance(row, int) or not isinstance(col, int):
                                                continue
                                            if not letter:
                                                continue
                                            placement_bits.append(f"{row}:{col}:{letter}")
                                    words_part = "|".join(sorted(set(words)))
                                    placements_part = ";".join(sorted(placement_bits))
                                    signature = (
                                        f"{words_part}#{placements_part}"
                                        if placements_part
                                        else words_part
                                    )
                                    scored_candidates.add(signature)
                            await self._emit_progress(
                                progress_callback,
                                {
                                    "status": "tool_result",
                                    "model": model_id,
                                    "tool_name": tool_name,
                                    "tool_args": args,
                                    "result": result,
                                    "message": f"✅ Výsledok {tool_name}",
                                },
                            )
                            conversation.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call_info["id"],
                                    "name": tool_name,
                                    "content": json.dumps(result, ensure_ascii=False),
                                }
                            )
                        continue

                content = self._message_content(message).strip()
                if not content:
                    elapsed = time.perf_counter() - start
                    return {
                        "model": model_id,
                        "content": "",
                        "error": "Model returned empty response",
                        "status": "error",
                        "tool_calls_executed": tool_calls_executed,
                        "tools_unsupported": tools_disabled,
                        "trace_id": trace_id,
                        "call_id": call_id,
                        "elapsed": elapsed,
                        "timeout_seconds": self.timeout_seconds,
                    }

                if min_word_validations > 0 or min_scored_candidates > 0:
                    best_content_so_far = content
                    remaining_after_content = session_deadline - time.monotonic()
                    needs_more_validations = validated_word_calls < min_word_validations
                    needs_more_scored = (
                        min_scored_candidates > 0
                        and len(scored_candidates) < min_scored_candidates
                    )
                    if (
                        (needs_more_validations or needs_more_scored)
                        and remaining_after_content > (round_timeout + 5)
                    ):
                        pending_reasons: list[str] = []
                        if needs_more_validations:
                            pending_reasons.append(
                                f"overených {validated_word_calls}/{min_word_validations} slov"
                            )
                        if needs_more_scored:
                            pending_reasons.append(
                                f"ohodnotených {len(scored_candidates)}/{min_scored_candidates} kandidátov"
                            )
                        await self._emit_progress(
                            progress_callback,
                            {
                                "status": "retry",
                                "model": model_id,
                                "model_name": model_id,
                                "error": (
                                    "Pokračujem v hľadaní: "
                                    + ", ".join(pending_reasons)
                                    + "."
                                ),
                                "attempt": round_index,
                                "max_attempts": max_rounds,
                                "remaining": int(max(0, remaining_after_content)),
                            },
                        )
                        conversation.append(
                            {
                                "role": "assistant",
                                "content": content,
                            }
                        )
                        conversation.append(
                            {
                                "role": "user",
                                "content": " ".join(
                                    part
                                    for part in (
                                        "Do not finalize yet. Evaluate more candidate words with tools.",
                                        (
                                            f"Validate at least {min_word_validations} words."
                                            if min_word_validations > 0
                                            else ""
                                        ),
                                        (
                                            f"Score at least {min_scored_candidates} distinct candidates."
                                            if min_scored_candidates > 0
                                            else ""
                                        ),
                                        "When time is short, return only the best move as JSON.",
                                    )
                                    if part
                                ),
                            }
                        )
                        continue

                usage = getattr(response, "usage", None)
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
                elapsed = time.perf_counter() - start
                return {
                    "model": model_id,
                    "content": content,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "status": "ok",
                    "tool_calls_executed": tool_calls_executed,
                    "tools_unsupported": tools_disabled,
                    "trace_id": trace_id,
                    "call_id": call_id,
                    "elapsed": elapsed,
                    "timeout_seconds": self.timeout_seconds,
                }

            elapsed = time.perf_counter() - start
            if best_content_so_far:
                return {
                    "model": model_id,
                    "content": best_content_so_far,
                    "status": "ok",
                    "tool_calls_executed": tool_calls_executed,
                    "tools_unsupported": tools_disabled,
                    "trace_id": trace_id,
                    "call_id": call_id,
                    "elapsed": elapsed,
                    "timeout_seconds": self.timeout_seconds,
                }
            return {
                "model": model_id,
                "content": "",
                "error": f"Tool loop exceeded {max_rounds} rounds",
                "status": "error",
                "tool_calls_executed": tool_calls_executed,
                "tools_unsupported": tools_disabled,
                "trace_id": trace_id,
                "call_id": call_id,
                "elapsed": elapsed,
                "timeout_seconds": self.timeout_seconds,
            }

    async def close(self) -> None:
        """Compatibility no-op (OpenAI sync client has no async close hook)."""
        return None
