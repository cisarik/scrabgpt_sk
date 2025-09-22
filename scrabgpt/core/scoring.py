from __future__ import annotations

from .board import Board
from .tiles import get_tile_points
from .types import Placement, Premium, ScoreBreakdown


def score_words(
    board: Board,
    placements: list[Placement],
    words_coords: list[tuple[str, list[tuple[int, int]]]],
) -> tuple[int, list[ScoreBreakdown]]:
    """Vypocita celkove skore tahu a vrati aj rozpis pre jednotlive slova.
    `words_coords` je zoznam (slovo, zoznam buniek).
    Prémie DL/TL/DW/TW sa uplatnia len na novych pismenach (placements).
    """
    placed = {(p.row, p.col): p for p in placements}
    total_score = 0
    breakdowns: list[ScoreBreakdown] = []

    # pomocna mapa pre rychle zistenie, ci bunka je nova
    new_cells = set(placed.keys())

    tile_points = get_tile_points()

    for word, coords in words_coords:
        word_multiplier = 1
        word_points = 0
        letter_bonus = 0
        for (r,c) in coords:
            cell = board.cells[r][c]
            letter = cell.letter or ""
            base = 0 if cell.is_blank else tile_points.get(letter, 0)
            # ak je to nova bunka, mozeme uplatnit prémie poli
            if (r,c) in new_cells and cell.premium and not cell.premium_used:
                if cell.premium == Premium.DL:
                    letter_bonus += base  # +1x dalsi nasobok (2x celkovo)
                elif cell.premium == Premium.TL:
                    letter_bonus += base * 2  # +2x (3x celkovo)
                elif cell.premium == Premium.DW:
                    word_multiplier *= 2
                elif cell.premium == Premium.TW:
                    word_multiplier *= 3
            word_points += base
        total = (word_points + letter_bonus) * word_multiplier
        total_score += total
        breakdowns.append(
            ScoreBreakdown(
                word=word,
                base_points=word_points,
                letter_bonus_points=letter_bonus,
                word_multiplier=word_multiplier,
                total=total,
            )
        )
    return total_score, breakdowns

def apply_premium_consumption(board: Board, placements: list[Placement]) -> None:
    """Po potvrdeni tahu oznac prémie novych buniek ako pouzite."""
    for p in placements:
        cell = board.cells[p.row][p.col]
        if cell.premium:
            cell.premium_used = True
