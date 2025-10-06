# Model Results UI Fixes

## Issues Fixed

Based on user feedback from `ui.png`, the following issues were fixed:

### 1. Removed Gradient Header

**Before**: Purple/blue gradient header with "🏆 AI Models Competition Results" took up space and didn't match the dark UI theme.

**After**: Header completely removed. Just the table now, matching the rest of the app's dark theme.

### 2. Dark Mode Styling

**Before**: Light theme with white background, gray borders
```css
background: white;
border: 1px solid #d0d0d0;
color: black;
```

**After**: Dark theme matching the rest of the UI
```css
background: #1a1a1a;
border: 1px solid #444;
color: white;
gridline-color: #333;
```

**Colors**:
- Table background: `#1a1a1a` (dark gray)
- Header background: `#2a2a2a` (slightly lighter)
- Border: `#444` (medium gray)
- Text: `white`
- Gridlines: `#333` (dark)

### 3. Larger Font Sizes

**Before**: 
- Items: default (~10-11px)
- Headers: 11px

**After**:
- Items: 13px
- Headers: 12px
- Padding: 8px (from 6px)

This makes the table much more readable.

### 4. Winner/Valid/Error Colors (Dark Mode)

**Before** (Light mode colors):
- Winner: White background, black text
- Valid: Light green (#EDF7ED), dark green text
- Invalid: Light gray (#FAFAFA), gray text
- Error: Light red (#FFF5F5), dark red text

**After** (Dark mode colors):
- Winner: Forest green (#228B22), white text, bold
- Valid: Dark green (#1C641C), light green text (#90EE90)
- Invalid: Dark gray (#323232), gray text (#787878)
- Error: Dark red (#501414), light red text (#FF6464)

### 5. Clear Results on Retry

**Problem**: When AI retries with a hint, the table showed stale data from the first attempt. User saw "Parse Error" even though retry succeeded with "MÁ" scoring 10 points.

**Solution**: Added `clear_results()` call when validation fails and retry begins:

```python
if err is not None and not bool(proposal.get("pass", False)):
    # Clear multi-model results since retry will use single model
    self.model_results_table.clear_results()
    
    self.status.showMessage("AI návrh neplatný, skúša znova…")
```

This ensures:
- Table is hidden during retry (no stale data)
- Only shows results from successful attempts
- User doesn't see confusing old errors

## Layout Comparison

### Before
```
┌─────────────────────────────────────────┐
│ 🏆 AI Models Competition Results         │ ← Purple gradient header
├─────────────────────────────────────────┤
│ Light theme table with small font        │
│ Shows stale data from failed attempts    │
└─────────────────────────────────────────┘
```

### After
```
┌─────────────────────────────────────────┐
│ Dark theme table, larger font           │ ← No header, just table
│ Clears on retry, only shows final data  │
└─────────────────────────────────────────┘
```

## Code Changes

### File: `scrabgpt/ui/model_results.py`

**Removed**:
- Title frame with gradient background
- QLabel with "🏆 AI Models Competition Results"
- QFrame container
- ~25 lines of header UI code

**Updated**:
- Table background: `#1a1a1a` (dark)
- Text color: `white`
- Font size: 13px for items, 12px for headers
- Padding: 8px
- Winner color: Forest green with white text
- Valid color: Dark green with light green text
- Error color: Dark red with light red text

### File: `scrabgpt/ui/app.py`

**Added**:
```python
if err is not None and not bool(proposal.get("pass", False)):
    # Clear multi-model results since retry will use single model
    self.model_results_table.clear_results()
```

This clears the table when AI validation fails and retry begins.

## User Experience Improvements

### Before Issues:
- ❌ Gradient header doesn't match UI theme
- ❌ Light theme doesn't match dark app
- ❌ Small font hard to read
- ❌ Stale data from failed attempts visible
- ❌ User confused by "Parse Error" when retry succeeded

### After Fixes:
- ✅ Clean table without header
- ✅ Dark theme matches entire app
- ✅ Larger font (13px) easy to read
- ✅ Table clears on retry
- ✅ Only shows final successful results
- ✅ Clear feedback on what each model did

## Example Scenarios

### Scenario 1: Both Models Succeed
```
[Table shows]
🥇 | DeepSeek V3    | MÁ  | 10 | ✓ | Valid ✓
🥈 | GLM 4.6        | ÁM  |  8 | ✓ | Valid ✓
```

### Scenario 2: One Model Fails
```
[Table shows]
🥇 | DeepSeek V3         | MÁ              | 10 | ✓ | Valid ✓
🥈 | Gemini 2.5 Flash    | ⚠️ Neplatný JSON | — | — | Parse Error
```

### Scenario 3: First Attempt Fails, Retry Succeeds
```
[First attempt - table shows errors]
[Validation fails, retry begins]
[Table clears → empty]
[Retry succeeds with single model]
[Table stays hidden since retry uses single model, not multi-model]
```

## Technical Details

### Dark Mode Colors

All colors carefully chosen for dark UI:
- High contrast for readability
- Consistent with app's dark theme
- Distinct colors for different states
- Accessible color combinations

### Table Styling

```css
QTableWidget {
    background: #1a1a1a;    /* Dark background */
    color: white;            /* White text */
    border: 1px solid #444;  /* Medium gray border */
    gridline-color: #333;    /* Dark gridlines */
    font-size: 13px;         /* Larger font */
}

QHeaderView::section {
    background: #2a2a2a;     /* Slightly lighter header */
    color: white;
    font-size: 12px;
    font-weight: bold;
    padding: 8px;
}
```

### Clear Results Logic

```python
def clear_results(self) -> None:
    """Clear the results table and hide the widget."""
    self.table.setRowCount(0)
    self.setVisible(False)
```

Called when:
- AI validation fails and retry begins
- Need to reset table state
- Preventing stale data display

## Testing

All tests pass:
- ✅ Type checking (mypy)
- ✅ Linting (ruff)
- ✅ Unit tests (pytest)

## Future Improvements

1. **Progressive display**: Show results as each model completes
2. **Animation**: Fade in/out when showing/hiding
3. **Expandable rows**: Click to see full error details
4. **Export**: Save results to file
5. **Statistics**: Track model performance over time

## Conclusion

The model results table now:
- Matches the dark UI theme
- Has no distracting header
- Uses larger, more readable font
- Clears properly on retry
- Shows only relevant, current data

These improvements make the multi-model feature more professional and user-friendly.
