"""Serializacia stavu hry do kompaktneho formatu pre AI.

Pozn.: Modul je bez UI/AI zalezitosti, vhodny pre unit testy a mypy.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from .board import Board
from .tiles import TileBag
from .variant_store import get_active_variant_slug


class BlankPos(TypedDict):
    row: int
    col: int


class AIState(TypedDict, total=False):
    grid: list[str]
    blanks: list[BlankPos]
    ai_rack: str
    human_score: int
    ai_score: int
    turn: Literal["HUMAN", "AI"]


def build_ai_state_dict(
    board: Board,
    ai_rack: list[str],
    human_score: int,
    ai_score: int,
    turn: Literal["HUMAN", "AI"],
) -> AIState:
    """Vytvori kompaktny stav pre AI.

    - grid: 15 retazcov po 15 znakov, '.' pre prazdne, 'A'..'Z' pre pismena
    - blanks: pozicie, kde je dlazdica blank (na gride je uz pismeno)
    - ai_rack: retazec pismen na racku AI
    - skore hracov a kto je na tahu
    """
    grid: list[str] = []
    blanks: list[BlankPos] = []
    for r in range(15):
        row_chars: list[str] = []
        for c in range(15):
            cell = board.cells[r][c]
            if cell.letter:
                row_chars.append(cell.letter)
                if cell.is_blank:
                    blanks.append({"row": r, "col": c})
            else:
                row_chars.append(".")
        grid.append("".join(row_chars))

    return AIState(
        grid=grid,
        blanks=blanks,
        ai_rack="".join(ai_rack),
        human_score=human_score,
        ai_score=ai_score,
        turn=turn,
    )


def parse_ai_state_dict(state: AIState) -> AIState:
    """Trivialna validacia/normalizacia vstupu – vrati AIState so spravneymi typmi.

    Pouzite v testoch na 'round-trip' kontrolu formatu.
    """
    # Validacia dlzok grid-u
    grid = state.get("grid", [])
    assert isinstance(grid, list) and len(grid) == 15
    for row in grid:
        assert isinstance(row, str) and len(row) == 15
    blanks = state.get("blanks", [])
    assert isinstance(blanks, list)
    for b in blanks:
        assert isinstance(b, dict)
        r = b.get("row")
        c = b.get("col")
        assert isinstance(r, int) and 0 <= r < 15
        assert isinstance(c, int) and 0 <= c < 15
    ai_rack = state.get("ai_rack", "")
    assert isinstance(ai_rack, str)
    human_score = state.get("human_score", 0)
    ai_score = state.get("ai_score", 0)
    assert isinstance(human_score, int) and isinstance(ai_score, int)
    turn = state.get("turn", "HUMAN")
    assert turn in ("HUMAN", "AI")
    return AIState(
        grid=grid,
        blanks=blanks,
        ai_rack=ai_rack,
        human_score=human_score,
        ai_score=ai_score,
        turn=turn,
    )


class _Pos(TypedDict):
    """Pomocná štruktúra pre pozície buniek (row,col)."""
    row: int
    col: int


class SaveGameState(TypedDict, total=False):
    """JSON-serializovateľný stav celej hry pre ukladanie/obnovu (schema v1).

    Povinné polia (schema_version=="1"):
    - schema_version: "1"
    - grid: 15× reťazec dĺžky 15 ('.' alebo 'A'..'Z')
    - blanks: zoznam pozícií, kde je blank (mapovaný už v `grid` na písmeno)
    - premium_used: zoznam pozícií, kde je prémie už spotrebované
    - human_rack, ai_rack: reťazce s písmenami na racku
    - bag: reťazec zvyšných kameňov (presné poradie)
    - human_score, ai_score: celé čísla
    - turn: "HUMAN" | "AI"
    - variant: slug aktuálneho Scrabble variantu

    Voliteľné:
    - last_move_cells: pozície posledného ťahu na zvýraznenie
    - last_move_points: body získané v poslednom ťahu (pre info panel)
    - consecutive_passes: počítadlo po sebe idúcich passov
    - human_pass_streak, ai_pass_streak: per-hráč počítadlá passov
    - game_over: či bola partia ukončená
    - game_end_reason: meno enum hodnoty `GameEndReason`
    - repro: bool (iba informačné)
    - seed: int (posledný seed pre Repro; iba informačné)
    """

    schema_version: str
    grid: list[str]
    blanks: list[_Pos]
    premium_used: list[_Pos]
    human_rack: str
    ai_rack: str
    bag: str
    human_score: int
    ai_score: int
    turn: Literal["HUMAN", "AI"]
    variant: str
    last_move_cells: list[_Pos]
    last_move_points: int
    consecutive_passes: int
    human_pass_streak: int
    ai_pass_streak: int
    game_over: bool
    game_end_reason: str
    repro: bool
    seed: int


def build_save_state_dict(
    *,
    board: Board,
    human_rack: list[str],
    ai_rack: list[str],
    bag: TileBag,
    human_score: int,
    ai_score: int,
    turn: Literal["HUMAN", "AI"],
    last_move_cells: list[tuple[int, int]] | None = None,
    last_move_points: int = 0,
    consecutive_passes: int = 0,
    human_pass_streak: int = 0,
    ai_pass_streak: int = 0,
    game_over: bool = False,
    game_end_reason: str | None = None,
    repro: bool = False,
    seed: int = 0,
    variant_slug: str | None = None,
) -> SaveGameState:
    """Vytvorí JSON-serializovateľný stav hry (schema v1).

    Pozn.: Neobsahuje dočasné rozloženia (pending placements).
    """
    grid: list[str] = []
    blanks: list[_Pos] = []
    premium_used: list[_Pos] = []
    for r in range(15):
        row_chars: list[str] = []
        for c in range(15):
            cell = board.cells[r][c]
            if getattr(cell, "premium_used", False):
                premium_used.append({"row": r, "col": c})
            if cell.letter:
                row_chars.append(cell.letter)
                if cell.is_blank:
                    blanks.append({"row": r, "col": c})
            else:
                row_chars.append(".")
        grid.append("".join(row_chars))

    variant = variant_slug or getattr(bag, "variant_slug", None) or get_active_variant_slug()

    return SaveGameState(
        schema_version="1",
        grid=grid,
        blanks=blanks,
        premium_used=premium_used,
        human_rack="".join(human_rack),
        ai_rack="".join(ai_rack),
        bag="".join(bag.tiles),
        human_score=human_score,
        ai_score=ai_score,
        turn=turn,
        variant=str(variant),
        last_move_cells=[{"row": r, "col": c} for (r, c) in (last_move_cells or [])],
        last_move_points=last_move_points,
        consecutive_passes=consecutive_passes,
        human_pass_streak=human_pass_streak,
        ai_pass_streak=ai_pass_streak,
        game_over=game_over,
        game_end_reason=game_end_reason or "",
        repro=repro,
        seed=seed,
    )


def parse_save_state_dict(data: dict[str, Any]) -> SaveGameState:
    """Overí a normalizuje vstupný slovník podľa schema v1 a vráti `SaveGameState`.

    Vyvolá `AssertionError` pri neplatnom formáte (vhodné pre testy a UI guardy).
    """
    schema = data.get("schema_version")
    assert schema == "1", "Nepodporovaná schema_version"

    grid = data.get("grid")
    assert isinstance(grid, list) and len(grid) == 15
    for row in grid:
        assert isinstance(row, str) and len(row) == 15

    def _parse_pos_list(key: str) -> list[_Pos]:
        arr = data.get(key, [])
        assert isinstance(arr, list)
        out: list[_Pos] = []
        for it in arr:
            assert isinstance(it, dict)
            r = it.get("row")
            c = it.get("col")
            assert isinstance(r, int) and isinstance(c, int)
            assert 0 <= r < 15 and 0 <= c < 15
            out.append({"row": r, "col": c})
        return out

    blanks = _parse_pos_list("blanks")
    premium_used = _parse_pos_list("premium_used")

    human_rack = data.get("human_rack", "")
    ai_rack = data.get("ai_rack", "")
    bag = data.get("bag", "")
    assert isinstance(human_rack, str)
    assert isinstance(ai_rack, str)
    assert isinstance(bag, str)

    human_score = data.get("human_score", 0)
    ai_score = data.get("ai_score", 0)
    assert isinstance(human_score, int) and isinstance(ai_score, int)

    turn = data.get("turn", "HUMAN")
    assert turn in ("HUMAN", "AI")

    variant = data.get("variant", get_active_variant_slug())
    assert isinstance(variant, str) and variant

    last_move_cells = _parse_pos_list("last_move_cells")
    last_move_points = data.get("last_move_points", 0)
    assert isinstance(last_move_points, int)
    consecutive_passes = data.get("consecutive_passes", 0)
    assert isinstance(consecutive_passes, int)
    human_pass_streak = data.get("human_pass_streak", 0)
    ai_pass_streak = data.get("ai_pass_streak", 0)
    assert isinstance(human_pass_streak, int)
    assert isinstance(ai_pass_streak, int)
    game_over = data.get("game_over", False)
    assert isinstance(game_over, bool)
    game_end_reason = data.get("game_end_reason", "")
    assert isinstance(game_end_reason, str)
    repro = data.get("repro", False)
    assert isinstance(repro, bool)
    seed = data.get("seed", 0)
    assert isinstance(seed, int)

    return SaveGameState(
        schema_version="1",
        grid=grid,
        blanks=blanks,
        premium_used=premium_used,
        human_rack=human_rack,
        ai_rack=ai_rack,
        bag=bag,
        human_score=human_score,
        ai_score=ai_score,
        turn=turn,
        variant=variant,
        last_move_cells=last_move_cells,
        last_move_points=last_move_points,
        consecutive_passes=consecutive_passes,
        human_pass_streak=human_pass_streak,
        ai_pass_streak=ai_pass_streak,
        game_over=game_over,
        game_end_reason=game_end_reason,
        repro=repro,
        seed=seed,
    )


def restore_board_from_save(state: SaveGameState, premiums_path: str) -> Board:
    """Z `SaveGameState` v1 vybuduje inštanciu `Board` s písmenami a príznakmi.

    - Prémiové typy sa načítajú zo `premiums_path` (statická mapa),
      iba príznak `premium_used` sa aplikuje zo stavu.
    """
    board = Board(premiums_path)
    # písmená + blank flagy
    for r in range(15):
        row = state["grid"][r]
        for c in range(15):
            ch = row[c]
            if ch != ".":
                board.cells[r][c].letter = ch
                board.cells[r][c].is_blank = False
    # blank pozície
    for pos in state.get("blanks", []):
        rr, cc = pos["row"], pos["col"]
        if board.cells[rr][cc].letter:
            board.cells[rr][cc].is_blank = True
    # prémie spotrebované
    for pos in state.get("premium_used", []):
        rr, cc = pos["row"], pos["col"]
        board.cells[rr][cc].premium_used = True
    return board


def restore_bag_from_save(state: SaveGameState) -> TileBag:
    """Z `SaveGameState` v1 zloží `TileBag` so zachovaným poradím kameňov."""
    # Dôležité: pri poskytnutých `tiles` sa taška už nesmie premiešať
    letters = list(state["bag"]) if state.get("bag") else []
    seed = state.get("seed", 0)
    variant = state.get("variant")
    return TileBag(seed=seed, tiles=letters, variant=variant)
