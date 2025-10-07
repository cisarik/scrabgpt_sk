"""BDD tests for MCP tool wrappers.

These tests define the expected behavior of each MCP tool that will be exposed
to AI agents. Each tool must be stateless and JSON-serializable.
"""

from __future__ import annotations

import pytest
from scrabgpt.core.board import Board
from scrabgpt.core.assets import get_premiums_path
from scrabgpt.core.types import Placement


@pytest.fixture
def empty_board() -> Board:
    """Empty 15x15 Scrabble board."""
    return Board(get_premiums_path())


@pytest.fixture
def board_with_word(empty_board: Board) -> Board:
    """Board with 'HELLO' placed horizontally at H8."""
    board = empty_board
    placements = [
        Placement(row=7, col=7, letter="H"),
        Placement(row=7, col=8, letter="E"),
        Placement(row=7, col=9, letter="L"),
        Placement(row=7, col=10, letter="L"),
        Placement(row=7, col=11, letter="O"),
    ]
    board.place_letters(placements)
    return board


class TestRuleTools:
    """Test rule validation tools that will be exposed via MCP."""

    def test_rules_first_move_must_cover_center_validates_correctly(
        self, empty_board: Board
    ) -> None:
        """Given: Agent proposes first move
        When: Move covers center square (7,7)
        Then: Tool returns true
        """
        from scrabgpt.ai.mcp_tools import tool_rules_first_move_must_cover_center

        result = tool_rules_first_move_must_cover_center(
            placements=[
                {"row": 7, "col": 7, "letter": "H"},
                {"row": 7, "col": 8, "letter": "I"},
            ]
        )
        
        assert result["valid"] is True
        assert "covers center" in result["reason"].lower()

    def test_rules_first_move_must_cover_center_rejects_missing_center(
        self, empty_board: Board
    ) -> None:
        """Given: Agent proposes first move
        When: Move does not cover center square
        Then: Tool returns false
        """
        from scrabgpt.ai.mcp_tools import tool_rules_first_move_must_cover_center

        result = tool_rules_first_move_must_cover_center(
            placements=[
                {"row": 8, "col": 8, "letter": "H"},
                {"row": 8, "col": 9, "letter": "I"},
            ]
        )
        
        assert result["valid"] is False
        assert "must cover center" in result["reason"].lower()

    def test_rules_placements_in_line_detects_across_direction(self) -> None:
        """Given: Agent proposes move
        When: All placements are in same row
        Then: Tool returns ACROSS direction
        """
        from scrabgpt.ai.mcp_tools import tool_rules_placements_in_line

        result = tool_rules_placements_in_line(
            placements=[
                {"row": 7, "col": 5, "letter": "C"},
                {"row": 7, "col": 6, "letter": "A"},
                {"row": 7, "col": 7, "letter": "T"},
            ]
        )
        
        assert result["valid"] is True
        assert result["direction"] == "ACROSS"

    def test_rules_placements_in_line_detects_down_direction(self) -> None:
        """Given: Agent proposes move
        When: All placements are in same column
        Then: Tool returns DOWN direction
        """
        from scrabgpt.ai.mcp_tools import tool_rules_placements_in_line

        result = tool_rules_placements_in_line(
            placements=[
                {"row": 5, "col": 7, "letter": "C"},
                {"row": 6, "col": 7, "letter": "A"},
                {"row": 7, "col": 7, "letter": "T"},
            ]
        )
        
        assert result["valid"] is True
        assert result["direction"] == "DOWN"

    def test_rules_placements_in_line_rejects_diagonal(self) -> None:
        """Given: Agent proposes move
        When: Placements are not in a line
        Then: Tool returns invalid
        """
        from scrabgpt.ai.mcp_tools import tool_rules_placements_in_line

        result = tool_rules_placements_in_line(
            placements=[
                {"row": 5, "col": 5, "letter": "C"},
                {"row": 6, "col": 6, "letter": "A"},
                {"row": 7, "col": 7, "letter": "T"},
            ]
        )
        
        assert result["valid"] is False
        assert result["direction"] is None

    def test_rules_connected_to_existing_validates_adjacent_placement(
        self, board_with_word: Board
    ) -> None:
        """Given: Board with existing word 'HELLO'
        When: Agent places letter adjacent to existing
        Then: Tool returns valid
        """
        from scrabgpt.ai.mcp_tools import tool_rules_connected_to_existing

        # Serialize board state
        grid = []
        for r in range(15):
            row_chars = []
            for c in range(15):
                letter = board_with_word.cells[r][c].letter
                row_chars.append(letter if letter else ".")
            grid.append("".join(row_chars))

        result = tool_rules_connected_to_existing(
            board_grid=grid,
            placements=[{"row": 6, "col": 7, "letter": "A"}],  # Above 'H'
        )
        
        assert result["valid"] is True

    def test_rules_connected_to_existing_rejects_isolated_placement(
        self, board_with_word: Board
    ) -> None:
        """Given: Board with existing word
        When: Agent places letter not adjacent to any existing
        Then: Tool returns invalid
        """
        from scrabgpt.ai.mcp_tools import tool_rules_connected_to_existing

        grid = []
        for r in range(15):
            row_chars = []
            for c in range(15):
                letter = board_with_word.cells[r][c].letter
                row_chars.append(letter if letter else ".")
            grid.append("".join(row_chars))

        result = tool_rules_connected_to_existing(
            board_grid=grid,
            placements=[{"row": 0, "col": 0, "letter": "X"}],  # Far from any letter
        )
        
        assert result["valid"] is False

    def test_rules_no_gaps_in_line_accepts_contiguous_placements(
        self, empty_board: Board
    ) -> None:
        """Given: Agent proposes move
        When: Placements form contiguous line
        Then: Tool returns valid
        """
        from scrabgpt.ai.mcp_tools import tool_rules_no_gaps_in_line

        grid = ["." * 15 for _ in range(15)]
        
        result = tool_rules_no_gaps_in_line(
            board_grid=grid,
            placements=[
                {"row": 7, "col": 7, "letter": "C"},
                {"row": 7, "col": 8, "letter": "A"},
                {"row": 7, "col": 9, "letter": "T"},
            ],
            direction="ACROSS",
        )
        
        assert result["valid"] is True

    def test_rules_no_gaps_in_line_rejects_gaps(self, empty_board: Board) -> None:
        """Given: Agent proposes move
        When: Placements have gaps in between
        Then: Tool returns invalid
        """
        from scrabgpt.ai.mcp_tools import tool_rules_no_gaps_in_line

        grid = ["." * 15 for _ in range(15)]
        
        result = tool_rules_no_gaps_in_line(
            board_grid=grid,
            placements=[
                {"row": 7, "col": 7, "letter": "C"},
                {"row": 7, "col": 9, "letter": "T"},  # Gap at col 8
            ],
            direction="ACROSS",
        )
        
        assert result["valid"] is False

    def test_rules_extract_all_words_finds_main_word(
        self, empty_board: Board
    ) -> None:
        """Given: Agent places letters forming word
        When: Tool extracts words
        Then: Main word is found
        """
        from scrabgpt.ai.mcp_tools import tool_rules_extract_all_words

        # Place "CAT" on empty board
        grid = ["." * 15 for _ in range(15)]
        placements = [
            {"row": 7, "col": 7, "letter": "C"},
            {"row": 7, "col": 8, "letter": "A"},
            {"row": 7, "col": 9, "letter": "T"},
        ]
        
        result = tool_rules_extract_all_words(
            board_grid=grid,
            placements=placements,
        )
        
        assert len(result["words"]) == 1
        assert result["words"][0]["word"] == "CAT"

    def test_rules_extract_all_words_finds_cross_words(
        self, board_with_word: Board
    ) -> None:
        """Given: Board with existing word 'HELLO'
        When: Agent places letters creating cross-words
        Then: All words (main + cross) are found
        """
        from scrabgpt.ai.mcp_tools import tool_rules_extract_all_words

        # Serialize board
        grid = []
        for r in range(15):
            row_chars = []
            for c in range(15):
                letter = board_with_word.cells[r][c].letter
                row_chars.append(letter if letter else ".")
            grid.append("".join(row_chars))

        # Place "A" above "E" to form "AE"
        placements = [
            {"row": 6, "col": 8, "letter": "A"},
        ]
        
        result = tool_rules_extract_all_words(
            board_grid=grid,
            placements=placements,
        )
        
        # Should find cross-word "AE"
        assert len(result["words"]) >= 1
        words = [w["word"] for w in result["words"]]
        assert "AE" in words or "A" in words


