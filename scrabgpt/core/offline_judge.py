from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .board import Board
from .rules import (
    connected_to_existing,
    extract_all_words,
    first_move_must_cover_center,
    no_gaps_in_line,
    placements_in_line,
)
from .types import Direction, Placement

"""Offline rozhodca pre Scrabble (ENABLE wordlist).

Tento modul poskytuje jednoduché offline overovanie slov podľa wordlistu
ENABLE (public domain). Súbor sa očakáva v používateľskom adresári
`~/.scrabgpt/wordlists/enable1.txt` (alebo na ceste určenej volajúcim).

Poznámky:
- Wordlist sa načítava do pamäte ako `set[str]` v UPPERCASE (A–Z).
- Overovanie je case-insensitive; vstupné slovo sa pred porovnaním
  normalizuje na UPPERCASE a ponechajú sa iba znaky A–Z.
- Blanky (`?`) sa majú rozvinúť ešte pred validáciou; tento modul očakáva
  hotové písmená (bez `?`).
"""
log = logging.getLogger("scrabgpt")


def get_default_enable_cache_path() -> str:
    """Vráti predvolenú cestu k ENABLE wordlistu v home priečinku.

    Príklad: `~/.scrabgpt/wordlists/enable1.txt`
    """
    home = Path.home()
    return str(home / ".scrabgpt" / "wordlists" / "enable1.txt")


@dataclass
class ValidateResult:
    """Výsledok validácie ťahu.

    - valid: či je ťah platný
    - reason: stručný kód dôvodu neplatnosti (alebo None pri úspechu)
    - placements: znormalizované placements pripravené na `Board.place_letters()`
      (blanky majú `letter='?'` a `blank_as` nastavené na mapované písmeno).
    """

    valid: bool
    reason: str | None = None
    placements: list[Placement] | None = None


