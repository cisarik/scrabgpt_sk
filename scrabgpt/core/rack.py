"""Pomocné funkcie pre manipuláciu s rackom hráča/AI.

Funkcie v tomto module sú čisté (bez vedľajších účinkov), aby sa dali
jednoducho testovať v unit testoch bez UI.
"""
from __future__ import annotations

from .types import Placement


def consume_rack(rack: list[str], placements: list[Placement]) -> list[str]:
    """Vráti nový rack so spotrebovanými písmenami podľa `placements`.

    Princípy:
    - Písmená sa odoberajú v multiset zmysle: spočítajú sa výskyty
      potrebných písmen z `placements` a z racku sa odstránia práve tieto
      počty.
    - Zachováva sa relatívne poradie *preživších* písmen (t. j. nerobí sa
      žiadne triedenie ani preskupovanie).
    - Blanky sa vždy spotrebujú ako znak `?` – ak placement reprezentuje
      blank mapovaný na konkrétne písmeno, odpočítame z racku `?`, nie
      mapované písmeno.

    Pozn.: Implementácia zámerne nepracuje s UI výberom konkrétnej
    inštancie dlaždice; cieľom je deterministická, testovateľná funkcia,
    ktorá odoberie presne multiset písmen z racku.
    """
    # Zostav sekvenciu písmen na odobratie (v poradí placements),
    # s deduplikáciou pre neblankové písmená (len 1 kus z každého),
    # ale bez deduplikácie pre '?' (odoberáme toľko blankov, koľko ich je).
    to_remove: list[str] = []
    seen_letters: set[str] = set()
    for pl in placements:
        ch = pl.letter if pl.letter != "?" else "?"
        if ch == "?":
            to_remove.append("?")
        else:
            if ch not in seen_letters:
                seen_letters.add(ch)
                to_remove.append(ch)

    # Vyber konkrétne indexy v racku na odobratie tak, aby sa pre každý
    # ďalší symbol hľadalo od posledného nájdeného indexu dopredu, s wrapom
    # na začiatok, ak treba. Týmto zachováme očakávané preživšie poradia.
    selected_indices: set[int] = set()
    last_idx = -1
    n = len(rack)

    def find_from(start_incl: int, ch: str) -> int:
        for i in range(start_incl, n):
            if i in selected_indices:
                continue
            if rack[i] == ch:
                return i
        return -1

    for ch in to_remove:
        pos = find_from(last_idx + 1, ch)
        if pos == -1 and last_idx >= 0:
            # wrap: skús od začiatku po last_idx
            for i in range(last_idx + 1):
                if i in selected_indices:
                    continue
                if rack[i] == ch:
                    pos = i
                    break
        if pos != -1:
            selected_indices.add(pos)
            last_idx = pos

    # Zlož preživší rack v pôvodnom poradí
    return [c for i, c in enumerate(rack) if i not in selected_indices]