class TestScoringTools:
    """Test scoring tools that will be exposed via MCP."""

    def test_scoring_score_words_calculates_basic_score(self) -> None:
        """Given: Agent places simple word with no premiums
        When: Tool calculates score
        Then: Basic letter values are summed
        """
        from scrabgpt.ai.mcp_tools import tool_scoring_score_words

        grid = ["." * 15 for _ in range(15)]
        placements = [
            {"row": 7, "col": 7, "letter": "C"},  # 3 points
            {"row": 7, "col": 8, "letter": "A"},  # 1 point
            {"row": 7, "col": 9, "letter": "T"},  # 1 point
        ]
        words = [
            {
                "word": "CAT",
                "cells": [[7, 7], [7, 8], [7, 9]],
            }
        ]
        
        result = tool_scoring_score_words(
            board_grid=grid,
            premium_grid=[],  # No premiums
            placements=placements,
            words=words,
        )
        
        assert result["total_score"] == 5
        assert len(result["breakdowns"]) == 1
        assert result["breakdowns"][0]["word"] == "CAT"

    def test_scoring_score_words_applies_double_letter_premium(self) -> None:
        """Given: Agent places letter on DL square
        When: Tool calculates score
        Then: Letter value is doubled
        """
        from scrabgpt.ai.mcp_tools import tool_scoring_score_words

        grid = ["." * 15 for _ in range(15)]
        # Mark center as DL for testing
        premium_grid = []
        for r in range(15):
            row = []
            for c in range(15):
                if r == 7 and c == 7:
                    row.append({"type": "DL", "used": False})
                else:
                    row.append(None)
            premium_grid.append(row)

        placements = [
            {"row": 7, "col": 7, "letter": "C"},  # On DL: 3 * 2 = 6
            {"row": 7, "col": 8, "letter": "A"},
        ]
        words = [{"word": "CA", "cells": [[7, 7], [7, 8]]}]
        
        result = tool_scoring_score_words(
            board_grid=grid,
            premium_grid=premium_grid,
            placements=placements,
            words=words,
        )
        
        # C=3*2=6, A=1, total=7
        assert result["total_score"] == 7


