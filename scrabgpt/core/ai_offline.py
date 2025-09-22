"""Pomocník pre AI cestu s offline validáciou.

Táto utilita zjednodušuje testovanie vetvy: "AI návrh -> offline validate_move -> apply".
Neobsahuje žiadne Qt závislosti.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .board import Board
from .offline_judge import OfflineJudge, ValidateResult


def validate_and_apply_ai_move(
    board: Board,
    rack: list[str] | str,
    judge: OfflineJudge,
    proposal: Mapping[str, Any],
) -> ValidateResult:
    """Overí AI návrh cez OfflineJudge a pri úspechu aplikuje na dosku.

    Komentár (SK): Funkcia vracia priamo `ValidateResult`. Pri `valid=True`
    už boli `placements` aplikované na `board`. Pri `valid=False` sa doska
    nemení a `reason` popisuje dôvod.
    """
    res = judge.validate_move(board, rack, proposal)
    if not res.valid:
        return res
    assert res.placements is not None
    board.place_letters(res.placements)
    return res
