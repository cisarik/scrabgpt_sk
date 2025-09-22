
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

## Offline judge (ENABLE)

You can validate words offline using the ENABLE word list (public domain).

- Enable in Settings: check "Offline judge (ENABLE)".
- On first enable, the app downloads the word list with a modal progress bar and saves it to `~/.scrabgpt/wordlists/enable1.txt`.
- Subsequent runs load it from disk; no further downloads.
- When offline mode is ON, both human and AI word validations use the local list, and the app does not call OpenAI for judging.
  Offline mode applies to both human and AI moves; AI still proposes moves, only validation is done locally.

### Dictionary Info & Re-download

In Settings, a Dictionary Info panel shows:
- Entries count, file size, last update timestamp, and the local path.
- Buttons: Re-download (fresh download with progress, then auto-reload) and Open folder…

You can override mirrors with `OFFLINE_JUDGE_URL` (comma-separated). The app validates downloads to avoid saving HTML error pages.

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
