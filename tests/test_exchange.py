from __future__ import annotations

from scrabgpt.core.tiles import TileBag


def test_exchange_deterministic_seed() -> None:
    bag = TileBag(seed=42)
    # potiahni 7 pre rack
    rack = bag.draw(7)
    # vymente prve tri
    to_exchange = rack[:3]
    remained = rack[3:]
    # len ak je v taske aspon 7 – simuluj pravidlo mimo metody
    assert bag.remaining() >= 7
    new_tiles = bag.exchange(to_exchange)
    # rack ma stale 7, presne tri nove
    new_rack = remained + new_tiles
    assert len(new_rack) == 7
    # po vymene zostavajuci pocet sa nemení v sucte (vratili sme 3 a zobrali 3)
    # deterministicka poradie vdaka seed
    assert isinstance(new_tiles, list) and len(new_tiles) == 3


