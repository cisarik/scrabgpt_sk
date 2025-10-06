# AI Prompt Customization System

This document describes the new customizable AI prompt system implemented in ScrabGPT.

## Overview

The AI prompt is now fully customizable through a user-friendly editor. Users can:
- Edit prompts with live preview
- Save multiple prompt variants
- Switch between different prompts
- Revert to default at any time

## Features

### 1. File-Based Prompts
- Prompts are stored in `prompts/*.txt` files
- Default prompt: `prompts/default.txt`
- Active prompt specified in `.env`: `AI_PROMPT_FILE='prompts/default.txt'`

### 2. Prompt Editor Dialog
- **Location**: Toolbar → `📝 Upraviť prompt`
- **Features**:
  - Large font text editor with syntax highlighting
  - Dropdown to select from available prompts
  - Save/Save As functionality
  - Revert to default button
  - Dark theme styling

### 3. Template System
Prompts support dynamic placeholders:
- `{language}` - Game language (e.g., "Slovak")
- `{tile_summary}` - Letter point values (e.g., "A:1, B:2, C:3...")
- `{compact_state}` - Current board state with premium squares overlay
- `{premium_legend}` - Premium square legend (e.g., "*=TW, ~=DW, $=TL, ^=DL")

### 4. Increased Token Limits
- Default `max_tokens` increased from 3600 to 10000
- Models can now use up to 20000 tokens
- Default calculated as `min(10000, context_length / 3)`

### 5. Markdown JSON Support
- Parser now handles ````json ... ```` code blocks
- Supports both markdown and plain JSON responses
- Prevents "Expecting value: line 1 column 1" errors

## Files Changed

### Core AI Logic
- `scrabgpt/ai/player.py` - Load prompts from file instead of hardcoded
- `scrabgpt/ai/schema.py` - Strip markdown code blocks from JSON responses

### UI Components
- `scrabgpt/ui/prompt_editor.py` - **NEW** Prompt editor dialog
- `scrabgpt/ui/app.py` - Added toolbar button and handler
- `scrabgpt/ui/ai_config.py` - Increased max_tokens range

### Configuration
- `.env.example` - Added `AI_PROMPT_FILE` variable
- `prompts/default.txt` - **NEW** Default prompt template
- `prompts/README.md` - **NEW** User guide

## Usage

### Editing Prompts (GUI)
1. Click `📝 Upraviť prompt` in toolbar
2. Edit the prompt text
3. Click `💾 Uložiť` to save
4. Click `✓ Použiť` to apply changes

### Creating New Prompts
1. Open prompt editor
2. Modify the prompt as desired
3. Click `💾 Uložiť ako...`
4. Enter a name (e.g., "aggressive")
5. New file created: `prompts/aggressive.txt`

### Switching Prompts
1. Open prompt editor
2. Select from dropdown
3. Click `✓ Použiť`

### Reverting to Default
1. Open prompt editor
2. Click `🔄 Vrátiť na pôvodný`
3. Confirms before reverting

## Technical Details

### Prompt Loading
```python
def _load_prompt_template() -> str:
    prompt_file = os.getenv("AI_PROMPT_FILE", "prompts/default.txt")
    # Load from file or fallback to embedded default
```

### Placeholder Substitution
```python
prompt = template.format(
    language=language,
    tile_summary=tile_summary,
    compact_state=compact_state_with_premiums,
    premium_legend=premium_legend or "",
)
```

### Markdown Stripping
```python
# Strip ```json and ``` from responses
cleaned = text.strip()
if cleaned.startswith("```json"):
    cleaned = cleaned[7:]
elif cleaned.startswith("```"):
    cleaned = cleaned[3:]
if cleaned.endswith("```"):
    cleaned = cleaned[:-3]
```

## Benefits

1. **Experimentation** - Users can test different prompt strategies
2. **Language-specific** - Create specialized prompts per language
3. **Version Control** - Prompts are normal text files (git-friendly)
4. **No Code Changes** - Adjust AI behavior without modifying Python code
5. **Shareability** - Users can share successful prompt strategies

## Future Enhancements

Potential improvements:
- Prompt versioning/history
- A/B testing different prompts
- Prompt templates library
- Syntax highlighting for placeholders
- Prompt performance metrics
