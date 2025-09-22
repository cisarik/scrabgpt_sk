
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

# Pozn.: Vsetky komentare su v slovencine podla preferencii pouzivatela.

class Direction(Enum):
    """Smer kladenia slova na doske."""
    ACROSS = auto()
    DOWN = auto()

@dataclass(frozen=True)
class Placement:
    """Jedno pismeno polozene v tomto tahu na suradnicu (row, col)."""
    row: int
    col: int
    letter: str   # 'A'..'Z' alebo '?' pre blank
    # Ak je to blank a uz bolo pouzite ako konkretne pismeno, ulozime jeho vyznam
    blank_as: str | None = None

@dataclass
class Move:
    """Navrh tahu (vsetky pismena v jednej linii)."""
    placements: list[Placement]

@dataclass
class WordFound:
    """Reprezentacia jedneho vzniknuteho slova na doske s jeho suradnicami."""
    word: str
    letters: list[tuple[int, int]]  # zoznam buniek tvoriacich slovo (row, col)

@dataclass
class ScoreBreakdown:
    """Detailne skore jedneho slova."""
    word: str
    base_points: int
    letter_bonus_points: int
    word_multiplier: int
    total: int

class Premium(Enum):
    """Premiove polia na doske."""
    DL = auto()  # Double Letter
    TL = auto()  # Triple Letter
    DW = auto()  # Double Word
    TW = auto()  # Triple Word

TilePoints = dict[str, int]
