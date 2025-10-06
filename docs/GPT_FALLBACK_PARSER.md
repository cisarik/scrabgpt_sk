# GPT Fallback Parser & Response Detail Dialog

## Overview

A powerful new feature that makes multi-model AI more robust and transparent:

1. **GPT Fallback Parser**: When a model's response can't be parsed as JSON, use GPT-5-mini to analyze it and extract the move
2. **Response Detail Dialog**: Click any model in the results table to see raw response + GPT analysis
3. **Full Transparency**: Users can see exactly how models think and respond

## Problem Solved

### Before
Models that include "thinking" or explanatory text before/after JSON were rejected:

```
Model Response:
"Let me analyze this board... The best move would be to place MÁ at H7-H8.
{
  "placements": [...],
  "word": "MÁ",
  "score": 10
}"

Result: ❌ Parse Error (thrown away, move lost)
```

### After
GPT analyzes the response and extracts the move:

```
Model Response: (same as above)

GPT Analysis:
✓ Found valid Scrabble move in response
✓ Extracted JSON from text
✓ Move: MÁ at H7-H8, score 10

Result: ✅ Move accepted and validated
```

## Implementation

### 1. GPT Fallback Parser

**File**: `scrabgpt/ai/multi_model.py`

When JSON parsing fails, automatically call GPT to analyze:

```python
def _analyze_response_with_gpt(raw_response: str, judge_client: OpenAIClient) -> dict[str, Any]:
    """Use GPT to analyze a non-JSON response and try to extract the move."""
    
    analysis_prompt = f"""A Scrabble AI model responded with the following text instead of pure JSON:

{raw_response[:2000]}

Your task:
1. Analyze if this response contains a valid Scrabble move proposal
2. If yes, extract the move details and format as JSON
3. If no, explain why the response is invalid

Respond with JSON only:
{{
    "has_move": boolean,
    "extracted_move": {{...}} or null,
    "analysis": "explanation of what you found"
}}"""

    # Call GPT-5-mini
    client = judge_client.client
    chat_completion = client.chat.completions.create(
        model=judge_client.model,
        messages=[{"role": "user", "content": analysis_prompt}],
        max_tokens=1000,
    )
    response_text = chat_completion.choices[0].message.content or ""
    
    # Parse and return
    gpt_response = json.loads(response_text)
    return {
        "analysis": gpt_response.get("analysis", "No analysis provided"),
        "move": gpt_response.get("extracted_move") if gpt_response.get("has_move") else None,
    }
```

**Trigger Conditions**:
- JSON parsing fails with exception
- Response has substantial content (> 50 characters)
- Automatically attempts GPT analysis

**Success Path**:
```python
if gpt_extracted_move:
    log.info("GPT successfully extracted move from %s", model_id)
    return {
        "model": model_id,
        "model_name": model_info.get("name", model_id),
        "status": "ok",  # ← Treated as successful
        "move": gpt_extracted_move,
        "score": gpt_extracted_move.get("score", 0),
        "raw_response": raw_response,
        "gpt_analysis": gpt_analysis,
    }
```

### 2. Response Detail Dialog

**File**: `scrabgpt/ui/response_detail.py`

Beautiful dark-mode dialog showing:
- Model name and status
- Raw response (monospace, scrollable)
- GPT analysis (monospace, scrollable)
- 50/50 splitter layout

```python
class ResponseDetailDialog(QDialog):
    """Dialog showing raw model response and GPT analysis."""
    
    def __init__(self, result_data: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.result_data = result_data
        self.setWindowTitle(f"Response Detail: {result_data.get('model_name', 'Unknown')}")
        self.setModal(True)
        self.resize(900, 700)
```

**Features**:
- **Header**: Model name with dark background
- **Status Line**: Shows status, score, judge result
- **Raw Response Section**: 
  - Green header "📄 Raw Response from Model"
  - Monospace font (Courier New)
  - Full text with scrolling
- **GPT Analysis Section**:
  - Blue header "🤖 GPT-5-mini Analysis"
  - Shows GPT's explanation
  - For successful parses, shows extracted placements
- **Splitter**: Resize sections as needed
- **Close Button**: Green "✓ Close" button

### 3. Clickable Table Rows

**File**: `scrabgpt/ui/model_results.py`

Made table rows clickable:

```python
# Setup
self.results: list[dict[str, Any]] = []
self.table.cellClicked.connect(self._on_cell_clicked)
self.table.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

# Handler
def _on_cell_clicked(self, row: int, column: int) -> None:
    """Handle cell click to show response details."""
    if 0 <= row < len(self.results):
        result = self.results[row]
        dialog = ResponseDetailDialog(result, parent=self)
        dialog.exec()
```

**Cursor**: Changes to pointing hand on hover

**Behavior**: Click anywhere in the row to open detail dialog

## User Experience

### Scenario 1: Model with Thinking Text

**Model Response** (Claude):
```
I'll analyze the board carefully. The rack has ŔMÁAZÓU.
Looking at the center star at H8, I can form a word crossing it.

Let me calculate the score...

The best move is MÁ:
{
  "placements": [
    {"row": 7, "col": 6, "letter": "M"},
    {"row": 7, "col": 7, "letter": "Á"}
  ],
  "direction": "ACROSS",
  "word": "MÁ",
  "score": 10
}
```

