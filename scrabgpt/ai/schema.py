"""AI JSON schéma a parser pre návrh ťahu.

Tento modul definuje tolerantný Pydantic model pre AI odpoveď, ktorý
unifikuje rôzne vstupné varianty (start vs. row/col, rôzne formy blanks)
na kanonický tvar vhodný pre následnú validáciu.

Poznámka (SK): Používame Pydantic v2, preto `field_validator` namiesto
historického `validator`.
"""
from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, Field, field_validator, model_validator

Direction = Literal["ACROSS", "DOWN"]


class Coord(BaseModel):
    """Súradnica na doske (0–14)."""

    row: int = Field(..., ge=0, le=14)
    col: int = Field(..., ge=0, le=14)


class Placement(BaseModel):
    """Jedno položené písmeno v tomto ťahu."""

    row: int = Field(..., ge=0, le=14)
    col: int = Field(..., ge=0, le=14)
    letter: str

    @field_validator("letter")
    @classmethod
    def _one_char(cls, v: str) -> str:
        """Písmeno musí mať dĺžku 1 (vrátane '?')."""
        s = str(v).strip()
        if len(s) != 1:
            raise ValueError("letter_len_must_be_1")
        return s


class MoveModel(BaseModel):
    """Tolerantný model pre AI návrh ťahu.

    - Toleruje `row`/`col` alebo `start={row,col}`.
    - `direction` normalizuje na UPPERCASE, validácia prebehne v `canonical_direction`.
    - `placements` obsahuje položky typu `Placement`.
    - `blanks` akceptuje viacero foriem (mapovanie podľa súradníc, '?', indexy …).
    - `pass_` je alias pre `pass` (Pyth. kľúčové slovo).
    """

    row: int | None = Field(None, ge=0, le=14)
    col: int | None = Field(None, ge=0, le=14)
    start: Coord | None = None

    direction: str = "ACROSS"
    placements: list[Placement] = Field(default_factory=list)
    blanks: dict[str, Any] | None = None
    word: str | None = None
    pass_: bool | None = Field(None, alias="pass")

    @model_validator(mode="after")
    def _ensure_pass_has_no_tiles(self) -> "MoveModel":
        """Overí konzistenciu medzi `pass` a zoznamom kameňov."""

        if self.pass_:
            if self.placements:
                raise ValueError("pass_move_must_not_have_placements")
        elif not self.placements:
            raise ValueError("placements_required_for_play")
        return self

    @field_validator("direction", mode="before")
    @classmethod
    def _norm_dir(cls, v: str | None) -> str:
        """Normalizuje smer na UPPERCASE, prázdny -> 'ACROSS'."""
        return str(v or "ACROSS").strip().upper()

    def canonical_start(self) -> Coord:
        """Vráti kanonický začiatok (`start` preferovaný pred `row`/`col`).

        Ak chýba, vráti (0,0) — následne to zachytí validačná vrstva judge.
        """
        if self.start is not None:
            return self.start
        if self.row is None or self.col is None:
            return Coord(row=0, col=0)
        return Coord(row=self.row, col=self.col)

    def canonical_direction(self) -> Direction:
        """Overí a vráti kanonický smer (ACROSS/DOWN)."""
        d = self.direction
        if d not in ("ACROSS", "DOWN"):
            raise ValueError("direction_invalid")
        return cast(Direction, d)


