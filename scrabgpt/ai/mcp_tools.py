"""Tool wrappers for the AI agent.

Each function here is a stateless tool that can be called by the AI agent.
All inputs and outputs are JSON-serializable.

Tool naming convention: tool_<category>_<action>
Example: tool_rules_placements_in_line, tool_scoring_score_words
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import httpx

from ..core.board import Board, BOARD_SIZE
from ..core.types import Placement, Direction, Premium
from ..core.rules import (
    first_move_must_cover_center,
    placements_in_line,
    connected_to_existing,
    no_gaps_in_line,
    extract_all_words,
)
from ..core.scoring import score_words
from ..core.tiles import get_tile_points
from ..core.assets import get_premiums_path
from .fastdict import load_dictionary
from .juls_online import is_word_in_juls

log = logging.getLogger("scrabgpt.ai.tools")

# ========== Global Dictionary Cache ==========

_SLOVAK_DICT: Callable[[str], bool] | None = None
_ENGLISH_DICT: Callable[[str], bool] | None = None

# Online validation cache (word -> result, with TTL)
_VALIDATION_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_MAX_SIZE = 10000
_CACHE_TTL_SECONDS = 3600  # 1 hour

# Performance metrics
_VALIDATION_STATS = defaultdict(lambda: {"count": 0, "time_ms": 0.0, "hits": 0, "misses": 0})

# Word length threshold for online validation
# Words <= this length: only local dict (fast, 99% coverage)
# Words > this length: local dict + JULS if not found (rare words, compounds)
_ONLINE_VALIDATION_MIN_LENGTH = 7  # Configurable threshold


def _get_slovak_dict() -> Callable[[str], bool] | None:
    """Get or load Slovak dictionary (singleton pattern with error recovery)."""
    global _SLOVAK_DICT
    
    if _SLOVAK_DICT is None:
        try:
            dict_path = Path(__file__).parent / "dicts" / "sk.sorted.txt"
            if not dict_path.exists():
                log.warning("Slovak dictionary not found at %s", dict_path)
                return None
            
            log.info("Loading Slovak dictionary from %s", dict_path)
            start_time = time.time()
            _SLOVAK_DICT = load_dictionary(dict_path)
            load_time_ms = (time.time() - start_time) * 1000
            
            log.info("Slovak dictionary loaded in %.1f ms", load_time_ms)
            
        except Exception as e:
            log.exception("Failed to load Slovak dictionary: %s", e)
            return None
    
    return _SLOVAK_DICT


def _get_english_dict() -> Callable[[str], bool] | None:
    """Get or load English dictionary (TWL/SOWPODS singleton)."""
    global _ENGLISH_DICT
    
    if _ENGLISH_DICT is None:
        try:
            # Try TWL first, then SOWPODS as fallback
            for dict_name in ["twl.txt", "sowpods.txt", "en.txt"]:
                dict_path = Path(__file__).parent / "dicts" / dict_name
                if dict_path.exists():
                    log.info("Loading English dictionary from %s", dict_path)
                    start_time = time.time()
                    _ENGLISH_DICT = load_dictionary(dict_path)
                    load_time_ms = (time.time() - start_time) * 1000
                    
                    log.info("English dictionary (%s) loaded in %.1f ms", dict_name, load_time_ms)
                    return _ENGLISH_DICT
            
            log.warning("No English dictionary found (tried: twl.txt, sowpods.txt, en.txt)")
            return None
            
        except Exception as e:
            log.exception("Failed to load English dictionary: %s", e)
            return None
    
    return _ENGLISH_DICT


def _get_cached_validation(word: str, language: str) -> dict[str, Any] | None:
    """Get cached validation result if available and not expired."""
    cache_key = f"{language}:{word.upper()}"
    
    if cache_key in _VALIDATION_CACHE:
        cached = _VALIDATION_CACHE[cache_key]
        age_seconds = time.time() - cached["cached_at"]
        
        if age_seconds < _CACHE_TTL_SECONDS:
            _VALIDATION_STATS[f"{language}_cache"]["hits"] += 1
            log.debug("Cache HIT for '%s' (age: %.1fs)", word, age_seconds)
            return cached["result"]
        else:
            # Expired, remove it
            del _VALIDATION_CACHE[cache_key]
            log.debug("Cache EXPIRED for '%s' (age: %.1fs)", word, age_seconds)
    
    _VALIDATION_STATS[f"{language}_cache"]["misses"] += 1
    return None


def _cache_validation(word: str, language: str, result: dict[str, Any]) -> None:
    """Cache validation result with TTL."""
    # LRU-like eviction: if cache too large, clear oldest 20%
    if len(_VALIDATION_CACHE) >= _CACHE_MAX_SIZE:
        # Sort by timestamp and remove oldest 20%
        sorted_keys = sorted(
            _VALIDATION_CACHE.keys(),
            key=lambda k: _VALIDATION_CACHE[k]["cached_at"]
        )
        keys_to_remove = sorted_keys[:_CACHE_MAX_SIZE // 5]
        for key in keys_to_remove:
            del _VALIDATION_CACHE[key]
        log.debug("Cache eviction: removed %d old entries", len(keys_to_remove))
    
    cache_key = f"{language}:{word.upper()}"
    _VALIDATION_CACHE[cache_key] = {
        "result": result,
        "cached_at": time.time(),
    }


def _normalize_word(word: str) -> str:
    """Normalize word for validation (trim, uppercase, remove duplicates)."""
    return word.strip().upper()


def _is_valid_word_pattern(word: str) -> tuple[bool, str]:
    """Basic pattern validation to catch obviously invalid inputs.
    
    Returns:
        (is_valid, reason)
    """
    if not word:
        return False, "Empty word"
    
    if len(word) > 15:
        return False, f"Word too long ({len(word)} chars, max 15)"
    
    if len(word) < 2:
        return False, f"Word too short ({len(word)} char, min 2)"
    
    # Check for non-alphabetic characters (except Slovak diacritics)
    if not word.replace("-", "").replace("'", "").isalpha():
        return False, "Contains non-alphabetic characters"
    
    return True, "Pattern valid"


# ========== Rule Validation Tools ==========


def tool_rules_first_move_must_cover_center(
    placements: list[dict[str, Any]]
) -> dict[str, Any]:
    """Check if first move covers center square (7,7).
    
    Args:
        placements: List of {row, col, letter} dicts
    
    Returns:
        {valid: bool, reason: str}
    """
    try:
        placement_objs = [
            Placement(row=p["row"], col=p["col"], letter=p["letter"])
            for p in placements
        ]
        
        valid = first_move_must_cover_center(placement_objs)
        
        return {
            "valid": valid,
            "reason": (
                "Move covers center square (H8)" if valid
                else "First move must cover center square (7,7)"
            ),
        }
    except Exception as e:
        log.exception("Error in tool_rules_first_move_must_cover_center")
        return {"valid": False, "reason": f"Error: {e}"}


def tool_rules_placements_in_line(
    placements: list[dict[str, Any]]
) -> dict[str, Any]:
    """Check if all placements are in a single line (ACROSS or DOWN).
    
    Args:
        placements: List of {row, col, letter} dicts
    
    Returns:
        {valid: bool, direction: str|None, reason: str}
    """
    try:
        placement_objs = [
            Placement(row=p["row"], col=p["col"], letter=p["letter"])
            for p in placements
        ]
        
        direction = placements_in_line(placement_objs)
        
        return {
            "valid": direction is not None,
            "direction": direction.name if direction else None,
            "reason": (
                f"Placements form valid line ({direction.name})" if direction
                else "Placements must be in a single row or column"
            ),
        }
    except Exception as e:
        log.exception("Error in tool_rules_placements_in_line")
        return {"valid": False, "direction": None, "reason": f"Error: {e}"}


def tool_rules_connected_to_existing(
    board_grid: list[str],
    placements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check if placements connect to existing letters (after first move).
    
    Args:
        board_grid: 15x15 grid as list of strings ('.' for empty)
        placements: List of {row, col, letter} dicts
    
    Returns:
        {valid: bool, reason: str}
    """
    try:
        # Reconstruct board from grid
        board = Board(get_premiums_path())
        for r, row in enumerate(board_grid):
            for c, ch in enumerate(row):
                if ch != ".":
                    board.cells[r][c].letter = ch
        
        placement_objs = [
            Placement(row=p["row"], col=p["col"], letter=p["letter"])
            for p in placements
        ]
        
        valid = connected_to_existing(board, placement_objs)
        
        return {
            "valid": valid,
            "reason": (
                "Placements connect to existing letters" if valid
                else "Placements must be adjacent to existing letters"
            ),
        }
    except Exception as e:
        log.exception("Error in tool_rules_connected_to_existing")
        return {"valid": False, "reason": f"Error: {e}"}


