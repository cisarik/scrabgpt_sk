
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .types import TilePoints

# Bodove hodnoty pismen pre anglicky Scrabble (oficialne)
TILE_POINTS: TilePoints = {
    **{c: 1 for c in "AEILNORSTU"},
    **{c: 2 for c in "DG"},
    **{c: 3 for c in "BCMP"},
    **{c: 4 for c in "FHVWY"},
    "K": 5,
    **{c: 8 for c in "JX"},
    **{c: 10 for c in "QZ"},
    "?": 0,  # blank
}

# Distribucia dlazdic
DISTRIBUTION = {
    "A": 9, "B": 2, "C": 2, "D": 4, "E": 12, "F": 2, "G": 3, "H": 2, "I": 9,
    "J": 1, "K": 1, "L": 4, "M": 2, "N": 6, "O": 8, "P": 2, "Q": 1, "R": 6,
    "S": 4, "T": 6, "U": 4, "V": 2, "W": 2, "X": 1, "Y": 2, "Z": 1, "?": 2,
}

@dataclass
class TileBag:
    """Taška s pismenami s deterministickym RNG pre TDD a reprodukovatelnost."""
    seed: int | None = None
    tiles: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Pozn.: Ak su poskytnute `tiles`, zachovaj ich presne v danom poradi
        # (pouzite pri load-e hry). Inak napln podla distribucie a premiešaj.
        if not self.tiles:
            for ch, count in DISTRIBUTION.items():
                self.tiles.extend([ch] * count)
            self._rng = random.Random(self.seed)
            self._rng.shuffle(self.tiles)
        else:
            self._rng = random.Random(self.seed)

    def draw(self, n: int) -> list[str]:
        """Potiahne n kociek (alebo menej, ak taška je prazdna)."""
        out, self.tiles = self.tiles[:n], self.tiles[n:]
        return out

    def put_back(self, letters: list[str]) -> None:
        """Vrati kocky spat (pouzivane pri zrebe startu)."""
        self.tiles.extend(letters)
        self._rng.shuffle(self.tiles)

    def exchange(self, letters: list[str]) -> list[str]:
        """Vymeni zadane pismena: vrati ich do tasky a potiahne rovnaky pocet.

        Pozn.: Neaplikuje pravidlo minimalne 7 v taske – to nech rieši volajúci.
        Vrati presne tolko pismen ako vstup.
        """
        # vrat najprv do tasky, potom miesaj a potiahni
        count = len(letters)
        self.put_back(letters)
        return self.draw(count)

    def remaining(self) -> int:
        return len(self.tiles)
