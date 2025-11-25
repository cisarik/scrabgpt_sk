"""Multi-model AI player using Novita reasoning models."""

from __future__ import annotations

import asyncio
import inspect
import logging
from copy import deepcopy
from dataclasses import asdict
from typing import Any, Callable, Optional

from ..core.variant_store import VariantDefinition
from ..core.board import Board
from ..core.types import Placement
from ..core.rules import extract_all_words
from ..core.scoring import score_words
from .novita import NovitaClient
from .schema import parse_ai_move, to_move_payload
from .player import _build_prompt
from .client import OpenAIClient
from .parsing_fallbacks import compute_parser_attempts, gpt_fallback_parse

log = logging.getLogger("scrabgpt.ai.novita_multi_model")


async def propose_move_novita_multi_model(
    client: NovitaClient,
    models: list[dict[str, Any]],
    compact_state: str,
    variant: VariantDefinition,
    board: Board,
    judge_client: OpenAIClient,
    progress_callback: Optional[Callable[[dict[str, Any]], Any]] = None,
    *,
    timeout_seconds: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Call multiple Novita models concurrently and return best move + all results.
    
    Validates each move with the judge before selecting the winner.
    Each model is called exactly once - no retries or fallbacks.
    
    Args:
        client: Novita client for API calls
        models: List of model configs with id, name, max_tokens
        compact_state: Game state string for AI prompt
        variant: Variant definition
        board: Current board state (for word extraction)
        judge_client: OpenAI client for judge validation
        progress_callback: Optional callable invoked after each model completes.
    
    Returns:
        (best_move, all_results) where:
        - best_move: The move dict with highest score (and valid by judge)
        - all_results: List of dicts with model, move, score, judge validation, error info
    """
    prompt = _build_prompt(compact_state, variant)
    
    async def call_one_model(model_info: dict[str, Any]) -> dict[str, Any]:
        model_id = model_info["id"]
        max_tokens = model_info.get("max_tokens") or client.ai_move_max_output_tokens

        log.info("Calling Novita model: %s", model_id)

        async def invoke_model() -> dict[str, Any]:
            return await client.call_model(model_id, prompt, max_tokens=max_tokens)

        async def _notify(payload: dict[str, Any]) -> dict[str, Any]:
            if progress_callback is None:
                return payload
            try:
                maybe = progress_callback(payload)
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception:  # noqa: BLE001
                log.exception("Progress callback failed for model %s", model_id)
            return payload

        try:
            if timeout_seconds is None or timeout_seconds <= 0:
                result = await invoke_model()
            else:
                result = await asyncio.wait_for(invoke_model(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            log.warning(
                "Model %s exceeded execution timeout of %ss", model_id, timeout_seconds
            )
            return await _notify({
                "model": model_id,
                "model_name": model_info.get("name", model_id),
                "status": "timeout",
                "error": f"Timed out after {timeout_seconds}s",
                "move": None,
                "score": -1,
                "words": [],
                "novita": {
                    "call_id": None,
                    "trace_id": None,
                    "elapsed": timeout_seconds,
                    "timeout_seconds": timeout_seconds,
                    "request_payload": None,
                    "request_headers": None,
                    "response_headers": None,
                    "raw_json": None,
                },
            })

        def build_novita_meta(resp: dict[str, Any]) -> dict[str, Any]:
            return {
                "call_id": resp.get("call_id"),
                "trace_id": resp.get("trace_id"),
                "elapsed": resp.get("elapsed"),
                "timeout_seconds": resp.get("timeout_seconds"),
                "request_payload": resp.get("request_payload"),
                "request_headers": resp.get("request_headers"),
                "response_headers": resp.get("response_headers"),
                "raw_json": resp.get("raw_json"),
                "reasoning_content": resp.get("reasoning_content", ""),
            }

        novita_meta = build_novita_meta(result)
        elapsed_value = novita_meta.get("elapsed")
        elapsed_display = (
            f"{elapsed_value:.2f}s" if isinstance(elapsed_value, (int, float)) else "?"
        )
        log.info(
            "Novita finished for %s status=%s call_id=%s trace=%s elapsed=%s",
            model_id,
            result.get("status"),
            novita_meta.get("call_id", "-"),
            novita_meta.get("trace_id", "-"),
            elapsed_display,
        )
        if result.get("error"):
            log.warning(
                "Model %s reported error from Novita: %s", model_id, result.get("error")
            )

        if result["status"] == "error":
            return await _notify({
                "model": model_id,
                "model_name": model_info.get("name", model_id),
                "status": "error",
                "error": result.get("error", "Unknown error"),
                "move": None,
                "score": -1,
                "words": [],
                "novita": novita_meta,
            })
        if result["status"] == "timeout":
            return await _notify({
                "model": model_id,
                "model_name": model_info.get("name", model_id),
                "status": "timeout",
                "error": result.get("error", "Timeout"),
                "move": None,
                "score": -1,
                "words": [],
                "novita": novita_meta,
            })
        
        try:
            raw_content = result["content"]
            
            # Check for empty or whitespace-only response
            if not raw_content:
                log.warning("Model %s returned None/empty content", model_id)
                return await _notify({
                    "model": model_id,
                    "model_name": model_info.get("name", model_id),
                    "status": "parse_error",
                    "error": "Empty response from model",
                    "move": None,
                    "score": -1,
                    "words": [],
                    "novita": novita_meta,
                })
            
            stripped = raw_content.strip()
            if not stripped:
                log.warning(
                    "Model %s returned whitespace-only content: %r", model_id, raw_content[:100]
                )
                return await _notify({
                    "model": model_id,
                    "model_name": model_info.get("name", model_id),
                    "status": "parse_error",
                    "error": "Empty response from model (whitespace only)",
                    "move": None,
                    "score": -1,
                    "words": [],
                    "novita": novita_meta,
                })
            
            # Log first 200 chars for debugging
            log.debug("Response from %s: %s...", model_id, stripped[:200])
            
            gpt_analysis = ""
            gpt_raw_response = ""
            try:
                model_obj, parse_method = parse_ai_move(stripped)
                move = to_move_payload(model_obj)
                parser_attempts = compute_parser_attempts(parse_method)
            except Exception as parse_err:
                log.warning(
                    "Primary parse failed for %s (%s) – trying GPT fallback",
                    model_id,
                    parse_err,
                )
                fallback_move, fallback_meta = await gpt_fallback_parse(
                    raw_content,
                    judge_client,
                )
                if fallback_move is None:
                    fallback_error = fallback_meta.get("error", "GPT fallback neuspel.")
                    log.warning(
                        "GPT fallback failed for %s: %s",
                        model_id,
                        fallback_error,
                    )
                    raise ValueError(f"GPT fallback failed: {fallback_error}") from parse_err
                move = fallback_move
                parse_method = fallback_meta.get("parse_method", "gpt_fallback")
                parser_attempts = fallback_meta.get(
                    "parser_attempts",
                    compute_parser_attempts(parse_method),
                )
                gpt_analysis = fallback_meta.get("analysis", "")
                gpt_raw_response = fallback_meta.get("raw_gpt_response", "")
                log.info("✓ GPT fallback extrahoval ťah pre %s", model_id)
            
            # Log which parsing method was used
            if parse_method == "markdown_extraction":
                log.info("✓ Model %s: JSON extrahovaný z markdown bloku", model_id)
            elif parse_method == "inline_json":
                log.info("✓ Model %s: JSON extrahovaný z textu (inline fallback)", model_id)
            elif parse_method == "gpt_fallback":
                log.info("✓ Model %s: ťah rekonštruovaný cez GPT fallback", model_id)
            
            if "exchange" not in move:
                move["exchange"] = []

            placements: list[Placement] = []
            try:
                for p in move.get("placements", []):
                    placements.append(
                        Placement(
                            row=int(p["row"]),
                            col=int(p["col"]),
                            letter=str(p["letter"]),
                            blank_as=p.get("blank_as"),
                        )
                    )
            except Exception as build_err:
                log.exception("Failed to build placements for %s: %s", model_id, build_err)
                return await _notify({
                    "model": model_id,
                    "model_name": model_info.get("name", model_id),
                    "status": "parse_error",
                    "error": f"Invalid placements format: {build_err}",
                    "move": None,
                    "score": -1,
                    "novita": novita_meta,
                })

            board_snapshot = deepcopy(board)
            board_snapshot.place_letters(placements)
            words_found = extract_all_words(board_snapshot, placements)
            words = [w.word for w in words_found]

            if words:
                words_coords = [(wf.word, wf.letters) for wf in words_found]
                score, raw_breakdowns = score_words(board_snapshot, placements, words_coords)
                breakdowns = [asdict(bd) for bd in raw_breakdowns]
            else:
                score = 0
                breakdowns = []

            return await _notify({
                "model": model_id,
                "model_name": model_info.get("name", model_id),
                "status": "ok",
                "move": move,
                "score": score,
                "raw_response": raw_content,
                "parse_method": parse_method,
                "parser_attempts": parser_attempts,
                "gpt_analysis": gpt_analysis,
                "gpt_raw_response": gpt_raw_response,
                "prompt_tokens": result.get("prompt_tokens", 0),
                "completion_tokens": result.get("completion_tokens", 0),
                "words": words,
                "score_breakdown": breakdowns,
                "novita": novita_meta,
            })
        
        except Exception as e:
            # Include first 200 chars of content in error for debugging
            content_preview = result.get("content", "")
            if content_preview:
                preview_text = repr(content_preview[:200])
                log.error(
                    "Failed to parse move from %s: %s. Content (repr): %s",
                    model_id,
                    e,
                    preview_text,
                )
            else:
                log.error("Failed to parse move from %s: %s. Content: EMPTY", model_id, e)
            
            raw_response = result.get("content", "")
            
            error_message = str(e)[:100]
            error_analysis = f"Failed to parse JSON: {e.__class__.__name__}: {error_message}"
            if "GPT fallback failed" in str(e):
                error_analysis += "\n\nFallback: GPT analýza nedokázala rekonštruovať ťah."
            if raw_response:
                if "```" in raw_response and "json" not in raw_response.lower():
                    error_analysis += "\n\nTip: Model used code blocks without 'json' marker"
                elif not raw_response.strip().startswith("{"):
                    error_analysis += "\n\nTip: Response doesn't start with JSON object"
                elif "placements" not in raw_response:
                    error_analysis += "\n\nTip: Missing 'placements' field in response"
            
            return await _notify({
                "model": model_id,
                "model_name": model_info.get("name", model_id),
                "status": "parse_error",
                "error": f"{e.__class__.__name__}: {str(e)[:50]}",
                "error_analysis": error_analysis,
                "raw_response": raw_response,
                "move": None,
                "score": -1,
                "novita": novita_meta,
            })
    
    tasks = [call_one_model(model) for model in models]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    all_results: list[dict[str, Any]] = []
    for r in results:
        if isinstance(r, BaseException):
            log.exception("Task failed with exception: %s", r)
            failure_payload = {
                "status": "exception",
                "error": str(r),
                "score": -1,
                "model": "unknown",
                "model_name": "Unknown",
                "words": [],
            }
            all_results.append(failure_payload)
            if progress_callback is not None:
                try:
                    maybe = progress_callback(failure_payload)
                    if inspect.isawaitable(maybe):
                        await maybe
                except Exception:  # noqa: BLE001
                    log.exception("Progress callback failed for exception payload")
        elif isinstance(r, dict):
            all_results.append(r)

    # Validate moves with judge (in parallel to avoid blocking)
    valid_results = [r for r in all_results if r.get("status") == "ok" and r.get("move")]
    
    if not valid_results:
        failure_summaries: list[str] = []
        for payload in all_results:
            if not isinstance(payload, dict):
                continue
            label = str(
                payload.get("model_name")
                or payload.get("model")
                or "unknown"
            )
            error_text = payload.get("error")
            status_text = payload.get("status")
            if isinstance(error_text, str) and error_text:
                failure_summaries.append(f"{label}: {error_text}")
            elif isinstance(status_text, str) and status_text and status_text != "ok":
                failure_summaries.append(f"{label}: {status_text}")

        summary = "; ".join(failure_summaries[:3])
        if len(failure_summaries) > 3:
            summary += f"; +{len(failure_summaries) - 3} more errors"

        reason = summary or "No valid move returned by any model"
        log.warning("No models returned valid moves; forcing pass. Reason=%s", reason)
        fallback_move: dict[str, Any] = {
            "pass": True,
            "placements": [],
            "blanks": {},
            "word": "",
            "exchange": [],
            "reason": reason,
        }
        return fallback_move, all_results
    
    # Extract words for all valid results first
    for result in valid_results:
        if result.get("words"):
            continue
        move = result["move"]
        try:
            placements: list[Placement] = []
            for p in move.get("placements", []):
                placements.append(
                    Placement(
                        row=p["row"],
                        col=p["col"],
                        letter=p["letter"],
                        blank_as=p.get("blank_as"),
                    )
                )

            if placements:
                board_snapshot = deepcopy(board)
                board_snapshot.place_letters(placements)
                words_found = extract_all_words(board_snapshot, placements)
                result["words"] = [w.word for w in words_found]
            else:
                result["words"] = []
        except Exception as e:
            log.exception("Failed to extract words from %s: %s", result["model_name"], e)
            result["words"] = []
    
    # Validate all moves with judge in parallel
    async def validate_one(result: dict[str, Any]) -> None:
        """Validate a single result with judge."""
        words = result.get("words", [])
        model_name = result.get("model_name", "Unknown")
        
        if not words:
            result["judge_valid"] = False
            result["status"] = "invalid"
            result["judge_reason"] = "No words formed"
            return
        
        try:
            log.info("Judge validating %s from %s...", words, model_name)
            judge_response = await asyncio.to_thread(
                judge_client.judge_words,
                words,
                language=variant.language,
            )
            
            all_valid = judge_response.get("all_valid", False)
            result["judge_valid"] = all_valid
            
            reasons = [r.get("reason", "") for r in judge_response.get("results", [])]
            result["judge_reason"] = "; ".join(reasons) if reasons else ""
            
            if not all_valid:
                result["status"] = "invalid"
                log.warning(
                    "Model %s proposed invalid words: %s (reason: %s)",
                    model_name,
                    words,
                    result["judge_reason"],
                )
            else:
                log.info("Model %s words %s validated successfully", model_name, words)
        except Exception as e:
            log.exception("Failed to validate move from %s: %s", model_name, e)
            result["judge_valid"] = False
            result["status"] = "invalid"
            result["judge_reason"] = f"Validation error: {e}"
    
    # Run all validations in parallel
    log.info("Validating %d moves with judge (in parallel)...", len(valid_results))
    start_time = asyncio.get_event_loop().time()
    await asyncio.gather(*[validate_one(r) for r in valid_results])
    elapsed = asyncio.get_event_loop().time() - start_time
    log.info("Judge validation completed in %.2f seconds", elapsed)
    
    # Select best valid move (by judge)
    judge_valid_results = [r for r in valid_results if r.get("judge_valid", False)]
    
    if not judge_valid_results:
        log.warning("No models returned judge-valid moves, using highest-scoring parsed move")
        valid_results.sort(key=lambda r: int(r.get("score", -1)), reverse=True)
        best_result = valid_results[0]
    else:
        judge_valid_results.sort(key=lambda r: int(r.get("score", -1)), reverse=True)
        best_result = judge_valid_results[0]
    
    best_move = best_result["move"]
    
    log.info(
        "Best move from %s with score %d (judge_valid=%s, out of %d total results)",
        best_result["model_name"],
        best_result["score"],
        best_result.get("judge_valid", False),
        len(all_results),
    )
    
    return best_move, all_results
