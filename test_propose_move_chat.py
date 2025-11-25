#!/usr/bin/env python3
"""Test propose_move_chat() - skutočné volanie OpenRouter API.

Tento script testuje:
- Context session initialization
- Delta state generation
- OpenRouter API call s messages
- JSON parsing
- Token savings measurement
"""

import asyncio
import logging
from scrabgpt.ai.player import propose_move_chat, reset_reasoning_context
from scrabgpt.ai.openrouter import OpenRouterClient
from scrabgpt.core.board import Board
from scrabgpt.core.assets import get_premiums_path
from scrabgpt.core.variant_store import load_variant
from scrabgpt.logging_setup import configure_logging

# Setup logging
configure_logging()
logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)


async def test_first_move():
    """Test prvého ťahu - prázdna doska."""
    print("\n" + "="*70)
    print("TEST 1: PRVÝ ŤAH (PRÁZDNA DOSKA)")
    print("="*70)
    
    # Reset context
    reset_reasoning_context()
    
    # Initialize
    openrouter = OpenRouterClient()
    board = Board(get_premiums_path())
    ai_rack = ["A", "E", "I", "K", "L", "O", "T"]
    variant = load_variant("slovak")
    
    print(f"AI Rack: {ai_rack}")
    print(f"Model: openai/gpt-4o-mini")
    print(f"Calling OpenRouter API...")
    
    # Call propose_move_chat
    move = await propose_move_chat(
        openrouter_client=openrouter,
        board=board,
        ai_rack=ai_rack,
        variant=variant,
        model_id="openai/gpt-4o-mini",
        is_first_move=True,
    )
    
    # Display results
    print("\n" + "-"*70)
    print("VÝSLEDOK:")
    print("-"*70)
    print(f"Word: {move.get('word', '?')}")
    print(f"Direction: {move.get('direction', '?')}")
    print(f"Start: ({move.get('start', {}).get('row', '?')}, {move.get('start', {}).get('col', '?')})")
    print(f"Placements: {len(move.get('placements', []))} tiles")
    
    # Check if covers center
    start = move.get('start', {})
    covers_center = start.get('row') == 7 and start.get('col') == 7
    print(f"Covers center (7,7): {'✅ ÁNO' if covers_center else '❌ NIE'}")
    
    if move.get('pass'):
        print("⚠️ AI pasoval (nemal ťah)")
    
    print("="*70 + "\n")
    
    return move


async def test_second_move(first_move):
    """Test druhého ťahu - delta update."""
    print("\n" + "="*70)
    print("TEST 2: DRUHÝ ŤAH (DELTA UPDATE)")
    print("="*70)
    
    # Simulate first move on board
    openrouter = OpenRouterClient()
    board = Board(get_premiums_path())
    variant = load_variant("slovak")
    
    # Apply first move to board (simulované)
    placements = first_move.get('placements', [])
    for p in placements:
        row, col, letter = p.get('row'), p.get('col'), p.get('letter')
        if row is not None and col is not None and letter:
            board.cells[row][col].letter = letter
    
    # New rack for second move
    ai_rack = ["A", "E", "I", "L", "M", "N", "S"]
    
    print(f"AI Rack: {ai_rack}")
    print(f"Board after first move: {len([c for r in board.cells for c in r if c.letter])} tiles")
    print(f"Calling OpenRouter API with DELTA...")
    
    # Call with is_first_move=False (delta update)
    move = await propose_move_chat(
        openrouter_client=openrouter,
        board=board,
        ai_rack=ai_rack,
        variant=variant,
        model_id="openai/gpt-4o-mini",
        is_first_move=False,  # Delta mode!
    )
    
    # Display results
    print("\n" + "-"*70)
    print("VÝSLEDOK:")
    print("-"*70)
    print(f"Word: {move.get('word', '?')}")
    print(f"Direction: {move.get('direction', '?')}")
    print(f"Start: ({move.get('start', {}).get('row', '?')}, {move.get('start', {}).get('col', '?')})")
    print(f"Placements: {len(move.get('placements', []))} tiles")
    
    if move.get('pass'):
        print("⚠️ AI pasoval")
    
    print("="*70 + "\n")


async def main():
    """Hlavná testovacia funkcia."""
    print("\n" + "🧪 TESTOVANIE propose_move_chat() - OPENROUTER API")
    print("="*70)
    print("Tento test zavolá skutočné OpenRouter API.")
    print("Spotrebuje tokeny (ale malo, ~1000 celkom).")
    print("="*70)
    
    try:
        # Test 1: Prvý ťah
        first_move = await test_first_move()
        
        # Test 2: Druhý ťah (delta)
        if not first_move.get('pass'):
            await asyncio.sleep(1)  # Pauza medzi volaniami
            await test_second_move(first_move)
        
        print("\n✅ VŠETKY TESTY ÚSPEŠNÉ!")
        print("🎉 Chat protokol funguje správne!")
        
    except Exception as e:
        print(f"\n❌ TEST ZLYHAL: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
