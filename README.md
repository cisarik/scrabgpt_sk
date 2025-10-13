
# ScrabGPT

Cross‑platform Python desktop app to play Scrabble against multiple AI models at once.

Supports OpenRouter and Novita reasoning providers, persists team presets per provider, and ships
with tooling to bootstrap localized variants from Wikipedia data.

MVP demonstrates:
- clean domain core (board, scoring, rules),
- **structured** OpenAI calls (AI player + batched judge),
- **async agent system** with background execution and real-time progress tracking,
- **unified settings dialog** with tabbed interface and green theme,
- **agent activity monitoring** with non-blocking dialogs and toolbar animations,
- PySide6 UI with thread-safe signal/slot architecture,
- TDD for scoring and rules.

## Quick start (Poetry)
```bash
poetry install
cp .env.example .env  # add your keys
poetry run python -m scrabgpt.ui.app
```

> All OpenAI requests/responses are pretty-printed to the terminal (key masked).
> Agent activities are tracked in real-time with OpenAI-style animations.

## Multi-provider AI setup
- `OpenRouter`: keep `OPENROUTER_API_KEY` in `.env`, configure models in **Nastavenia → AI
  Protivník**, and use the multi-model dialog to pick up to 10 competitors.
- `Novita`: add `NOVITA_API_KEY`; the shared `AI_MOVE_MAX_OUTPUT_TOKENS` and
  `AI_MOVE_TIMEOUT_SECONDS` settings apply automatically to Novita calls. Select **Novita AI**
  in the same settings tab to launch the
  dedicated model browser with reasoning metadata.
- `Teams`: selections persist under `~/.scrabgpt/teams/*.json`; the app loads them on
  startup and also restores the last opponent mode from `~/.scrabgpt/config.json`.
- Docs: see `docs/NOVITA_INTEGRATION.md`, `docs/NOVITA_QUICKSTART.md`, and
  `docs/PERSISTENCE_FIX.md` for setup, troubleshooting, and persistence details.

### Runtime Limits (Unified)
- `AI_MOVE_MAX_OUTPUT_TOKENS` — hard cap used for every AI move (OpenRouter, Novita, single-model, and agents)
- `AI_MOVE_TIMEOUT_SECONDS` — single timeout applied to all multi-model calls and background agents
- `JUDGE_MAX_OUTPUT_TOKENS` — dedicated cap for referee validation responses

Both move-related settings can be adjusted inside **Nastavenia → AI Protivník**; changes sync back into `.env` automatically and propagate to saved team presets.

## AI player prompt rules

- The AI may hook onto existing strings only when the resulting main word is valid; avoid glueing.
- The returned `word` must equal the final main word on the board (existing letters + placements).

## Repro mode (deterministic TileBag)

To reproduce games or debug reliably:

1. Open Settings (⚙️), enable "Repro mód" and set an integer "Seed".
2. Start a new game (🆕). When enabled, the tile bag is created as `TileBag(seed=<seed>)`.
3. Each new game logs `game_start seed=<X> repro=<true|false>` to console and `scrabgpt.log`.

This is runtime-only; no values are persisted to `.env`.

## Agent System with Background Execution

ScrabGPT features a sophisticated async agent system for background operations:

### Key Features
- **Non-blocking dialogs**: Agents Dialog can be closed while operations continue in background
- **Real-time progress tracking**: OpenAI-style animations with fading text and animated dots
- **Thread-safe architecture**: Qt signals/slots for safe cross-thread communication
- **Progress callbacks**: Agents report thinking process, status updates, and results
- **Toolbar integration**: Animated status widget shows current agent activity
- **Multiple concurrent agents**: Global agent dispatcher tracks all running agents

### Components

#### Agents Dialog (`scrabgpt/ui/agents_dialog.py`)
- Tabbed interface with one tab per agent
- Activity log showing thinking process
- Progress bar and status updates
- Response viewer with results
- Can be closed anytime - agents continue in background

#### Language Agent (`scrabgpt/ai/language_agent.py`)
- Async/await MCP pattern implementation
- Fetches supported languages from OpenAI API
- Uses `asyncio.to_thread()` for blocking operations
- Progress callbacks at each step
- 1-hour caching for efficiency

#### Agent Status Widget (`scrabgpt/ui/agent_status_widget.py`)
- OpenAI-style fading animation
- Shows "🤖 Agent: Status..." with animated dots (1-3 cycling)
- Auto-hides after completion (2 second delay)
- Smooth fade in/out with QPropertyAnimation

### Thread Safety
All agent operations use proper Qt threading patterns:
```python
# Worker thread emits signals (thread-safe)
worker.progress_update.emit(update)

# Main thread receives via signal/slot (safe for UI updates)
worker.progress_update.connect(on_progress_handler)
```

Workers live in MainWindow's `agent_workers` dict so they survive dialog closures.

