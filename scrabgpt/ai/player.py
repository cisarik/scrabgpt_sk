from __future__ import annotations

import logging
import json
import os
from pathlib import Path
from typing import Any, cast

from openai.types.chat import ChatCompletionMessageParam

from ..ai.schema import parse_ai_move, to_move_payload
from ..core.board import Board
from ..core.assets import get_premiums_path
from ..core.variant_store import VariantDefinition
from ..core.types import Placement, Premium
from .client import OpenAIClient
from .openrouter import OpenRouterClient

log = logging.getLogger("scrabgpt.ai")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_CONTEXT_SESSION: "GameContextSession | None" = None
_CONTEXT_HISTORY_LIMIT = 8


class GameContextSession:
    """Keeps a rolling transcript so reasoning models can reuse context.
    
    Nový režim: chat-based protokol s delta updates pre úsporu tokenov.
    Podporuje:
    - Delta updates (len zmeny na doske)
    - User chat messages (užívateľ môže AI písať)
    - Kompaktný formát (80-90% úspora tokenov)
    - MCP tools integration
    """

    def __init__(self, variant_slug: str, *, history_limit: int = _CONTEXT_HISTORY_LIMIT) -> None:
        self.variant_slug = variant_slug
        self._base_prompt: str | None = None
        self._history_limit = max(1, history_limit)
        self._turn_log: list[str] = []
        self._reasoning_context: list[ChatCompletionMessageParam] = []  # Track full message history for reasoning models
        self._turn_count = 0  # Počítadlo ťahov pre číslovanie
        self._last_board_state: dict[tuple[int, int], str] = {}  # Posledný stav dosky pre delta

    def prepare_prompt(self, base_prompt: str, compact_state: str) -> str:
        """Return prompt enriched with prior moves."""

        if not self._base_prompt:
            self._base_prompt = base_prompt
            self._turn_log.clear()
            return base_prompt

        recent = self._turn_log[-self._history_limit :]
        log_lines = "\n".join(f"{idx + 1}. {entry}" for idx, entry in enumerate(recent))
        history_block = log_lines or "(Žiadne záznamy – prvý ťah v tomto kontexte.)"
        return (
            f"{self._base_prompt}\n\n"
            "Chronológia posledných ťahov:\n"
            f"{history_block}\n\n"
            "Aktuálny stav (preparovaný len raz, aktualizujeme iba hracie dáta):\n"
            f"{compact_state}\n\n"
            "Použi interné 'thinking/reasoning' tokeny na plánovanie a odpovedz iba finálnym JSON-om."
        )

    def prepare_messages(self, base_prompt: str, compact_state: str) -> list[ChatCompletionMessageParam]:
        """Return message list for chat completion (supports reasoning models).
        
        For the first turn, returns system prompt + initial state.
        For subsequent turns, appends new state to existing conversation.
        """
        if not self._reasoning_context:
            # First turn: initialize with system prompt
            self._reasoning_context = [
                cast(ChatCompletionMessageParam, {"role": "system", "content": base_prompt}),
                cast(ChatCompletionMessageParam, {"role": "user", "content": compact_state})
            ]
            self._base_prompt = base_prompt
            return self._reasoning_context
        
        # Subsequent turns: append new state
        self._reasoning_context.append(cast(ChatCompletionMessageParam, {
            "role": "user", 
            "content": f"New turn state:\n{compact_state}"
        }))
        return self._reasoning_context
    
    def remember_response(self, message: dict[str, Any]) -> None:
        """Store assistant response (including thinking content for reasoning models)."""
        self._reasoning_context.append(cast(ChatCompletionMessageParam, message))
        
        # Also update legacy turn log for compatibility
        content = message.get("content", "")
        if content:
            # Try to extract word from JSON response
            try:
                import json
                parsed = json.loads(content)
                word = parsed.get("word", "?")
                direction = parsed.get("direction", "?")
                start = parsed.get("start", {})
                row = start.get("row", "?")
                col = start.get("col", "?")
                summary = f"{word} {direction} od ({row},{col})"
                self._turn_log.append(summary)
                if len(self._turn_log) > self._history_limit:
                    self._turn_log = self._turn_log[-self._history_limit :]
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    def add_human_move(
        self, 
        word: str, 
        score: int, 
        placements: list[Placement],
        board: Board
    ) -> None:
        """Pridá ťah hráča do kontextu ako user message.
        
        Generuje delta update s novými políčkami.
        """
        self._turn_count += 1
        
        # Vytvoriť zoznam políčok
        placement_strs = [f"({p.row},{p.col},{p.letter})" for p in placements]
        placements_text = ", ".join(placement_strs)
        
        # Aktualizovať stav dosky
        occupied = _serialize_occupied_cells(board)
        
        message = (
            f"=== ŤAH #{self._turn_count} ===\n\n"
            f"Hráč zahral: \"{word}\" za {score} bodov\n"
            f"Políčka: {placements_text}\n\n"
            f"Doska teraz (obsadené):\n{occupied}\n\n"
            "Je na tebe."
        )
        
        self._reasoning_context.append(cast(ChatCompletionMessageParam, {
            "role": "user",
            "content": message
        }))
        
        log.debug("Added human move to context: %s for %d points", word, score)
    
    def add_ai_move(self, move: dict[str, Any], score: int, board: Board) -> None:
        """Pridá vlastný ťah AI do kontextu ako assistant message.
        
        Uchovávanie vlastného ťahu pre kontinuitu konverzácie.
        """
        # JSON odpoveď AI bola už zapamätaná cez remember_response()
        # Tu len aktualizujeme legacy log
        word = move.get("word", "?")
        direction = move.get("direction", "?")
        start = move.get("start", {})
        
        summary = f"{word} {direction} za {score} bodov"
        self._turn_log.append(summary)
        if len(self._turn_log) > self._history_limit:
            self._turn_log = self._turn_log[-self._history_limit :]
        
        log.debug("Added AI move to context: %s", summary)
    
    def add_user_message(self, message: str) -> None:
        """Pridá chat správu od užívateľa (voľný text).
        
        Umožňuje užívateľovi komunikovať s AI mimo herného protokolu.
        """
        self._reasoning_context.append(cast(ChatCompletionMessageParam, {
            "role": "user",
            "content": message
        }))
        log.info("User chat message added: %s", message[:100])
    
    def add_system_message(self, message: str) -> None:
        """Pridá systémovú správu (napr. chyba validácie, herné eventy).
        
        Používa sa pre notifikácie o chybných ťahoch, konci hry atď.
        """
        self._reasoning_context.append(cast(ChatCompletionMessageParam, {
            "role": "system",
            "content": message
        }))
        log.debug("System message added: %s", message[:100])
    
    def get_compact_delta(
        self, 
        board: Board, 
        rack: list[str], 
        is_first_move: bool = False
    ) -> str:
        """Vygeneruje kompaktnú delta správu s aktuálnym stavom.
        
        Pre prvý ťah: plný popis (prázdna doska + všetky prémiá)
        Pre ďalšie ťahy: len rack + voľné prémiá (doska už je v kontexte)
        """
        rack_str = ", ".join(rack)
        
        if is_first_move:
            # Prvý ťah - potrebujeme všetko
            premiums = _serialize_unused_premiums(board)
            return (
                "=== NOVÁ HRA ===\n\n"
                "Začínaš. Doska je prázdna.\n\n"
                f"Tvoj rack: [{rack_str}]\n\n"
                f"Prémiové políčka:\n{premiums}\n\n"
                "Pripomenutie: Prvý ťah musí pokryť stred (7,7)."
            )
        else:
            # Ďalší ťah - delta (rack + prémiá sú už v predošlej správe)
            premiums = _serialize_unused_premiums(board)
            return (
                f"Tvoj rack: [{rack_str}]\n\n"
                f"Voľné prémiá:\n{premiums}\n\n"
                "Je na tebe."
            )

    def remember_turn(self, move: dict[str, Any]) -> None:
        """Append a compact summary of the AI move (legacy method)."""

        start = move.get("start") or {}
        row = start.get("row", "?")
        col = start.get("col", "?")
        direction = move.get("direction", "?")
        word = move.get("word") or "?"
        placements = move.get("placements") or []
        placement_bits: list[str] = []
        for placement in placements:
            if not isinstance(placement, dict):
                continue
            placement_bits.append(
                f"({placement.get('row', '?')},{placement.get('col', '?')}={placement.get('letter', '?')})"
            )
        placements_text = ", ".join(placement_bits) or "n/a"
        summary = f"{word} {direction} od ({row},{col}) -> {placements_text}"
        self._turn_log.append(summary)
        if len(self._turn_log) > self._history_limit:
            self._turn_log = self._turn_log[-self._history_limit :]


