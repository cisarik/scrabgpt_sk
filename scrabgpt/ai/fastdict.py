from __future__ import annotations

import unicodedata as ud
from pathlib import Path
from typing import Callable

def _nfc_casefold(s: str) -> str:
    """Zachová diakritiku, len zjednotí veľkosť písmen a normalizuje Unicode."""
    return ud.normalize("NFC", s).casefold()

def load_dictionary(
    path: str | Path,
    *,
    normalize: Callable[[str], str] | None = _nfc_casefold,
    comment_prefix: str = "#",
) -> Callable[[str], bool]:
    """Načíta slová (1 slovo na riadok) do pamäte a vráti rýchlu contains(word) funkciu.

    - Riadky začínajúce comment_prefix sa ignorujú.
    - Orezáva sa whitespace; prázdne riadky sa ignorujú.
    - Predvolené normalize: NFC + casefold (rozlišuje diakritiku, nerozlišuje veľkosť písmen).
      Ak chceš presnú zhodu aj s veľkosťou písmen -> normalize=None.
    """
    path = Path(path)
    words: set[str] = set()

    with path.open("r", encoding="utf-8", errors="strict") as f:
        for line in f:
            if comment_prefix and line.startswith(comment_prefix):
                continue
            w = line.strip()
            if not w:
                continue
            words.add(normalize(w) if normalize else w)

    frozen_words = frozenset(words)

    if normalize:
        def contains(word: str) -> bool:
            return normalize(word) in frozen_words
    else:
        def contains(word: str) -> bool:
            return word in frozen_words

    return contains
