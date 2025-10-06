
# ScrabGPT

Cross‑platform Python desktop app to play Scrabble vs **GPT‑5‑mini**.  
MVP demonstrates:
- clean domain core (board, scoring, rules),
- **structured** OpenAI calls (AI player + batched judge),
- PySide6 UI,
- TDD for scoring and rules.

## Quick start (Poetry)
```bash
poetry install
cp .env.example .env  # add your key
poetry run python -m scrabgpt.ui.app
```

> All OpenAI requests/responses are pretty-printed to the terminal (key masked).

## AI player prompt rules

- The AI must not “glue” its letters to adjacent existing strings unless the entire resulting contiguous main string is a valid English word. Prefer proper hooks/intersections.
- The returned `word` must exactly match the final main word formed on the board (existing letters + placements).

## Repro mode (deterministic TileBag)

To reproduce games or debug reliably:

1. Open Settings (⚙️), enable "Repro mód" and set an integer "Seed".
2. Start a new game (🆕). When enabled, the tile bag is created as `TileBag(seed=<seed>)`.
3. Each new game logs `game_start seed=<X> repro=<true|false>` to console and `scrabgpt.log`.

This is runtime-only; no values are persisted to `.env`.

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

### Multi-Model AI Support
- **OpenRouter Integration**: Support for multiple AI models via OpenRouter API with concurrent execution
- **Model Competition**: Up to 10 AI models compete simultaneously, best valid move is selected
- **AI Configuration Dialog**: Visual interface to select and configure multiple models with real-time cost estimation
- **Competition Results Table**: Beautiful dark-themed table showing all model proposals, scores, and judge validation results
- **Model Tracking**: Status bar displays which model proposed which move throughout gameplay
- **Click-to-View Details**: Click any model result row to see raw response and GPT analysis

### Intelligent Error Handling & Recovery
- **GPT Fallback Parser**: When models return non-JSON responses (with thinking/reasoning), GPT-5-mini automatically extracts the move
- **Response Detail Dialog**: View raw model responses and GPT analysis for transparency
- **Empty Response Handling**: Graceful handling of empty/invalid responses from models
- **Slovak Error Messages**: User-friendly error messages in Slovak with full details in tooltips
- **OpenRouter Reasoning Field**: Support for models that return content in `reasoning` field (like GLM-4.6)

### Performance & UX Improvements
- **Parallel Judge Validation**: All model moves validated concurrently (3-5x speed improvement)
- **No UI Freezing**: Background validation keeps UI responsive with multiple models
- **Dark Mode Styling**: All new UI components match the app's dark theme
- **Larger Fonts**: Improved readability in AI config dialog and results table
- **Top Weekly Models**: AI config dialog shows trending models from OpenRouter
- **Clear on Retry**: Results table clears when AI retries, preventing stale data display
- **Cost Visibility**: Prominent display of maximum cost per turn with smart decimal formatting

### Technical Improvements
- **GPT-5 Support**: Proper parameter handling for GPT-5 models (`max_completion_tokens` vs `max_tokens`)
- **Improved Logging**: Detailed logging throughout multi-model pipeline with timing information
- **Better Prompts**: Enhanced GPT-5 extraction prompts for more reliable move recovery
- **3-Tier Validation**: Efficient Slovak word validation (local dictionary → simplified check → full OpenAI validation)
- **Error Classification**: Distinct handling of parse errors, API errors, and validation failures

### UI/UX Enhancements
- **Compact Layouts**: More efficient use of space in dialogs and tables
- **Visual Hierarchy**: Important information (cost, winner, status) prominently displayed
- **Medals for Winners**: Top 3 models shown with 🥇🥈🥉 medals in results table
- **Status Messages**: Detailed status updates showing current model, phase, and results
- **Responsive Design**: Proper window sizing (800×650 for config, auto-sizing for results)

See detailed documentation in `docs/` directory for implementation details of each feature.
