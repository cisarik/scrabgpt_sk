
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .types import Direction, Placement, Premium, WordFound

BOARD_SIZE = 15

@dataclass
class Cell:
    """Bunka na doske."""
    letter: str | None = None  # 'A'..'Z' uz ulozene
    is_blank: bool = False        # ci povodne bola '?'
    premium: Premium | None = None  # DL/TL/DW/TW
    premium_used: bool = False    # prémie sa uplatnia len pri prvom polozeni

class Board:
    """Model scrabble dosky 15x15 s premiami."""
    def __init__(self, premiums_path: str) -> None:
        self.cells: list[list[Cell]] = [
            [Cell() for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)
        ]
        self._load_premiums(premiums_path)

    def _load_premiums(self, path: str) -> None:
        # Bez zmeny správania: použijeme Path a kontext manažér
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                tag = data[r][c]
                if tag == "DL":
                    self.cells[r][c].premium = Premium.DL
                elif tag == "TL":
                    self.cells[r][c].premium = Premium.TL
                elif tag == "DW":
                    self.cells[r][c].premium = Premium.DW
                elif tag == "TW":
                    self.cells[r][c].premium = Premium.TW

    def inside(self, row: int, col: int) -> bool:
        return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE

    def get_letter(self, row: int, col: int) -> str | None:
        return self.cells[row][col].letter

    def place_letters(self, placements: list[Placement]) -> None:
        """Aplikuje pismena na dosku (bez validacii pravidiel)."""
        for p in placements:
            cell = self.cells[p.row][p.col]
            cell.letter = (p.blank_as or p.letter)
            cell.is_blank = (p.letter == "?")
            # Prémie sa oznacia ako pouzite po tomto tahu v score(), nie tu.

    def clear_letters(self, placements: list[Placement]) -> None:
        """Odstrani pismena (pouzite pri 'Undo' pred potvrdenim')."""
        for p in placements:
            cell = self.cells[p.row][p.col]
            cell.letter = None
            cell.is_blank = False
            # premium_used nechavame bez zmeny, lebo sa aplikuje az po potvrdeni tahu

    def letters_in_line(self, placements: list[Placement]) -> Direction | None:
        """Zisti, ci su vsetky nove pismena v jednom riadku alebo stlpci."""
        rows = {p.row for p in placements}
        cols = {p.col for p in placements}
        if len(rows) == 1:
            return Direction.ACROSS
        if len(cols) == 1:
            return Direction.DOWN
        return None

    def extend_word(self, row: int, col: int, direction: Direction) -> list[tuple[int, int]]:
        """Vrati suradnice celeho slova prechadzajuceho danym polom v danom smere."""
        dr, dc = (0,1) if direction == Direction.ACROSS else (1,0)
        # posun dolava/nahor
        r, c = row, col
        while self.inside(r - dr, c - dc) and self.get_letter(r - dr, c - dc):
            r -= dr
            c -= dc
        coords: list[tuple[int, int]] = []
        # dopln doprava/nadol
        while self.inside(r, c) and self.get_letter(r, c):
            coords.append((r, c))
            r += dr
            c += dc
        return coords

    def build_words_for_move(self, placements: list[Placement]) -> list[WordFound]:
        """Najde hlavne + vsetky nove krizove slova po polozenej sade pismen.
        Predpoklad: pismena su uz provizorne na doske.
        """
        words: dict[tuple[int, int, Direction], WordFound] = {}
        direction = self.letters_in_line(placements)
        if direction is None:
            return []

        # hlavne slovo: vyhladame cez akukolvek novu bunku v smere dir
        r0, c0 = placements[0].row, placements[0].col
        main_coords = self.extend_word(r0, c0, direction)
        if len(main_coords) >= 2:
            w = ''.join(self.get_letter(r, c) or '' for r,c in main_coords)
            words[(main_coords[0][0], main_coords[0][1], direction)] = WordFound(w, main_coords)

        # krizove slova: pre kazdu novu dlazdicu pozri opacny smer
        cross_dir = Direction.DOWN if direction == Direction.ACROSS else Direction.ACROSS
        for p in placements:
            coords = self.extend_word(p.row, p.col, cross_dir)
            if len(coords) >= 2:  # jednopismenne sa nepocita
                w = ''.join(self.get_letter(r, c) or '' for r,c in coords)
                words[(coords[0][0], coords[0][1], cross_dir)] = WordFound(w, coords)

        return list(words.values())
