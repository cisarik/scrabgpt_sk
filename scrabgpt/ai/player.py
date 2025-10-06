from __future__ import annotations

import logging
import json
import os
from pathlib import Path
from typing import Any

from ..ai.schema import parse_ai_move, to_move_payload
from ..core.board import Board
from ..core.assets import get_premiums_path
from ..core.variant_store import VariantDefinition
from .client import OpenAIClient

log = logging.getLogger("scrabgpt.ai")


def _load_prompt_template() -> str:
    """Load AI prompt template from file specified in .env or use default."""
    prompt_file = os.getenv("AI_PROMPT_FILE", "prompts/default.txt")
    
    try:
        path = Path(prompt_file)
        if path.exists():
            return path.read_text(encoding="utf-8")
        else:
            log.warning("Prompt file not found: %s, using fallback", prompt_file)
    except Exception as e:
        log.exception("Failed to load prompt from %s: %s", prompt_file, e)
    
    # Fallback to embedded default if file loading fails
    return """You are an expert Scrabble player for the {language} language variant. Play to win and obey official Scrabble rules for that language. Do NOT overwrite existing board letters; place only on empty cells. Placements must form a single contiguous line with no gaps and must connect to existing letters after previous move. Use only letters from ai_rack; for '?' use chosen uppercase letter (respecting diacritics). Points you can get for each tile: {tile_summary}. Always evaluate moves that use all 7 rack tiles for the 50 point bingo bonus; play it when legal. Prefer the move that maximizes total points, spending high-value rack letters on premium squares. Do not glue your letters to adjacent existing letters unless the resulting main word is a valid {language} word. Use intersections/hooks properly; you may share letters with the board only at overlapping cells; do not extend an existing word into a non-word. The field 'word' must equal the final main word formed on the board (existing board letters plus your placements). All cross-words should plausibly be valid {language} words. Diacritics is very important so distinguishing between 'Ú' and 'U' for example and every letter with diacritic. ONLY If no legal move exists, you may pass (set 'pass': true) but it's better to gain some points then pass. If the board is empty, the first move must cross the center star at H8 (row=7,col=7). Coordinates are 0-based. No explanations — JSON only. Always return a JSON object with keys: start:{{row:int,col:int}}, direction:'ACROSS'|'DOWN', placements:[{{row,col,letter}}]. Empty premium squares in the grid already show their multiplier symbol (see legend). Prioritize TL/DL for high-value letters and aim to span DW/TW with the main word when possible; stacking letter multipliers that feed into word multipliers yields maximal score. Also value high-scoring cross-words created by your placements.

Given this compact state, propose exactly one move with placements in a single line using only valid {language} words.

Sanity rules:
- Place tiles in exactly one line (ACROSS or DOWN); no gaps.
- Do not extend existing words unless the resulting contiguous main word is valid in {language}.
- Prefer hooks/intersections instead of blind prefix/suffix sticking.
- 'word' must equal the final main word on the board.

State:
{compact_state}

Premium legend: {premium_legend}"""


def _format_tile_summary(variant: VariantDefinition) -> str:
    entries = []
    for letter in variant.letters:
        entries.append(f"{letter.letter}:{letter.points}")
    return ", ".join(entries)


def _build_prompt(compact_state: str, variant: VariantDefinition) -> str:
    """Zostaví prompt pre AI hráča načítaním šablóny zo súboru.
    
    Šablóna je načítaná zo súboru definovaného v AI_PROMPT_FILE (.env).
    Podporuje placeholdery: {language}, {tile_summary}, {compact_state}, {premium_legend}
    """
    def _overlay_premiums(state: str) -> tuple[str, str] | None:
        """Vráti stav s prémiami priamo v gride a legendu symbolov.

        - Pre prázdne prémiové políčka nahradí '.' symbolom z legendy.
        - Obsadené políčka nechá bez zmeny, aby ostali pôvodné písmená.
        """

        trailing_newline = state.endswith("\n")
        lines = state.splitlines()

        try:
            grid_idx = lines.index("grid:")
        except ValueError:
            return None

        grid_rows = lines[grid_idx + 1 : grid_idx + 16]
        if len(grid_rows) != 15:
            return None

        try:
            with open(get_premiums_path(), "r", encoding="utf-8") as f:
                premium_layout: list[list[str]] = json.load(f)
        except Exception:
            return None

        if len(premium_layout) != 15 or any(len(row) != 15 for row in premium_layout):
            return None

        symbol_map: dict[str, str] = {"TW": "*", "DW": "~", "TL": "$", "DL": "^"}
        new_grid_rows: list[str] = []
        for r, row in enumerate(grid_rows):
            if len(row) != 15:
                return None
            new_row_chars: list[str] = []
            for c, ch in enumerate(row):
                if ch != ".":
                    new_row_chars.append(ch)
                    continue

                tag = premium_layout[r][c]
                symbol = symbol_map.get(tag)
                new_row_chars.append(symbol if symbol else ".")

            new_grid_rows.append("".join(new_row_chars))

        lines[grid_idx + 1 : grid_idx + 16] = new_grid_rows
        updated_state = "\n".join(lines)
        if trailing_newline:
            updated_state += "\n"

        legend = "*=TW (word*3), ~=DW (word*2), $=TL (letter*3), ^=DL (letter*2)"
        return updated_state, legend

    # Process state to overlay premium symbols
    overlay = _overlay_premiums(compact_state)
    if overlay:
        compact_state_with_premiums, premium_legend = overlay
    else:
        compact_state_with_premiums = compact_state
        premium_legend = "*=TW, ~=DW, $=TL, ^=DL"
    
    language = variant.language
    tile_summary = _format_tile_summary(variant)
    
    # Load prompt template and substitute placeholders
    template = _load_prompt_template()
    
    prompt = template.format(
        language=language,
        tile_summary=tile_summary,
        compact_state=compact_state_with_premiums,
        premium_legend=premium_legend or "",
    )
    
    return prompt


def propose_move(
    client: OpenAIClient,
    compact_state: str,
    variant: VariantDefinition,
) -> dict[str, Any]:
    """Zavolá OpenAI, parsuje odpoveď lokálne a normalizuje payload.

    Komentár (SK): Nepoužívame serverovú JSON schému; spoliehame sa na
    lokálne pydantic parsovanie `parse_ai_move` a konverziu na kanonický
    formát vhodný pre validáciu a UI. Výstup obsahuje aj kľúč `exchange`
    (prázdny zoznam) kvôli UI kompatibilite.
    """

    prompt = _build_prompt(compact_state, variant)
    raw = client._call_text(prompt, max_output_tokens=client.ai_move_max_output_tokens)
    
    # Parse response - no retry on failure
    model = parse_ai_move(raw)
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
