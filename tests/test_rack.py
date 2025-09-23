from __future__ import annotations

from scrabgpt.core.rack import consume_rack, restore_rack
from scrabgpt.core.types import Placement
from scrabgpt.core.tiles import TileBag


def test_consume_rack_simple() -> None:
    # Vstupný rack a ťah "DOLL". Očakávané preživšie písmená zachovajú svoj
    # RELATÍVNY poriadok.
    rack = list("LDSVDOL")
    placements = [
        Placement(row=7, col=7, letter="D"),
        Placement(row=7, col=8, letter="O"),
        Placement(row=7, col=9, letter="L"),
        Placement(row=7, col=10, letter="L"),
    ]
    out = consume_rack(rack, placements)
    assert out == ["L", "S", "V", "D"], out


def test_consume_rack_blank_mapping() -> None:
    # Blank sa má spotrebovať ako '?' – nie mapované písmeno.
    rack = list("E?A")
    placements = [Placement(row=5, col=5, letter="?", blank_as="E")]
    out = consume_rack(rack, placements)
    # Ostáva 'E' a 'A' v rovnakom poradí -> ["E", "A"]
    assert out == ["E", "A"], out


def test_refill_from_bag_seeded() -> None:
    # Po spotrebe K písmen doplníme K z tašky so seedom a overíme dĺžky.
    bag = TileBag(seed=123)
    rack = list("ABCDEFG")
    k = 3
    placements = [
        Placement(row=7, col=7, letter="A"),
        Placement(row=7, col=8, letter="B"),
        Placement(row=7, col=9, letter="C"),
    ]
    before_remaining = bag.remaining()
    consumed = consume_rack(rack, placements)
    drawn = bag.draw(k)
    refilled = consumed + drawn
    assert len(refilled) == len(rack)
    assert bag.remaining() == before_remaining - k


def test_restore_rack_returns_pending_letters() -> None:
    rack = list("AEIRST?")
    mutated = rack.copy()
    # simuluj UI – po položení odstránime konkrétne písmená z racku
    mutated.remove("A")
    mutated.remove("?")
    placements = [
        Placement(row=7, col=7, letter="A"),
        Placement(row=7, col=8, letter="?", blank_as="E"),
    ]
    restored = restore_rack(mutated, placements)
    assert restored[:len(mutated)] == mutated
    assert restored[-2:] == ["A", "?"]
    assert sorted(restored) == sorted(rack)


def test_restore_rack_handles_duplicates() -> None:
    rack = list("AABBCD")
    mutated = rack.copy()
    mutated.remove("A")
    mutated.remove("B")
    mutated.remove("B")
    placements = [
        Placement(row=7, col=7, letter="A"),
        Placement(row=7, col=8, letter="B"),
        Placement(row=7, col=9, letter="B"),
    ]
    restored = restore_rack(mutated, placements)
    assert sorted(restored) == sorted(rack)
    assert restored[-3:] == ["A", "B", "B"]

