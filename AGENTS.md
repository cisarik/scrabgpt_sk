# Repository Guidelines

## Project Structure & Module Organization

`scrabgpt/` contains runtime code grouped by domain:

- `core/` — deterministic game domain and persistence primitives
  - `board.py`, `rules.py`, `scoring.py`, `tiles.py`, `rack.py`, `state.py`, `game.py`
  - `variant_store.py` — variant registry + active variant persistence (`SCRABBLE_VARIANT`)
  - `team_config.py` — provider model selections, teams, opponent mode persistence
  - `opponent_mode.py` — `LMSTUDIO`, `BEST_MODEL`, `OPENROUTER`, `NOVITA`, `GEMINI`

- `ai/` — provider clients, orchestration, tools, and agents
  - Core clients: `client.py` (OpenAI), `openai_tools_client.py`, `openrouter.py`, `novita.py`, `vertex.py`
  - Orchestration: `multi_model.py`, `novita_multi_model.py`
  - Tooling: `mcp_tools.py`, `tool_adapter.py`, `mcp_adapter.py`, `tool_schemas.py`, `tool_registry.py`
  - Variant/bootstrap: `variant_agent.py`, `wiki_loader.py`, `variants.py`, `language_agent.py`
  - Model utilities: `model_selector_agent.py`, `model_auto_updater.py`, `model_fetcher.py`
  - Experimental/partial: `agent_player.py` (currently stub)

- `ui/` — PySide6 UI and interaction flow
  - Main app loop: `app.py`
  - Primary settings entrypoint: `settings_dialog.py`
  - Provider dialogs: `ai_config.py`, `novita_config_dialog.py`, `opponent_mode_selector.py`
  - Profiling/inspection: `agents_dialog.py`, `agent_status_widget.py`, `model_results.py`, `response_detail.py`, `chat_dialog.py`
  - Optional/legacy/experimental dialogs: `model_selector_dialog.py`, `agent_config_dialog.py`, `iq_creator.py`

- `assets/`
  - `premiums.json`
  - `variants/` (installed variant JSON, cached Wikipedia HTML, generated summarizations)

- `tests/` mirrors runtime features (domain, AI integration, UI-adjacent logic).
- `tools/` contains utility scripts (parsing, provider tests, persistence checks).

Important reality check:
- `BoardView` and `RackView` are currently implemented inside `scrabgpt/ui/app.py`.
- `scrabgpt/ui/app.py` still contains legacy/internal classes and remains a large module.

## Environment Variables

### Core Runtime

- `OPENAI_API_KEY`
- `AI_MOVE_MAX_OUTPUT_TOKENS`
- `AI_MOVE_TIMEOUT_SECONDS`
- `JUDGE_MAX_OUTPUT_TOKENS`
- `SHOW_AGENT_ACTIVITY_AUTO`

### OpenAI / Local OpenAI-compatible

- `OPENAI_MODELS` (CSV)
- `OPENAI_MODEL`
- `OPENAI_BASE_URL` or `LLMSTUDIO_BASE_URL`
- `LLMSTUDIO_MODEL`
- `AI_CONTEXT_SESSION` or `SCRABGPT_CONTEXT_SESSION`
- `AI_CONTEXT_HISTORY`

### OpenAI Tool Workflow Controls

- `OPENAI_ENFORCE_TOOL_WORKFLOW`
- `OPENAI_MIN_WORD_VALIDATIONS`
- `OPENAI_MIN_SCORED_CANDIDATES`
- `OPENAI_TOOL_ROUND_TIMEOUT_SECONDS`

### OpenRouter / Novita

- `OPENROUTER_API_KEY`
- `NOVITA_API_KEY`

### Google Vertex / Gemini

- `GOOGLE_API_KEY` (legacy/direct Gemini fallback path)
- `GOOGLE_CLOUD_PROJECT` or `GCLOUD_PROJECT`
- `GOOGLE_CLOUD_LOCATION` or `VERTEX_LOCATION`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `GEMINI_MODEL` / `GOOGLE_GEMINI_MODEL`
- `GEMINI_MODELS` / `GOOGLE_GEMINI_MODELS`
- `GEMINI_PROBE_MODEL`
- `VERTEX_MODEL_ROUND_TIMEOUT_SECONDS`

### Variant / Logging / Misc

- `SCRABBLE_VARIANT`
- `SCRABGPT_LOG_PATH`
- `OPENAI_BEST_MODEL_AUTO_UPDATE`

## Unified AI Move Budget (Mandatory)

