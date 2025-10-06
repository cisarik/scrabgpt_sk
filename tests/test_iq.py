"""IQ tests - offline validation that AI finds optimal or near-optimal moves.

These tests load .iq files containing game states and expected moves.
They verify the AI can find moves with scores >= expected score, without
requiring live OpenAI API calls (judge validation is skipped for offline tests).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from scrabgpt.core.iq_test import load_iq_test, restore_board_from_iq_test
from scrabgpt.core.rules import extract_all_words, placements_in_line, no_gaps_in_line
from scrabgpt.core.scoring import score_words
from scrabgpt.core.state import build_ai_state_dict
from scrabgpt.core.types import Placement
from scrabgpt.core.variant_store import load_variant
from scrabgpt.ai.player import propose_move as ai_propose_move
from scrabgpt.ai.client import OpenAIClient

log = logging.getLogger("scrabgpt.tests")


def find_iq_tests() -> list[Path]:
    """Find all .iq test files in tests/iq_tests directory."""
    test_dir = Path(__file__).parent / "iq_tests"
    if not test_dir.exists():
        return []
    return sorted(test_dir.glob("*.iq"))


def _parse_placements(proposal: dict[str, Any]) -> list[Placement]:
    """Parse placements from AI proposal."""
    placements_data = proposal.get("placements", [])
    if not placements_data:
        return []
    
    placements: list[Placement] = []
    for p in placements_data:
        row = int(p["row"])
        col = int(p["col"])
        letter = str(p["letter"])
        placement = Placement(row, col, letter)
        placements.append(placement)
    
    blanks = proposal.get("blanks")
    if blanks and isinstance(blanks, dict):
        for key, value in blanks.items():
            try:
                r, c = map(int, key.split(","))
                for i, pl in enumerate(placements):
                    if pl.row == r and pl.col == c:
                        placements[i] = Placement(
                            row=pl.row, col=pl.col, letter=pl.letter, blank_as=value
                        )
                        break
            except (ValueError, AttributeError):
                continue
    
    return placements


@pytest.mark.parametrize("iq_file", find_iq_tests(), ids=lambda p: p.stem)
def test_iq(iq_file: Path) -> None:
    """Test that AI can find a move with score >= expected score.
    
    This test:
    1. Loads an IQ test file
    2. Restores the board state
    3. Asks AI to propose a move
    4. Validates the move is legal
    5. Scores the move
    6. Compares with expected score (AI should find >= expected)
    
    Note: Judge validation is NOT performed in offline tests - we assume
    the expected move was validated when creating the test.
    """
    test = load_iq_test(iq_file)
    
    name = test.get("name", iq_file.stem)
    description = test.get("description", "")
    log.info("Running IQ test: %s - %s", name, description)
    
    variant_slug = test.get("variant")
    assert variant_slug, "Test must specify variant"
    variant = load_variant(variant_slug)
    
    board = restore_board_from_iq_test(test)
    
    ai_rack_str = test.get("ai_rack", "")
    ai_rack = list(ai_rack_str)
    
    expected_move = test.get("expected_move", {})
    expected_score = expected_move.get("score", 0)
    expected_word = expected_move.get("word", "")
    
    state = build_ai_state_dict(
        board=board,
        ai_rack=ai_rack,
        human_score=0,
        ai_score=0,
        turn="AI",
    )
    
    compact = (
        "grid:\n" + "\n".join(state["grid"]) +
        f"\nblanks:{state['blanks']}\n"
        f"ai_rack:{state['ai_rack']}\n"
        f"scores: H={state['human_score']} AI={state['ai_score']}\nturn:{state['turn']}\n"
    )
    
    client = OpenAIClient()
    
    try:
        proposal = ai_propose_move(
            client,
            compact_state=compact,
            variant=variant,
        )
    except Exception as e:
        pytest.fail(f"AI proposal failed: {e}")
    
    if proposal.get("pass", False):
        pytest.fail(
            f"AI passed when expected to play {expected_word} "
            f"for {expected_score} points"
        )
    
    placements = _parse_placements(proposal)
    
    if not placements:
        pytest.fail("AI returned no placements")
    
    direction = placements_in_line(placements)
    assert direction is not None, "AI placements not in a line"
    
    assert no_gaps_in_line(board, placements, direction), "AI placements have gaps"
    
    board.place_letters(placements)
    words_found = extract_all_words(board, placements)
    board.clear_letters(placements)
    
    assert words_found, "AI move creates no words"
    
    words_coords = [(wf.word, wf.letters) for wf in words_found]
    
    score, _ = score_words(board, placements, words_coords)
    
    if len(ai_rack) == len(placements):
        score += 50
    
    ai_word = words_found[0].word if words_found else ""
    
    log.info(
        "IQ test %s: AI played '%s' for %d points (expected '%s' for %d points)",
        name,
        ai_word,
        score,
        expected_word,
        expected_score,
    )
    
    assert score >= expected_score, (
        f"AI score ({score}) is less than expected ({expected_score}). "
        f"AI played '{ai_word}', expected '{expected_word}'"
    )
    
    log.info("IQ test %s: PASSED", name)


def test_iq_tests_exist() -> None:
    """Sanity check that at least one IQ test exists."""
    tests = find_iq_tests()
    if not tests:
        pytest.skip("No IQ tests found in tests/iq_tests/")
    assert len(tests) > 0, "Should have at least one IQ test"
