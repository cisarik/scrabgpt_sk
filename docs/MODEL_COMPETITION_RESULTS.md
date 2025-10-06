# AI Model Competition Results Display

## Overview

When using multi-model AI mode, the application now displays a beautiful, eye-candy results table showing how each AI model performed in the competition. The table appears below the rack and shows detailed information about each model's proposed move, including judge validation.

## Features

### Visual Elements

**Location**: Directly below the rack area

**Components**:
1. **Gradient header** with title "🏆 AI Models Competition Results"
2. **Results table** with 6 columns:
   - 🏅 **Rank**: Shows medals (🥇🥈🥉) for top 3, numbers for others
   - **Model**: Full model name
   - **Move**: Words formed by the move (or error message)
   - **Score**: Points scored
   - **✓**: Judge validation (✓ for valid, ✗ for invalid, — for not validated)
   - **Status**: Overall status (Valid ✓, Invalid, Parse Error, API Error)

### Styling Rules

The table uses color-coding to make results instantly recognizable:

#### 🥇 Winner (Rank 1 + Valid)
- **Background**: Pure white (#FFFFFF)
- **Text**: Bold, black
- **Criteria**: Highest score AND passed judge validation

#### ✅ Valid Moves
- **Background**: Light green (#EDF7ED)
- **Text**: Dark green (#2E7D32)
- **Criteria**: Successfully proposed and passed judge validation

#### ❌ Invalid Moves
- **Background**: Light gray (#FAFAFA)
- **Text**: Gray (#787878)
- **Criteria**: Successfully parsed but failed judge validation
- **Effect**: Semi-transparent appearance

#### ⚠️ Errors
- **Background**: Light red (#FFF5F5)
- **Text**: Dark red (#C62828)
- **Criteria**: API errors or parse errors

### Sorting

Models are sorted by:
1. **Score** (highest first)
2. **Status** (ok > invalid > parse_error > error)

This ensures the best-performing models are always at the top.

### Judge Validation

Each model's proposed move is automatically validated by the judge:

1. **Word Extraction**: Extracts all words formed by the placements
2. **Judge Validation**: Calls the judge to validate each word
3. **Result Display**: Shows ✓ or ✗ with tooltip containing validation reasons
4. **Winner Selection**: Only judge-valid moves can win

The validation happens asynchronously during the AI turn, so results are immediately available when displayed.

## Implementation Details

### Data Flow

```
1. User clicks "Navrhnúť ťah" with multi-model enabled
   ↓
2. ProposeWorker starts, calls propose_move_multi_model()
   ↓
3. All models called concurrently (asyncio)
   ↓
4. Each result parsed and validated with judge
   ↓
5. Best valid move selected
   ↓
6. Results emitted via multi_model_results signal
   ↓
7. AIModelResultsTable displays results
```

### Key Files

**scrabgpt/ui/model_results.py**
- `AIModelResultsTable`: Main widget class
- `set_results()`: Updates table with new results
- `_populate_row()`: Applies styling based on result status

**scrabgpt/ai/multi_model.py**
- `propose_move_multi_model()`: Enhanced with judge validation
- Validates each move's words using `extract_all_words()` and `judge_words()`
- Returns both best move and all results

**scrabgpt/ui/app.py**
- Integrates `AIModelResultsTable` below rack
- `_on_multi_model_results()`: Handler for results signal
- ProposeWorker enhanced to emit multi_model_results

### Result Data Structure

Each result dict contains:
```python
{
    "model": str,              # Model ID
    "model_name": str,         # Display name
    "status": str,             # 'ok', 'invalid', 'error', 'parse_error'
    "move": dict | None,       # The proposed move
    "score": int,              # Move score
    "words": list[str],        # Words formed
    "judge_valid": bool,       # Judge validation result
    "judge_reason": str,       # Validation reason (for tooltip)
    "error": str | None,       # Error message if any
}
```

## User Experience

### Before (without results table)
- User sees only the final move
- No visibility into which model won
- No information about other models' proposals
- No feedback on validation

### After (with results table)
- **Immediate feedback**: See all models' proposals at once
- **Transparency**: Understand why each model succeeded/failed
- **Competition visibility**: See which model won and by how much
- **Validation details**: Tooltips show why moves were invalid
- **Beautiful presentation**: Eye-candy styling makes data easy to understand

## Example View

```
┌──────────────────────────────────────────────────────────┐
│     🏆 AI Models Competition Results                     │
├──────┬─────────────┬────────┬───────┬───┬───────────────┤
│  🥇  │ GPT-4 Turbo │ SLOVO  │  45   │ ✓ │ Valid ✓       │  ← Winner (bold, white)
├──────┼─────────────┼────────┼───────┼───┼───────────────┤
│  🥈  │ Claude 3    │ DOMOV  │  42   │ ✓ │ Valid ✓       │  ← Valid (green)
├──────┼─────────────┼────────┼───────┼───┼───────────────┤
│  🥉  │ Gemini Pro  │ XYZAB  │  38   │ ✗ │ Invalid       │  ← Invalid (gray)
├──────┼─────────────┼────────┼───────┼───┼───────────────┤
│  4.  │ Llama 3     │ Error  │   —   │ — │ Parse Error   │  ← Error (red)
└──────┴─────────────┴────────┴───────┴───┴───────────────┘
```

## Configuration

The table automatically:
- Shows/hides based on whether multi-model is active
- Adjusts height based on number of results (max 5 rows visible)
- Provides tooltips for judge reasons and long error messages
- Uses hover effects for better interactivity

## Future Enhancements

Potential improvements:
1. **Statistics tracking**: Keep history of which models win most often
2. **Performance graphs**: Visualize model accuracy over time
3. **Export results**: Save competition data for analysis
4. **Filtering**: Show/hide certain models or status types
5. **Detailed view**: Click row to see full move details