def _serialize_occupied_cells(board: Board) -> str:
    """Vráti kompaktný zoznam obsadených políčok.
    
    Formát: "(r,c)=L (r,c)=L ..."
    Príklad: "(7,7)=K (7,8)=O (7,9)=T"
    """
    cells = []
    for r in range(15):
        for c in range(15):
            letter = board.cells[r][c].letter
            if letter:
                cells.append(f"({r},{c})={letter}")
    return " ".join(cells) if cells else "(prázdna doska)"


def _serialize_unused_premiums(board: Board) -> str:
    """Vráti kompaktný zoznam nepoužitých prémií.
    
    Formát zoskupený podľa typu:
    * (TW): (r,c), (r,c)
    ~ (DW): (r,c), (r,c)
    $ (TL): (r,c), (r,c)
    ^ (DL): (r,c), (r,c)
    """
    premiums_by_type: dict[str, list[tuple[int, int]]] = {
        "TW": [],
        "DW": [],
        "TL": [],
        "DL": [],
    }
    
    symbol_map = {
        Premium.TRIPLE_WORD: ("*", "TW"),
        Premium.DOUBLE_WORD: ("~", "DW"),
        Premium.TRIPLE_LETTER: ("$", "TL"),
        Premium.DOUBLE_LETTER: ("^", "DL"),
    }
    
    for r in range(15):
        for c in range(15):
            cell = board.cells[r][c]
            if cell.premium and not cell.premium_used:
                if cell.premium in symbol_map:
                    _, ptype = symbol_map[cell.premium]
                    premiums_by_type[ptype].append((r, c))
    
    lines = []
    for ptype in ["TW", "DW", "TL", "DL"]:
        coords = premiums_by_type[ptype]
        if coords:
            symbol = {"TW": "*", "DW": "~", "TL": "$", "DL": "^"}[ptype]
            coords_str = ", ".join(f"({r},{c})" for r, c in coords)
            lines.append(f"{symbol} ({ptype}): {coords_str}")
    
    return "\n".join(lines) if lines else "(žiadne voľné prémiá)"


