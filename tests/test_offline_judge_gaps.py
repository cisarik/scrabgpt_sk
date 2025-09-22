from __future__ import annotations

import tempfile
from pathlib import Path

from scrabgpt.core.board import Board
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


def test_no_gaps_in_line_invalid() -> None:
    wordfile = _temp_dict_with(["AXE"])  # slovník je nedôležitý, testujeme diery
    j = OfflineJudge.from_path(wordfile)
    b = Board(_premiums_path())
    rack = "AXEZZZZ"
    move = {
        "row": 7,
        "col": 5,
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 5, "letter": "A"},
            # diera na (7,6)
            {"row": 7, "col": 7, "letter": "X"},
        ],
    }
    res = j.validate_move(b, rack, move)
    assert not res.valid
    assert res.reason == "gaps_in_line"


def test_mixed_directions_in_one_move_invalid() -> None:
    wordfile = _temp_dict_with(["AT"])  # slovník ok
    j = OfflineJudge.from_path(wordfile)
    b = Board(_premiums_path())
    rack = "ATZZZZZ"
    # placements nie sú v jednej línii => invalid
    move = {
        "row": 7,
        "col": 5,
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 5, "letter": "A"},
            {"row": 8, "col": 5, "letter": "T"},
        ],
    }
    res = j.validate_move(b, rack, move)
    assert not res.valid
    # môže byť not_in_one_line alebo direction_mismatch v závislosti od implementácie
    assert res.reason in ("not_in_one_line", "direction_mismatch")

