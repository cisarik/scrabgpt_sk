"""Pomocné funkcie pre prístup k assetom (napr. premiums.json).

Komentár (SK): Používame Path pre robustné zostavenie ciest nezávislé od cwd.
"""

from __future__ import annotations

from pathlib import Path


def get_assets_path() -> Path:
    """Vráti cestu k priečinku `assets/` v projekte.

    Nájde sa relatívne k tomuto modulu (`scrabgpt/core/assets.py`).
    """

    return Path(__file__).resolve().parent.parent / "assets"


def get_premiums_path() -> str:
    """Úplná cesta k súboru `premiums.json` (ako textová cesta).

    Vracia sa `str` kvôli kompatibilite s existujúcimi volaniami.
    """

    return str(get_assets_path() / "premiums.json")


