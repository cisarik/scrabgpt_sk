# Model Tracking Improvements

## Problem

Users couldn't tell which AI model proposed which move during multi-model gameplay:

### Issue 1: Which model proposed "BAMUS"?
- Table showed 3 models: DeepSeek (Invalid), GLM (Parse Error), Claude (Parse Error)
- Board showed "BAMUS" being judged
- Status: "Rozhodca rozhoduje slovo BAMUS.."
- **User had no idea which model proposed it**

### Issue 2: Which model proposed "SUMA" after retry?
- First attempt failed validation
- Retry happened with single model
- "SUMA" appeared on board (16 points)
- Table still showed old data (DeepSeek Invalid, GLM/Claude Parse Error)
- **User had no idea which model succeeded with retry**

## Solution

### 1. Track Winning Model Name

Store which model's move is currently being processed:

```python
def _on_multi_model_results(self, results: list[dict[str, Any]]) -> None:
    """Handle multi-model competition results and display in table."""
    self.model_results_table.set_results(results)
    
    # Store the winning model name for status messages
    valid_results = [r for r in results if r.get("judge_valid")]
    if valid_results:
        valid_results.sort(key=lambda r: int(r.get("score", -1)), reverse=True)
        self._current_ai_model = valid_results[0].get("model_name", "AI")
    else:
        # Find highest scoring attempt
        all_sorted = sorted(results, key=lambda r: int(r.get("score", -1)), reverse=True)
        self._current_ai_model = all_sorted[0].get("model_name", "AI") if all_sorted else "AI"
```

### 2. Show Model Name in Status Messages

Modified `_format_judge_status()` to include model name:

```python
def _format_judge_status(self, words: list[str]) -> str:
    """Format judge status message with model name if available."""
    model_name = getattr(self, '_current_ai_model', None)
    model_prefix = f"[{model_name}] " if model_name and model_name != "AI" else ""
    
    if len(words) == 1:
        return f"{model_prefix}Rozhodca rozhoduje slovo {words[0]}"
    # ...
```

**Result**: Status bar now shows `"[DeepSeek] Rozhodca rozhoduje slovo BAMUS.."`

### 3. Update Status for Retry

When validation fails and retry happens:

```python
def _on_ai_proposal(self, proposal: dict[str, object]) -> None:
    err = self._validate_ai_move(proposal)
    if err is not None:
        # Show which model failed
        model_name = getattr(self, '_current_ai_model', "AI")
        self.status.showMessage(f"[{model_name}] Neplatný návrh, retry s GPT-5-mini...")
        
        # Mark that we're using single-model retry
        self._current_ai_model = "GPT-5-mini (retry)"
```

**Result**: User sees `"[DeepSeek] Neplatný návrh, retry s GPT-5-mini..."`

### 4. Show Retry Result in Table

When retry succeeds and goes to judge, create a single-row table entry:

```python
# For retry success, show in table
if self._ai_retry_used and hasattr(self, '_current_ai_model'):
    retry_result = {
        "model": "gpt-5-mini",
        "model_name": self._current_ai_model,
        "status": "ok",
        "move": {"word": words[0] if words else ""},
        "score": 0,  # Will be calculated
        "words": words,
        "judge_valid": None,  # Will be set after judge
    }
    self.model_results_table.set_results([retry_result])
```

**Result**: Table shows single row: `"GPT-5-mini (retry)" | "SUMA" | ... | "Valid ✓"`

## User Experience Flow

### Before
```
1. Multi-model proposes moves
   Table: DeepSeek (Invalid), GLM (Parse Error), Claude (Parse Error)
   Board: Shows "BAMUS"
   Status: "Rozhodca rozhoduje slovo BAMUS.."
   ❌ User: "Which model proposed BAMUS?"

2. Judge rejects "BAMUS"
   Status: "AI návrh neplatný, skúša znova..."
   ❌ User: "Which model failed?"

3. Retry succeeds with "SUMA"
   Board: Shows "SUMA" (16 points)
   Table: Still shows old data (DeepSeek/GLM/Claude)
   ❌ User: "Which model succeeded? Why is table wrong?"
```

