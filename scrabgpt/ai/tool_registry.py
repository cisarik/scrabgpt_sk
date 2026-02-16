"""Internal Scrabble tool registry for AI tool-calling."""

from __future__ import annotations

from .mcp_tools import (
    ALL_TOOLS,
    get_all_tool_names,
    get_tool_function,
    is_word_in_juls,
    tool_calculate_move_score,
    tool_get_board_state,
    tool_get_premium_squares,
    tool_get_rack_letters,
    tool_get_tile_values,
    tool_get_validation_stats,
    tool_rules_connected_to_existing,
    tool_rules_extract_all_words,
    tool_rules_first_move_must_cover_center,
    tool_rules_no_gaps_in_line,
    tool_rules_placements_in_line,
    tool_scoring_score_words,
    tool_validate_move_legality,
    tool_validate_word_english,
    tool_validate_word_slovak,
)

__all__ = [
    "ALL_TOOLS",
    "get_all_tool_names",
    "get_tool_function",
    "is_word_in_juls",
    "tool_calculate_move_score",
    "tool_get_board_state",
    "tool_get_premium_squares",
    "tool_get_rack_letters",
    "tool_get_tile_values",
    "tool_get_validation_stats",
    "tool_rules_connected_to_existing",
    "tool_rules_extract_all_words",
    "tool_rules_first_move_must_cover_center",
    "tool_rules_no_gaps_in_line",
    "tool_rules_placements_in_line",
    "tool_scoring_score_words",
    "tool_validate_move_legality",
    "tool_validate_word_english",
    "tool_validate_word_slovak",
]
