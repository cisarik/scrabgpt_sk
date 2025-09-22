from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scrabgpt.ai.schema import parse_ai_move, to_offline_payload
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


def test_e2e_blank_mapping_coords() -> None:
    # Wordlist s AEROBE
    wordfile = _temp_dict_with(["AEROBE"])  # malý slovník
    judge = OfflineJudge.from_path(wordfile)
    b = Board(_premiums_path())

    # AI odpoveď: prvé písmeno ako '?', mapované cez coords
    resp = {
        "start": {"row": 7, "col": 7},
        "direction": "across",
        "placements": [
            {"row": 7, "col": 7, "letter": "?"},
            {"row": 7, "col": 8, "letter": "E"},
            {"row": 7, "col": 9, "letter": "R"},
            {"row": 7, "col": 10, "letter": "O"},
            {"row": 7, "col": 11, "letter": "B"},
            {"row": 7, "col": 12, "letter": "E"},
        ],
        "blanks": {"7,7": "A"},
    }
    rack = list("?EROBEZ")

    model = parse_ai_move(json.dumps(resp))
    payload = to_offline_payload(model)
    res = validate_and_apply_ai_move(b, rack, judge, payload)
    assert res.valid
    # over prítomnosť písmen na doske
    assert b.cells[7][7].letter in ("?", "A")  # po aplikácii uložené ako '?' s blank_as
    assert b.cells[7][8].letter == "E"
    assert b.cells[7][12].letter == "E"


def test_e2e_use_blank_when_letter_not_in_rack() -> None:
    # Wordlist s AEROBE
    wordfile = _temp_dict_with(["AEROBE"])  # malý slovník
    judge = OfflineJudge.from_path(wordfile)
    b = Board(_premiums_path())

    # AI odpoveď: priamo písmeno 'A' na začiatku, ale v racku nie je 'A'
    # (k dispozícii je '?', ktorú mapujeme cez blanks). Toto musí prejsť.
    resp = {
        "start": {"row": 7, "col": 7},
        "direction": "ACROSS",
        "placements": [
            {"row": 7, "col": 7, "letter": "A"},
            {"row": 7, "col": 8, "letter": "E"},
            {"row": 7, "col": 9, "letter": "R"},
            {"row": 7, "col": 10, "letter": "O"},
            {"row": 7, "col": 11, "letter": "B"},
            {"row": 7, "col": 12, "letter": "E"},
        ],
        "blanks": {"7,7": "A"},
    }
    rack = list("?EROBEZ")  # nie je 'A', ale je '?' s mapovaním

    model = parse_ai_move(json.dumps(resp))
    payload = to_offline_payload(model)
    res = validate_and_apply_ai_move(b, rack, judge, payload)
    assert res.valid
    assert b.cells[7][7].letter in ("?", "A")