### After
```
1. Multi-model proposes moves
   Table: DeepSeek (Invalid), GLM (Parse Error), Claude (Parse Error)
   Board: Shows "BAMUS"
   Status: "[DeepSeek] Rozhodca rozhoduje slovo BAMUS.."
   ✓ User: "Ah, DeepSeek proposed BAMUS"

2. Judge rejects "BAMUS"
   Status: "[DeepSeek] Neplatný návrh, retry s GPT-5-mini..."
   ✓ User: "DeepSeek failed, now retrying with GPT-5-mini"

3. Retry succeeds with "SUMA"
   Board: Shows "SUMA" (16 points)
   Status: "[GPT-5-mini (retry)] Rozhodca rozhoduje slovo SUMA"
   Table: Shows single row: "GPT-5-mini (retry)" | "SUMA" | ...
   ✓ User: "GPT-5-mini succeeded with SUMA!"
```

## Benefits

### For Users
- ✅ **Always know which model is playing** - shown in status bar
- ✅ **Understand failures** - see which model failed and why
- ✅ **Track retry source** - know when GPT-5-mini is retrying
- ✅ **Table stays accurate** - updates to show current state
- ✅ **Full transparency** - complete visibility into AI decisions

### For Debugging
- ✅ **Better logs** - model names in status messages
- ✅ **Track model performance** - see which models fail often
- ✅ **Identify issues** - know exactly which model/word combination failed
- ✅ **User feedback** - users can report "DeepSeek keeps failing" with specifics

## Implementation Details

### State Tracking

Added `self._current_ai_model` attribute:
- Set when multi-model results arrive
- Updated when retry begins
- Used in all status messages
- Shown in table for retry results

### Status Message Format

```
"[Model Name] Message"

Examples:
"[DeepSeek: DeepSeek V3.2 Exp] Rozhodca rozhoduje slovo BAMUS.."
"[GPT-5-mini (retry)] Rozhodca rozhoduje slovo SUMA"
"[Z.AI: GLM 4.6] Neplatný návrh, retry s GPT-5-mini..."
```

### Table Updates

**Initial multi-model**: Shows all 3-10 models with their results

**Retry scenario**: Replaces table with single row showing retry model

**Advantages**:
- User always sees relevant current information
- No confusion from stale data
- Clear indication of retry vs multi-model

## Edge Cases Handled

### 1. No Valid Results
```python
if valid_results:
    self._current_ai_model = valid_results[0].get("model_name", "AI")
else:
    # Fallback to highest scoring attempt
    all_sorted = sorted(results, key=lambda r: int(r.get("score", -1)), reverse=True)
    self._current_ai_model = all_sorted[0].get("model_name", "AI") if all_sorted else "AI"
```

### 2. Missing Model Name
```python
model_name = getattr(self, '_current_ai_model', None)
model_prefix = f"[{model_name}] " if model_name and model_name != "AI" else ""
```

### 3. Retry Without Multi-Model
If single-model mode is used from the start, `_current_ai_model` may not be set:
```python
model_name = getattr(self, '_current_ai_model', "AI")  # Defaults to "AI"
```

## Testing

All existing tests pass:
- ✅ Type checking (mypy)
- ✅ Linting (ruff)
- ✅ Unit tests (pytest)

## Future Enhancements

1. **Color-code status bar** by model performance
2. **Animation** when switching models
3. **Model statistics** - track success rates
4. **Model preferences** - learn which models work best
5. **Detailed tooltips** - hover status bar for full model info

## Conclusion

Users now have **complete visibility** into which AI model is playing at any moment:
- Status bar shows `[Model Name]` prefix
- Table updates to show current state
- Retry results clearly marked
- No more confusion about which model did what

This makes the multi-model feature much more transparent and user-friendly!