### Usage Example
```python
# Create agent
agent = VariantBootstrapAgent()

# Create worker with auto-injected progress callback
worker = AsyncAgentWorker(
    agent.bootstrap,
    force_refresh=True,
)

# Connect signals
worker.progress_update.connect(on_progress)
worker.agent_finished.connect(on_finished)
worker.agent_error.connect(on_error)

# Start in background
worker.start()

# Dialog can be closed - worker continues!
```

### Settings Integration
- **Auto-show agents**: `SHOW_AGENT_ACTIVITY_AUTO=true` in `.env`
- Settings accessible from "⚙️ Nastavenia" toolbar button
- 4 tabs: Všeobecné, AI Protivník, Nastavenia API, Upraviť prompt protihráča
- Green forest theme matching game aesthetic

## Variant bootstrap pipeline
- `VariantBootstrapAgent` turns Wikipedia Scrabble tables into JSON-like summaries for each
  language while streaming progress through the Agents dialog.
- `wiki_loader.py` caches the source page at
  `scrabgpt/assets/variants/wikipedia_scrabble_cache.html` for offline parsing.
- Generated summaries live in `scrabgpt/assets/variants/lang_summarizations/` (gitignored) and
  seed future variant definitions.
- Tooling: `tools/parse_wikipedia_languages.py`, `tools/test_novita.py`, and
  `tools/test_teams.py` exercise the new pipelines and persistence logic.
- Tests: `tests/test_variant_agent.py` plus updates to agent, model, and opponent selector tests
  cover parsing edge cases, persistence, and Novita provider flows.

## Save/Load

ScrabGPT supports saving and loading the full game state to JSON.

- schema_version: "1"
- grid: 15 strings of length 15 ('.' or 'A'..'Z')
- blanks: positions where a blank tile was used
- premium_used: positions where board premiums were consumed
- human_rack, ai_rack: letters currently on racks
- bag: exact order of remaining tiles
- human_score, ai_score, turn
- optional: last_move_cells, last_move_points, consecutive_passes, repro, seed

Notes:
- The format is versioned and future migrations may be introduced. Always check `schema_version`.
- No secrets are stored in save files.

---

## Changelist - Recent Features & Improvements

### Novita Reasoning Provider & Multi-Model Upgrades
- Added `NovitaClient` with dynamic model fetch and reasoning content capture.
- New `NovitaConfigDialog` enables search, filters, and 10-model selection caps.
- Concurrent orchestration in `novita_multi_model.py` mirrors OpenRouter pipeline.
- Status bar, medals, and response detail dialog highlight Novita turns.
- `.env` now supports `NOVITA_API_KEY` and reuses the shared `AI_MOVE_MAX_OUTPUT_TOKENS` and
  `AI_MOVE_TIMEOUT_SECONDS` limits for Novita orchestration.
- Deep dives live in `docs/NOVITA_INTEGRATION.md` and `docs/NOVITA_QUICKSTART.md`.

### Persistent Teams & Opponent Mode
- `TeamManager` saves per-provider teams under `~/.scrabgpt/teams/*.json`.
- Teams auto-load on startup, restoring selected models and timeouts.
- Opponent mode persists in `~/.scrabgpt/config.json`, preventing BEST_MODEL resets.
- Settings dialog syncs selections, logging updates instead of alert popups.
- New tooling (`tools/test_teams.py`) verifies load/save flows and cleanup.

### Variant Bootstrap Toolkit
- `VariantBootstrapAgent` streams Wikipedia fragment summaries with progress hooks.
- Cached HTML lives in `scrabgpt/assets/variants/wikipedia_scrabble_cache.html`.
- Summaries render to `assets/variants/lang_summarizations/` (ignored by git).
- `wiki_loader.py` plus `tools/parse_wikipedia_languages.py` parse table fragments.
- `tests/test_variant_agent.py` covers parsing accuracy and file writes.

### Agent System & Background Execution
- Non-blocking Agents dialog tracks async workers across providers and variants.
- Animated toolbar widget reports agent status with dot cycling and fade effects.
- Language and variant agents run via `AsyncAgentWorker` with auto progress hooks.
- Signal/slot wiring keeps UI updates on the main thread.

### Multi-Model AI Support
- OpenRouter multi-model dialog allows picking up to 10 concurrent competitors.
- Results table shows medals, validity, and scores per model.
- Response detail dialog reveals raw payloads and GPT fallback analysis.
- Status bar emits `[model] status` messages through each turn.

### Intelligent Error Handling & Recovery
- GPT fallback parser extracts moves when responses are free-form text.
- Structured logging groups parse, network, and validation failures.
- Slovak-facing errors mirror detailed English entries in tooltips and logs.
- Supports providers that shift content into `reasoning_content`.

### Performance & UX Improvements
- Parallel judge validation cuts total turn latency by several seconds.
- Results table clears on retry to prevent stale rows.
- Config dialogs use dark theme styling for all providers.
- Settings forms resize gracefully across desktop platforms.

### Technical Improvements
- GPT-5 parameter fixes ensure `max_completion_tokens` is passed correctly.
- Prompt templates refined for resilient extraction under chain-of-thought replies.
- Timing logs measure per-model latency and total orchestration duration.
- Team persistence tested end-to-end with new CLI scripts.
