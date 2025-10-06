# Repository Guidelines

## Project Structure & Module Organization
`scrabgpt/` holds all runtime code organized into clear domains:
- **`core/`** — Pure domain logic: board math, rules, scoring, tile management. Zero dependencies on UI or network.
- **`ai/`** — AI integration layer:
  - `client.py` — OpenAI client wrapper
  - `judge.py`, `player.py` — Single-model AI judge and player
  - `openrouter.py` — OpenRouter API client for multi-model support
  - `multi_model.py` — Multi-model orchestration, concurrent execution, GPT fallback parser
  - `schema.py` — Pydantic models for structured AI responses
- **`ui/`** — PySide6 widgets and dialogs:
  - `app.py` — Main application window and game loop
  - `board_view.py`, `rack_view.py` — Game board and tile rack widgets
  - `ai_config.py` — Multi-model configuration dialog
  - `model_results.py` — Competition results table
  - `response_detail.py` — Raw response viewer with GPT analysis
  - `prompt_editor.py`, `iq_creator.py` — Prompt and IQ test management (experimental)
- **`assets/`** — Static data: `premiums.json` for board premium squares
- **`logging_setup.py`** — Rich logging configuration

**Tests** live in `tests/`, mirroring domain areas. Add fixtures beside the scenarios they support. **Utility scripts** stay in `tools/` (e.g., `clear.sh`). **Documentation** includes `README.md` (user-facing), `PRD.md` (product spec), and `docs/` (detailed feature documentation). The `prompts/` directory holds prompt templates for AI models.

## Build, Test, and Development Commands
`poetry install` provisions dependencies and the virtualenv. Run the desktop app via `poetry run python -m scrabgpt.ui.app` or the CLI shim `poetry run scrabgpt`. Execute automated checks with `poetry run pytest`, optionally `-k keyword` for a subset. Enforce style through `poetry run ruff check` (add `--fix` when safe) and typing with `poetry run mypy`. Run commands from the repo root so relative paths resolve.

## Coding Style & Naming Conventions
Code targets Python ≥3.10, 4-space indentation, and a 100-character limit enforced by Ruff. Type hints are mandatory because `mypy` runs in strict mode. Modules remain snake_case; Qt classes and QObject descendants use CamelCase. Pydantic models or dataclasses should back structured exchanges with OpenAI, and avoid heavy logic at import time—prefer pure functions plus explicit wiring in entry points.

### Async/Await Patterns
Multi-model features use `asyncio` for concurrent API calls. Follow these patterns:
- Use `async def` for functions that perform I/O (API calls, file operations)
- Use `asyncio.gather()` for parallel operations (e.g., validating multiple models)
- Use `asyncio.to_thread()` to run blocking sync code in thread pools (e.g., judge validation)
- Always type hint async functions with proper return types: `async def foo() -> ResultType:`
- For Qt integration, use `QThread` workers that internally run async code with `asyncio.run()`

### Error Handling & Logging
- **Graceful degradation**: Handle API errors without crashing. Return error status in result dicts.
- **Logging levels**: Use `log.debug()` for verbose details, `log.info()` for normal flow, `log.warning()` for recoverable issues, `log.error()` for failures, `log.exception()` for caught exceptions.
- **User-facing errors**: Display Slovak messages in UI; include full English technical details in logs/tooltips.
- **Validation**: Check for empty/null responses before parsing JSON. Log full response on unexpected structure.

### Qt-Specific Patterns
- Signals must be declared as class attributes: `signal_name = Signal(type1, type2)`
- Use `@Slot()` decorator for slot methods connected to signals
- Long-running operations (API calls, validation) must run in `QThread` workers
- Emit signals from worker threads to update UI (never call UI methods directly from threads)
- Dark theme: Use `#1a1a1a` for backgrounds, `#2a2a2a` for headers, `white` for text, `#444` for borders

## Testing Guidelines
Tests follow the `tests/test_<feature>.py` pattern and use pytest. Name functions `test_<behavior>_<condition>` to clarify intent. Reuse fixtures that craft boards and racks; place new fixtures in the same module when feature-specific. Always run `poetry run pytest` locally, and do not rely on real OpenAI traffic.

### Mocking AI Services
- **OpenAI**: Mock `OpenAIClient` methods to return canned responses. Never make real API calls in tests.
- **OpenRouter**: Mock `httpx.AsyncClient` responses with structured JSON matching OpenRouter's API format.
- **Multi-model**: Mock `propose_move_multi_model()` to return a list of result dicts with known moves/scores.
- **Judge validation**: Mock judge responses for both valid and invalid words to test all code paths.

### Testing Async Code
- Use `pytest-asyncio` for async test functions: `async def test_something():`
- Mock async functions with `AsyncMock` from `unittest.mock`
- Test concurrent operations (e.g., `asyncio.gather()`) by mocking individual async calls
- Verify that parallel execution happens correctly (all models called, results aggregated)

### UI Testing
- UI tests are optional and should be marked with `@pytest.mark.ui` to skip on CI
- Test business logic separately from UI rendering when possible
- For Qt widgets, test signal/slot connections and state changes, not pixel-perfect rendering
- Mock long-running operations (API calls) to avoid blocking tests

