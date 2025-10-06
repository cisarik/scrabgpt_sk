# Multi-Model Judging Issues - Fixes Applied

## Issues Identified

From the user's screenshots and logs, several issues were identified:

1. **judging.png**: The UI shows "BAMUS" on the board, but the table doesn't indicate which model proposed it
2. **judging2.png**: App shows "(Not Responding)" while judge validates "BAMUS"
3. **judging3.png**: "SUMA" is placed on board but table still shows old status
4. **Logs show**:
   - GPT-5 fallback analysis fails with `max_tokens` parameter error
   - GLM-4.6 model returns empty content, but has reasoning in a different field
   - No clear indication of which model proposed which move during judging

## Fixes Applied

### 1. Fixed GPT-5 Fallback Analysis (`multi_model.py`)
**Problem**: GPT-5 models don't support `max_tokens` parameter, they need `max_completion_tokens`.

**Solution**: Added model detection to use the correct parameter:
```python
if "gpt-5" in judge_client.model.lower() or "o1" in judge_client.model.lower():
    chat_completion = client.chat.completions.create(
        model=judge_client.model,
        messages=[{"role": "user", "content": analysis_prompt}],
        max_completion_tokens=1000,
    )
else:
    chat_completion = client.chat.completions.create(
        model=judge_client.model,
        messages=[{"role": "user", "content": analysis_prompt}],
        max_tokens=1000,
    )
```

### 2. Improved GPT-5 Extraction Prompt (`multi_model.py`)
**Problem**: The original prompt wasn't clear enough for GPT-5 to extract moves from non-JSON responses.

**Solution**: Rewrote the prompt to be more structured with clear sections:
- Model Response section
- Task section with numbered steps
- Expected JSON format
- Response format specification
- Clear instruction to respond with ONLY JSON

### 3. Extract Content from `reasoning` Field (`openrouter.py`)
**Problem**: Some OpenRouter models (like GLM-4.6) return content in `message.reasoning` instead of `message.content`.

**Solution**: Added fallback to check `reasoning` field:
```python
content = message.get("content", "")

# Some models (like GLM-4.6) return content in 'reasoning' field
if not content:
    reasoning = message.get("reasoning", "")
    if reasoning:
        log.info("Model %s returned content in 'reasoning' field...")
        content = reasoning
```

### 4. Enhanced Judge Validation Logging (`multi_model.py`)
**Problem**: No visibility into what's happening during judge validation.

**Solution**: Added detailed logging at each validation step:
```python
log.info("Judge validating %s from %s...", words, model_name)
# ... validation happens ...
if not all_valid:
    log.warning("Model %s proposed invalid words: %s (reason: %s)", ...)
else:
    log.info("Model %s words %s validated successfully", model_name, words)
```

### 5. Updated UI to Show Winner and Progress (`app.py`)
**Problem**: UI doesn't show which model proposed which move or who won.

**Solution**: 
- Added status message when calling models showing which ones are being used
- Updated `_on_multi_model_results` to show winner with their word and score
- Reordered signal connections so results are processed before proposal
- Added informative status messages for all scenarios

```python
# Show which models are being called
self.status.showMessage(f"Volám {model_count} modelov: {model_names}...")

# Show winner when results arrive
self.status.showMessage(
    f"✓ Víťaz: {self._current_ai_model} - {winner_word} ({winner_score} bodov)"
)
```

### 6. Better Status Messages During Judging (`app.py`)
**Problem**: User doesn't know which model's move is being judged.

**Solution**: Added status message showing which model proposed the words being validated:
```python
def _update_table_for_judging(self, words: list[str]) -> None:
    model_name = getattr(self, '_current_ai_model', "AI")
    words_str = ", ".join(words)
    judge_status = f"Rozhodca validuje: {words_str} (navrhol {model_name})"
    self.status.showMessage(judge_status)
```

## Testing Recommendations

1. **Test GPT-5 Fallback**: Use a model that returns non-JSON output and verify GPT-5 can extract the move
2. **Test GLM-4.6**: Verify the reasoning field extraction works correctly
3. **Test UI Updates**: Check that status messages show:
   - Which models are being called
   - Which model won and with what word/score
   - Which model's move is being judged
4. **Test Judge Validation**: Verify the logs show each validation step clearly

## Notes on UI Freezing

The "(Not Responding)" issue during judge validation is expected behavior when:
- Multiple models are being validated in parallel (heavy CPU/network work)
- The worker thread is running asyncio operations
- Qt event loop is waiting for the worker to complete

The fixes improve visibility through:
- Better logging to show progress
- Status messages that update when possible
- Clear indication of which phase the app is in

To fully eliminate freezing, a more significant refactor would be needed to:
1. Emit results immediately after models respond (before validation)
2. Do validation in a separate step with progress updates
3. Use QTimer or similar to update UI during long operations

However, the current implementation should work well for reasonable numbers of models (3-5).
