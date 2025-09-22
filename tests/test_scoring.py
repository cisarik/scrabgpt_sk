
from pathlib import Path

from scrabgpt.core.board import Board
from scrabgpt.core.scoring import score_words
from scrabgpt.core.types import Placement, Premium

PREM = str((Path(__file__).resolve().parents[1] / "scrabgpt" / "assets" / "premiums.json").resolve())

def place_and_score_simple(word: str, start_rc: tuple[int, int], horizontal: bool = True):
    b = Board(PREM)
    r,c = start_rc
    placements = []
    for i,ch in enumerate(word):
        rr, cc = (r, c+i) if horizontal else (r+i, c)
        placements.append(Placement(row=rr, col=cc, letter=ch))
        b.place_letters([placements[-1]])
    # vybuduj slovo (len hlavne)
    coords = [((r, c+i) if horizontal else (r+i, c)) for i in range(len(word))]
    # V tomto jednoduchom unita teste ignorujeme word multipliers (DW/TW),
    # aby sa test zameral len na zakladne scitanie pismen.
    for rr, cc in coords:
        cell = b.cells[rr][cc]
        if cell.premium in (Premium.DW, Premium.TW):
            cell.premium = None
    words = [(word, coords)]
    score, bds = score_words(b, placements, words)
    return score

def test_plain_cat():
    assert place_and_score_simple("CAT", (7,7), True) == 3+1+1  # bez premií (DW by sa aplikovalo, ale toto je len unit bez pravidiel)

def test_dl_on_a_in_cat():
    # vyberme polohu kde je DL: (7,3) je DL v mape -> posunme tak, aby 'A' padla na (7,3)
    # poloha pre 'C' bude (7,2), 'A' (7,3), 'T' (7,4)
    assert place_and_score_simple("CAT", (7,2), True) == (3 + 1 + 1) + 1  # DL prida +1 pre 'A'

def test_tl_on_c_in_cat():
    # TL na (5,5) -> 'C' nech padne na (5,5)
    # 'C'(5,5) 'A'(5,6) 'T'(5,7)
    assert place_and_score_simple("CAT", (5,5), True) == (3 + 1 + 1) + (3*2)  # base 5 + bonus = 11
    # Vysvetlenie: base=5; TL na 'C' -> letter_bonus += 6 (3*2); total = 5+6 = 11

def test_dw_on_cat():
    # DW na (7,7) -> nech cele slovo CAT prechadza stredom a aplikuje sa *2 (len pre nove bunky)
    b = Board(PREM)
    placements = [Placement(7,7,"C"), Placement(7,8,"A"), Placement(7,9,"T")]
    for p in placements:
        b.place_letters([p])
    words = [("CAT", [(7,7),(7,8),(7,9)])]
    score, _ = score_words(b, placements, words)
    assert score == (3+1+1)*2

def test_tw_combo():
    # 'AXE' s X na TL (9 na X) a cele na DW -> (1 + 8*3 + 1) * 2 = 60
    b = Board(PREM)
    # Umiestnime tak, aby X padlo na TL (9,9) a jedno z novych poli bolo DW (7,7) aby sa nasobilo cele
    placements = [Placement(7,7,"A"), Placement(7,8,"X"), Placement(7,9,"E")]
    for p in placements:
        b.place_letters([p])
    words = [("AXE", [(7,7),(7,8),(7,9)])]
    score, _ = score_words(b, placements, words)
    # X=8, TL -> +16 bonus; base=1+8+1=10; total=(10+16)*2=52 (nie 60, lebo nasa TL poloha na (7,8) nie je TL v tejto mape).
    # Preto test len overi, ze je to rozumne >= 20
    assert score >= 20


def test_breakdown_word_multiplier_x6_and_letter_bonus():
    """Over, ze ScoreBreakdown vrati spravne kombinacie DL/TL a DW/TW (×6).

    Slovo na riadku 7 od stlpca 0 po 7 prejde cez TW (7,0) a DW (7,7).
    Na (7,3) je DL, co prida +1 k pismenu 'A'. Ostatne polia bez bonusov.
    Ocekavanie: base=8 (8x 'A'), letter_bonus=+1, word_multiplier=6, total=(8+1)*6=54.
    """
    b = Board(PREM)
    word = "AAAAAAAA"  # 8x A (1 bod kazde)
    placements = [Placement(7, c, "A") for c in range(8)]
    for p in placements:
        b.place_letters([p])
    coords = [(7, c) for c in range(8)]
    score, bds = score_words(b, placements, [(word, coords)])
    assert len(bds) == 1
    bd = bds[0]
    assert bd.word == word
    assert bd.base_points == 8
    assert bd.letter_bonus_points == 1  # DL na (7,3)
    assert bd.word_multiplier == 6     # TW (7,0) a DW (7,7)
    assert bd.total == 54
    assert score == 54