class OfflineJudge:
    """Jednoduchý offline rozhodca nad wordlistom.

    Atribúty:
        words: množina povolených slov v UPPERCASE.
    """

    def __init__(self, words: set[str]) -> None:
        self.words: set[str] = words

    @staticmethod
    def _normalize(word: str) -> str:
        """Normalizuje slovo na UPPERCASE a ponechá iba A–Z.

        Blanky sa neočakávajú – musia byť rozvinuté pred volaním.
        """
        # Rýchla normalizácia len ASCII písmen
        return "".join(ch for ch in word.upper() if "A" <= ch <= "Z")

    @classmethod
    def from_path(cls, path: str) -> OfflineJudge:
        """Načíta wordlist zo súboru a vytvorí inštanciu.

        Každý riadok = jedno slovo; prázdne riadky a komentáre sa ignorujú.
        """
        words: set[str] = set()
        with Path(path).open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                w = cls._normalize(line.strip())
                if not w:
                    continue
                words.add(w)
        return cls(words)

    def contains(self, word: str) -> bool:
        """Vracia True, ak je `word` v wordliste (case-insensitive).

        Očakáva sa, že `word` už neobsahuje blank `?` (je rozvinutý).
        """
        if not word:
            return False
        # Ak sa do validácie dostal znak '?' (blank), považuj za neplatné
        # podľa zmluvy modulu: blanky majú byť rozvinuté ešte pred volaním.
        if "?" in word:
            return False
        w = self._normalize(word)
        return w in self.words

    def count(self) -> int:
        """Počet slov v aktuálne načítanom wordliste."""
        return len(self.words)


    # ---------------- Zjednotená validácia ťahu ----------------
    def validate_move(
        self,
        board: Board,
        rack: str | list[str],
        move: Mapping[str, Any],
        *,
        check_dict: bool = True,
    ) -> ValidateResult:
        """Overí ťah podľa pravidiel, racku a (voliteľne) slovníka.

        Komentár (SK):
        - Normalizuje vstup (podporí `start` aj `row`/`col`, rôzne formy `blanks`).
        - Pri tvorbe slovníkových reťazcov vždy používa mapované písmená namiesto `?`.
        - Pri spotrebe racku blank vždy odpočíta ako `?`.
        """
        m = _normalize_move_payload(move)
        direction_str = m["direction"]
        # Guard: smer musi byt ACROSS alebo DOWN
        if direction_str not in ("ACROSS", "DOWN"):
            return ValidateResult(False, "direction_invalid")
        direction = Direction.ACROSS if direction_str == "ACROSS" else Direction.DOWN
        blanks = m.get("blanks")

        # 1) Základná kontrola vstupov a rozsahov
        try:
            raw_ps: list[dict[str, Any]] = cast(list[dict[str, Any]], m.get("placements", []))
            ps_in: list[Placement] = [
                Placement(int(p["row"]), int(p["col"]), str(p["letter"]).strip())
                for p in raw_ps
            ]
        except Exception:
            return ValidateResult(False, "invalid_placements_format")

        for p in ps_in:
            if not (0 <= p.row < 15 and 0 <= p.col < 15):
                return ValidateResult(False, "out_of_bounds")
            if board.cells[p.row][p.col].letter:
                return ValidateResult(False, "cell_occupied")

        dir_detected = placements_in_line(ps_in)
        if dir_detected is None:
            return ValidateResult(False, "not_in_one_line")
        if dir_detected != direction:
            return ValidateResult(False, "direction_mismatch")
        if not no_gaps_in_line(board, ps_in, direction):
            return ValidateResult(False, "gaps_in_line")

        has_any = any(board.cells[r][c].letter for r in range(15) for c in range(15))
        if not has_any:
            if not first_move_must_cover_center(ps_in):
                return ValidateResult(False, "first_move_must_cover_center")
        else:
            if not connected_to_existing(board, ps_in):
                return ValidateResult(False, "not_connected")

        # 2) Rack kontrola a rozvinutie blankov
        rack_list: list[str] = list(rack) if isinstance(rack, str) else list(rack)
        rack_counter = Counter(ch.upper() for ch in rack_list)

        def _coord_allows_blank(row: int, col: int, ch: str) -> bool:
            if blanks is None:
                return False
            try:
                if isinstance(blanks, dict):
                    coord_key = f"{row},{col}"
                    if coord_key in blanks and str(blanks[coord_key]).strip().upper() == ch:
                        return True
                    if "?" in blanks and str(blanks["?"]).strip().upper() == ch:
                        return True
            except Exception:
                return False
            return False

        blank_ord = 0
        ps_out: list[Placement] = []
        for p in ps_in:
            ch = p.letter.strip().upper()
            # Guard: pismeno musi byt presne 1 znak
            if len(ch) != 1:
                return ValidateResult(False, "letter_len_must_be_1")
            if ch == "?":
                mapped = _resolve_blank_letter_for_pos(p.row, p.col, blanks, blank_ord)
                if not mapped:
                    return ValidateResult(False, "blank_has_no_mapping")
                if rack_counter["?"] <= 0:
                    return ValidateResult(False, "rack_missing_blank_for_mapping")
                rack_counter["?"] -= 1
                ps_out.append(Placement(p.row, p.col, "?", blank_as=mapped))
                blank_ord += 1
            else:
                if rack_counter[ch] > 0:
                    rack_counter[ch] -= 1
                    ps_out.append(Placement(p.row, p.col, ch))
                elif rack_counter["?"] > 0 and _coord_allows_blank(p.row, p.col, ch):
                    rack_counter["?"] -= 1
                    ps_out.append(Placement(p.row, p.col, "?", blank_as=ch))
                else:
                    return ValidateResult(False, f"rack_missing_tile:{ch}")

        # 3) Zostavenie slov a slovníková kontrola
        board.place_letters(ps_out)
        try:
            words_found = extract_all_words(board, ps_out)
        finally:
            board.clear_letters(ps_out)

        if check_dict:
            # Rozliš cross-wordy od hlavného slova pre presnejší dôvod
            def _orientation(letters: list[tuple[int, int]]) -> Direction | None:
                rows = {r for (r, _c) in letters}
                cols = {c for (_r, c) in letters}
                if len(rows) == 1:
                    return Direction.ACROSS
                if len(cols) == 1:
                    return Direction.DOWN
                return None

            for wf in words_found:
                w = wf.word
                if len(w) < 2:
                    continue
                if not self.contains(w.upper()):
                    ori = _orientation(wf.letters)
                    if ori == direction:
                        return ValidateResult(False, f"word_not_in_dict:{w}")
                    return ValidateResult(False, f"cross_word_not_in_dict:{w}")

        return ValidateResult(True, None, ps_out)



