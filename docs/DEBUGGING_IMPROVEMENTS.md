# Model Debugging & Response Analysis Improvements

## Issues Fixed

### 1. **No Raw Response Visible** ✅
**Problem**: UI showed "No response available" even when models returned content

**Solution**: 
- Store `raw_response` in all result dictionaries
- Display in Response Detail Dialog

### 2. **Missing Error Analysis** ✅
**Problem**: No insight into why JSON parsing failed

**Solution**:
- Added `error_analysis` field for parse errors
- Provides helpful tips:
  - "Model used code blocks without 'json' marker"
  - "Response doesn't start with JSON object"
  - "Missing 'placements' field in response"

### 3. **First Move Validation** ✅
**Problem**: Models not crossing center star (H8 = row=7, col=7) on first move

**Solution**:
- Enhanced prompt with explicit examples
- Shows VALID vs INVALID first moves
- Emphasizes that at least ONE placement must be at (7,7)

### 4. **Response Detail Dialog Improvements** ✅
Now shows:
- ✅ **Parse status** and judge validation
- 📝 **Words formed** with judge verdict
- 🎯 **Placements** (up to 10 tiles shown)
- ✗ **Invalid move reasons** with judge feedback
- 💡 **Error analysis** for parse failures

## UI Changes

### Response Detail Dialog
**Before**:
- "No response available"
- "No GPT analysis available"

**After**:
- Shows full raw response from model
- Shows structured analysis:
  - Success: Word list, placements, judge validation
  - Parse error: Helpful tips for debugging
  - Invalid: Judge reasons and error details

## Prompt Enhancements

### First Move Rule
**Before** (1 line):
```
- If board is empty: first move MUST cross center star at H8 (row=7, col=7)
```

**After** (8 lines with examples):
```
- ⭐ CRITICAL: If board is empty, the FIRST MOVE MUST include a tile at coordinates (row=7, col=7)
  This is the center star (H8 in chess notation). AT LEAST ONE of your placements must have row=7 AND col=7.
  Example valid first moves:
    * ACROSS from (7,5): places tiles at (7,5), (7,6), (7,7) ✓ crosses center
    * DOWN from (5,7): places tiles at (5,7), (6,7), (7,7) ✓ crosses center
    * ACROSS from (7,8): INVALID ✗ doesn't cross (7,7)
    * DOWN from (8,7): INVALID ✗ doesn't cross (7,7)
```

## Files Modified

- `scrabgpt/ai/multi_model.py`
  - Store `raw_response` in successful results
  - Add `error_analysis` for parse errors
  
- `scrabgpt/ui/response_detail.py`
  - Enhanced dialog to show error analysis
  - Better formatting for move details
  - Show judge validation inline
  
- `prompts/default.txt`
  - Enhanced first-move rule with examples
  - 56 → 62 lines total

## Usage

### View Model Response
1. Click on any row in "AI Model Results" table
2. Dialog shows:
   - **Raw Response**: Exact text returned by model
   - **Analysis**: Structured breakdown or error tips

### Debugging Parse Errors
When a model returns parse error:
1. Check "Raw Response" section
2. Read "Analysis" for helpful tips
3. Common issues:
   - Missing markdown json marker
   - Extra text before/after JSON
   - Missing required fields

### First Move Debugging
If models fail first move:
1. Check if any placement has row=7 AND col=7
2. Example valid: `{"row": 7, "col": 7, "letter": "A"}`
3. Models should now follow this better with enhanced prompt

## Testing

All 46 tests pass ✅

## Benefits

1. **Better Visibility**: See exactly what models returned
2. **Faster Debugging**: Error analysis provides immediate hints
3. **Better First Moves**: Enhanced prompt reduces first-move failures
4. **Judge Transparency**: See why moves were marked invalid
