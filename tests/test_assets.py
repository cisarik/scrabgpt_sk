from __future__ import annotations

from scrabgpt.core.assets import get_assets_path, get_premiums_path


def test_assets_paths_exist() -> None:
    assets = get_assets_path()
    assert assets.name == "assets"
    premiums = get_premiums_path()
    assert premiums.endswith("premiums.json")

