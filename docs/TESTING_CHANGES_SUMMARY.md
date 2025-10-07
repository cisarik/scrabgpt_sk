# Testing Infrastructure Changes - Summary

## What Changed

We've completely restructured the testing philosophy to allow **real API calls** while maintaining **cost control** through selective test execution.

## Key Changes

### 1. Test Philosophy Change (PRD.md)

**Before:**
> "Deterministickosť: všetky doménové testy bez siete; OpenAI volania sa mockujú."

**After:**
- **Domain tests** (core/): Offline, deterministic, no mocks
- **Integration tests** (ai/, ui/): Real API calls allowed, marked with pytest markers
- **CI/CD**: GitHub workflow skips `internet`, `openai`, `openrouter`, `ui` tests
- **Local dev**: All tests run with real API calls (if `.env` configured)

### 2. Pytest Configuration (pyproject.toml)

**Added:**
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"  # Enable async test support
markers = [
    "network: tests that perform live network requests (httpx)",
    "openai: tests that call OpenAI API (requires OPENAI_API_KEY)",
    "openrouter: tests that call OpenRouter API (requires OPENROUTER_API_KEY)",
    "internet: tests that require internet access (network or API calls)",
    "stress: stress tests / IQ tests for AI validation",
    "ui: tests that require Qt UI (skipped on CI)",
]
```

**Dependencies:**
- Added `pytest-asyncio` for async test support

### 3. Environment Loading (tests/conftest.py) ✨ NEW FILE

Automatically loads `.env` file at test session start:
```python
def pytest_configure(config):
    """Load environment variables from .env file."""
    load_dotenv(Path(__file__).parent.parent / ".env")
    # Check for API keys and warn if missing
```

**Provides fixtures:**
- `openai_api_key` - Get OpenAI API key from environment
- `openrouter_api_key` - Get OpenRouter API key from environment

**Auto-marks tests:**
- Tests with `@pytest.mark.openai` → auto-marked as `internet`
- Tests with `@pytest.mark.network` → auto-marked as `internet`

### 4. CI/CD Workflow (.github/workflows/tests.yml) ✨ NEW FILE

**Main test job:** Runs only offline tests
```yaml
- name: Run offline tests only
  run: poetry run pytest -v -m "not internet and not ui" --tb=short
```

**Optional integration job:** Runs only on manual trigger
```yaml
integration-tests:
  if: github.event_name == 'workflow_dispatch' || github.event_name == 'schedule'
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: poetry run pytest -v -m "internet and not ui" --tb=short
```

### 5. IQ Test Infrastructure ✨ NEW FEATURE

**Created:**
- `tests/iq_tests/` - Directory for user-created test scenarios
- `tests/iq_tests/README.md` - Documentation for IQ test format
- `tests/iq_tests/example_first_move.iq.json` - Example IQ test
- `tests/test_iq_tests.py` - Pytest infrastructure for running IQ tests

**What are IQ Tests?**
- User-created JSON files defining AI validation scenarios
- Tests AI agent move quality, judge accuracy, edge cases
- Marked with `@pytest.mark.stress`
- Not run on CI (manual execution only)

**Example IQ Test:**
```json
{
  "name": "Optimal first move with CATS",
  "difficulty": "easy",
  "scenario": {
    "board_state": "empty",
    "rack": ["C", "A", "T", "S", "D", "O", "G"]
  },
  "validation": {
    "judge_calls": [
      {"word": "CATS", "expected_valid": true}
    ]
  }
}
```

**Run IQ Tests:**
```bash
# Run all IQ tests
poetry run pytest tests/test_iq_tests.py -v -m stress

# Run with real API calls
poetry run pytest tests/test_iq_tests.py -v -m "stress and openai"
```

### 6. Documentation Updates

**Updated:**
- `PRD.md` - New testing section with marker documentation
- `AGENTS.md` - New testing guidelines, removed mocking requirements

**Created:**
- `TEST_PHILOSOPHY.md` - Comprehensive testing documentation
- `TESTING_CHANGES_SUMMARY.md` - This file

## Test Statistics

```
Offline tests (run on CI):          ~93 tests
Integration tests (manual):         ~20 tests  
UI tests (local only):             ~10 tests
IQ tests (user-created):           Unlimited
```

## Usage Examples

### For Developers (Local)

```bash
# Run all tests (includes real API calls if .env configured)
poetry run pytest -v

# Run only offline tests (fast, free)
poetry run pytest -m "not internet and not ui" -v

# Run integration tests (requires API keys in .env)
poetry run pytest -m internet -v

# Run only OpenAI tests
poetry run pytest -m openai -v

# Run IQ tests
poetry run pytest tests/test_iq_tests.py -v -m stress
```

### For CI/CD

```bash
# GitHub Actions automatically runs:
poetry run pytest -v -m "not internet and not ui" --tb=short
```

### Writing New Tests

**Integration test with real API:**
```python
@pytest.mark.openai
async def test_judge_validates_word(openai_api_key):
    """Test real OpenAI judge validation."""
    if not openai_api_key:
        pytest.skip("OPENAI_API_KEY not set")
    
    client = OpenAIClient()
    result = client.judge_words(["HELLO"], language="English")
    assert result["all_valid"] is True
```

## Migration Guide

### For Existing Tests

1. **No changes needed** for domain tests (test_scoring.py, test_rules.py, etc.)
2. **Add markers** to integration tests:
   ```python
   # Before
   async def test_something():
       ...
   
   # After
   @pytest.mark.openai
   async def test_something(openai_api_key):
       if not openai_api_key:
           pytest.skip("OPENAI_API_KEY not set")
       ...
   ```

### For New Tests

1. **Domain tests:** No marker, no network, deterministic
2. **Integration tests:** Add `@pytest.mark.openai` or `@pytest.mark.network`
3. **UI tests:** Add `@pytest.mark.ui`
4. **Stress tests:** Create `.iq.json` file in `tests/iq_tests/`

## Benefits

✅ **Fast feedback** - Offline tests run on every commit (~93 tests, < 5 seconds)  
✅ **Real confidence** - Integration tests validate actual API behavior  
✅ **Cost control** - Expensive tests don't run on CI  
✅ **Flexibility** - Developers choose when to run expensive tests  
✅ **Quality** - IQ tests prevent regressions in AI behavior  
✅ **Documentation** - Clear markers show test requirements  

## Breaking Changes

⚠️ **None!** This is purely additive. Old tests still work.

## Future UI Integration

The IQ test infrastructure is ready for UI integration:
- **UI Button:** "Create IQ Test" → saves current game state as `.iq.json`
- **User flow:** Play game → interesting scenario → save as IQ test → validate AI behavior
- **See:** `tests/test_iq_tests.py::create_iq_test()` helper function

## Questions?

See:
- `TEST_PHILOSOPHY.md` - Comprehensive testing guide
- `tests/iq_tests/README.md` - IQ test format documentation
- `AGENTS.md` - Testing guidelines section
- `PRD.md` - Updated testing requirements