Use a single budget pair for all AI move calls:

- `AI_MOVE_MAX_OUTPUT_TOKENS`
- `AI_MOVE_TIMEOUT_SECONDS`

Guidelines:
- Do not introduce provider-specific move token knobs when unified knobs are available.
- Clamp outgoing values before API calls (tokens: `500..20000`, timeout: minimum `5s`).
- Keep persisted provider selections synchronized with these limits.

## Build, Test, and Dev Commands

Run from repo root.

```bash
poetry install
poetry run scrabgpt
```

Preferred app start:

```bash
poetry run scrabgpt
# or
poetry run python -m scrabgpt.ui.app
```

Quality checks:

```bash
poetry run ruff check .
poetry run mypy scrabgpt
poetry run pytest
```

Offline CI-like tests:

```bash
poetry run pytest -m "not internet and not ui"
```

## Coding Style & Type Expectations

- Python requirement: `>=3.11,<3.14`.
- Ruff line length: 100.
- `mypy` strict mode is enabled.
- Use explicit typing for public interfaces and async functions.
- Keep `core/` pure (no UI/network dependencies).
- Prefer deterministic pure helpers in `core/`; wire side effects in `ai/` and `ui/` layers.

## Async + Qt Patterns

- Network and long-running tasks must not block UI thread.
- Use `AsyncAgentWorker`/`QThread` patterns for background execution.
- Emit signals from worker thread; update widgets in slots on main thread.
- For parallel model calls, use `asyncio.gather()` and isolate per-model failure states.

## Multi-Provider AI Development Rules

### Response Handling

- Validate structure before parse (`choices`, `message`, `content` equivalents).
- Handle empty/whitespace responses explicitly.
- Preserve provider metadata (`trace_id`, `call_id`, raw payload) for diagnostics.
- Return structured error status dictionaries instead of hard crashes.

### Parsing & Fallback

- Primary move parse uses `parse_ai_move` + `to_move_payload`.
- If parse fails and response has substantial content, use GPT fallback (`parsing_fallbacks.py`).
- Keep raw response + analysis for transparency in UI detail dialogs.

### Tool Workflow

- Tool registry source of truth: `mcp_tools.ALL_TOOLS`.
- OpenAI schema adapter: `tool_adapter.get_openai_tools()`.
- Vertex/Gemini adapter: `tool_adapter.get_gemini_tools()`.
- Enforce workflow toggles only through existing env flags.

## Persistence Rules

- Global config: `~/.scrabgpt/config.json`
- Provider selections / teams: `~/.scrabgpt/teams/`
- Variant assets: `scrabgpt/assets/variants/`

When changing persistence:
- Maintain backward compatibility where possible (`TeamConfig.from_dict` already migrates legacy `models`).
- Avoid breaking existing user files silently.

## Testing Guidelines

### Test Categories

1. Domain logic: pure offline tests in `tests/test_*` for rules/scoring/tiles/state.
2. Integration/API tests: provider and network calls (marker-based).
3. UI-adjacent tests: mark with `@pytest.mark.ui`.
4. Stress/benchmark suites: mark with `@pytest.mark.stress`.

### Markers

Configured markers include:

- `network`
- `openai`
- `google`
- `openrouter`
- `internet`
- `stress`
- `ui`

`tests/conftest.py` auto-applies `internet` to API/network-marked tests.

### CI Notes

Workflows currently exist in:

- `.github/workflows/ci.yml`
- `.github/workflows/tests.yml`

When updating CI behavior, keep offline-safe test runs available.

## Known Technical Debt (Do Not Hide)

- `scrabgpt/ai/agent_player.py` is still a stub (`NotImplementedError`).
- `MainWindow._on_user_chat_message` in `scrabgpt/ui/app.py` is placeholder logic.
- `scrabgpt/ui/app.py` is a large mixed-responsibility module (ongoing decomposition target).
- `model_fetcher.py` uses static model pricing metadata.

## Practical Refactor Priorities

If you touch these areas, prioritize:

1. Reduce `app.py` coupling by extracting self-contained widgets/services.
2. Keep provider clients thin; place orchestration logic in dedicated modules.
3. Preserve observability (trace ids, attempt logs, partial status updates).
4. Prefer explicit migration paths over one-off format rewrites.

## Commit & PR Guidance

- Use concise imperative commit titles.
- In PR descriptions include:
  - behavior change summary
  - test/lint/type-check evidence
  - env or persistence changes
  - UI screenshots for visible changes
- Never commit secrets or `.env`.
