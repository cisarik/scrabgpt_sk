from __future__ import annotations

from pathlib import Path

from scrabgpt.core.board import Board
from scrabgpt.core.types import Placement
from scrabgpt.ai.player import is_board_empty, should_auto_trigger_ai_opening


def _premiums_path() -> str:
    # tests/ -> repo root -> scrabgpt/assets/premiums.json
    root = Path(__file__).resolve().parents[1]
    return str(root / "scrabgpt" / "assets" / "premiums.json")


def test_is_board_empty_true_false() -> None:
    b = Board(_premiums_path())
    assert is_board_empty(b) is True
    # Polož jedno písmeno a over, že už nie je prázdna
    b.place_letters([Placement(row=7, col=7, letter="A")])
    assert is_board_empty(b) is False


def test_should_auto_trigger_ai_opening() -> None:
    assert should_auto_trigger_ai_opening("AI", True) is True
    assert should_auto_trigger_ai_opening("AI", False) is False
    assert should_auto_trigger_ai_opening("HUMAN", True) is False
    assert should_auto_trigger_ai_opening("human", True) is False