class TestStateTools:
    """Test state/information tools that will be exposed via MCP."""

    def test_get_board_state_returns_serialized_grid(
        self, board_with_word: Board
    ) -> None:
        """Given: Board with letters
        When: Tool serializes board state
        Then: Grid is returned as list of strings
        """
        from scrabgpt.ai.mcp_tools import tool_get_board_state

        result = tool_get_board_state(board=board_with_word)
        
        assert len(result["grid"]) == 15
        assert len(result["grid"][0]) == 15
        # Row 7 should contain "HELLO"
        assert "HELLO" in result["grid"][7]

    def test_get_rack_letters_returns_available_letters(self) -> None:
        """Given: Rack with letters
        When: Tool retrieves rack
        Then: Letters are returned as string
        """
        from scrabgpt.ai.mcp_tools import tool_get_rack_letters

        result = tool_get_rack_letters(rack=["A", "B", "C", "D", "E", "F", "G"])
        
        assert result["rack"] == "ABCDEFG"
        assert result["count"] == 7

    def test_get_premium_squares_returns_unused_premiums(
        self, empty_board: Board
    ) -> None:
        """Given: Board with premium squares
        When: Tool retrieves premiums
        Then: All unused premiums are returned
        """
        from scrabgpt.ai.mcp_tools import tool_get_premium_squares

        result = tool_get_premium_squares(board=empty_board)
        
        # Should have TW, DW, TL, DL squares
        assert "TW" in [p["type"] for p in result["premiums"]]
        assert "DW" in [p["type"] for p in result["premiums"]]
        assert len(result["premiums"]) > 0

    def test_get_tile_values_returns_point_values(self) -> None:
        """Given: Language variant
        When: Tool retrieves tile values
        Then: Point values for all letters are returned
        """
        from scrabgpt.ai.mcp_tools import tool_get_tile_values

        result = tool_get_tile_values(variant="slovak")
        
        assert result["values"]["A"] == 1
        assert result["values"]["?"] == 0  # Blank
        assert len(result["values"]) > 0


