from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterable, Sequence

from .board import Board
from .rack import consume_rack
from .rules import (
    connected_to_existing,
    first_move_must_cover_center,
    no_gaps_in_line,
    placements_in_line,
)
from .scoring import apply_premium_consumption, score_words
from .tiles import TileBag, get_tile_points
from .types import Placement


class GameEndReason(Enum):
    """Dôvod ukončenia partie."""

    BAG_EMPTY_AND_PLAYER_OUT = auto()
    NO_MOVES_AVAILABLE = auto()
    ALL_PLAYERS_PASSED_TWICE = auto()


@dataclass
class PlayerState:
    """Lokalný stav hráča pre simuláciu partie bez UI."""

    name: str
    rack: list[str] = field(default_factory=list)
    score: int = 0
    pass_streak: int = 0

    def rack_points(self) -> int:
        """Obratková hodnota nepoužitých písmen."""

        points = get_tile_points()
        return sum(points.get(letter, 0) for letter in self.rack)


def determine_end_reason(
    *,
    bag_remaining: int,
    racks: dict[str, Sequence[str]],
    pass_streaks: dict[str, int],
    no_moves_available: bool,
) -> GameEndReason | None:
    """Vyhodnotí, či hra končí a vráti dôvod podľa definovaných pravidiel."""

    if bag_remaining == 0 and any(len(rack) == 0 for rack in racks.values()):
        return GameEndReason.BAG_EMPTY_AND_PLAYER_OUT
    if no_moves_available:
        return GameEndReason.NO_MOVES_AVAILABLE
    if racks and all(pass_streaks.get(name, 0) >= 2 for name in racks):
        return GameEndReason.ALL_PLAYERS_PASSED_TWICE
    return None


def apply_final_scoring(players: Iterable[PlayerState]) -> dict[str, int]:
    """Upraví skóre hráčov podľa nepoužitých písmen a vráti mapu bodových odpočtov."""

    leftover: dict[str, int] = {player.name: player.rack_points() for player in players}
    finisher = next((player for player in players if not player.rack), None)
    total_bonus = sum(value for value in leftover.values())

    for player in players:
        player.score -= leftover[player.name]
    if finisher is not None:
        player_bonus = total_bonus - leftover[finisher.name]
        finisher.score += player_bonus
    return leftover


class Game:
    """Jednoduchá simulácia Scrabble partie pre testovanie koncovky."""

    def __init__(
        self,
        *,
        board: Board,
        bag: TileBag,
        players: Sequence[PlayerState],
        starting_index: int = 0,
    ) -> None:
        if not players:
            raise ValueError("Game vyžaduje aspoň jedného hráča")
        self.board = board
        self.bag = bag
        self.players: list[PlayerState] = list(players)
        self.current_index = starting_index % len(self.players)
        self.ended: bool = False
        self.end_reason: GameEndReason | None = None
        self.leftover_points: dict[str, int] = {}
        self._no_moves_available: bool = False

    def current_player(self) -> PlayerState:
        return self.players[self.current_index]

    def _has_any_letters(self) -> bool:
        return any(cell.letter for row in self.board.cells for cell in row)

    def _advance_turn(self) -> None:
        self.current_index = (self.current_index + 1) % len(self.players)

    def play_move(self, placements: Sequence[Placement]) -> int:
        """Aplikuje ťah aktuálneho hráča vrátane skórovania a doplnenia racku."""

        if self.ended:
            raise RuntimeError("Partia je už ukončená")
        if not placements:
            raise ValueError("Ťah musí obsahovať aspoň jedno písmeno")
        player = self.current_player()

        # Over základné pravidlá umiestnenia
        direction = placements_in_line(list(placements))
        if direction is None:
            raise ValueError("Ťah musí byť v jednom riadku alebo stĺpci")
        if not self._has_any_letters():
            if not first_move_must_cover_center(list(placements)):
                raise ValueError("Prvý ťah musí prejsť stredom")
        else:
            if not connected_to_existing(self.board, list(placements)):
                raise ValueError("Ťah musí nadväzovať na existujúce písmená")
        if not no_gaps_in_line(self.board, list(placements), direction):
            raise ValueError("Ťah má medzery v hlavnej línii")
        for placement in placements:
            cell = self.board.cells[placement.row][placement.col]
            if cell.letter:
                raise ValueError("Pole je už obsadené")

        placements_list = list(placements)
        self.board.place_letters(placements_list)
        words_found = self.board.build_words_for_move(placements_list)
        words_coords = [(wf.word, wf.letters) for wf in words_found]
        if not words_coords:
            raise ValueError("Ťah nevytvoril platné slovo")

        total, _ = score_words(self.board, placements_list, words_coords)
        if len(placements_list) == 7:
            total += 50
        apply_premium_consumption(self.board, placements_list)
        player.score += total
        player.rack = consume_rack(player.rack, placements_list)
        draw_count = max(0, 7 - len(player.rack))
        if draw_count and self.bag.remaining():
            drawn = self.bag.draw(min(draw_count, self.bag.remaining()))
            player.rack.extend(drawn)
        player.pass_streak = 0
        self._no_moves_available = False

        self._evaluate_endgame()
        if not self.ended:
            self._advance_turn()
        return total

    def pass_turn(self) -> None:
        if self.ended:
            raise RuntimeError("Partia je už ukončená")
        player = self.current_player()
        player.pass_streak += 1
        self._advance_turn()
        self._evaluate_endgame()

    def declare_no_moves_available(self) -> None:
        if self.ended:
            return
        self._no_moves_available = True
        self._evaluate_endgame()

    def _evaluate_endgame(self) -> None:
        if self.ended:
            return
        reason = determine_end_reason(
            bag_remaining=self.bag.remaining(),
            racks={player.name: player.rack for player in self.players},
            pass_streaks={player.name: player.pass_streak for player in self.players},
            no_moves_available=self._no_moves_available,
        )
        if reason is None:
            return
        self.end_reason = reason
        self.leftover_points = apply_final_scoring(self.players)
        self.ended = True

    def scores(self) -> dict[str, int]:
        return {player.name: player.score for player in self.players}
