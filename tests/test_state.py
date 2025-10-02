from __future__ import annotations

from pathlib import Path

from scrabgpt.core.board import Board
from scrabgpt.core.state import build_ai_state_dict, parse_ai_state_dict
from scrabgpt.core.types import Placement


PREM = str((Path(__file__).resolve().parents[1] / "scrabgpt" / "assets" / "premiums.json").resolve())


def test_state_format_and_round_trip() -> None:
    b = Board(PREM)
    # poloz par pismen, vcitane blanku
    b.place_letters([Placement(7, 7, "C"), Placement(7, 8, "?", blank_as="A"), Placement(7, 9, "T")])
    ai_rack = list("AEIRST?")
    st = build_ai_state_dict(b, ai_rack, human_score=12, ai_score=7, turn="AI")
    # validacia rozmerov
    assert len(st["grid"]) == 15
    assert all(len(row) == 15 for row in st["grid"])
    # na stredovych poziciach mame "C", "A" (z blanku), "T"
    assert st["grid"][7][7:10] == "CAT"
    # blank pozicia by mala byt zaznamenana
    assert any(bpos["row"] == 7 and bpos["col"] == 8 for bpos in st["blanks"])  # type: ignore[index]
    # rack retezec
    assert st["ai_rack"] == "AEIRST?"
    # round-trip kontrola
    st2 = parse_ai_state_dict(st)
    assert st2["ai_rack"] == st["ai_rack"]
    assert st2["turn"] == "AI"


def test_blank_tiles_render_real_letter_in_grid() -> None:
    b = Board(PREM)
    b.place_letters([Placement(4, 5, "?", blank_as="R")])

    state = build_ai_state_dict(b, ai_rack=list("AEIOU?"), human_score=0, ai_score=0, turn="AI")

    # blank pozicia je zaznamenana, ale v samotnom gride je ulozene realne pismeno
    assert state["blanks"] == [{"row": 4, "col": 5}]
    assert state["grid"][4][5] == "R"
    assert "?" not in state["grid"][4]
