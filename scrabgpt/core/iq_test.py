"""IQ test format for offline AI evaluation.

An IQ test captures a game state and the expected best move that a human
would make if they were playing as AI. Tests are used to verify the AI
can find optimal or near-optimal moves without requiring live OpenAI calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

from scrabgpt.core.board import Board
from scrabgpt.core.assets import get_premiums_path
from scrabgpt.core.types import Placement


class IQTestMove(TypedDict):
    """Expected move for an IQ test."""
    placements: list[dict[str, int | str]]
    direction: str
    word: str
    score: int
    blanks: dict[str, str] | None


class IQTest(TypedDict):
    """IQ test format (schema v1)."""
    schema_version: str
    name: str
    description: str
    grid: list[str]
    blanks: list[dict[str, int]]
    premium_used: list[dict[str, int]]
    ai_rack: str
    variant: str
    expected_move: IQTestMove


def create_iq_test(
    *,
    name: str,
    description: str,
    board: Board,
    ai_rack: list[str],
    expected_placements: list[Placement],
    expected_direction: str,
    expected_word: str,
    expected_score: int,
    expected_blanks: dict[tuple[int, int], str] | None,
    variant_slug: str,
) -> IQTest:
    """Create an IQ test from current game state and expected move."""
    grid: list[str] = []
    blanks: list[dict[str, int]] = []
    premium_used: list[dict[str, int]] = []
    
    for r in range(15):
        row_chars: list[str] = []
        for c in range(15):
            cell = board.cells[r][c]
            if getattr(cell, "premium_used", False):
                premium_used.append({"row": r, "col": c})
            if cell.letter:
                row_chars.append(cell.letter)
                if cell.is_blank:
                    blanks.append({"row": r, "col": c})
            else:
                row_chars.append(".")
        grid.append("".join(row_chars))
    
    [
        {"row": p.row, "col": p.col, "letter": p.letter}
        for p in expected_placements
    ]
    
    blanks_data = None
    if expected_blanks:
        blanks_data = {f"{r},{c}": letter for (r, c), letter in expected_blanks.items()}
    
    placements_typed = cast(list[dict[str, int | str]], [{"row": p.row, "col": p.col, "letter": p.letter} for p in expected_placements])
    move_data: IQTestMove = {
        "placements": placements_typed,
        "direction": expected_direction,
        "word": expected_word,
        "score": expected_score,
        "blanks": blanks_data,
    }
    return {
        "schema_version": "1",
        "name": name,
        "description": description,
        "grid": grid,
        "blanks": blanks,
        "premium_used": premium_used,
        "ai_rack": "".join(ai_rack),
        "variant": variant_slug,
        "expected_move": move_data,
    }


def save_iq_test(test: IQTest, path: Path) -> None:
    """Save IQ test to file."""
    with path.open("w", encoding="utf-8") as f:
        json.dump(test, f, indent=2, ensure_ascii=False)


def load_iq_test(path: Path) -> IQTest:
    """Load IQ test from file."""
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert data.get("schema_version") == "1", "Unsupported IQ test schema"
    assert isinstance(data.get("grid"), list) and len(data["grid"]) == 15
    
    return cast(IQTest, data)


def restore_board_from_iq_test(test: IQTest) -> Board:
    """Restore board state from IQ test."""
    board = Board(get_premiums_path())
    
    for r in range(15):
        row = test["grid"][r]
        for c in range(15):
            ch = row[c]
            if ch != ".":
                board.cells[r][c].letter = ch
                board.cells[r][c].is_blank = False
    
    for pos in test.get("blanks", []):
        rr, cc = pos["row"], pos["col"]
        if board.cells[rr][cc].letter:
            board.cells[rr][cc].is_blank = True
    
    for pos in test.get("premium_used", []):
        rr, cc = pos["row"], pos["col"]
        board.cells[rr][cc].premium_used = True
    
    return board
