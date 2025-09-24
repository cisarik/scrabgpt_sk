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


def parse_ai_move(text: str) -> MoveModel:
    """Napevno očakávaj JSON objekt; pri zlyhaní vyhoď výnimku s dôvodom.

    Komentár (SK): Parsuje sa striktne cez `json.loads` a `model_validate`.
    """
    import json

    obj = json.loads(text)
    return MoveModel.model_validate(obj)


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
