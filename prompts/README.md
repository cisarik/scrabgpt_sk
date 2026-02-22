# AI Prompts

This directory contains prompt artifacts used for ScrabGPT move generation.

## Usage

1. Prompt engineering for gameplay is now unified and hardcoded in `scrabgpt/ai/player.py`.
2. `chat_protocol.txt` is kept as reference material for tool-oriented prompting.
3. Runtime no longer loads `AI_PROMPT_FILE` from `.env`.

## Note

`default.txt` was removed to avoid divergent behavior between providers and modes.
