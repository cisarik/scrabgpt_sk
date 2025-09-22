from __future__ import annotations

import tempfile
from pathlib import Path

from scrabgpt.core.board import Board
from scrabgpt.core.ai_offline import validate_and_apply_ai_move
from scrabgpt.core.offline_judge import OfflineJudge


def _premiums_path() -> str:
    root = Path(__file__).resolve().parents[1]
    return str((root / "scrabgpt" / "assets" / "premiums.json").resolve())


def _temp_dict_with(words: list[str]) -> str:
    tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
    with tmp as f:
        for w in words:
            f.write(w.upper() + "\n")
    return tmp.name


def test_validate_and_apply_ai_move_success() -> None:
    wordfile = _temp_dict_with(["CAT"])  # jednoduchý slovník
    judge = OfflineJudge.from_path(wordfile)
    b = Board(_premiums_path())
    rack = list("CATZZZZ")
    proposal = {
        "row": 7,
        "col": 7,
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 7, "letter": "C"},
            {"row": 7, "col": 8, "letter": "A"},
            {"row": 7, "col": 9, "letter": "T"},
        ],
    }
    res = validate_and_apply_ai_move(b, rack, judge, proposal)
    assert res.valid
    # over, že písmená sú na doske
    assert b.cells[7][7].letter == "C"
    assert b.cells[7][8].letter == "A"
    assert b.cells[7][9].letter == "T"


def test_validate_and_apply_ai_move_invalid() -> None:
    wordfile = _temp_dict_with(["CAT"])  # len CAT, nie COT
    judge = OfflineJudge.from_path(wordfile)
    b = Board(_premiums_path())
    rack = list("COTZZZZ")
    proposal = {
        "row": 7,
        "col": 7,
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 7, "letter": "C"},
            {"row": 7, "col": 8, "letter": "O"},
            {"row": 7, "col": 9, "letter": "T"},
        ],
    }
    res = validate_and_apply_ai_move(b, rack, judge, proposal)
    assert not res.valid
    assert res.reason and res.reason.startswith("word_not_in_dict:")
    # doska by mala ostať prázdna
    assert b.cells[7][7].letter is None
