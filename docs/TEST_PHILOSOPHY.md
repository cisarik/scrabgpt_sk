# Test Philosophy & Infrastructure

This document describes the testing philosophy and infrastructure for ScrabGPT project.

## Overview

ScrabGPT uses a hybrid testing approach that combines **offline unit tests** with **online integration tests**. This allows us to:
- **Develop quickly** with fast, deterministic unit tests
- **Validate reality** with integration tests that call real APIs
- **Control costs** by skipping expensive tests on CI
- **Maintain quality** with comprehensive test coverage

## Test Categories

### 1. Domain Tests (Offline)
**Location:** `tests/test_scoring.py`, `tests/test_rules.py`, `tests/test_tiles.py`, etc.  
**Philosophy:** Pure logic, no mocks, no network, 100% deterministic

These tests validate core game logic:
- Scoring calculations
- Rule enforcement
- Tile management
- Board state

**Run:** Always run on local dev and CI

```bash
poetry run pytest tests/test_scoring.py -v
```

### 2. Integration Tests (Online)
**Location:** `tests/test_internet_tools.py`, `tests/test_agent_player.py`, etc.  
**Philosophy:** Real API calls, real network requests, validates actual behavior

These tests validate:
- OpenAI API integration
- OpenRouter API integration
- HTTP requests to external services
- Multi-model orchestration

**Markers:**
- `@pytest.mark.openai` - Calls OpenAI API (requires `OPENAI_API_KEY`)
- `@pytest.mark.openrouter` - Calls OpenRouter API (requires `OPENROUTER_API_KEY`)
- `@pytest.mark.network` - Makes HTTP requests
- `@pytest.mark.internet` - Auto-applied to all above

**Run:** On local dev with `.env` configured; **skipped on CI**

```bash
# Run all internet tests
poetry run pytest -m internet -v

# Run only OpenAI tests
poetry run pytest -m openai -v

# Skip internet tests (for CI)
poetry run pytest -m "not internet" -v
```

### 3. UI Tests
**Location:** Tests that use Qt widgets  
**Marker:** `@pytest.mark.ui`  
**Philosophy:** Test business logic, not pixel-perfect rendering

**Run:** On local dev; **skipped on CI** (no display server)

```bash
# Run UI tests
poetry run pytest -m ui -v

# Skip UI tests (for CI)
poetry run pytest -m "not ui" -v
```

### 4. Stress Tests / IQ Tests
**Location:** `tests/test_iq_tests.py`, `tests/iq_tests/*.iq.json`  
**Marker:** `@pytest.mark.stress`  
**Philosophy:** User-created validation scenarios for AI quality

These tests are **user-generated** and stored as JSON files. They validate:
- AI agent optimal move generation
- Judge word validation accuracy
- Edge cases and corner cases
- Regression prevention

**Format:** See `tests/iq_tests/README.md` for JSON schema

**Run:** On demand, not part of regular test suite

```bash
# Run all IQ tests
poetry run pytest tests/test_iq_tests.py -v -m stress

# Run specific difficulty
poetry run pytest tests/test_iq_tests.py -v -m stress -k easy
```

## Environment Setup

### Local Development

1. **Install dependencies:**
   ```bash
   poetry install
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

3. **Run all tests:**
   ```bash
   poetry run pytest -v
   ```

### Continuous Integration (CI)

**GitHub workflow** (`.github/workflows/tests.yml`) runs:
```bash
poetry run pytest -m "not internet and not ui" -v
```

This skips expensive/flaky tests while validating core logic.

**Optional:** Separate workflow for integration tests (manual trigger or schedule).

## Pytest Configuration

### pyproject.toml

```toml
[tool.pytest.ini_options]
addopts = "-q"
asyncio_mode = "auto"  # Enable pytest-asyncio
markers = [
    "network: tests that perform live network requests (httpx)",
    "openai: tests that call OpenAI API (requires OPENAI_API_KEY)",
    "openrouter: tests that call OpenRouter API (requires OPENROUTER_API_KEY)",
    "internet: tests that require internet access (network or API calls)",
    "stress: stress tests / IQ tests for AI validation",
    "ui: tests that require Qt UI (skipped on CI)",
]
```

### conftest.py

`tests/conftest.py` automatically:
- Loads `.env` file at test session start
- Checks for API keys and warns if missing
- Auto-applies `internet` marker to API/network tests
- Provides `openai_api_key` and `openrouter_api_key` fixtures

## Writing Tests

### Example: Domain Test (Offline)

```python
def test_scoring_calculates_basic_word():
    """Test pure scoring logic without external dependencies."""
    board = Board()
    rack = ["C", "A", "T"]
    placements = [
        Placement(7, 7, "C"),
        Placement(7, 8, "A"),
        Placement(7, 9, "T"),
    ]
    
    score = calculate_score(board, placements)
    assert score == 5  # C(3) + A(1) + T(1)