def _extract_json_from_markdown(text: str) -> str | None:
    """Extrahuje JSON z markdown code blocku (```json ... ``` alebo ``` ... ```).
    
    Hľadá prvý výskyt code blocku v texte a extrahuje jeho obsah.
    Vracia None ak žiadny blok nebol nájdený.
    """
    import re
    
    # Hľadaj ```json ... ``` alebo ``` ... ```
    # Pattern zachytí všetko medzi značkami
    patterns = [
        r'```json\s*\n(.*?)\n```',  # ```json ... ```
        r'```\s*\n(.*?)\n```',       # ``` ... ```
        r'```json\s*(.*?)```',       # ```json...``` (bez newline)
        r'```(.*?)```',               # ```...``` (bez newline)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
    
    return None


def _extract_inline_json_object(text: str) -> str | None:
    """Nájde prvý vyvážený JSON objekt mimo markdown blokov.

    Vyhľadáva prvú složenú zátvorku a snaží sa nájsť zodpovedajúcu koncovú.
    Ignoruje zátvorky vo vnútri stringov a vráti kandidáta len v prípade,
    že obsahuje kľúč `placements` (aby sa predišlo nesúvisiacim objektom).
    """
    start = 0
    length = len(text)
    while start < length:
        brace_index = text.find("{", start)
        if brace_index == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for idx in range(brace_index, length):
            char = text[idx]
            if in_string:
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
                continue
            if char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[brace_index : idx + 1]
                    if "placements" not in candidate:
                        start = brace_index + 1
                        break
                    return candidate.strip()
        else:
            # Nedokázali nájsť ukončovaciu zátvorku - ukonči prehliadanie
            return None
        start = brace_index + 1
    return None


def parse_ai_move(text: str) -> tuple[MoveModel, str]:
    """Napevno očakávaj JSON objekt; pri zlyhaní vyhoď výnimku s dôvodom.

    Komentár (SK): Parsuje sa striktne cez `json.loads` a `model_validate`.
    Podporuje markdown code blocks (```json ... ```).
    
    Fallback stratégia:
    1. Skúsi parsovať priamo (s odstránením markdown blokov na začiatku/konci)
    2. Ak zlyhá, hľadá JSON v markdown blokoch vo vnútri textu
    3. Ak ani to zlyhá, hľadá prvý JSON objekt priamo v texte
    4. Ak aj to zlyhá, vyhodí pôvodnú chybu
    
    Returns:
        tuple[MoveModel, str]: (parsed_move, parse_method) kde parse_method je:
            - "direct": JSON bol parsovaný priamo
            - "markdown_extraction": JSON bol extrahovaný z markdown bloku
            - "inline_json": JSON blok nájdený priamo v texte (mimo markdown)
    """
    import json
    import logging
    
    log = logging.getLogger("scrabgpt.ai.schema")

    # Strip markdown code blocks if present at start/end
    import re

    # Odstráň reasoning bloky <think>...</think>
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]  # Remove ```json
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]  # Remove ```
    
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]  # Remove trailing ```
    
    cleaned = cleaned.strip()
    
    # Pokus 1: Parsuj priamo
    try:
        obj = json.loads(cleaned)
        return MoveModel.model_validate(obj), "direct"
    except json.JSONDecodeError as e:
        log.debug("Priamy JSON parse zlyhal: %s", e)
        
        # Pokus 2: Hľadaj JSON v markdown blokoch
        extracted = _extract_json_from_markdown(text)
        if extracted:
            log.info("Našiel som JSON v markdown bloku, skúšam parsovať...")
            log.debug("Extrahovaný JSON (prvých 200 znakov): %s", extracted[:200])
            try:
                obj = json.loads(extracted)
                log.info("✓ Úspešne parsovaný JSON z markdown bloku")
                return MoveModel.model_validate(obj), "markdown_extraction"
            except (json.JSONDecodeError, ValueError) as e2:
                log.warning("Parsing extrahovaného JSON zlyhal: %s", e2)
                # Pokračuj k vyhodeniu pôvodnej chyby

        # Pokus 3: inline JSON objekt mimo markdown blockov
        inline = _extract_inline_json_object(text)
        if inline:
            log.info("Našiel som JSON blok mimo markdown, skúšam inline fallback...")
            log.debug("Inline JSON kandidát (prvých 200 znakov): %s", inline[:200])
            try:
                obj = json.loads(inline)
                log.info("✓ Úspešne parsovaný JSON z textu (inline fallback)")
                return MoveModel.model_validate(obj), "inline_json"
            except (json.JSONDecodeError, ValueError) as e3:
                log.warning("Parsing inline JSON kandidáta zlyhal: %s", e3)
                # Pokračuj k vyhodeniu pôvodnej chyby
        
        # Žiadny fallback nezabrral, vyhoď pôvodnú chybu
        log.warning("Všetky parsing pokusy zlyhali (raw text dĺžka: %d)", len(text))
        raise


def to_move_payload(m: MoveModel) -> dict[str, Any]:
    """Prekonvertuje `MoveModel` do kanonického `dict` pre ďalšie spracovanie.

    Pozn.: `pass_` mapujeme späť na kľúč `'pass'` kvôli kompatibilite.
    """
    s = m.canonical_start()
    return {
        "row": s.row,
        "col": s.col,
        "direction": m.canonical_direction(),
        "placements": [p.model_dump() for p in m.placements],
        "blanks": m.blanks,
        "word": m.word,
        "pass": m.pass_,
    }