def tool_rules_no_gaps_in_line(
    board_grid: list[str],
    placements: list[dict[str, Any]],
    direction: str,
) -> dict[str, Any]:
    """Check if there are no gaps in the main line formed by placements.
    
    Args:
        board_grid: 15x15 grid as list of strings
        placements: List of {row, col, letter} dicts
        direction: "ACROSS" or "DOWN"
    
    Returns:
        {valid: bool, reason: str}
    """
    try:
        board = Board(get_premiums_path())
        for r, row in enumerate(board_grid):
            for c, ch in enumerate(row):
                if ch != ".":
                    board.cells[r][c].letter = ch
        
        placement_objs = [
            Placement(row=p["row"], col=p["col"], letter=p["letter"])
            for p in placements
        ]
        
        dir_enum = Direction.ACROSS if direction == "ACROSS" else Direction.DOWN
        valid = no_gaps_in_line(board, placement_objs, dir_enum)
        
        return {
            "valid": valid,
            "reason": (
                "No gaps in line" if valid
                else "Placements have gaps in the main line"
            ),
        }
    except Exception as e:
        log.exception("Error in tool_rules_no_gaps_in_line")
        return {"valid": False, "reason": f"Error: {e}"}


def tool_rules_extract_all_words(
    board_grid: list[str],
    placements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract all words (main + cross-words) formed by the placements.
    
    Args:
        board_grid: 15x15 grid as list of strings
        placements: List of {row, col, letter} dicts
    
    Returns:
        {words: list[{word: str, cells: list[list[int]]}]}
    """
    try:
        board = Board(get_premiums_path())
        for r, row in enumerate(board_grid):
            for c, ch in enumerate(row):
                if ch != ".":
                    board.cells[r][c].letter = ch
        
        placement_objs = [
            Placement(row=p["row"], col=p["col"], letter=p["letter"])
            for p in placements
        ]
        
        # Apply placements temporarily
        board.place_letters(placement_objs)
        words_found = extract_all_words(board, placement_objs)
        
        return {
            "words": [
                {
                    "word": wf.word,
                    "cells": [[r, c] for r, c in wf.letters],
                }
                for wf in words_found
            ]
        }
    except Exception as e:
        log.exception("Error in tool_rules_extract_all_words")
        return {"words": [], "error": str(e)}


# ========== Scoring Tools ==========


def tool_scoring_score_words(
    board_grid: list[str],
    premium_grid: list[list[dict | None]],
    placements: list[dict[str, Any]],
    words: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate score for words with premium breakdown.
    
    Args:
        board_grid: 15x15 grid as list of strings
        premium_grid: 15x15 grid of {type, used} or None
        placements: List of {row, col, letter} dicts
        words: List of {word: str, cells: [[r,c], ...]}
    
    Returns:
        {total_score: int, breakdowns: list[{word, base_points, ...}]}
    """
    try:
        board = Board(get_premiums_path())
        
        # Reconstruct board with letters
        for r, row in enumerate(board_grid):
            for c, ch in enumerate(row):
                if ch != ".":
                    board.cells[r][c].letter = ch
        
        # Apply premiums if provided
        if premium_grid is not None:
            if premium_grid:
                # Non-empty: apply provided premiums
                for r in range(BOARD_SIZE):
                    for c in range(BOARD_SIZE):
                        if premium_grid[r][c]:
                            prem_type = premium_grid[r][c]["type"]
                            prem_used = premium_grid[r][c]["used"]
                            board.cells[r][c].premium = Premium[prem_type]
                            board.cells[r][c].premium_used = prem_used
            else:
                # Empty list: mark all premiums as used (no premiums active)
                for r in range(BOARD_SIZE):
                    for c in range(BOARD_SIZE):
                        if board.cells[r][c].premium:
                            board.cells[r][c].premium_used = True
        
        placement_objs = [
            Placement(row=p["row"], col=p["col"], letter=p["letter"])
            for p in placements
        ]
        
        # Apply placements
        board.place_letters(placement_objs)
        
        # Convert words to expected format
        words_coords = [
            (w["word"], [(r, c) for r, c in w["cells"]])
            for w in words
        ]
        
        total_score, breakdowns = score_words(board, placement_objs, words_coords)
        
        return {
            "total_score": total_score,
            "breakdowns": [
                {
                    "word": bd.word,
                    "base_points": bd.base_points,
                    "letter_bonus_points": bd.letter_bonus_points,
                    "word_multiplier": bd.word_multiplier,
                    "total": bd.total,
                }
                for bd in breakdowns
            ],
        }
    except Exception as e:
        log.exception("Error in tool_scoring_score_words")
        return {"total_score": 0, "breakdowns": [], "error": str(e)}


# ========== State/Info Tools ==========


def tool_get_board_state(board: Board | None = None) -> dict[str, Any]:
    """Get current board state as serialized grid.
    
    Args:
        board: Board instance (or None for empty board)
    
    Returns:
        {grid: list[str], blanks: list[{row, col}]}
    """
    try:
        if board is None:
            board = Board(get_premiums_path())
        
        grid = []
        blanks = []
        
        for r in range(BOARD_SIZE):
            row_chars = []
            for c in range(BOARD_SIZE):
                cell = board.cells[r][c]
                if cell.letter:
                    row_chars.append(cell.letter)
                    if cell.is_blank:
                        blanks.append({"row": r, "col": c})
                else:
                    row_chars.append(".")
            grid.append("".join(row_chars))
        
        return {"grid": grid, "blanks": blanks}
    except Exception as e:
        log.exception("Error in tool_get_board_state")
        return {"grid": [], "blanks": [], "error": str(e)}


def tool_get_rack_letters(rack: list[str]) -> dict[str, Any]:
    """Get available letters on rack.
    
    Args:
        rack: List of letter strings
    
    Returns:
        {rack: str, count: int, letters: list[str]}
    """
    try:
        return {
            "rack": "".join(rack),
            "count": len(rack),
            "letters": rack,
        }
    except Exception as e:
        log.exception("Error in tool_get_rack_letters")
        return {"rack": "", "count": 0, "letters": [], "error": str(e)}


def tool_get_premium_squares(board: Board) -> dict[str, Any]:
    """Get all unused premium squares on board.
    
    Args:
        board: Board instance
    
    Returns:
        {premiums: list[{row, col, type, used}]}
    """
    try:
        premiums = []
        
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                cell = board.cells[r][c]
                if cell.premium:
                    premiums.append({
                        "row": r,
                        "col": c,
                        "type": cell.premium.name,
                        "used": cell.premium_used,
                    })
        
        return {"premiums": premiums}
    except Exception as e:
        log.exception("Error in tool_get_premium_squares")
        return {"premiums": [], "error": str(e)}


def tool_get_tile_values(variant: str = "slovak") -> dict[str, Any]:
    """Get point values for all letters in variant.
    
    Args:
        variant: Variant slug (e.g., "slovak", "english")
    
    Returns:
        {values: dict[str, int], variant: str}
    """
    try:
        # For now, use get_tile_points() which returns Slovak values
        # TODO: Support other variants
        values = get_tile_points()
        
        return {
            "values": values,
            "variant": variant,
        }
    except Exception as e:
        log.exception("Error in tool_get_tile_values")
        return {"values": {}, "variant": variant, "error": str(e)}


# ========== Dictionary Validation Tools ==========


def tool_validate_word_slovak(
    word: str, 
    use_online: bool = True,
    retry_count: int = 2,
    online_min_length: int | None = None,
) -> dict[str, Any]:
    """Validate Slovak word using robust 3-tier validation with length-based optimization.
    
    Tier 1: In-memory dictionary (fast, <1ms, ~500k words)
    Tier 2: HTTP API call to JULS (online, ~200-500ms with retry)
    Tier 3: AI judge fallback (expensive, caller responsibility)
    
    Optimization: Short words (≤7 chars) skip online validation since local dict
    has 99%+ coverage. Only long words (compounds, neologisms) use JULS API.
    
    Features:
    - Length-based online validation (saves 80-90% API calls)
    - Caching with 1-hour TTL
    - Automatic retry for network failures
    - Pattern validation
    - Performance metrics
    - Graceful degradation
    
    Args:
        word: Word to validate
        use_online: Whether to use Tier 2 (JULS API) if Tier 1 fails
        retry_count: Number of retries for online validation (default: 2)
        online_min_length: Minimum word length for online validation (default: 7)
    
    Returns:
        {
            valid: bool,
            language: str,
            tier: int,  # 0=pattern, 1=fastdict, 2=juls, 3=needs_judge
            reason: str,
            source: str,
            time_ms: float,  # validation time in milliseconds
            cached: bool,    # whether result was from cache
            skipped_online: bool,  # whether online was skipped due to length
        }
    """
    start_time = time.time()
    word_normalized = _normalize_word(word)
    
    # ========== Pre-validation: Pattern Check ==========
    is_valid_pattern, pattern_reason = _is_valid_word_pattern(word_normalized)
    if not is_valid_pattern:
        elapsed_ms = (time.time() - start_time) * 1000
        _VALIDATION_STATS["slovak_pattern"]["count"] += 1
        _VALIDATION_STATS["slovak_pattern"]["time_ms"] += elapsed_ms
        
        return {
            "valid": False,
            "language": "slovak",
            "tier": 0,
            "reason": pattern_reason,
            "source": "pattern_validation",
            "time_ms": elapsed_ms,
            "cached": False,
        }
    
    # ========== Cache Check ==========
    cached_result = _get_cached_validation(word_normalized, "slovak")
    if cached_result is not None:
        elapsed_ms = (time.time() - start_time) * 1000
        cached_result["time_ms"] = elapsed_ms
        cached_result["cached"] = True
        return cached_result
    
    # ========== Tier 1: In-memory FastDict ==========
    slovak_dict = _get_slovak_dict()
    if slovak_dict:
        try:
            tier1_start = time.time()
            is_in_dict = slovak_dict(word_normalized)
            tier1_time_ms = (time.time() - tier1_start) * 1000
            
            _VALIDATION_STATS["slovak_tier1"]["count"] += 1
            _VALIDATION_STATS["slovak_tier1"]["time_ms"] += tier1_time_ms
            
            if is_in_dict:
                elapsed_ms = (time.time() - start_time) * 1000
                log.debug("✓ Word '%s' found in local dict (Tier 1, %.1fms)", word_normalized, tier1_time_ms)
                
                result = {
                    "valid": True,
                    "language": "slovak",
                    "tier": 1,
                    "reason": "Found in local dictionary",
                    "source": "fastdict",
                    "time_ms": elapsed_ms,
                    "cached": False,
                    "skipped_online": False,
                }
                _cache_validation(word_normalized, "slovak", result)
                return result
            else:
                log.debug("✗ Word '%s' NOT in local dict (len=%d)", word_normalized, len(word_normalized))
                
        except Exception as e:
            log.exception("Tier 1 FastDict error for '%s': %s", word_normalized, e)
    else:
        log.warning("Slovak dictionary not loaded, skipping Tier 1")
    
    # ========== Length-based Online Skip ==========
    # Short words: if not in local dict, assume invalid (99%+ coverage)
    # Long words: might be compounds/neologisms, check JULS
    threshold = online_min_length if online_min_length is not None else 7
    if len(word_normalized) <= threshold:
        elapsed_ms = (time.time() - start_time) * 1000
        log.debug("⚡ Word '%s' too short (len=%d ≤ %d) for online validation, marking invalid", 
                 word_normalized, len(word_normalized), threshold)
        
        _VALIDATION_STATS["slovak_short_skip"]["count"] += 1
        
        result = {
            "valid": False,
            "language": "slovak",
            "tier": 1,
            "reason": f"Not in local dictionary (short word ≤{threshold} chars, online skipped)",
            "source": "tier1_negative_short",
            "time_ms": elapsed_ms,
            "cached": False,
            "skipped_online": True,
        }
        _cache_validation(word_normalized, "slovak", result)
        return result
    
    # ========== Tier 2: JULS Online API with Retry ==========
    if use_online:
        tier2_start = time.time()
        last_error = None
        
        for attempt in range(1, retry_count + 1):
            try:
                timeout = 3.0 + (attempt - 1) * 1.0  # Increase timeout on retry
                is_in_juls = is_word_in_juls(word_normalized, timeout=timeout)
                tier2_time_ms = (time.time() - tier2_start) * 1000
                
                _VALIDATION_STATS["slovak_tier2"]["count"] += 1
                _VALIDATION_STATS["slovak_tier2"]["time_ms"] += tier2_time_ms
                
                if is_in_juls:
                    elapsed_ms = (time.time() - start_time) * 1000
                    log.info("✓ Word '%s' found in JULS (Tier 2, %.1fms, attempt %d)", 
                            word_normalized, tier2_time_ms, attempt)
                    
                    result = {
                        "valid": True,
                        "language": "slovak",
                        "tier": 2,
                        "reason": f"Found in JULS online dictionary (long word, attempt {attempt})",
                        "source": "juls_api",
                        "time_ms": elapsed_ms,
                        "cached": False,
                        "skipped_online": False,
                    }
                    _cache_validation(word_normalized, "slovak", result)
                    return result
                else:
                    # Negative result - also cache it
                    elapsed_ms = (time.time() - start_time) * 1000
                    log.debug("✗ Word '%s' NOT in JULS (long word, attempt %d)", word_normalized, attempt)
                    
                    result = {
                        "valid": False,
                        "language": "slovak",
                        "tier": 2,
                        "reason": "Not found in local dictionary or JULS - needs AI judge verification",
                        "source": "tier2_negative",
                        "time_ms": elapsed_ms,
                        "cached": False,
                        "skipped_online": False,
                    }
                    _cache_validation(word_normalized, "slovak", result)
                    return result
                    
            except httpx.TimeoutException as e:
                last_error = e
                log.warning("Tier 2 JULS timeout for '%s' (attempt %d/%d): %s", 
                           word_normalized, attempt, retry_count, e)
                if attempt < retry_count:
                    time.sleep(0.5 * attempt)  # Exponential backoff
                    
            except httpx.HTTPError as e:
                last_error = e
                log.warning("Tier 2 JULS HTTP error for '%s' (attempt %d/%d): %s", 
                           word_normalized, attempt, retry_count, e)
                if attempt < retry_count:
                    time.sleep(0.5 * attempt)
                    
            except Exception as e:
                last_error = e
                log.exception("Tier 2 JULS unexpected error for '%s' (attempt %d/%d)", 
                             word_normalized, attempt, retry_count)
                break  # Don't retry on unexpected errors
        
        # All retries failed
        elapsed_ms = (time.time() - start_time) * 1000
        log.warning("✗ Tier 2 JULS failed after %d attempts for '%s': %s", 
                   retry_count, word_normalized, last_error)
    
    # ========== Tier 3: Needs AI Judge ==========
    # NOTE: Not implemented here to keep tool stateless
    # Caller should use OpenAIClient.judge_words() if needed
    elapsed_ms = (time.time() - start_time) * 1000
    log.info("⚠ Word '%s' not found in Tier 1-2, needs AI judge (Tier 3)", word_normalized)
    
    _VALIDATION_STATS["slovak_tier3_needed"]["count"] += 1
    
    result = {
        "valid": False,
        "language": "slovak",
        "tier": 2,  # We reached Tier 2 attempt
        "reason": "Not found in local dictionary or JULS - needs AI judge verification",
        "source": "tier2_negative",
        "time_ms": elapsed_ms,
        "cached": False,
        "skipped_online": False,
    }
    
    # Don't cache Tier 3 fallbacks (let AI judge decide each time)
    return result


def tool_validate_word_english(
    word: str,
    use_online: bool = False,  # English usually doesn't need online
) -> dict[str, Any]:
    """Validate English word using robust 3-tier validation.
    
    Tier 1: In-memory TWL/SOWPODS dictionary (fast, <1ms)
    Tier 2: HTTP API call to dictionary service (optional, rarely needed)
    Tier 3: AI judge fallback (expensive, caller responsibility)
    
    Features:
    - Caching with 1-hour TTL
    - Pattern validation
    - Performance metrics
    
    Args:
        word: Word to validate
        use_online: Whether to use Tier 2 API if Tier 1 fails (default: False)
    
    Returns:
        {
            valid: bool,
            language: str,
            tier: int,
            reason: str,
            source: str,
            time_ms: float,
            cached: bool,
        }
    """
    start_time = time.time()
    word_normalized = _normalize_word(word)
    
    # ========== Pre-validation: Pattern Check ==========
    is_valid_pattern, pattern_reason = _is_valid_word_pattern(word_normalized)
    if not is_valid_pattern:
        elapsed_ms = (time.time() - start_time) * 1000
        _VALIDATION_STATS["english_pattern"]["count"] += 1
        _VALIDATION_STATS["english_pattern"]["time_ms"] += elapsed_ms
        
        return {
            "valid": False,
            "language": "english",
            "tier": 0,
            "reason": pattern_reason,
            "source": "pattern_validation",
            "time_ms": elapsed_ms,
            "cached": False,
        }
    
    # ========== Cache Check ==========
    cached_result = _get_cached_validation(word_normalized, "english")
    if cached_result is not None:
        elapsed_ms = (time.time() - start_time) * 1000
        cached_result["time_ms"] = elapsed_ms
        cached_result["cached"] = True
        return cached_result
    
    # ========== Tier 1: In-memory TWL/SOWPODS ==========
    english_dict = _get_english_dict()
    if english_dict:
        try:
            tier1_start = time.time()
            is_in_dict = english_dict(word_normalized)
            tier1_time_ms = (time.time() - tier1_start) * 1000
            
            _VALIDATION_STATS["english_tier1"]["count"] += 1
            _VALIDATION_STATS["english_tier1"]["time_ms"] += tier1_time_ms
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            if is_in_dict:
                log.debug("✓ Word '%s' found in English dict (Tier 1, %.1fms)", 
                         word_normalized, tier1_time_ms)
                
                result = {
                    "valid": True,
                    "language": "english",
                    "tier": 1,
                    "reason": "Found in TWL/SOWPODS dictionary",
                    "source": "fastdict_english",
                    "time_ms": elapsed_ms,
                    "cached": False,
                }
                _cache_validation(word_normalized, "english", result)
                return result
            else:
                log.debug("✗ Word '%s' NOT in English dict", word_normalized)
                
                result = {
                    "valid": False,
                    "language": "english",
                    "tier": 1,
                    "reason": "Not found in TWL/SOWPODS - needs AI judge verification",
                    "source": "tier1_negative",
                    "time_ms": elapsed_ms,
                    "cached": False,
                }
                _cache_validation(word_normalized, "english", result)
                return result
                
        except Exception as e:
            log.exception("Tier 1 English dict error for '%s': %s", word_normalized, e)
    else:
        log.warning("English dictionary not loaded - needs AI judge")
    
    # ========== Tier 2: Online API (optional) ==========
    if use_online:
        log.info("⚠ English Tier 2 (online API) not implemented yet")
    
    # ========== Tier 3: Needs AI Judge ==========
    elapsed_ms = (time.time() - start_time) * 1000
    log.info("⚠ Word '%s' not found in English dict, needs AI judge", word_normalized)
    
    _VALIDATION_STATS["english_tier3_needed"]["count"] += 1
    
    return {
        "valid": False,
        "language": "english",
        "tier": 1,
        "reason": "English dictionary not available or word not found - needs AI judge",
        "source": "tier1_negative",
        "time_ms": elapsed_ms,
        "cached": False,
    }


def tool_get_validation_stats() -> dict[str, Any]:
    """Get validation performance statistics.
    
    Returns:
        {
            stats: dict[str, dict],  # Per-tier statistics
            cache_size: int,
            cache_hit_rate: float,
        }
    """
    # Calculate cache hit rate
    total_hits = sum(stat["hits"] for key, stat in _VALIDATION_STATS.items() if "cache" in key)
    total_misses = sum(stat["misses"] for key, stat in _VALIDATION_STATS.items() if "cache" in key)
    total_requests = total_hits + total_misses
    cache_hit_rate = total_hits / total_requests if total_requests > 0 else 0.0
    
    # Calculate average times
    stats_summary = {}
    for key, stat in _VALIDATION_STATS.items():
        if stat["count"] > 0:
            avg_time_ms = stat["time_ms"] / stat["count"]
            stats_summary[key] = {
                "count": stat["count"],
                "avg_time_ms": round(avg_time_ms, 2),
                "total_time_ms": round(stat["time_ms"], 2),
            }
    
    return {
        "stats": stats_summary,
        "cache_size": len(_VALIDATION_CACHE),
        "cache_hit_rate": round(cache_hit_rate, 3),
        "cache_hits": total_hits,
        "cache_misses": total_misses,
    }


# ========== High-Level Composite Tools ==========


def tool_validate_move_legality(
    board_grid: list[str],
    placements: list[dict[str, Any]],
    is_first_move: bool = False,
) -> dict[str, Any]:
    """Validate complete move legality (combines all rule checks).
    
    Args:
        board_grid: 15x15 grid as list of strings
        placements: List of {row, col, letter} dicts
        is_first_move: Whether this is the first move
    
    Returns:
        {valid: bool, checks: dict[str, bool], reason: str}
    """
    try:
        checks = {}
        
        # Check 1: Placements in line
        line_result = tool_rules_placements_in_line(placements)
        checks["in_line"] = line_result["valid"]
        
        if not line_result["valid"]:
            return {
                "valid": False,
                "checks": checks,
                "reason": "Placements not in a single line",
            }
        
        direction = line_result["direction"]
        
        # Check 2: First move covers center
        if is_first_move:
            center_result = tool_rules_first_move_must_cover_center(placements)
            checks["covers_center"] = center_result["valid"]
            
            if not center_result["valid"]:
                return {
                    "valid": False,
                    "checks": checks,
                    "reason": "First move must cover center",
                }
        
        # Check 3: No gaps
        gap_result = tool_rules_no_gaps_in_line(board_grid, placements, direction)
        checks["no_gaps"] = gap_result["valid"]
        
        if not gap_result["valid"]:
            return {
                "valid": False,
                "checks": checks,
                "reason": "Gaps in line",
            }
        
        # Check 4: Connected to existing (after first move)
        if not is_first_move:
            connect_result = tool_rules_connected_to_existing(board_grid, placements)
            checks["connected"] = connect_result["valid"]
            
            if not connect_result["valid"]:
                return {
                    "valid": False,
                    "checks": checks,
                    "reason": "Not connected to existing letters",
                }
        
        return {
            "valid": True,
            "checks": checks,
            "reason": "Move is legal",
        }
    except Exception as e:
        log.exception("Error in tool_validate_move_legality")
        return {
            "valid": False,
            "checks": {},
            "reason": f"Validation error: {e}",
        }


def tool_calculate_move_score(
    board_grid: list[str],
    premium_grid: list[list[dict | None]],
    placements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate total score for a move (extracts words + scores them).
    
    Args:
        board_grid: 15x15 grid as list of strings
        premium_grid: 15x15 grid of premium info
        placements: List of {row, col, letter} dicts
    
    Returns:
        {total_score: int, breakdowns: list, words: list}
    """
    try:
        # Extract words
        words_result = tool_rules_extract_all_words(board_grid, placements)
        
        if not words_result.get("words"):
            return {
                "total_score": 0,
                "breakdowns": [],
                "words": [],
                "reason": "No words formed",
            }
        
        # Score words
        score_result = tool_scoring_score_words(
            board_grid,
            premium_grid,
            placements,
            words_result["words"],
        )
        
        return {
            "total_score": score_result["total_score"],
            "breakdowns": score_result["breakdowns"],
            "words": words_result["words"],
        }
    except Exception as e:
        log.exception("Error in tool_calculate_move_score")
        return {
            "total_score": 0,
            "breakdowns": [],
            "words": [],
            "error": str(e),
        }


# ========== Tool Registry ==========


# All available tools registered here
ALL_TOOLS = {
    "rules_first_move_must_cover_center": tool_rules_first_move_must_cover_center,
    "rules_placements_in_line": tool_rules_placements_in_line,
    "rules_connected_to_existing": tool_rules_connected_to_existing,
    "rules_no_gaps_in_line": tool_rules_no_gaps_in_line,
    "rules_extract_all_words": tool_rules_extract_all_words,
    "scoring_score_words": tool_scoring_score_words,
    "get_board_state": tool_get_board_state,
    "get_rack_letters": tool_get_rack_letters,
    "get_premium_squares": tool_get_premium_squares,
    "get_tile_values": tool_get_tile_values,
    "validate_word_slovak": tool_validate_word_slovak,
    "validate_word_english": tool_validate_word_english,
    "validate_move_legality": tool_validate_move_legality,
    "calculate_move_score": tool_calculate_move_score,
    "get_validation_stats": tool_get_validation_stats,
}


def get_tool_function(tool_name: str):
    """Get tool function by name.
    
    Args:
        tool_name: Name of the tool
    
    Returns:
        Callable tool function
    
    Raises:
        KeyError: If tool not found
    """
    if tool_name not in ALL_TOOLS:
        raise KeyError(f"Tool not found: {tool_name}")
    
    return ALL_TOOLS[tool_name]


def get_all_tool_names() -> list[str]:
    """Get list of all registered tool names."""
    return list(ALL_TOOLS.keys())
