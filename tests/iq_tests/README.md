# IQ Tests - AI Intelligence Tests

This directory contains IQ tests for evaluating the AI's ability to find optimal or near-optimal moves in Scrabble games.

## What are IQ Tests?

IQ tests are offline validation tests that verify the AI can find good moves without requiring live API calls. Each test contains:

- A specific game state (board configuration)
- The AI's rack (letters available)
- An expected "best" move (or near-optimal move) that a human would make
- The expected score for that move

## Creating IQ Tests

### Using the UI

1. Start the ScrabGPT application: `poetry run scrabgpt`
2. Start a new game or load an existing one
3. Click the "🧠 Uložiť ako test" button in the toolbar
4. A new window opens with a copy of the current board and the AI's rack
5. Place letters from the AI's rack onto the board as if you were the AI
6. Click "Validovať ťah" to validate the move (checks rules and word validity)
7. Once validated, click "Uložiť ako IQ test" to save the test
8. Enter a test name and description
9. The test is saved as a `.iq` file in `tests/iq_tests/`

### IQ File Format

IQ test files use JSON format with schema version 1:

```json
{
  "schema_version": "1",
  "name": "opening_center_bingo",
  "description": "AI should find a 7-letter word through the center star for maximum points",
  "grid": ["...", "...", ...],  // 15x15 grid
  "blanks": [],  // positions of blank tiles
  "premium_used": [],  // which premium squares are already used
  "ai_rack": "RETINAS",  // AI's letters
  "variant": "slovak",  // language variant
  "expected_move": {
    "placements": [{"row": 7, "col": 4, "letter": "R"}, ...],
    "direction": "ACROSS",
    "word": "RETINAS",
    "score": 65,  // including bingo bonus
    "blanks": null  // or {"7,4": "R"} for blank tiles
  }
}
```

## Running IQ Tests

### Run all IQ tests
```bash
poetry run pytest tests/test_iq.py -v
```

### Run a specific test
```bash
poetry run pytest tests/test_iq.py::test_iq[test_name] -v
```

### Skip IQ tests
```bash
poetry run pytest -k "not iq"
```

## How IQ Tests Work

1. **Load** - The test loads the game state and AI rack from the `.iq` file
2. **Propose** - The AI is asked to propose a move for the given state
3. **Validate** - The proposed move is checked for legality (rules, no gaps, etc.)
4. **Score** - The proposed move is scored
5. **Compare** - The AI's score is compared with the expected score
   - **Pass** if AI score >= expected score
   - **Fail** if AI score < expected score

Note: Word validation (judge) is NOT performed during tests since the expected move was already validated when creating the test.

## Test Naming Conventions

Use descriptive names that indicate:
- The scenario (opening, endgame, etc.)
- The challenge (bingo opportunity, premium usage, etc.)
- The language variant if relevant

Examples:
- `opening_center_bingo.iq` - First move with 7-letter word through center
- `double_word_premium.iq` - Optimal use of double word premium
- `endgame_rack_dump.iq` - Best move to empty rack at game end

## Why IQ Tests?

IQ tests provide several benefits:

1. **Offline Testing** - No API costs or rate limits during CI/CD
2. **Regression Detection** - Catch when AI performance degrades
3. **Quality Benchmarking** - Track AI improvement over time
4. **Edge Case Coverage** - Test specific scenarios systematically
5. **Fast Feedback** - Run in seconds vs. minutes for online tests

## Contributing

When adding new IQ tests:

1. Ensure the test represents a realistic game scenario
2. Verify the expected move is actually optimal or near-optimal
3. Include a clear description of what the AI should achieve
4. Test the .iq file by running pytest before committing