## Multi-Model Development Guidelines
When working with multi-model features, follow these practices:

### API Response Handling
- **Always validate structure** before parsing: check for `choices`, `message`, and `content` keys
- **Handle empty responses**: Check `if not content or not content.strip()` before JSON parsing
- **Support alternate fields**: Some models (GLM-4.6) return content in `reasoning` field instead of `content`
- **Log full responses**: On unexpected structure, log the entire response for debugging
- **Return error status**: Don't raise exceptions; return `{"status": "error", "error": "description"}` dicts

### GPT Fallback Parser
- Trigger only when: JSON parse fails AND response has substantial content (>50 chars)
- Use GPT-5-mini with `max_completion_tokens` (not `max_tokens` for GPT-5/o1 models)
- Store both `raw_response` and `gpt_analysis` in result dicts for transparency
- If extraction succeeds, set `status="ok"` so the move is treated as valid
- Cost is negligible (~$0.0001 per fallback), so don't over-optimize

### Parallel Validation
- Use `asyncio.gather()` to validate all models concurrently
- Each validation runs in `asyncio.to_thread()` to avoid blocking event loop
- Log timing: `elapsed = loop.time() - start_time` to monitor performance
- Handle individual failures gracefully: one model failing shouldn't block others
- Target: <5 seconds for 5-10 models (3-5x speedup vs sequential)

### UI Integration
- Display results in dark-themed table with medals (🥇🥈🥉) for top 3
- Show model tracking in status bar: `[Model Name] Status message`
- Clear results table on retry to avoid stale data confusion
- Make result rows clickable to show response detail dialog
- Use color coding: green for valid, gray for invalid, red for errors

## Commit & Pull Request Guidelines
History is empty, so default to concise, imperative commit subjects (e.g., `Refine AI prompt budget`) with optional short bodies for context or follow-ups. PRs should brief the functional change, cite manual/automated checks, and link related issues. Attach screenshots or clips for UI updates and list any `.env` keys, migrations, or assets reviewers must prepare.

## Configuration & Secrets
Copy `.env.example` to `.env` and supply API credentials prior to launch:
- **`OPENAI_API_KEY`** — Required for single-model mode (GPT-5-mini) and judge validation
- **`OPENROUTER_API_KEY`** — Required for multi-model mode (competing AI models from OpenRouter.ai)
- Both keys are optional if you only use one mode

Never commit generated files, secrets, or `.env` to version control. The `.env.example` file shows required variables without exposing real credentials.

### Environment Setup Checklist
1. Copy: `cp .env.example .env`
2. Add your OpenAI key for single-model + judge: `OPENAI_API_KEY=sk-...`
3. (Optional) Add OpenRouter key for multi-model: `OPENROUTER_API_KEY=sk-or-v1-...`
4. (Optional) Set default model: `OPENAI_MODEL=gpt-5-mini`
5. Verify keys work: `poetry run python -m scrabgpt.ui.app`

If you plan to develop multi-model features, you'll need both API keys. For basic gameplay or testing, just OpenAI is sufficient.

## Debugging & Development Tools

### Logging
All API requests and responses are logged to console with Rich formatting. Key loggers:
- `scrabgpt.ai.client` — OpenAI API calls (keys masked automatically)
- `scrabgpt.ai.openrouter` — OpenRouter API calls and responses
- `scrabgpt.ai.multi_model` — Multi-model orchestration, timing, validation
- `scrabgpt.ui.app` — UI state changes, user actions, game flow

Adjust log levels in `logging_setup.py` or via environment: `SCRABGPT_LOG_LEVEL=DEBUG`

### Development Mode Features
- **Repro Mode**: Settings → Enable "Repro mód" with a seed for deterministic tile draws
- **Response Detail Dialog**: Click any model result row to inspect raw response + GPT analysis
- **Prompt Editor**: (Experimental) Edit AI prompts without code changes
- **IQ Test Creator**: (Experimental) Create test scenarios for AI validation

### Performance Profiling
- Multi-model timing is logged automatically: `Judge validation completed in 4.82 seconds`
- For deeper profiling, use Python's `cProfile` or `line_profiler` on `propose_move_multi_model()`
- Monitor asyncio event loop with `asyncio.all_tasks()` in debug mode

### Common Issues
- **UI freezing**: Long operations must run in QThread workers, not main thread
- **Empty responses**: Check OpenRouter API status and model availability
- **Parse errors**: Use Response Detail Dialog to see raw model output
- **Type errors**: Run `poetry run mypy` before committing; strict mode catches issues early
- **Import errors**: Ensure `poetry install` completed successfully and virtual env is activated

### Useful Commands
```bash
# Run with debug logging
SCRABGPT_LOG_LEVEL=DEBUG poetry run scrabgpt

# Run specific test file
poetry run pytest tests/test_scoring.py -v

# Check types only in one module
poetry run mypy scrabgpt/ai/multi_model.py

# Fix auto-fixable style issues
poetry run ruff check --fix

# Run app with asyncio debug mode
PYTHONASYNCIODEBUG=1 poetry run scrabgpt
```
