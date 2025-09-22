from __future__ import annotations

import logging
import json
from typing import Any

from ..ai.schema import parse_ai_move, to_move_payload
from ..core.board import Board
from ..core.assets import get_premiums_path
from .client import OpenAIClient

log = logging.getLogger("scrabgpt.ai")


def _build_prompt(compact_state: str, retry_hint: str | None) -> str:
    """Zostaví system+user prompt pre AI hráča.

    - Pravidlá explicitne zakazujú neplatné „lepenie" k existujúcim slovám,
      ak výsledný súvislý reťazec nie je platné anglické slovo.
    - Dopĺňa sanity pravidlá a krátky príklad hook vs. zlé lepenie.
    - `retry_hint` (ak je) doplní na koniec promptu.
    """
    def _build_premium_summary() -> str:
        """Vytvorí kompaktný zoznam súradníc prémiových polí.

        Komentár (SK): Čítame `premiums.json` a vraciame krátku vetu,
        ktorú vložíme do promptu pre lepšie rozhodovanie AI.
        """
        try:
            with open(get_premiums_path(), "r", encoding="utf-8") as f:
                data: list[list[str]] = json.load(f)
            tags: dict[str, list[tuple[int, int]]] = {"TW": [], "DW": [], "TL": [], "DL": []}
            for r, row in enumerate(data):
                for c, tag in enumerate(row):
                    if tag in tags:
                        tags[tag].append((r, c))
            def fmt(lst: list[tuple[int, int]]) -> str:
                return "[" + ",".join(f"({r},{c})" for r, c in lst) + "]"
            return (
                "Premiums (0-based row,col): "
                f"TW:{fmt(tags['TW'])}; DW:{fmt(tags['DW'])}; "
                f"TL:{fmt(tags['TL'])}; DL:{fmt(tags['DL'])}."
            )
        except Exception:
            return ""

    prem_summary = _build_premium_summary()

    sys_prompt = (
        "You are an expert Scrabble player. Play to win. Use premium fields of the board like proffesional player would. Reply with JSON only. "
        "Do NOT overwrite existing board letters; place only on EMPTY cells. "
        "Placements must form a single contiguous line with NO GAPS and must connect "
        "to existing letters after the first move. "
        "Use only letters from ai_rack; for '?' provide mapping in 'blanks' with "
        "chosen uppercase letter. "
        "Do not \"glue\" your letters to adjacent existing letters unless the entire "
        "resulting contiguous main string is a valid English word. "
        "Use intersections/hooks properly: you may share letters with the board only "
        "at overlapping cells; do not extend an existing word into a non-word. "
        "The field 'word' must be exactly the final main word formed on the board "
        "(existing board letters + your placements). "
        "Do not overwrite existing tiles; placements must be in one line without gaps; "
        "all cross-words should plausibly be valid English words. "
        "If no valid high-value move exists, you may pass (set 'pass': true). "
        "If the board is empty, your first move must cross the center star at H8. "
        "Coordinates in this JSON are 0-based; the center star (H8) is at row=7,col=7. "
        "The starting move lands on a double-word (DW) premium at the center. "
        "No explanations — JSON only. "
        # Preferovaný jednotný formát výstupu pre ľahšie lokálne parsovanie
        "Always return a JSON object with keys: "
        "start:{row:int,col:int}, direction:'ACROSS'|'DOWN', placements:[{row,col,letter}], "
        "optional blanks mapping where keys are 'row,col' (e.g. '7,7': 'R'), "
        "optional pass (boolean), and optional word (string). If you use '?' in placements, "
        "you must include blanks mapping for each '?'."
    )

    if prem_summary:
        # Kompaktné vysvetlenie prémií + stručné odporúčanie pre maximalizáciu skóre
        sys_prompt += (
            " "
            + prem_summary
            + " Prioritize TL/DL for high-value letters and aim to span DW/TW "
              "with the main word when possible; stacking letter multipliers "
              "that feed into word multipliers yields maximal score. "
              "Prefer TW (x3 word) if reachable, or combine multiple word multipliers "
              "in one move when legal (e.g., DW+DW=4x, TW+TW=9x). Also value high-scoring "
              "cross-words created by your placements."
        )

    rules = (
        "Sanity rules:\n"
        "- Place in exactly one line (ACROSS or DOWN); no gaps.\n"
        "- Do not extend existing words unless the whole resulting contiguous main word is valid.\n"
        "- Prefer hooks/intersections (overlaps) rather than blind prefix/suffix sticking.\n"
        "- 'word' must equal the final main word on the board.\n"
        "- Provide 'blanks' mapping for any '?' used.\n"
        "Examples:\n"
        "- Valid hook: existing TEE, place N at the end -> TEEN (if allowed).\n"
        "- Invalid: place WHAT before TEE -> WHATEE (not a word) — forbidden.\n"
    )

    user_prompt = (
        "Given this compact state, propose exactly one move with placements in a single line.\n"
        f"{rules}"
        f"State:\n{compact_state}"
    )

    if retry_hint:
        user_prompt += f"\nHINT:{retry_hint}"

    return sys_prompt + "\n" + user_prompt


def propose_move(
    client: OpenAIClient,
    compact_state: str,
    *,
    retry_hint: str | None = None,
) -> dict[str, Any]:
    """Zavolá OpenAI, parsuje odpoveď lokálne a normalizuje payload.

    Komentár (SK): Nepoužívame serverovú JSON schému; spoliehame sa na
    lokálne pydantic parsovanie `parse_ai_move` a konverziu na kanonický
    formát vhodný pre validáciu a UI. Pri chybných dátach spravíme jeden
    riadený retry. Výstup obsahuje aj kľúč `exchange` (prázdny zoznam)
    kvôli UI kompatibilite.
    """

    prompt = _build_prompt(compact_state, retry_hint)
    raw = client._call_text(prompt, max_output_tokens=client.ai_move_max_output_tokens)
    try:
        model = parse_ai_move(raw)
        move = to_move_payload(model)
    except Exception as e:  # noqa: BLE001
        log.warning("ai_parse_failed reason=%s raw=%r", e, (raw or "")[:300])
        hint = (
            "Return a strict JSON object with keys start,row/col,direction,placements,"
            "optional blanks mapping by 'row,col', optional pass. No prose."
        )
        retry_prompt = _build_prompt(compact_state, retry_hint=hint)
        raw2 = client._call_text(retry_prompt, max_output_tokens=client.ai_move_max_output_tokens)
        model = parse_ai_move(raw2)
        move = to_move_payload(model)

    # Kompatibilita s UI – udržiavaj 'exchange' kľúč (prázdny zoznam)
    if "exchange" not in move:
        move["exchange"] = []
    return move


def is_board_empty(board: Board) -> bool:
    """Zistí, či je doska prázdna (bez jediného písmena).

    Komentár (SK): Čistá pomocná funkcia bez UI závislostí, vhodná do testov.
    """
    for r in range(15):
        for c in range(15):
            if board.cells[r][c].letter:
                return False
    return True


def should_auto_trigger_ai_opening(starting_side: str, board_empty: bool) -> bool:
    """Vracia True, ak sa má automaticky spustiť AI na prázdnej doske.

    - Spúšťa sa, len ak začína AI a doska je prázdna.
    """
    return starting_side.upper() == "AI" and bool(board_empty)