def _context_session_enabled() -> bool:
    """Return True when persistent context should be reused."""

    for key in ("AI_CONTEXT_SESSION", "SCRABGPT_CONTEXT_SESSION"):
        raw = os.getenv(key)
        if raw and raw.strip().lower() in _TRUE_VALUES:
            return True
    return False


def _context_history_limit() -> int:
    raw = os.getenv("AI_CONTEXT_HISTORY")
    if not raw:
        return _CONTEXT_HISTORY_LIMIT
    try:
        value = int(raw)
    except ValueError:
        return _CONTEXT_HISTORY_LIMIT
    return max(1, min(value, 20))


def _ensure_context_session(variant: VariantDefinition) -> GameContextSession:
    """Create or reuse cached session scoped to the current variant."""

    global _CONTEXT_SESSION
    slug = getattr(variant, "slug", variant.language)
    if _CONTEXT_SESSION is None or _CONTEXT_SESSION.variant_slug != slug:
        _CONTEXT_SESSION = GameContextSession(slug, history_limit=_context_history_limit())
        log.info("Initialized AI context session for variant=%s", slug)
    return _CONTEXT_SESSION


def reset_reasoning_context() -> None:
    """Clear cached context session (called on new game/variant switch)."""

    global _CONTEXT_SESSION
    if _CONTEXT_SESSION is not None:
        log.info("Reset AI context session")
    _CONTEXT_SESSION = None


