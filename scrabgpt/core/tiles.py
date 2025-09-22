
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .types import TilePoints
from .variant_store import VariantDefinition, get_active_variant, load_variant


def _resolve_variant(variant: VariantDefinition | str | None) -> VariantDefinition:
    if isinstance(variant, VariantDefinition):
        return variant
    if isinstance(variant, str) and variant:
        return load_variant(variant)
    return get_active_variant()


def get_tile_points(variant: VariantDefinition | str | None = None) -> TilePoints:
    """Vráti bodové hodnoty písmen pre daný (alebo aktívny) variant."""

    resolved = _resolve_variant(variant)
    return dict(resolved.tile_points)


def get_tile_distribution(variant: VariantDefinition | str | None = None) -> dict[str, int]:
    """Vráti distribúciu písmen pre daný (alebo aktívny) variant."""

    resolved = _resolve_variant(variant)
    return dict(resolved.distribution)

@dataclass
class TileBag:
    """Taška s písmenami, ktorá rešpektuje aktívny Scrabble variant."""

    seed: int | None = None
    tiles: list[str] = field(default_factory=list)
    variant: VariantDefinition | str | None = None

    def __post_init__(self) -> None:
        self._variant = _resolve_variant(self.variant)
        self.variant = self._variant
        self.variant_slug = self._variant.slug
        # Pozn.: Ak sú poskytnuté `tiles`, zachovaj ich presne v danom poradí
        # (použité pri load-e hry). Inak naplň podľa distribúcie a premiešaj.
        if not self.tiles:
            for ch, count in self._variant.distribution.items():
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