def should_use_offline_judge(is_offline_enabled: bool, wordlist_loaded: bool) -> bool:
    """Rozhodne, ci pouzit offline rozhodcu.

    Pravidlo:
    - Vracia True iba ak je offline rezim zapnuty a wordlist je nacitany.
    - Ak je OFFLINE zapnuty, ale wordlist nie je nacitany, vrati False
      (volajuci moze spustit stiahnutie alebo zalogovat dovod fallbacku).

    Args:
        is_offline_enabled: Ci je v UI/konfiguracii zapnuty offline rezim.
        wordlist_loaded: Ci je instncia `OfflineJudge`/wordlist realne k dispozicii.

    Returns:
        True ak sa ma pouzit offline judge, inak False.
    """
    return bool(is_offline_enabled and wordlist_loaded)


# ------------------------- Pomocné utility -------------------------
def _normalize_move_payload(move: Mapping[str, Any]) -> dict[str, Any]:
    """Znormalizuje AI move payload na jednotný tvar.

    Ak je move vo forme:
      - {'row': int, 'col': int} alebo {'start': {'row': int, 'col': int}}
      - 'placements': [{'row': int, 'col': int, 'letter': str}, ...]
      - 'direction': 'ACROSS'|'DOWN' (case-insensitive)
      - 'blanks': mapa alebo zoznam (podporované varianty)
    Vráti dict s kľúčmi:
      - 'row', 'col', 'direction' (uppercase), 'placements', 'blanks'
    """
    if "start" in move and isinstance(move["start"], Mapping):
        start = cast(Mapping[str, Any], move["start"])
        row = int(start.get("row", 0))
        col = int(start.get("col", 0))
    else:
        row = int(move.get("row", 0))
        col = int(move.get("col", 0))

    direction = str(move.get("direction", "ACROSS")).strip().upper()

    placements_obj = move.get("placements", [])
    placements: list[dict[str, Any]] = []
    if isinstance(placements_obj, list):
        def _to_int(v: Any) -> int | None:
            try:
                return int(v)
            except Exception:
                return None

        for p in placements_obj:
            m = cast(Mapping[str, Any], p) if isinstance(p, Mapping) else None
            if m is None:
                placements.append(cast(dict[str, Any], p))
                continue
            r = _to_int(m.get("row"))
            c = _to_int(m.get("col"))
            letter = str(m.get("letter", "")).strip()
            if r is None or c is None:
                placements.append(cast(dict[str, Any], p))
            else:
                placements.append({"row": r, "col": c, "letter": letter})

    blanks = move.get("blanks", None)
    return {
        "row": row,
        "col": col,
        "direction": direction,
        "placements": placements,
        "blanks": blanks,
        "word": move.get("word"),
    }


def _resolve_blank_letter_for_pos(
    row: int, col: int, blanks: Any, ordinal_index: int
) -> str | None:
    """Z `blanks` vráti mapované písmeno pre blank na danej pozícii.

    Podporované formy `blanks`:
      - dict s kľúčom '?' -> 'R' (single blank)
      - dict s kľúčom f"{row},{col}" -> 'R'
      - dict s kľúčmi '?1','?2',... (indexované podľa poradia výskytu blankov)
      - list/tuple -> písmená podľa poradia výskytu blankov v placements
    Vráti uppercase písmeno alebo None, ak sa nenašlo.
    """
    if blanks is None:
        return None
    if isinstance(blanks, dict):
        coord_key = f"{row},{col}"
        if coord_key in blanks:
            return str(blanks[coord_key]).strip().upper() or None
        if "?" in blanks:
            return str(blanks["?"]).strip().upper() or None
        key = f"?{ordinal_index+1}"
        if key in blanks:
            return str(blanks[key]).strip().upper() or None
        return None
    if isinstance(blanks, list | tuple) and 0 <= ordinal_index < len(blanks):
        return str(blanks[ordinal_index]).strip().upper() or None
    return None
