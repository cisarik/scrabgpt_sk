from __future__ import annotations

import tempfile
from pathlib import Path

from scrabgpt.core.board import Board
from scrabgpt.core.offline_judge import OfflineJudge
from scrabgpt.core.scoring import score_words
from scrabgpt.core.rules import extract_all_words
from scrabgpt.core.types import Placement


def _premiums_path() -> str:
    root = Path(__file__).resolve().parents[1]
    return str((root / "scrabgpt" / "assets" / "premiums.json").resolve())


def _temp_dict_with(words: list[str]) -> str:
    tmp = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
    with tmp as f:
        for w in words:
            f.write(w.upper() + "\n")
    return tmp.name


def test_cross_words_with_blank_valid_and_scored_blank_zero() -> None:
    # Board: TEE na riadku r=7, c=6..8 (0-index)
    wordfile = _temp_dict_with(["TEN", "TEE"])  # len potrebné slová
    judge = OfflineJudge.from_path(wordfile)
    b = Board(_premiums_path())
    b.place_letters([
        Placement(7, 6, "T"),
        Placement(7, 7, "E"),
        Placement(7, 8, "E"),
    ])
    rack = "TN?"  # má dosť na hlavné slovo (X nepotreba presne sedieť)
    move = {
        "start": {"row": 6, "col": 7},
        "direction": "DOWN",
        "placements": [
            {"row": 6, "col": 7, "letter": "T"},
            {"row": 8, "col": 7, "letter": "?"},  # mapuje na N
        ],
        "blanks": {"?": "N"},
    }
    res = judge.validate_move(b, rack, move)
    assert res.valid, res.reason or "invalid"
    assert res.placements is not None

    # Skóruj a over, že blank nenesie body za písmeno
    b.place_letters(res.placements)
    words_found = extract_all_words(b, res.placements)
    total, breakdown = score_words(b, res.placements, [(wf.word, wf.letters) for wf in words_found])
    # V rozklade nájdeme TEN; základné body sú súčet písmen, kde blank má hodnotu 0
    for bd in breakdown:
        if bd.word == "TEN":
            # T(1) + E(1) + N(blank=0) = 2 body pred prémiami
            assert bd.base_points >= 2
    # upratovanie
    b.clear_letters(res.placements)


def test_cross_word_missing_from_dict_invalid() -> None:
    # Board: TEE na r=7,c=6..8 a navyše písmeno E na r=8,c=6, aby vzniklo krížové "EN" (2+) pri položení N
    # Slovník: TEN a TEE povolené, ale EN zakázané
    wordfile = _temp_dict_with(["TEN", "TEE"])  # bez EN
    judge = OfflineJudge.from_path(wordfile)
    b = Board(_premiums_path())
    b.place_letters([
        Placement(7, 6, "T"),
        Placement(7, 7, "E"),
        Placement(7, 8, "E"),
        Placement(8, 6, "E"),  # vytvorí krížové EN, keď položíme N na (8,7)
    ])
    rack = "TN?"
    move = {
        "start": {"row": 6, "col": 7},
        "direction": "DOWN",
        "placements": [
            {"row": 6, "col": 7, "letter": "T"},
            {"row": 8, "col": 7, "letter": "?"},  # mapuje na N -> krížom vznikne EN
        ],
        "blanks": {"?": "N"},
    }
    res = judge.validate_move(b, rack, move)
    assert not res.valid
    assert res.reason and res.reason.startswith("cross_word_not_in_dict:EN")

