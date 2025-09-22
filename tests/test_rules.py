
from pathlib import Path

from scrabgpt.core.board import Board
from scrabgpt.core.rules import connected_to_existing, first_move_must_cover_center
from scrabgpt.core.types import Placement

PREM = str((Path(__file__).resolve().parents[1] / "scrabgpt" / "assets" / "premiums.json").resolve())

def test_line_detection():
    b = Board(PREM)  # noqa: F841
    ps = [Placement(7,7,"C"), Placement(7,8,"A"), Placement(7,9,"T")]
    from scrabgpt.core.rules import placements_in_line
    assert placements_in_line(ps) is not None

def test_center_on_first_move():
    ps = [Placement(7,7,"C")]
    assert first_move_must_cover_center(ps)

def test_connected_after_first_move():
    b = Board(PREM)
    # prvy tah:
    p1 = [Placement(7,7,"C")]
    for p in p1:
        b.place_letters([p])
    # druhy tah mimo kontaktu
    p2 = [Placement(0,0,"A")]
    assert not connected_to_existing(b, p2)