def _load_prompt_template(use_chat_protocol: bool = True) -> str:
    """Load AI prompt template from file specified in .env or use default.
    
    Args:
        use_chat_protocol: If True, load chat protocol template (delta updates, MCP tools).
                          If False, load legacy zero-shot template.
    """
    if use_chat_protocol:
        # Nový chat protokol s MCP tools
        prompt_file = os.getenv("AI_PROMPT_FILE_CHAT", "prompts/chat_protocol.txt")
    else:
        # Legacy zero-shot protokol
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
    if use_chat_protocol:
        # Embedded chat protocol fallback
        return """Hráš Scrabble v jazyku {language}. Používaj MCP tools na validáciu.

=== PRAVIDLÁ ===
- Prvý ťah musí pokrývať stred (7,7)
- Políčka v jednom riadku/stĺpci bez medzier
- Pripájaj sa k existujúcim písmenám
- Všetky slová platné v {language}

=== BODOVÉ HODNOTY ===
{tile_summary}

=== PRÉMIÁ ===
* = TW (×3 slovo)
~ = DW (×2 slovo)
$ = TL (×3 písmeno)
^ = DL (×2 písmeno)

=== FORMÁT ODPOVEDE ===
```json
{{
  "start": {{"row": 7, "col": 7}},
  "direction": "ACROSS",
  "placements": [{{"row": 7, "col": 7, "letter": "K"}}],
  "word": "KOT"
}}
```

Ak nie je možný ťah: skús nájsť aspoň výmenu, ale NIKDY nepasuj bezdôvodne.
"""
    else:
        # Embedded legacy fallback
        return """You are an expert Scrabble player for the {language} language variant. Play to win and obey official Scrabble rules for that language. Do NOT overwrite existing board letters; place only on empty cells. Placements must form a single contiguous line with no gaps and must connect to existing letters after previous move. Use only letters from ai_rack; for '?' use chosen uppercase letter (respecting diacritics). Points you can get for each tile: {tile_summary}. Always evaluate moves that use all 7 rack tiles for the 50 point bingo bonus; play it when legal. Prefer the move that maximizes total points, spending high-value rack letters on premium squares. Do not glue your letters to adjacent existing letters unless the resulting main word is a valid {language} word. Use intersections/hooks properly; you may share letters with the board only at overlapping cells; do not extend an existing word into a non-word. The field 'word' must equal the final main word formed on the board (existing board letters plus your placements). All cross-words should plausibly be valid {language} words. Diacritics is very important so distinguishing between 'Ú' and 'U' for example and every letter with diacritic. NEVER GIVE UP. Always find a valid move. Do not pass. If the board is empty, the first move must cross the center star at H8 (row=7,col=7). Coordinates are 0-based. No explanations — JSON only. Always return a JSON object with keys: start:{{row:int,col:int}}, direction:'ACROSS'|'DOWN', placements:[{{row,col,letter}}]. Empty premium squares in the grid already show their multiplier symbol (see legend). Prioritize TL/DL for high-value letters and aim to span DW/TW with the main word when possible; stacking letter multipliers that feed into word multipliers yields maximal score. Also value high-scoring cross-words created by your placements.

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
    
    # Extract rack from compact_state if possible
    import re
    # Match both "ai_rack:ABC" and "rack:[...]" formats
    rack_match = re.search(r"(?:ai_)?rack:\s*(?:\[(.*?)\]|(.*))", compact_state)
    if rack_match:
        # Group 1 is for [...], Group 2 is for plain string
        rack_str = rack_match.group(1) or rack_match.group(2) or ""
        rack_str = rack_str.strip()
    else:
        rack_str = "Neznáme (chyba v extrakcii)"

    prompt = template.format(
        language=language,
        tile_summary=tile_summary,
        compact_state=compact_state_with_premiums,
        premium_legend=premium_legend or "",
        rack=rack_str,
    )
    
    return prompt


def propose_move(
    client: OpenAIClient,
    compact_state: str,
    variant: VariantDefinition,
    *,
    stream_callback: "Callable[[str], None] | None" = None,
    reasoning_callback: "Callable[[str], None] | None" = None,
) -> dict[str, Any]:
    """Zavolá OpenAI, parsuje odpoveď lokálne a normalizuje payload.

    Komentár (SK): Nepoužívame serverovú JSON schému; spoliehame sa na
    lokálne pydantic parsovanie `parse_ai_move` a konverziu na kanonický
    formát vhodný pre validáciu a UI. Výstup obsahuje aj kľúč `exchange`
    (prázdny zoznam) kvôli UI kompatibilite.
    
    Ak je zapnutý AI_CONTEXT_SESSION, používa konverzačný režim s historickým
    kontextom - drasticky znižuje spotrebu tokenov (80-90%) a podporuje
    reasoning modely (deepseek-r1) s thinking/reasoning channelom.
    """

    session: GameContextSession | None = None
    
    if _context_session_enabled():
        # NEW PATH: Use context session with message history
        session = _ensure_context_session(variant)
        base_prompt = _build_prompt(compact_state, variant)
        messages = session.prepare_messages(base_prompt, compact_state)
        
        log.info("Context session: turn with %d messages in history", len(messages))
        
        # Call with context - returns (content, full_message)
        content, full_message, usage_info = client._call_text_with_context(
            messages,
            max_output_tokens=client.ai_move_max_output_tokens,
            stream_callback=stream_callback,
            reasoning_callback=reasoning_callback,
        )
        
        # Store response for next turn (including thinking/reasoning)
        session.remember_response(full_message)
        
        # Parse JSON from content
        model, _parse_method = parse_ai_move(content)
        move = to_move_payload(model)
        if usage_info:
            move["_usage"] = usage_info
        
        log.info("Context session: parsed move=%s", move.get("word", "?"))
    else:
        # EXISTING PATH: Build full prompt each turn (legacy mode)
        prompt = _build_prompt(compact_state, variant)
        raw = client._call_text(prompt, max_output_tokens=client.ai_move_max_output_tokens)
        
        # Parse response - no retry on failure
        model, _parse_method = parse_ai_move(raw)
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


def get_context_transcript() -> str:
    """Vráti textový prepis aktuálnej reasoning konverzácie (ak existuje)."""
    global _CONTEXT_SESSION
    if _CONTEXT_SESSION is None or not _CONTEXT_SESSION._reasoning_context:
        return ""
    lines: list[str] = []
    for idx, msg in enumerate(_CONTEXT_SESSION._reasoning_context):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = "\n".join(str(part) for part in content)
        lines.append(f"{idx+1}. {role}: {content}")
    return "\n".join(lines)


async def propose_move_chat(
    openrouter_client: OpenRouterClient,
    board: Board,
    ai_rack: list[str],
    variant: VariantDefinition,
    model_id: str = "openai/gpt-4o-mini",
    *,
    is_first_move: bool = False,
) -> dict[str, Any]:
    """Navrhne ťah cez OpenRouter s chat protokolom (delta updates + context session).
    
    Nový prístup:
    - Vždy používa context session (úspora 80-90% tokenov)
    - Delta updates namiesto plného stavu
    - MCP tools v system prompte
    - OpenRouter ako default provider
    
    Args:
        openrouter_client: OpenRouter API klient
        board: Aktuálny stav dosky
        ai_rack: Písmená na racku AI
        variant: Definícia Scrabble variantu
        model_id: ID modelu na OpenRouter (default: gpt-4o-mini)
        is_first_move: Či je to prvý ťah hry
    
    Returns:
        dict s kľúčmi: start, direction, placements, word, (exchange), (pass)
        
    Komentár (SK): Táto funkcia je navrhnutá ako náhrada za pôvodnú 
    `propose_move()` pri používaní chat protokolu. Podporuje delta updates
    a MCP tools pre efektívnejšiu komunikáciu.
    """
    
    # Získať alebo vytvoriť context session
    session = _ensure_context_session(variant)
    
    # Pripraviť system prompt (len pri prvom volaní)
    if not session._base_prompt:
        template = _load_prompt_template(use_chat_protocol=True)
        tile_summary = _format_tile_summary(variant)
        system_prompt = template.format(
            language=variant.language,
            tile_summary=tile_summary,
        )
        session._base_prompt = system_prompt
        
        log.info("Chat protocol: initialized system prompt for %s", variant.language)
    
    # Vytvoriť delta state
    delta_state = session.get_compact_delta(board, ai_rack, is_first_move=is_first_move)
    
    # Pripraviť messages
    messages = session.prepare_messages(session._base_prompt, delta_state)
    
    log.info(
        "Chat protocol: calling OpenRouter model=%s (messages=%d, first_move=%s)",
        model_id,
        len(messages),
        is_first_move,
    )
    log.debug("Delta state:\n%s", delta_state)
    
    # Zavolať OpenRouter API s messages (chat protocol)
    response_dict = await openrouter_client.call_model(
        model_id=model_id,
        messages=messages,
        max_tokens=openrouter_client.ai_move_max_output_tokens,
    )
    
    # Kontrola chyby
    if response_dict.get("status") != "ok":
        error = response_dict.get("error", "Unknown error")
        log.error("OpenRouter call failed: %s", error)
        return {
            "pass": True,
            "error": error,
            "exchange": [],
        }
    
    # Extrahovať content
    content = response_dict.get("content", "")
    if not content or not content.strip():
        log.error("OpenRouter returned empty content")
        return {
            "pass": True,
            "error": "Empty response from model",
            "exchange": [],
        }
    
    # Parsovať JSON odpoveď
    try:
        model_response, _parse_method = parse_ai_move(content)
        move = to_move_payload(model_response)
    except Exception as e:
        log.exception("Failed to parse OpenRouter response: %s", e)
        log.error("Raw content: %s", content)
        return {
            "pass": True,
            "error": f"Parse error: {e}",
            "exchange": [],
        }
    
    # Zapamätať odpoveď do context session
    # OpenRouter vracia dict, potrebujeme message formát
    assistant_message = {
        "role": "assistant",
        "content": content,
    }
    session.remember_response(assistant_message)
    
    # Kompatibilita s UI
    if "exchange" not in move:
        move["exchange"] = []
    
    log.info(
        "Chat protocol: parsed move word=%s direction=%s (tokens: prompt=%d, completion=%d)",
        move.get("word", "?"),
        move.get("direction", "?"),
        response_dict.get("prompt_tokens", 0),
        response_dict.get("completion_tokens", 0),
    )
    
    return move
