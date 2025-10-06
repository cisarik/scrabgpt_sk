# AI Prompts

This directory contains AI prompt templates used by ScrabGPT for move generation.

## Usage

1. **Edit prompts** via the UI: Click `📝 Upraviť prompt` in the toolbar
2. **Set active prompt** in `.env`: `AI_PROMPT_FILE='prompts/your_prompt.txt'`
3. **Create custom prompts**: Save new `.txt` files in this directory

## Template Placeholders

Your prompt can use these placeholders (they will be automatically replaced):

- `{language}` - Game language (e.g., "Slovak", "English")
- `{tile_summary}` - Letter point values (e.g., "A:1, B:2, C:3...")
- `{compact_state}` - Current board state with premium squares
- `{premium_legend}` - Premium square legend (e.g., "*=TW, ~=DW, $=TL, ^=DL")

## Example

```
You are an expert Scrabble player for {language}.
Available tiles: {tile_summary}

Current board:
{compact_state}

Premium legend: {premium_legend}
```

## Tips

- **Be specific**: Clearly state rules and constraints
- **Use examples**: Show valid vs. invalid moves
- **JSON format**: Always instruct AI to return pure JSON
- **Test iteratively**: Adjust prompt based on AI behavior

## Default Prompt

The `default.txt` file contains the original prompt. You can always revert to it using the "🔄 Vrátiť na pôvodný" button in the editor.
