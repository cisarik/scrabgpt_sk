from __future__ import annotations

from pathlib import Path

from scrabgpt.core.board import Board
from scrabgpt.core.scoring import apply_premium_consumption
from scrabgpt.core.state import (
    build_save_state_dict,
    parse_save_state_dict,
    restore_bag_from_save,
    restore_board_from_save,
)
from scrabgpt.core.tiles import TileBag
from scrabgpt.core.types import Placement


ASSETS = Path(__file__).resolve().parents[1] / "scrabgpt" / "assets"
PREMIUMS_PATH = str((ASSETS / "premiums.json").resolve())


def _place_simple_word(board: Board) -> list[Placement]:
    # Polož "CAT" cez stred (8,7)-(8,9) ACROSS pre deterministický test
    ps = [
        Placement(7, 7, "C"),
        Placement(7, 8, "A"),
        Placement(7, 9, "T"),
    ]
    board.place_letters(ps)
    # Simuluj spotrebovanie prémií po potvrdení ťahu
    apply_premium_consumption(board, ps)
    return ps


def test_round_trip_save_load_preserves_state_and_bag_order() -> None:
    # Inicializuj deterministicku tasku
    bag = TileBag(seed=123)
    human_rack = bag.draw(7)
    ai_rack = bag.draw(7)

    board = Board(PREMIUMS_PATH)
    placements = _place_simple_word(board)

    # Stav skóre a meta
    human_score = 10
    ai_score = 5
    last_move_points = 10
    consecutive_passes = 1

    # Ulož
    st = build_save_state_dict(
        board=board,
        human_rack=human_rack,
        ai_rack=ai_rack,
        bag=bag,
        human_score=human_score,
        ai_score=ai_score,
        turn="HUMAN",
        last_move_cells=[(p.row, p.col) for p in placements],
        last_move_points=last_move_points,
        consecutive_passes=consecutive_passes,
        repro=True,
        seed=123,
    )

    # Validuj JSON dict
    st2 = parse_save_state_dict(st)  # type: ignore[arg-type]
    assert st2["schema_version"] == "1"

    # Obnov board a tašku
    board2 = restore_board_from_save(st2, PREMIUMS_PATH)
    bag2 = restore_bag_from_save(st2)

    # Over grid identicky
    for r in range(15):
        for c in range(15):
            a = board.cells[r][c]
            b = board2.cells[r][c]
            assert a.letter == b.letter
            assert a.is_blank == b.is_blank
            assert a.premium_used == b.premium_used

    # Over racky a poradie v taške
    assert st2["human_rack"] == "".join(human_rack)
    assert st2["ai_rack"] == "".join(ai_rack)
    assert st2["bag"] == "".join(bag.tiles)
    assert bag2.tiles == bag.tiles  # presne rovnake poradie

    # Over skóre a meta
    assert st2["human_score"] == human_score
    assert st2["ai_score"] == ai_score
    assert st2["turn"] == "HUMAN"
    assert st2["variant"] == bag.variant_slug
    assert st2["last_move_points"] == last_move_points
    assert st2["consecutive_passes"] == consecutive_passes
    # zvýraznenie posledného ťahu
    lm = {(p.row, p.col) for p in placements}
    lm2 = {(pos["row"], pos["col"]) for pos in st2["last_move_cells"]}
    assert lm == lm2

