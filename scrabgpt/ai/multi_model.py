"""Multi-model AI player that calls multiple models concurrently."""

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
from ..core.rules import (
    extract_all_words,
    placements_in_line,
    no_gaps_in_line,
    first_move_must_cover_center,
    connected_to_existing,
)
from ..core.scoring import score_words
from .openrouter import OpenRouterClient
from .schema import parse_ai_move, to_move_payload
from .player import _build_prompt
from .client import OpenAIClient
from .parsing_fallbacks import compute_parser_attempts, gpt_fallback_parse

log = logging.getLogger("scrabgpt.ai.multi_model")


async def propose_move_multi_model(
    client: OpenRouterClient,
    models: list[dict[str, Any]],
    compact_state: str,
    variant: VariantDefinition,
    board: Board,
    judge_client: OpenAIClient,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    timeout_seconds: int = 60,
    thinking_mode: bool = False,
    tools: list[Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Call multiple models concurrently and return best move + all results.
    
    Validates each move with the judge before selecting the winner.
    Each model is called exactly once - no retries or fallbacks.
    """
    prompt = _build_prompt(compact_state, variant)
    
    if tools:
        prompt += "\n\nIMPORTANT: You have access to tools. You MUST use 'get_board_state' to verify the board if needed, OR proceed directly to generating a move. DO NOT ask for permission. DO NOT output conversational text. Output ONLY the JSON move or use a tool. NEVER PASS - always find a valid move."
    
    async def call_one_model(model_info: dict[str, Any]) -> dict[str, Any]:
        model_id = model_info["id"]
        # Use provided timeout or default, but ensure we have a deadline
        deadline = asyncio.get_event_loop().time() + (timeout_seconds or 60)
        
        # History for retries
        conversation_history: list[dict[str, Any]] = []

        log.info("Calling model: %s (deadline in %ds)", model_id, timeout_seconds)

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

        while True:
            remaining_time = deadline - asyncio.get_event_loop().time()
            if remaining_time <= 0:
                log.warning("Model %s timeout before call", model_id)
                break

            # Prepare kwargs
            kwargs = {}
            sig = inspect.signature(client.call_model)
            if "thinking_mode" in sig.parameters:
                kwargs["thinking_mode"] = thinking_mode
            if "tools" in sig.parameters:
                kwargs["tools"] = tools
            if "messages" in sig.parameters and conversation_history:
                kwargs["messages"] = conversation_history
            if "progress_callback" in sig.parameters:
                kwargs["progress_callback"] = _notify

            # Call model
            try:
                # Always pass the prompt (system instruction).
                # Clients must handle whether to use it as system msg or prepend to messages.
                result = await asyncio.wait_for(
                    client.call_model(
                        model_id, 
                        prompt, 
                        max_tokens=model_info.get("max_tokens") or client.ai_move_max_output_tokens, 
                        **kwargs
                    ), 
                    timeout=remaining_time
                )
            except asyncio.TimeoutError:
                log.warning("Model %s timed out", model_id)
                return await _notify({
                    "model": model_id,
                    "model_name": model_info.get("name", model_id),
                    "status": "timeout",
                    "error": "Timeout during generation",
                    "move": None,
                    "score": -1,
                    "words": [],
                })
            except Exception as e:
                log.exception("Model %s call failed", model_id)
                return await _notify({
                    "model": model_id,
                    "model_name": model_info.get("name", model_id),
                    "status": "error",
                    "error": str(e),
                    "move": None,
                    "score": -1,
                    "words": [],
                })

            # Process result
            raw_content = result.get("content", "")
            
            # 1. Parse
            parse_error = None
            move = None
            try:
                if not raw_content or not raw_content.strip():
                    raise ValueError("Empty response")
                
                model_obj, parse_method = parse_ai_move(raw_content)
                move = to_move_payload(model_obj)
                
                # Basic structural validation
                if "placements" not in move:
                    move["placements"] = []
                
                # Validate placements structure
                placements: list[Placement] = []
                for p in move.get("placements", []):
                    placements.append(Placement(
                        row=int(p["row"]),
                        col=int(p["col"]),
                        letter=str(p["letter"]),
                        blank_as=p.get("blank_as")
                    ))
                
                # Extract rack from compact_state
                import re
                rack_match = re.search(r"(?:ai_)?rack:\s*(?:\[(.*?)\]|(.*))", compact_state)
                if rack_match:
                    rack_str = rack_match.group(1) or rack_match.group(2) or ""
                    # Rack letters - comma separated or just string?
                    # Usually "A, B, C" or "ABC"
                    if "," in rack_str:
                        rack_letters = [x.strip() for x in rack_str.split(",") if x.strip()]
                    else:
                        # Handle JSON style "['A', 'B']" if present (regex might catch quotes)
                        cleaned = rack_str.replace("'", "").replace('"', "")
                        if "," in cleaned:
                            rack_letters = [x.strip() for x in cleaned.split(",") if x.strip()]
                        else:
                            rack_letters = list(cleaned.strip())
                    
                    # Validate letter usage
                    rack_copy = list(rack_letters)
                    
                    # Check against board (for redundant placements)
                    # We need to ignore placements that are already on board (redundant)
                    # But multi_model doesn't have easy access to board cells directly here 
                    # (it has 'board' object but we need to check specific cells)
                    
                    final_placements = []
                    for p in placements:
                        # Check if cell occupied
                        existing = board.cells[p.row][p.col].letter
                        if existing:
                            if existing == p.letter:
                                # Redundant, ignore
                                continue
                            else:
                                raise ValueError(f"Attempt to overwrite existing '{existing}' at ({p.row},{p.col}) with '{p.letter}'")
                        final_placements.append(p)
                    
                    # Now validate against rack
                    for p in final_placements:
                        # Handle blanks (if p.letter is not in rack but '?' is)
                        # If AI proposes 'A' but has '?', we use '?'
                        # But if AI explicitly sends '?', we use '?'
                        
                        # Logic:
                        # 1. If letter in rack, use it.
                        # 2. If not, check for '?'.
                        # 3. If neither, error.
                        
                        # Note: UI app.py logic:
                        # if p.letter == "?" or consume_as_blank: ...
                        # Here we simplify:
                        
                        if p.letter in rack_copy:
                            rack_copy.remove(p.letter)
                        elif "?" in rack_copy:
                            rack_copy.remove("?")
                        else:
                            raise ValueError(f"Used letter '{p.letter}' which is not in rack {rack_letters}")
                    
                    # If we survived, update placements to final_placements (stripped of redundant)
                    # We must update the 'placements' variable as it is used below for board operations
                    placements = final_placements
                    
                    # If stripped placements are empty, but AI sent a word, something is wrong (unless exchange/pass)
                    if not placements and not move.get("pass") and not move.get("exchange"):
                        # AI sent redundant placements for existing word but no new letters?
                        # This is effectively a pass or invalid move.
                        # But wait, maybe AI thought it's placing new letters but they were already there?
                        # If so, it's invalid because you must place at least one tile.
                        raise ValueError("No new tiles placed (all placements were redundant/occupied). You must place at least one new tile from your rack.")

                # Geometry Validation (Gaps, Line, Center, Connection)
                if placements: # skip for pass/exchange
                    # 1. Line check
                    direction = placements_in_line(placements)
                    if direction is None:
                        raise ValueError("Placements are not in a single line (ACROSS or DOWN).")
                    
                    # 2. Gaps check
                    if not no_gaps_in_line(board, placements, direction):
                        raise ValueError("Placements contain gaps (empty cells between letters). Move must be contiguous.")
                    
                    # 3. Center / Connection check
                    # Check if board has any letters
                    has_any = any(board.cells[r][c].letter for r in range(15) for c in range(15))
                    
                    if not has_any:
                        if not first_move_must_cover_center(placements):
                            raise ValueError("First move must cover the center star (7,7).")
                    else:
                        if not connected_to_existing(board, placements):
                            raise ValueError("Move must connect to existing words on the board.")

                # Check board validity (geometry)
                board_snapshot = deepcopy(board)
                board_snapshot.place_letters(placements)
                words_found = extract_all_words(board_snapshot, placements)
                words = [w.word for w in words_found]
                
            except Exception as e:
                parse_error = str(e)
                log.warning("Parse/Board error for %s: %s", model_id, e)

            # 2. Judge Validation (if parsed successfully)
            judge_valid = False
            judge_reason = ""
            if not parse_error and move:
                if not words:
                    # No words formed? Might be exchange or pass.
                    if move.get("pass") or move.get("exchange"):
                        judge_valid = True # Pass/Exchange is valid game move
                    else:
                        judge_reason = "No words formed by placements."
                else:
                    # Validate words
                    try:
                        judge_response = await asyncio.to_thread(
                            judge_client.judge_words, words, language=variant.language
                        )
                        judge_valid = judge_response.get("all_valid", False)
                        if not judge_valid:
                            reasons = [r.get("reason", "") for r in judge_response.get("results", [])]
                            judge_reason = "; ".join(reasons)
                    except Exception as je:
                        judge_reason = f"Judge error: {je}"

            # 3. Decision: Return or Retry
            if not parse_error and judge_valid:
                # Success!
                # Calculate score
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
                    "words": words,
                    "judge_valid": True,
                    "raw_response": raw_content,
                    "score_breakdown": breakdowns,
                })
            
            # Failure - Prepare retry
            remaining_time = deadline - asyncio.get_event_loop().time()
            if remaining_time < 5: # Give up if less than 5s
                log.warning("Not enough time to retry %s", model_id)
                break
            
            # Construct feedback
            feedback = ""
            if parse_error:
                feedback = f"Your response was invalid JSON or structurally incorrect: {parse_error}. Please correct it."
            elif not judge_valid:
                feedback = f"Your move '{move.get('word', '?')}' is invalid according to the rules/dictionary: {judge_reason}. Try again with a valid word."
            
            log.info("Retrying %s due to: %s", model_id, feedback)
            
            # Update history
            if not conversation_history:
                # First retry: add the initial assistant response
                conversation_history.append({"role": "assistant", "content": raw_content})
            else:
                # Subsequent retries: append assistant response
                conversation_history.append({"role": "assistant", "content": raw_content})
            
            # Append user feedback
            conversation_history.append({"role": "user", "content": feedback})
            
            # Notify UI about retry
            await _notify({
                "status": "retry",
                "model": model_id,
                "error": feedback,
                "remaining": int(remaining_time)
            })

        # Loop finished (timeout or give up) -> Return last error result
        return await _notify({
            "model": model_id,
            "model_name": model_info.get("name", model_id),
            "status": "error",
            "error": "Failed to find valid move after retries",
            "move": None,
            "score": -1,
            "words": [],
        })

    tasks = [call_one_model(model) for model in models]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Flatten results
    all_results = []
    for r in results:
        if isinstance(r, dict):
            all_results.append(r)
        else:
            # Exception
            all_results.append({"status": "exception", "error": str(r)})

    valid_results = [r for r in all_results if r.get("status") == "ok"]
    
    if not valid_results:
         return (
            {
                "pass": True,
                "exchange": [],
                "placements": [],
                "word": "",
                "reason": "No models returned valid moves",
            },
            all_results,
        )

    valid_results.sort(key=lambda r: int(r.get("score", -1)), reverse=True)
    best_result = valid_results[0]
    
    return best_result["move"], all_results
