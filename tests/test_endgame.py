from __future__ import annotations

from pathlib import Path

from scrabgpt.core.board import Board
from scrabgpt.core.game import Game, GameEndReason, PlayerState
from scrabgpt.core.tiles import TileBag, get_tile_points
from scrabgpt.core.types import Placement

PREMIUMS_PATH = str((Path(__file__).resolve().parents[1] / "scrabgpt" / "assets" / "premiums.json").resolve())


def test_endgame_bag_empty_player_out() -> None:
    board = Board(PREMIUMS_PATH)
    bag = TileBag()
    bag.tiles = []
    human = PlayerState("Human", list("READING"))
    ai = PlayerState("AI", list("STAPLES"))
    game = Game(board=board, bag=bag, players=[human, ai])

    placements = [Placement(7, 4 + idx, letter) for idx, letter in enumerate("READING")]
    move_score = game.play_move(placements)

    assert game.ended is True
    assert game.end_reason == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT
    assert not human.rack
    assert ai.rack == list("STAPLES")
    points = get_tile_points()
    leftover_ai = sum(points.get(ch, 0) for ch in ai.rack)
    assert game.leftover_points == {"Human": 0, "AI": leftover_ai}
    scores = game.scores()
    assert scores["Human"] == move_score + leftover_ai
    assert scores["AI"] == -leftover_ai


def test_endgame_no_moves_available() -> None:
    board = Board(PREMIUMS_PATH)
    bag = TileBag()
    bag.tiles = []
    human = PlayerState("Human", list("CATERSN"))
    ai = PlayerState("AI", list("SDOGLIN"))
    game = Game(board=board, bag=bag, players=[human, ai])

    placements_human = [Placement(7, 7 + idx, letter) for idx, letter in enumerate("CAT")]
    human_score = game.play_move(placements_human)
    placements_ai = [Placement(6, 8, "S"), Placement(8, 8, "D")]
    ai_score = game.play_move(placements_ai)

    game.declare_no_moves_available()

    assert game.ended is True
    assert game.end_reason == GameEndReason.NO_MOVES_AVAILABLE

    points = get_tile_points()
    leftover_human = sum(points.get(ch, 0) for ch in human.rack)
    leftover_ai = sum(points.get(ch, 0) for ch in ai.rack)
    assert game.leftover_points == {"Human": leftover_human, "AI": leftover_ai}

    scores = game.scores()
    assert scores["Human"] == human_score - leftover_human
    assert scores["AI"] == ai_score - leftover_ai


def test_endgame_all_players_pass_twice() -> None:
    board = Board(PREMIUMS_PATH)
    bag = TileBag(tiles=list("ABCDE"))
    human = PlayerState("Human", list("AEI"))
    ai = PlayerState("AI", list("DG"))
    game = Game(board=board, bag=bag, players=[human, ai])

    game.pass_turn()
    game.pass_turn()
    assert game.ended is False
    game.pass_turn()
    assert game.ended is False
    game.pass_turn()

    assert game.ended is True
    assert game.end_reason == GameEndReason.ALL_PLAYERS_PASSED_TWICE

    points = get_tile_points()
    leftover_human = sum(points.get(ch, 0) for ch in human.rack)
    leftover_ai = sum(points.get(ch, 0) for ch in ai.rack)
    assert game.leftover_points == {"Human": leftover_human, "AI": leftover_ai}
    scores = game.scores()
    assert scores["Human"] == -leftover_human
    assert scores["AI"] == -leftover_ai
