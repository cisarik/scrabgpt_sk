from __future__ import annotations

import json

import pytest

from scrabgpt.ai.schema import parse_ai_move, to_move_payload


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
    m, method = parse_ai_move(json.dumps(payload))
    assert method == "direct"
    can = to_move_payload(m)
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
    m, method = parse_ai_move(json.dumps(payload))
    assert method == "direct"
    can = to_move_payload(m)
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
    m, _ = parse_ai_move(json.dumps(payload))
    with pytest.raises(ValueError) as ei:
        _ = to_move_payload(m)
    assert "direction_invalid" in str(ei.value)


def test_pass_without_placements_is_allowed() -> None:
    payload = {"pass": True}
    m, method = parse_ai_move(json.dumps(payload))
    assert method == "direct"
    can = to_move_payload(m)
    assert can["pass"] is True
    assert can["placements"] == []


def test_pass_with_tiles_is_rejected() -> None:
    payload = {
        "pass": True,
        "placements": [{"row": 7, "col": 7, "letter": "A"}],
    }
    with pytest.raises(ValueError) as ei:
        parse_ai_move(json.dumps(payload))
    assert "pass_move_must_not_have_placements" in str(ei.value)


def test_missing_placements_without_pass_is_rejected() -> None:
    payload = {"start": {"row": 7, "col": 7}, "direction": "ACROSS"}
    with pytest.raises(ValueError) as ei:
        parse_ai_move(json.dumps(payload))
    assert "placements_required_for_play" in str(ei.value)


def test_parse_json_wrapped_in_markdown_block() -> None:
    """Test parsovania JSON wrapped v ```json ... ```"""
    payload = {
        "start": {"row": 8, "col": 2},
        "direction": "ACROSS",
        "placements": [
            {"row": 8, "col": 2, "letter": "F"},
            {"row": 8, "col": 3, "letter": "L"},
        ],
    }
    
    # Simuluj odpoveď s markdown blokom
    response = f"```json\n{json.dumps(payload)}\n```"
    
    m, method = parse_ai_move(response)
    assert method == "direct"  # Odstránenie na začiatku/konci sa počíta ako direct
    can = to_move_payload(m)
    assert can["row"] == 8 and can["col"] == 2
    assert can["direction"] == "ACROSS"
    assert len(can["placements"]) == 2


def test_parse_json_with_reasoning_text_before() -> None:
    """Test parsovania JSON keď pred ním je reasoning text (ako na screenshote)"""
    payload = {
        "start": {"row": 8, "col": 2},
        "direction": "ACROSS",
        "placements": [
            {"row": 8, "col": 2, "letter": "F"},
            {"row": 8, "col": 3, "letter": "L"},
            {"row": 8, "col": 4, "letter": "O"},
            {"row": 8, "col": 5, "letter": "R"},
            {"row": 8, "col": 6, "letter": "A"},
        ],
        "word": "FLORA",
    }
    
    # Simuluj odpoveď ako na screenshote - reasoning text pred JSON blokom
    response = """Let me play ORAL across at row 8, using existing letters if any:
ORAL at (8,6) going across: O(8,6), R(8,7), A(8,8), L(8,9)
This intersects with I at (7,7)... no, (8,7) is below (7,7).

Playing FLORA down from (4,7): F(4,7), L(5,7), O(6,7), R(7,7), A(8,7)
But (7,7) has 'I' not 'R'.

Let me play AFLOAT or similar. Actually, with ?QOFALR, I can make FLORA, FOAL, ORAL, LOAF.

Playing LOAF down from (5,7): L(5,7), O(6,7), A(7,7), F(8,7)
But (7,7) has 'I'.

Playing ORAL across from (7,9): O(7,9), R(7,10), A(7,11), L(7,12)
This extends from WIN to make WINORAL (not valid).

Let me play a separate word: FLORA at row 8 starting at column 2:
F(8,2), L(8,3), O(8,4), R(8,5), A(8,6)

```json
{"start":{"row":8,"col":2},"direction":"ACROSS","placements":[{"row":8,"col":2,"letter":"F"},{"row":8,"col":3,"letter":"L"},{"row":8,"col":4,"letter":"O"},{"row":8,"col":5,"letter":"R"},{"row":8,"col":6,"letter":"A"}],"word":"FLORA"}
```"""
    
    m, method = parse_ai_move(response)
    assert method == "markdown_extraction"  # Extrahované z markdown bloku vo vnútri textu
    can = to_move_payload(m)
    assert can["row"] == 8 and can["col"] == 2
    assert can["direction"] == "ACROSS"
    assert len(can["placements"]) == 5
    assert can["word"] == "FLORA"


def test_parse_json_without_markdown_still_works() -> None:
    """Test že priamy JSON (bez markdown) stále funguje"""
    payload = {
        "start": {"row": 7, "col": 7},
        "direction": "DOWN",
        "placements": [
            {"row": 7, "col": 7, "letter": "T"},
            {"row": 8, "col": 7, "letter": "E"},
        ],
    }
    
    # Priamy JSON bez markdown
    response = json.dumps(payload)
    
    m, method = parse_ai_move(response)
    assert method == "direct"
    can = to_move_payload(m)
    assert can["row"] == 7 and can["col"] == 7
    assert can["direction"] == "DOWN"
    assert len(can["placements"]) == 2


def test_parse_multiple_markdown_blocks_uses_first() -> None:
    """Test že ak je viac markdown blokov, použije sa prvý"""
    payload1 = {
        "start": {"row": 7, "col": 7},
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 7, "letter": "A"},
        ],
    }
    payload2 = {
        "start": {"row": 8, "col": 8},
        "direction": "DOWN",
        "placements": [
            {"row": 8, "col": 8, "letter": "B"},
        ],
    }
    
    response = f"""
Here's option 1:
```json
{json.dumps(payload1)}
```

Or option 2:
```json
{json.dumps(payload2)}
```
"""
    
    m, method = parse_ai_move(response)
    assert method == "markdown_extraction"
    can = to_move_payload(m)
    # Mal by použiť prvý blok
    assert can["row"] == 7 and can["col"] == 7
    assert can["placements"][0]["letter"] == "A"


def test_parse_inline_json_without_code_block() -> None:
    """Parser má nájsť JSON objekt mimo markdown blokov (inline fallback)."""
    payload = {
        "start": {"row": 9, "col": 3},
        "direction": "ACROSS",
        "placements": [
            {"row": 9, "col": 3, "letter": "S"},
            {"row": 9, "col": 4, "letter": "K"},
            {"row": 9, "col": 5, "letter": "A"},
        ],
        "word": "SKA",
    }
    response = (
        "Here's my thought process:\n"
        "- Trying to connect existing tiles\n"
        "- Ensuring I use high-value letters\n"
        "Final move proposal:\n"
        f"{json.dumps(payload)}\n"
        "This should score solid points."
    )

    m, method = parse_ai_move(response)
    assert method == "inline_json"
    can = to_move_payload(m)
    assert can["row"] == 9 and can["col"] == 3
    assert can["direction"] == "ACROSS"
    assert len(can["placements"]) == 3
