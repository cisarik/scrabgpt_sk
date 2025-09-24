from scrabgpt.core.tiles import TileBag, get_tile_distribution
from scrabgpt.core.variant_store import list_installed_variants


EXPECTED_TILE_COUNTS: dict[str, int] = {
    "english": 100,
    "slovak": 108,
}


def test_bag_total_count() -> None:
    variants = list_installed_variants()
    found_slugs = {variant.slug for variant in variants}
    missing_expectations = sorted(found_slugs - EXPECTED_TILE_COUNTS.keys())
    assert not missing_expectations, (
        "Add expected tile totals for new variants:"
        f" {', '.join(missing_expectations)}"
    )

    for variant in variants:
        distribution = get_tile_distribution(variant)
        assert sum(distribution.values()) == EXPECTED_TILE_COUNTS[variant.slug]


def test_draw_putback() -> None:
    bag = TileBag(seed=42)
    hand = bag.draw(7)
    assert len(hand) == 7
    before = bag.remaining()
    bag.put_back(hand)
    assert bag.remaining() == before + 7


def test_deterministic_first_rack_same_seed() -> None:
    """Pre rovnaký seed musí byť prvý odber 7 kameňov identický.

    Cieľ: reprodukovateľnosť pre Analytic Programming.
    """
    seed = 12345
    b1 = TileBag(seed=seed)
    b2 = TileBag(seed=seed)
    assert b1.draw(7) == b2.draw(7)
