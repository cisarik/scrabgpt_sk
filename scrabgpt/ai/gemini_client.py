from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

try:
    import google.generativeai as genai  # type: ignore
    from google.generativeai.types import FunctionDeclaration, Tool, GenerationConfig
except Exception:  # pragma: no cover - optional dependency
    genai = None  # type: ignore
    FunctionDeclaration = Tool = GenerationConfig = None  # type: ignore

log = logging.getLogger("scrabgpt.ai.gemini")


def _require_genai() -> None:
    if genai is None:
        raise RuntimeError("google-generativeai nie je nainštalované. Spusti: poetry install")


def _make_function_decls() -> list[FunctionDeclaration]:
    """Define MCP tool signatures for Gemini function calling."""
    return [
        FunctionDeclaration(
            name="validate_word_slovak",
            description="Validuje slovo v slovníku (slovenčina).",
            parameters={
                "type": "object",
                "properties": {"word": {"type": "string"}},
                "required": ["word"],
            },
        ),
        FunctionDeclaration(
            name="validate_move_legality",
            description="Kontroluje legalitu ťahu (riadok, prepojenie, medzery, stred).",
            parameters={
                "type": "object",
                "properties": {
                    "board_grid": {"type": "array", "items": {"type": "string"}},
                    "placements": {"type": "array", "items": {"type": "object"}},
                    "is_first_move": {"type": "boolean"},
                },
                "required": ["board_grid", "placements", "is_first_move"],
            },
        ),
        FunctionDeclaration(
            name="calculate_move_score",
            description="Počíta skóre ťahu vrátane prémií.",
            parameters={
                "type": "object",
                "properties": {
                    "board_grid": {"type": "array", "items": {"type": "string"}},
                    "premium_grid": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "placements": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["board_grid", "premium_grid", "placements"],
            },
        ),
        FunctionDeclaration(
            name="rules_extract_all_words",
            description="Extrahuje všetky slová vytvorené ťahom (hlavné + krížové).",
            parameters={
                "type": "object",
                "properties": {
                    "board_grid": {"type": "array", "items": {"type": "string"}},
                    "placements": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["board_grid", "placements"],
            },
        ),
    ]


class GeminiClient:
    """Thin wrapper for Google Gemini 3 Pro (thinking=high, streaming, tools)."""

    def __init__(self, *, api_key: str | None = None, timeout_seconds: int = 120) -> None:
        _require_genai()
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY nie je nastavené")
        self.timeout_seconds = timeout_seconds
        self.model = "gemini-3-pro-preview"
        genai.configure(api_key=self.api_key)
        self._tool_decls = _make_function_decls()
        log.info("Gemini client init (model=%s, timeout=%ss)", self.model, timeout_seconds)

    def _call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatch to local MCP tools."""
        from .mcp_tools import (
            tool_rules_first_move_must_cover_center,
            tool_rules_placements_in_line,
            tool_rules_connected_to_existing,
            tool_rules_no_gaps_in_line,
            tool_scoring_score_words,
            tool_rules_extract_all_words,
        )
        # Simplified mapping to exposed tools
        if name == "validate_word_slovak":
            from .mcp_tools import is_word_in_juls as _is_word
            word = str(args.get("word", "")).strip()
            valid = bool(word) and bool(_is_word(word))
            return {"valid": valid, "reason": "local+JULS" if valid else "not found"}
        if name == "validate_move_legality":
            # Basic combo of rule checks
            placements = args.get("placements", [])
            checks = {
                "first_move": tool_rules_first_move_must_cover_center(placements),
                "line": tool_rules_placements_in_line(placements),
                "connected": tool_rules_connected_to_existing(
                    args.get("board_grid", []), placements
                ),
                "gaps": tool_rules_no_gaps_in_line(placements),
            }
            valid = all(c.get("valid", False) for c in checks.values())
            return {"valid": valid, "checks": checks, "reason": "ok" if valid else "invalid"}
        if name == "calculate_move_score":
            return tool_scoring_score_words(
                args.get("board_grid", []),
                args.get("premium_grid", []),
                args.get("placements", []),
            )
        if name == "rules_extract_all_words":
            return tool_rules_extract_all_words(args.get("board_grid", []), args.get("placements", []))
        raise ValueError(f"Unknown tool: {name}")

    def _build_tool_choice(self) -> Tool:
        return Tool(function_declarations=self._tool_decls)

    def _to_content(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert our message dicts to Gemini Content list."""
        converted: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "tool":
                converted.append(
                    {
                        "role": "user",
                        "parts": [{"text": f"<tool_response>\n{content}\n</tool_response>"}],
                    }
                )
            else:
                converted.append({"role": role, "parts": [{"text": str(content)}]})
        return converted

    def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        stream_callback: Callable[[str], None] | None = None,
        reasoning_callback: Callable[[str], None] | None = None,
        debug_callback: Callable[[str], None] | None = None,
    ) -> tuple[str, dict[str, int]]:
        """Run Gemini with tool calling and stream."""
        contents = self._to_content(messages)
        model = genai.GenerativeModel(
            model_name=self.model,
            tools=[self._build_tool_choice()],
            generation_config=GenerationConfig(
                temperature=0.4,
                top_p=0.95,
                top_k=40,
            ),
        )

        if debug_callback:
            debug_callback(f"[Gemini REQUEST] messages={messages}")

        tool_responses: list[dict[str, Any]] = []
        final_text: str = ""
        usage = {"prompt_tokens": 0, "context_length": 0}

        try:
            # Single-pass stream
            stream = model.generate_content(contents, stream=True)
            for chunk in stream:
                if chunk.candidates and chunk.candidates[0].content:
                    parts = chunk.candidates[0].content.parts or []
                    for p in parts:
                        text = getattr(p, "text", "") or ""
                        if text:
                            if "<think>" in text and "</think>" in text:
                                start = text.find("<think>") + len("<think>")
                                end = text.find("</think>")
                                reasoning = text[start:end].strip()
                                if reasoning and reasoning_callback:
                                    reasoning_callback(reasoning)
                                remainder = text[end + len("</think>") :].lstrip()
                                if remainder and stream_callback:
                                    stream_callback(remainder)
                                final_text += remainder
                            else:
                                if stream_callback:
                                    stream_callback(text)
                                final_text += text
                        fc = getattr(p, "function_call", None)
                        if fc and fc.name:
                            if debug_callback:
                                debug_callback(
                                    f"[TOOL CALL {time.strftime('%H:%M:%S')}] {fc.name} args={fc.args}"
                                )
                            try:
                                args = fc.args if isinstance(fc.args, dict) else {}
                                result = self._call_tool(fc.name, args)
                                if debug_callback:
                                    debug_callback(
                                        f"[TOOL RESULT {time.strftime('%H:%M:%S')}] {fc.name} -> {result}"
                                    )
                                tool_responses.append(
                                    {
                                        "role": "tool",
                                        "parts": [
                                            {"text": f"<tool_response>\n{result}\n</tool_response>"}
                                        ],
                                    }
                                )
                            except Exception as exc:  # pragma: no cover - runtime
                                log.exception("Tool call failed: %s", exc)
                # After tool responses, continue
                if tool_responses:
                    # Extend conversation and continue generation (non-stream) to finalize
                    contents.extend(tool_responses)
                    tool_responses.clear()
                    follow = model.generate_content(contents, stream=True)
                    for follow_chunk in follow:
                        if follow_chunk.candidates and follow_chunk.candidates[0].content:
                            parts2 = follow_chunk.candidates[0].content.parts or []
                            for p2 in parts2:
                                text2 = getattr(p2, "text", "") or ""
                                if text2:
                                    if stream_callback:
                                        stream_callback(text2)
                                    final_text += text2
                                fc2 = getattr(p2, "function_call", None)
                                if fc2 and debug_callback:
                                    debug_callback(
                                        f"[TOOL CALL {time.strftime('%H:%M:%S')}] {fc2.name} args={fc2.args}"
                                    )
        except Exception as e:  # capture quota etc.
            if debug_callback:
                debug_callback(f"[Gemini ERROR] {e}")
            raise

        # Usage extraction (best-effort)
        try:
            stats = getattr(stream, "usage_metadata", None)
            if stats:
                usage["prompt_tokens"] = int(getattr(stats, "prompt_token_count", 0))
                usage["context_length"] = int(getattr(stats, "cached_content_token_count", 0) or 0)
        except Exception:
            pass

        if debug_callback:
            debug_callback(f"[Gemini RESPONSE] {final_text}")
            debug_callback(f"[Gemini USAGE] {usage}")

        return final_text, usage
