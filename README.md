# ScrabGPT

Desktop Scrabble app (PySide6) with multi-provider AI opponents, tool-calling workflows,
and rich profiling of model decisions.

This README reflects the current codebase on branch `feat/vertex-gemini-3-1` (February 23, 2026).

## North Star

The core mission of this project is to build a Scrabble AI opponent that becomes
practically unbeatable for human players through better orchestration, stronger prompt
engineering, and continuous benchmark-driven improvement.

## What Is Implemented

- Full Scrabble board/rack/scoring/rules core in `scrabgpt/core/`.
- AI opponent modes:
  - `OpenAI` (parallel OpenAI model competition via `OPENAI_MODELS`)
  - `LMStudio` (local OpenAI-compatible endpoint)
  - `OpenRouter` (parallel external model competition)
  - `Novita AI` (parallel reasoning models)
  - `Google` (Vertex Gemini models)
- Unified per-move budget across providers:
  - `AI_MOVE_MAX_OUTPUT_TOKENS`
  - `AI_MOVE_TIMEOUT_SECONDS`
- Tool-calling gameplay workflow with local Scrabble tools (`get_board_state`, `validate_move_legality`, `calculate_move_score`, dictionary checks, etc.).
- Persistent provider model selections and opponent mode in `~/.scrabgpt/`.
- Variant system with installable JSON variants and active variant persistence.
- Async background agents with non-modal activity dialog and model profiling UI.
- Save/load game state (JSON schema versioned).

## Quick Start

```bash
poetry install
cp .env.example .env
poetry run scrabgpt
```

Alternative entrypoint:

```bash
poetry run python -m scrabgpt.ui.app
```

## Python & Dependencies

- Python: `>=3.11,<3.14`
- UI: `PySide6`
- LLM/API: `openai`, `httpx`, `google-genai`, `google-generativeai`

## Environment Variables

### Core

- `OPENAI_API_KEY`
- `AI_MOVE_MAX_OUTPUT_TOKENS` (clamped to `500..20000`)
- `AI_MOVE_TIMEOUT_SECONDS` (minimum `5s`)
- `JUDGE_MAX_OUTPUT_TOKENS`
- `SHOW_AGENT_ACTIVITY_AUTO`

### OpenAI / LMStudio

- `OPENAI_MODELS` (CSV, used by OpenAI mode)
- `OPENAI_MODEL` (single-model fallback)
- `OPENAI_BASE_URL` or `LLMSTUDIO_BASE_URL`
- `LLMSTUDIO_MODEL`
- `AI_CONTEXT_SESSION` or `SCRABGPT_CONTEXT_SESSION`
- `AI_CONTEXT_HISTORY` (1..20)

### OpenAI Tool Workflow Controls

- `OPENAI_ENFORCE_TOOL_WORKFLOW`
- `OPENAI_MIN_WORD_VALIDATIONS`
- `OPENAI_MIN_SCORED_CANDIDATES`
- `OPENAI_TOOL_ROUND_TIMEOUT_SECONDS`

### OpenRouter / Novita

- `OPENROUTER_API_KEY`
- `NOVITA_API_KEY`

### Google Vertex / Gemini

- `GOOGLE_API_KEY` (used by legacy direct Gemini fallback path)
- `GOOGLE_CLOUD_PROJECT` (or `GCLOUD_PROJECT`)
- `GOOGLE_CLOUD_LOCATION` (or `VERTEX_LOCATION`)
- `GOOGLE_APPLICATION_CREDENTIALS` (optional if ADC is used)
- `GEMINI_MODEL` / `GOOGLE_GEMINI_MODEL`
- `GEMINI_MODELS` / `GOOGLE_GEMINI_MODELS` (CSV)
- `GEMINI_PROBE_MODEL`
- `VERTEX_MODEL_ROUND_TIMEOUT_SECONDS`

### Variant & Logging

- `SCRABBLE_VARIANT`
- `SCRABGPT_LOG_PATH`
- `OPENAI_BEST_MODEL_AUTO_UPDATE`

## Running By Mode

### OpenAI mode (cloud)

1. Set `OPENAI_API_KEY`.
2. Configure `OPENAI_MODELS` (comma-separated).
3. In Settings, choose `OpenAI` mode.

### LMStudio mode (local)

1. Start local OpenAI-compatible server (e.g. on `http://localhost:1234/v1`).
2. Set:

```bash
OPENAI_BASE_URL=http://localhost:1234/v1
LLMSTUDIO_MODEL=your-local-model-id
AI_CONTEXT_SESSION=1
```

3. In Settings, choose `LMStudio` mode.

### OpenRouter mode

1. Set `OPENROUTER_API_KEY`.
2. In Settings, configure OpenRouter model set.
3. Choose `OpenRouter` mode.

### Novita mode

1. Set `NOVITA_API_KEY`.
2. Configure Novita models in Settings.
3. Choose `Novita AI` mode.

### Google mode (Vertex)

1. Configure GCP auth (ADC or `GOOGLE_APPLICATION_CREDENTIALS`).
2. Set `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION`.
3. Set `GEMINI_MODEL` (and optional `GEMINI_MODELS`).
4. Choose `Google` mode.

## Key Runtime Flows

### Tool-calling multi-model loop

- `scrabgpt.ai.multi_model.propose_move_multi_model()` orchestrates concurrent model calls.
- Each model attempt can perform tool calls via `OpenAIToolClient` (or Vertex tool adapter).
- Attempts are validated/scored locally, then judge-validated.
- Results stream into `AIModelResultsTable` and agent profile tabs.

### Context session for reasoning models

- In `scrabgpt.ai.player`, when `AI_CONTEXT_SESSION` is on:
  - Prompt history is kept as message transcript.
  - Assistant reasoning/thinking payload is preserved.
  - Context resets on new game/load/variant switch.

### Persistence

- Global config: `~/.scrabgpt/config.json`
- Provider selections and legacy teams: `~/.scrabgpt/teams/`
- Variant definitions: `scrabgpt/assets/variants/*.json`

## Development

```bash
poetry run ruff check .
poetry run mypy scrabgpt
poetry run pytest
```

Useful subsets:

```bash
poetry run pytest -m "not internet and not ui"
poetry run pytest tests/test_multi_model.py -v
poetry run pytest tests/test_openai_tools_client.py -v
```

## Tests and CI

- Markers: `network`, `openai`, `google`, `openrouter`, `internet`, `stress`, `ui`.
- `tests/conftest.py` auto-adds `internet` to API/network-marked tests.
- Workflow coverage currently exists in:
  - `.github/workflows/ci.yml`
  - `.github/workflows/tests.yml`

## Known Gaps / Technical Debt

- `scrabgpt/ai/agent_player.py` is intentionally a stub (`NotImplementedError`).
- In `scrabgpt/ui/app.py`, `_on_user_chat_message` is placeholder (chat response is dummy).
- `scrabgpt/ui/app.py` is still a large monolith containing legacy in-file UI classes.
- `scrabgpt/ai/model_fetcher.py` uses static pricing metadata (not a live pricing API).

## Additional Docs

- `ARCHITECTURE.md` (runtime flow diagrams and extension map)
- `AGENTS.md` (developer/contributor guidance)
- `PRD.md` (living product requirements)
- `docs/NOVITA_INTEGRATION.md`
- `docs/NOVITA_QUICKSTART.md`
- `docs/PERSISTENCE_FIX.md`
- `docs/TEAMS_FEATURE.md`