class TestDictionaryTools:
    """Test dictionary validation tools that will be exposed via MCP."""

    def test_validate_word_slovak_accepts_valid_word(self) -> None:
        """Given: Valid Slovak word
        When: Tool validates word
        Then: Returns valid=True
        """
        from scrabgpt.ai.mcp_tools import tool_validate_word_slovak

        result = tool_validate_word_slovak(word="OČI")
        
        assert result["valid"] is True
        assert result["language"] == "slovak"

    def test_validate_word_slovak_rejects_invalid_word(self) -> None:
        """Given: Invalid Slovak word
        When: Tool validates word
        Then: Returns valid=False
        """
        from scrabgpt.ai.mcp_tools import tool_validate_word_slovak

        result = tool_validate_word_slovak(word="XYZQQ")
        
        assert result["valid"] is False

    @pytest.mark.skip(reason="English validation not implemented yet")
    def test_validate_word_english_accepts_valid_word(self) -> None:
        """Given: Valid English word
        When: Tool validates word
        Then: Returns valid=True
        """
        from scrabgpt.ai.mcp_tools import tool_validate_word_english

        result = tool_validate_word_english(word="HELLO")
        
        assert result["valid"] is True
        assert result["language"] == "english"


class TestHighLevelTools:
    """Test high-level composite tools that combine multiple validations."""

    def test_validate_move_legality_accepts_valid_first_move(
        self, empty_board: Board
    ) -> None:
        """Given: Empty board and valid first move
        When: Tool validates move legality
        Then: All checks pass
        """
        from scrabgpt.ai.mcp_tools import tool_validate_move_legality

        grid = ["." * 15 for _ in range(15)]
        placements = [
            {"row": 7, "col": 7, "letter": "H"},
            {"row": 7, "col": 8, "letter": "I"},
        ]
        
        result = tool_validate_move_legality(
            board_grid=grid,
            placements=placements,
            is_first_move=True,
        )
        
        assert result["valid"] is True
        assert result["checks"]["covers_center"] is True
        assert result["checks"]["in_line"] is True
        assert result["checks"]["no_gaps"] is True

    def test_validate_move_legality_rejects_invalid_move(
        self, empty_board: Board
    ) -> None:
        """Given: Empty board and invalid first move (no center)
        When: Tool validates move legality
        Then: Validation fails
        """
        from scrabgpt.ai.mcp_tools import tool_validate_move_legality

        grid = ["." * 15 for _ in range(15)]
        placements = [
            {"row": 0, "col": 0, "letter": "H"},
            {"row": 0, "col": 1, "letter": "I"},
        ]
        
        result = tool_validate_move_legality(
            board_grid=grid,
            placements=placements,
            is_first_move=True,
        )
        
        assert result["valid"] is False
        assert result["checks"]["covers_center"] is False

    def test_calculate_move_score_returns_total_with_breakdown(self) -> None:
        """Given: Valid move with placements
        When: Tool calculates score
        Then: Total score and breakdown are returned
        """
        from scrabgpt.ai.mcp_tools import tool_calculate_move_score

        grid = ["." * 15 for _ in range(15)]
        placements = [
            {"row": 7, "col": 7, "letter": "C"},
            {"row": 7, "col": 8, "letter": "A"},
            {"row": 7, "col": 9, "letter": "T"},
        ]
        
        result = tool_calculate_move_score(
            board_grid=grid,
            premium_grid=[],
            placements=placements,
        )
        
        assert result["total_score"] >= 0
        assert "breakdowns" in result
        assert len(result["breakdowns"]) > 0