```

### Example: Integration Test (Online)

```python
@pytest.mark.openai
async def test_judge_validates_real_word(openai_api_key):
    """Test real OpenAI API call for word validation."""
    if not openai_api_key:
        pytest.skip("OPENAI_API_KEY not set")
    
    client = OpenAIClient()
    result = client.judge_words(["HELLO"], language="English")
    
    assert result["all_valid"] is True
    assert result["results"][0]["word"] == "HELLO"
```

### Example: Stress Test (IQ Test)

1. **Create IQ test:** `tests/iq_tests/my_scenario.iq.json`
   ```json
   {
     "name": "Test optimal move",
     "difficulty": "easy",
     "scenario": {
       "board_state": "empty",
       "rack": ["C", "A", "T", "S"]
     },
     "validation": {
       "judge_calls": [
         {"word": "CATS", "expected_valid": true}
       ]
     }
   }
   ```

2. **Run tests:**
   ```bash
   poetry run pytest tests/test_iq_tests.py -v -m stress
   ```

## Best Practices

### DO:
✅ Use real API calls for integration tests (marked with `@pytest.mark.internet`)  
✅ Load API keys from `.env` via `conftest.py`  
✅ Skip tests gracefully if API keys not set: `pytest.skip("OPENAI_API_KEY not set")`  
✅ Use deterministic seeds for domain tests  
✅ Test business logic separately from UI rendering  
✅ Create IQ tests for edge cases and regressions  

### DON'T:
❌ Mock OpenAI/OpenRouter in integration tests (defeats the purpose)  
❌ Commit `.env` file to git (use `.env.example`)  
❌ Run integration tests on every commit (expensive)  
❌ Test pixel-perfect UI rendering (test logic instead)  
❌ Mix domain logic with network logic (separate concerns)  

## Cost Management

**Integration tests cost money!** Here's how we manage it:

1. **Skip on CI:** Internet tests don't run on every commit
2. **Manual trigger:** Integration tests run on-demand via GitHub Actions
3. **Local dev:** Developers control when to run expensive tests
4. **Markers:** Easy to filter tests by cost

**Example:**
```bash
# Free: Run only offline tests
poetry run pytest -m "not internet" -v

# Paid: Run integration tests (requires API keys)
poetry run pytest -m internet -v

# Very paid: Run all stress tests with real API
poetry run pytest -m "stress and openai" -v
```

## Useful Commands

```bash
# Run all tests
poetry run pytest -v

# Run offline tests only (CI mode)
poetry run pytest -m "not internet and not ui" -v

# Run integration tests
poetry run pytest -m internet -v

# Run specific marker
poetry run pytest -m openai -v
poetry run pytest -m stress -v
poetry run pytest -m ui -v

# Run specific file
poetry run pytest tests/test_scoring.py -v

# Run with coverage
poetry run pytest --cov=scrabgpt --cov-report=html

# Debug mode
poetry run pytest -vv --tb=long -s
```

## Summary

| Category | Marker | Network | Cost | Run On CI |
|----------|--------|---------|------|-----------|
| Domain | None | ❌ | Free | ✅ Yes |
| Integration | `internet` | ✅ | $$$ | ❌ No |
| OpenAI | `openai` | ✅ | $$ | ❌ No |
| OpenRouter | `openrouter` | ✅ | $ | ❌ No |
| UI | `ui` | ❌ | Free | ❌ No (no display) |
| Stress/IQ | `stress` | Varies | Varies | ❌ No (manual) |

This hybrid approach gives us:
- **Fast feedback** from offline tests
- **Real confidence** from integration tests
- **Cost control** by running expensive tests selectively
- **Quality** through comprehensive coverage