**What Happens**:
1. JSON parser fails (extra text before JSON)
2. GPT fallback triggers automatically
3. GPT extracts the valid JSON
4. Move is accepted: MÁ, 10 points
5. Result shows as "ok" (green) in table
6. Click row → see full thinking + GPT analysis

### Scenario 2: Model with Pure JSON

**Model Response** (DeepSeek):
```json
{
  "placements": [...],
  "word": "SLOVO",
  "score": 42
}
```

**What Happens**:
1. JSON parser succeeds immediately
2. No GPT fallback needed
3. Move accepted directly
4. Click row → see clean JSON + success message

### Scenario 3: Model with No Valid Move

**Model Response** (Gemini):
```
I cannot form any valid words with these letters on this board.
Perhaps try exchanging some tiles?
```

**What Happens**:
1. JSON parser fails
2. GPT fallback triggers
3. GPT analysis: "Response contains no move proposal, only suggestion"
4. Result shows as "parse_error" (red) in table
5. Click row → see full text + GPT explanation

## Data Flow

```
Model Response
    ↓
Try JSON parse
    ↓
Success? ────────Yes────→ Use move directly
    ↓
    No
    ↓
Has content > 50 chars?
    ↓
    Yes
    ↓
Call GPT fallback
    ↓
GPT analysis
    ↓
Found move? ─────Yes────→ Use extracted move (status="ok")
    ↓
    No
    ↓
Parse error with GPT analysis stored
    ↓
User clicks row
    ↓
Show ResponseDetailDialog
    - Raw response
    - GPT analysis
```

## Benefits

### For Users
- ✅ **More moves recovered**: Models with thinking text no longer rejected
- ✅ **Full transparency**: See exactly what models said
- ✅ **Better debugging**: Understand why moves failed
- ✅ **Learn from models**: See how they think through problems
- ✅ **Trust**: Can verify GPT's interpretation is correct

### For Developers
- ✅ **Robust parsing**: Handles various response formats
- ✅ **Better logging**: Raw responses stored for debugging
- ✅ **Fewer rejections**: More models contribute valid moves
- ✅ **Easy debugging**: Click to see full context
- ✅ **User feedback**: Can see if prompts need improvement

## Cost Considerations

**GPT Fallback Cost**:
- Only called when JSON parsing fails
- Uses GPT-5-mini (very cheap)
- Max 1000 output tokens per analysis
- Typical cost: $0.0001 per fallback

**Example**:
- 5 models, 2 fail to parse JSON
- 2 GPT fallback calls per turn
- Cost: ~$0.0002 per turn
- Negligible compared to OpenRouter costs

## Edge Cases Handled

### Empty Response
```python
if not raw_response:
    # No fallback attempt
    return parse_error("Empty response from model")
```

### Whitespace Only
```python
if not stripped:
    # No fallback attempt
    return parse_error("Empty response (whitespace only)")
```

### Short Response
```python
if len(raw_response) <= 50:
    # Not enough content to analyze
    return parse_error without fallback
```

### GPT Fallback Fails
```python
except Exception as gpt_error:
    log.warning("GPT fallback failed: %s", gpt_error)
    # Store attempt but return parse_error
    return {
        "status": "parse_error",
        "gpt_analysis": f"GPT analysis failed: {gpt_error}",
        ...
    }
```

## UI Design

### Response Detail Dialog

```
┌─────────────────────────────────────────────────────────────┐
│ Model: Claude Sonnet 4.5                                    │
│ Status: ok | Score: 10 | Judge: ✓ Valid                     │
├─────────────────────────────────────────────────────────────┤
│ 📄 Raw Response from Model                                  │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ I'll analyze the board carefully...                     │ │
│ │                                                           │ │
│ │ {                                                         │ │
│ │   "placements": [...],                                   │ │
│ │   "word": "MÁ",                                          │ │
│ │   "score": 10                                            │ │
│ │ }                                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ 🤖 GPT-5-mini Analysis                                      │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ✓ Found valid Scrabble move in response                 │ │
│ │ ✓ Extracted JSON from text                              │ │
│ │                                                           │ │
│ │ Move: MÁ at (7,6)-(7,7) ACROSS                          │ │
│ │ Score: 10 points                                         │ │
│ │                                                           │ │
│ │ The model provided reasoning before the JSON,            │ │
│ │ which was successfully extracted.                        │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                                        [  ✓ Close  ]        │
└─────────────────────────────────────────────────────────────┘
```

## Testing

All tests pass:
- ✅ Type checking (mypy)
- ✅ Linting (ruff)
- ✅ Unit tests (pytest)

## Future Enhancements

1. **Batch analysis**: Analyze all failed responses in one GPT call
2. **Learning**: Train model on successful extractions
3. **Pattern detection**: Identify common failure modes
4. **Export**: Save response details to file
5. **Statistics**: Track GPT fallback success rate
6. **Prompt tuning**: Use failed parses to improve prompts

## Conclusion

The GPT fallback parser + response detail dialog combination:
- **Recovers** more valid moves from models
- **Increases** transparency for users
- **Improves** debugging for developers
- **Enhances** trust in the system
- **Costs** almost nothing (GPT-5-mini is cheap)

This makes the multi-model feature production-ready and user-friendly!
