# IQ Tests / Stress Tests for AI Validation

This directory contains user-created "IQ tests" - stress test scenarios for validating AI behavior in ScrabGPT.

## What are IQ Tests?

IQ tests are pre-defined game scenarios that test:
- AI agent's ability to find optimal moves
- Judge's word validation accuracy
- Rule enforcement correctness
- Edge cases and corner cases

## Format

Each IQ test is a JSON file with the following structure:

```json
{
  "name": "Test optimal first move",
  "description": "AI should find the highest scoring first move",
  "difficulty": "easy",
  "scenario": {
    "board_state": "empty",
    "rack": ["C", "A", "T", "S", "D", "O", "G"],
    "expected_behavior": {
      "type": "optimal_move",
      "min_score": 10,
      "should_use_center": true
    }
  },
  "validation": {
    "judge_calls": [
      {
        "word": "CATS",
        "expected_valid": true
      }
    ],
    "scoring": {
      "expected_min": 10,
      "expected_max": 50
    }
  },
  "tags": ["first-move", "scoring", "basic"]
}
```

## Running IQ Tests

```bash
# Run all IQ tests
poetry run pytest tests/test_iq_tests.py -v -m stress

# Run specific difficulty
poetry run pytest tests/test_iq_tests.py -v -m stress -k easy

# Run with real API calls (requires .env)
poetry run pytest tests/test_iq_tests.py -v -m "stress and openai"
```

## Creating IQ Tests

### Via UI (Future Feature)
The UI will have a "Create IQ Test" button that:
1. Saves current game state
2. Allows user to define expected behavior
3. Exports to JSON in this directory

### Manually
Create a new `.iq.json` file in this directory following the format above.

## Test Categories

- **easy** - Basic scenarios (first move, simple words)
- **medium** - Multiple possibilities, cross-words
- **hard** - Complex board states, blank tiles
- **expert** - Edge cases, rule violations, adversarial scenarios

## Purpose

IQ tests serve as:
1. **Regression tests** - Ensure AI doesn't regress in quality
2. **Benchmarks** - Compare different AI models or prompts
3. **Documentation** - Show expected behavior for edge cases
4. **Development** - Test-driven development for AI features
