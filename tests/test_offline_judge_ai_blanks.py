from __future__ import annotations

import tempfile
from pathlib import Path

from scrabgpt.core.board import Board
from scrabgpt.core.offline_judge import OfflineJudge


def _premiums_path() -> str:
    root = Path(__file__).resolve().parents[1]
    return str((root / "scrabgpt" / "assets" / "premiums.json").resolve())


def _temp_dict_with(words: list[str]) -> str:
    """Vytvor dočasný wordlist so zadanými slovami (UPPERCASE riadky)."""
    tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
    with tmp as f:
        for w in words:
            f.write(w.upper() + "\n")
    return tmp.name


def test_blank_with_mapping_is_valid() -> None:
    wordfile = _temp_dict_with(["AEROBE"])  # povolíme testované slovo
    j = OfflineJudge.from_path(wordfile)

    board = Board(_premiums_path())
    rack = "AEABE?O"
    move = {
        "row": 7,
        "col": 5,
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 5, "letter": "A"},
            {"row": 7, "col": 6, "letter": "E"},
            {"row": 7, "col": 7, "letter": "?"},
            {"row": 7, "col": 8, "letter": "O"},
            {"row": 7, "col": 9, "letter": "B"},
            {"row": 7, "col": 10, "letter": "E"},
        ],
        "blanks": {"?": "R"},
    }
    res = j.validate_move(board, rack, move)
    assert res.valid, res.reason or "invalid"


def test_letter_in_placements_consume_blank() -> None:
    wordfile = _temp_dict_with(["AEROBE"])  # povolíme testované slovo
    j = OfflineJudge.from_path(wordfile)

    board = Board(_premiums_path())
    rack = "AEABE?O"
    move = {
        "start": {"row": 7, "col": 5},
        "direction": "across",  # case-insensitive
        "placements": [
            {"row": 7, "col": 5, "letter": "A"},
            {"row": 7, "col": 6, "letter": "E"},
            {"row": 7, "col": 7, "letter": "R"},  # AI poslala už mapované písmeno
            {"row": 7, "col": 8, "letter": "O"},
            {"row": 7, "col": 9, "letter": "B"},
            {"row": 7, "col": 10, "letter": "E"},
        ],
        "blanks": {"?": "R"},
    }
    res = j.validate_move(board, rack, move)
    assert res.valid, res.reason or "invalid"


def test_blank_missing_mapping_is_invalid() -> None:
    wordfile = _temp_dict_with(["AEROBE"])  # slovník je nepodstatný; testujeme blank mapovanie
    j = OfflineJudge.from_path(wordfile)

    board = Board(_premiums_path())
    rack = "AEABE?O"
    move = {
        "row": 7,
        "col": 5,
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 5, "letter": "A"},
            {"row": 7, "col": 6, "letter": "E"},
            {"row": 7, "col": 7, "letter": "?"},  # chýba blanks
            {"row": 7, "col": 8, "letter": "O"},
            {"row": 7, "col": 9, "letter": "B"},
            {"row": 7, "col": 10, "letter": "E"},
        ],
    }
    res = j.validate_move(board, rack, move)
    assert not res.valid


def test_double_blank_list_order_valid() -> None:
    # slovník obsahuje ARISE (pouzijeme 2 blanky pre R a S)
    wordfile = _temp_dict_with(["ARISE"])  # UPPERCASE kontrola
    j = OfflineJudge.from_path(wordfile)
    board = Board(_premiums_path())
    rack = "ABE??IO"  # A,E,I + 2 blanky
    move = {
        "row": 7,
        "col": 5,
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 5, "letter": "A"},
            {"row": 7, "col": 6, "letter": "?"},  # R
            {"row": 7, "col": 7, "letter": "I"},
            {"row": 7, "col": 8, "letter": "?"},  # S
            {"row": 7, "col": 9, "letter": "E"},
        ],
        "blanks": ["R", "S"],  # poradie podľa výskytu
    }
    res = j.validate_move(board, rack, move)
    assert res.valid, res.reason or "invalid"


def test_double_blank_coords_map_valid() -> None:
    wordfile = _temp_dict_with(["ARISE"])  # UPPERCASE kontrola
    j = OfflineJudge.from_path(wordfile)
    board = Board(_premiums_path())
    rack = "ABE??IO"
    move = {
        "row": 7,
        "col": 5,
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 5, "letter": "A"},
            {"row": 7, "col": 6, "letter": "?"},  # R
            {"row": 7, "col": 7, "letter": "I"},
            {"row": 7, "col": 8, "letter": "?"},  # S
            {"row": 7, "col": 9, "letter": "E"},
        ],
        "blanks": {"7,6": "R", "7,8": "S"},
    }
    res = j.validate_move(board, rack, move)
    assert res.valid, res.reason or "invalid"


def test_direct_letters_with_available_blanks_valid() -> None:
    wordfile = _temp_dict_with(["ARISE"])  # UPPERCASE
    j = OfflineJudge.from_path(wordfile)
    board = Board(_premiums_path())
    rack = "ABE??IO"
    move = {
        "start": {"row": 7, "col": 5},
        "direction": "across",
        "placements": [
            {"row": 7, "col": 5, "letter": "A"},
            {"row": 7, "col": 6, "letter": "R"},  # spotrebuje '?'
            {"row": 7, "col": 7, "letter": "I"},
            {"row": 7, "col": 8, "letter": "S"},  # spotrebuje druhý '?'
            {"row": 7, "col": 9, "letter": "E"},
        ],
        "blanks": {"?": "X", "7,6": "R", "7,8": "S"},  # '?' key ignorovaný, ale coords rozhodujú
    }
    res = j.validate_move(board, rack, move)
    assert res.valid, res.reason or "invalid"


def test_direct_letter_without_blank_in_rack_invalid() -> None:
    wordfile = _temp_dict_with(["ARISE"])  # slovník ok
    j = OfflineJudge.from_path(wordfile)
    board = Board(_premiums_path())
    rack = "ABEIOOX"  # bez '?'
    move = {
        "row": 7,
        "col": 5,
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 5, "letter": "A"},
            {"row": 7, "col": 6, "letter": "R"},  # chcelo by '?', ale nie je
            {"row": 7, "col": 7, "letter": "I"},
            {"row": 7, "col": 8, "letter": "S"},
            {"row": 7, "col": 9, "letter": "E"},
        ],
        "blanks": {"7,6": "R", "7,8": "S"},
    }
    res = j.validate_move(board, rack, move)
    assert not res.valid
    assert res.reason and res.reason.startswith("rack_missing_tile:R")


def test_direction_case_and_start_down_valid() -> None:
    wordfile = _temp_dict_with(["AX"])  # minimalny slovník
    j = OfflineJudge.from_path(wordfile)
    board = Board(_premiums_path())
    rack = "A?X"
    move = {
        "start": {"row": 7, "col": 7},
        "direction": "down",  # case-insensitive
        "placements": [
            {"row": 7, "col": 7, "letter": "A"},
            {"row": 8, "col": 7, "letter": "?"},  # X
        ],
        "blanks": {"?": "X"},
    }
    res = j.validate_move(board, rack, move)
    assert res.valid, res.reason or "invalid"
