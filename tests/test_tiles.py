
from scrabgpt.core.tiles import DISTRIBUTION, TileBag

def test_bag_total_count():
    assert sum(DISTRIBUTION.values()) == 100

def test_draw_putback():
    bag = TileBag(seed=42)
    hand = bag.draw(7)
    assert len(hand) == 7
    before = bag.remaining()
    bag.put_back(hand)
    assert bag.remaining() == before + 7

def test_deterministic_first_rack_same_seed():
    """Pre rovnaký seed musí byť prvý odber 7 kameňov identický.

    Cieľ: reprodukovateľnosť pre Analytic Programming.
    """
    seed = 12345
    b1 = TileBag(seed=seed)
    b2 = TileBag(seed=seed)
    assert b1.draw(7) == b2.draw(7)
