
from pathlib import Path

from scrabgpt.core.board import Board, BOARD_SIZE

def test_premium_counts():
    path = Path(__file__).resolve().parents[1] / "scrabgpt" / "assets" / "premiums.json"
    b = Board(str(path.resolve()))
    counts = {"DL":0,"TL":0,"DW":0,"TW":0,"":0}
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            tag = b.cells[r][c].premium.name if b.cells[r][c].premium else ""
            counts[tag] += 1
    assert counts["TW"] == 8
    assert counts["DW"] == 17
    assert counts["TL"] == 12
    assert counts["DL"] == 24
    assert counts[""] == 225 - (8+17+12+24)

def test_dw_spotchecks():
    path = Path(__file__).resolve().parents[1] / "scrabgpt" / "assets" / "premiums.json"
    b = Board(str(path.resolve()))
    # B2, C3, D4, E5, K11, L12, M13, N14
    checks = [(1,1),(2,2),(3,3),(4,4),(10,10),(11,11),(12,12),(13,13),
              (1,13),(2,12),(3,11),(4,10),(10,4),(11,3),(12,2),(13,1), (7,7)]
    for r,c in checks:
        assert b.cells[r][c].premium and b.cells[r][c].premium.name == "DW"
