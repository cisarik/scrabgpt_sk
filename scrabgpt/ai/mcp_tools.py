"""MCP tool wrappers for AI agent.

Each function here is a stateless tool that can be called by the AI agent
via Model Context Protocol (MCP). All inputs and outputs are JSON-serializable.

Tool naming convention: tool_<category>_<action>
Example: tool_rules_placements_in_line, tool_scoring_score_words
"""

from __future__ import annotations

import logging
from typing import Any

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

log = logging.getLogger("scrabgpt.ai.mcp_tools")


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
                        "type": cell.premium.value,
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


def tool_validate_word_slovak(word: str) -> dict[str, Any]:
    """Validate Slovak word using 3-tier validation.
    
    Tier 1: In-memory dictionary (fast)
    Tier 2: HTTP API call to JULS or similar (when available)
    Tier 3: AI judge fallback
    
    Args:
        word: Word to validate
    
    Returns:
        {valid: bool, language: str, tier: int, reason: str}
    """
    # TODO: Implement 3-tier validation
    # For now, return stub
    log.warning("tool_validate_word_slovak not fully implemented - returning stub")
    
    return {
        "valid": True,  # Stub: always valid for now
        "language": "slovak",
        "tier": 0,  # 0 = not validated
        "reason": "Validation not implemented - stub only",
    }


def tool_validate_word_english(word: str) -> dict[str, Any]:
    """Validate English word using 3-tier validation.
    
    Tier 1: In-memory TWL/SOWPODS dictionary
    Tier 2: HTTP API call to dictionary service
    Tier 3: AI judge fallback
    
    Args:
        word: Word to validate
    
    Returns:
        {valid: bool, language: str, tier: int, reason: str}
    """
    # TODO: Implement 3-tier validation
    log.warning("tool_validate_word_english not implemented - returning stub")
    
    return {
        "valid": False,
        "language": "english",
        "tier": 0,
        "reason": "English validation not implemented yet",
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
