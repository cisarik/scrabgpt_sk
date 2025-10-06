# Error Handling Improvements for Multi-Model AI

## Issue

Some AI models (particularly Gemini and Claude) were returning empty responses from OpenRouter API, causing JSON parsing errors:

```
JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

This happened even though the HTTP response was "200 OK", but the actual content was empty or null.

## Root Cause

The code was not checking for empty responses before attempting to parse JSON:

1. OpenRouter API returned `{"choices": [{"message": {"content": ""}}]}` (empty content)
2. Code tried to parse empty string as JSON: `json.loads("")`
3. JSON parser failed with "Expecting value" error

## Solution

### 1. Enhanced OpenRouter Response Validation

**File**: `scrabgpt/ai/openrouter.py`

Added checks before parsing:

```python
# Check if response has expected structure
if "choices" not in data or not data["choices"]:
    log.error("Model %s returned unexpected response structure: %s", model_id, data)
    return {
        "model": model_id,
        "content": "",
        "error": "Unexpected response structure",
        "status": "error",
    }

message = data["choices"][0].get("message", {})
content = message.get("content", "")

# Check for empty content
if not content:
    log.warning("Model %s returned empty content. Response: %s", model_id, data)
    return {
        "model": model_id,
        "content": "",
        "error": "Model returned empty response",
        "status": "error",
    }
```

**Benefits**:
- Catches empty responses immediately
- Logs full response for debugging
- Returns proper error status instead of crashing

### 2. Enhanced Multi-Model Parsing

**File**: `scrabgpt/ai/multi_model.py`

Added validation before JSON parsing:

```python
raw_content = result["content"]

# Check for empty or whitespace-only response
if not raw_content or not raw_content.strip():
    log.warning("Model %s returned empty response", model_id)
    return {
        "model": model_id,
        "model_name": model_info.get("name", model_id),
        "status": "parse_error",
        "error": "Empty response from model",
        "move": None,
        "score": -1,
    }

# Log first 200 chars for debugging
log.debug("Response from %s: %s...", model_id, raw_content[:200])
```

**Enhanced error reporting**:
```python
except Exception as e:
    log.exception("Failed to parse move from %s: %s", model_id, e)
    # Include first 100 chars of content in error for debugging
    content_preview = result.get("content", "")[:100] if result.get("content") else "NO CONTENT"
    return {
        "model": model_id,
        "model_name": model_info.get("name", model_id),
        "status": "parse_error",
        "error": f"{e.__class__.__name__}: {str(e)[:50]} (content: {content_preview}...)",
        "move": None,
        "score": -1,
    }
```

### 3. User-Friendly Error Display

**File**: `scrabgpt/ui/model_results.py`

Improved error messages in the results table:

```python
if error:
    # Show more concise error message
    if "Empty response" in error:
        move_text = "⚠️ Prázdna odpoveď"
    elif "Unexpected response" in error:
        move_text = "⚠️ Neplatná odpoveď"
    elif "JSONDecodeError" in error or "Expecting value" in error:
        move_text = "⚠️ Neplatný JSON"
    else:
        move_text = f"⚠️ {error[:30]}..."

# Full error in tooltip
move_item.setToolTip(error if error else move_text)
```

## Error Handling Flow

```
OpenRouter API Call
    ↓
Check HTTP status
    ↓
Check response structure (has "choices")
    ↓
Check content is not empty/null
    ↓
Return with status="error" if any check fails
    ↓
Multi-model handler receives error status
    ↓
Marks model as "parse_error" or "error"
    ↓
Results table displays user-friendly message
    ↓
Full error available in tooltip
```

## Benefits

### For Users
- ✅ No more crashes when models return empty responses
- ✅ Clear error messages in Slovak ("Prázdna odpoveď")
- ✅ Tooltips provide full error details
- ✅ Game continues with successful models
- ✅ Failed models shown in red with warning icon

### For Developers
- ✅ Better logging with response previews
- ✅ Easier debugging with content snapshots
- ✅ Clear distinction between API errors and parse errors
- ✅ Full response logged when structure is unexpected

## Error Types Handled

| Error Type | Detection | Message | Color |
|-----------|-----------|---------|-------|
| Empty response | `content == ""` | ⚠️ Prázdna odpoveď | Red |
| Missing structure | No "choices" key | ⚠️ Neplatná odpoveď | Red |
| JSON parse error | `json.loads()` fails | ⚠️ Neplatný JSON | Red |
| API error | Exception during call | ⚠️ Error message | Red |

## Testing

All existing tests pass:
- ✅ Type checking (mypy)
- ✅ Linting (ruff)
- ✅ Unit tests (pytest)

## Future Improvements

1. **Retry logic**: Automatically retry failed models once
2. **Fallback models**: If primary model fails, try backup
3. **Statistics**: Track which models fail most often
4. **Model filtering**: Allow hiding unreliable models
5. **Timeout handling**: Detect and handle slow models

## Example Log Output

**Before** (crashed with traceback):
```
ERROR Failed to parse move from google/gemini-2.5-flash-preview-09-2025: Expecting value: line 1 column 1 (char 0)
[Full stack trace...]
```

**After** (handled gracefully):
```
WARNING Model google/gemini-2.5-flash-preview-09-2025 returned empty content. Response: {'choices': [{'message': {'content': ''}}]}
INFO Received multi-model results: 5 models
INFO Best move from deepseek/deepseek-v3.2-exp with score 42 (judge_valid=True, out of 5 total results)
```

## Conclusion

The application now gracefully handles all types of model failures:
- Empty responses don't crash the app
- Users see clear error messages
- Other models continue working
- Full error details available for debugging

This makes the multi-model feature much more robust and production-ready.
