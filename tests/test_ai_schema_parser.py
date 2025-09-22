from __future__ import annotations

import json

import pytest

from scrabgpt.ai.schema import parse_ai_move, to_offline_payload


def test_parse_with_start_and_blanks_coords() -> None:
    payload = {
        "start": {"row": 7, "col": 7},
        "direction": "across",  # case-insensitive
        "placements": [
            {"row": 7, "col": 7, "letter": "?"},
            {"row": 7, "col": 8, "letter": "E"},
        ],
        "blanks": {"7,7": "A"},
    }
    m = parse_ai_move(json.dumps(payload))
    can = to_offline_payload(m)
    assert can["row"] == 7 and can["col"] == 7
    assert can["direction"] == "ACROSS"
    assert isinstance(can["placements"], list) and len(can["placements"]) == 2
    assert can["blanks"] == {"7,7": "A"}


def test_parse_with_row_col_and_upper_direction() -> None:
    payload = {
        "row": 5,
        "col": 10,
        "direction": "DOWN",
        "placements": [
            {"row": 5, "col": 10, "letter": "C"},
            {"row": 6, "col": 10, "letter": "A"},
        ],
    }
    m = parse_ai_move(json.dumps(payload))
    can = to_offline_payload(m)
    assert can["row"] == 5 and can["col"] == 10
    assert can["direction"] == "DOWN"


def test_invalid_letter_too_long_raises() -> None:
    payload = {
        "start": {"row": 0, "col": 0},
        "direction": "ACROSS",
        "placements": [
            {"row": 0, "col": 0, "letter": "AB"},
        ],
    }
    with pytest.raises(ValueError) as ei:
        parse_ai_move(json.dumps(payload))
    assert "letter_len_must_be_1" in str(ei.value)


def test_invalid_direction_raises_in_canonicalization() -> None:
    payload = {
        "start": {"row": 1, "col": 1},
        "direction": "LEFT",
        "placements": [
            {"row": 1, "col": 1, "letter": "A"},
        ],
    }
    m = parse_ai_move(json.dumps(payload))
    with pytest.raises(ValueError) as ei:
        _ = to_offline_payload(m)
    assert "direction_invalid" in str(ei.value)

