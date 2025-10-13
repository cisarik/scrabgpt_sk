# Novita AI Integration

## Overview

ScrabGPT now supports **Novita AI** as a multi-model reasoning provider alongside OpenRouter. Novita provides access to specialized reasoning models including DeepSeek R1, Qwen, GLM, and LLaMA series.

## Features

### 1. **Dynamic Model Discovery**
- Fetches available models from Novita API (`/openai/v1/models`)
- Automatic categorization by model family (DeepSeek, Qwen, GLM, LLaMA)
- Context length and metadata displayed for each model

### 2. **Multi-Model Competition**
- Select up to 10 reasoning models to compete simultaneously
- Each model proposes a move in parallel
- Judge validates all proposed words
- Best valid move wins (or highest scoring if none valid)

### 3. **Real-Time UI Feedback**
- **Results Table**: Shows activity, proposed moves, and scores for each model
- **Status Bar**: Displays current model being called and results
- **Progress Updates**: Partial results emitted as each model completes
- **Medals**: 🥇🥈🥉 for top 3 performers

### 4. **Reasoning Content Support**
- Novita reasoning models return special `reasoning_content` field
- Captured and stored for transparency
- Available in response detail dialogs

## Setup

### 1. Environment Configuration

Add to `.env`:
```bash
NOVITA_API_KEY='your-api-key-here'
AI_MOVE_TIMEOUT_SECONDS='120'    # Shared timeout for all AI moves
# Shared per-move cap (applies to OpenRouter & Novita)
AI_MOVE_MAX_OUTPUT_TOKENS='5000'
```

### 2. Get API Key

1. Visit [Novita.ai](https://novita.ai/)
2. Sign up/login
3. Navigate to API Keys section
4. Generate new API key
5. Copy to `.env` file

### 3. Select Models

1. Open ScrabGPT
2. Go to **Nastavenia** (Settings) → **AI Protivník** tab
3. Select **Novita AI** mode
4. Click **Nastaviť** button
5. Choose models from the list (max 10)
6. Click **OK**

## Architecture

### File Structure

```
scrabgpt/
├── ai/
│   ├── novita.py                  # Novita API client
│   ├── novita_multi_model.py      # Multi-model orchestration
│   └── ...
├── ui/
│   ├── novita_config_dialog.py    # Model selection dialog
│   ├── opponent_mode_selector.py  # Updated with Novita option
│   ├── settings_dialog.py         # Novita configuration handling
│   └── app.py                     # ProposeWorker updated
└── core/
    └── opponent_mode.py           # OpponentMode.NOVITA added
```

### Key Components

#### 1. `NovitaClient` (novita.py)

OpenAI-compatible client for Novita API:
- Base URL: `https://api.novita.ai/openai`
- Methods:
  - `fetch_models()` - GET `/v1/models`
  - `call_model(model_id, prompt, max_tokens)` - POST `/chat/completions`
  - `close()` - Cleanup
- Features:
  - Trace ID logging
  - Request/response sanitization
  - Timeout handling
  - Error recovery

#### 2. `propose_move_novita_multi_model()` (novita_multi_model.py)

Orchestrates concurrent model calls:
```python
async def propose_move_novita_multi_model(
    client: NovitaClient,
    models: list[dict[str, Any]],
    compact_state: str,
    variant: VariantDefinition,
    board: Board,
    judge_client: OpenAIClient,
    progress_callback: Optional[Callable] = None,
    *,
    timeout_seconds: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ...
```

Flow:
1. Build prompt from game state
2. Call all models concurrently (`asyncio.gather`)
3. Parse JSON responses
4. Extract words and calculate scores
5. Validate with judge (parallel)
6. Select best valid move
7. Return move + all results

#### 3. `NovitaConfigDialog` (novita_config_dialog.py)

Model selection UI:
- Search/filter models
- Grouped by category
- Shows context length
- Selection limit (10 models)
- Token configuration

#### 4. `ProposeWorker` Updates (app.py)

Worker class now supports both providers:
```python
class ProposeWorker(QObject):
    def __init__(self, ..., *, provider_type: str = "openrouter"):
        ...
    
    def run(self) -> None:
        if self.provider_type == "novita":
            # Use NovitaClient + propose_move_novita_multi_model
            ...
        else:
            # Use OpenRouterClient + propose_move_multi_model
            ...
```

Provider selection logic in `_start_ai_turn()`:
```python
if self.opponent_mode == OpponentMode.NOVITA and self.selected_novita_models:
    provider_type = "novita"
    selected_models = self.selected_novita_models
    timeout_seconds = self.ai_move_timeout_seconds
    use_multi = True
```

### Data Flow

```
User Selects Novita Mode
        ↓
OpponentMode.NOVITA set
        ↓
AI Turn Triggered
        ↓
ProposeWorker(provider_type="novita")
        ↓
NovitaClient.call_model() × N (parallel)
        ↓
propose_move_novita_multi_model()
        ↓
partial_result signals → UI updates
        ↓
Judge validates words (parallel)
        ↓
multi_model_results signal → Results table
        ↓
Best move selected → Game continues
```

## API Details

### Endpoints

1. **List Models**
   - `GET /openai/v1/models`
   - Returns: `{"object": "list", "data": [...]}`

2. **Chat Completions**
   - `POST /openai/chat/completions`
   - Payload:
     ```json
     {
       "model": "deepseek/deepseek-r1",
       "messages": [{"role": "user", "content": "..."}],
       "max_tokens": 4096,
       "temperature": 0.6,
       "top_p": 0.95
     }
     ```
   - Returns:
     ```json
     {
       "choices": [{
         "message": {
           "content": "...",
           "reasoning_content": "..."
         }
       }],
       "usage": {
         "prompt_tokens": 123,
         "completion_tokens": 456
       }
     }
     ```

### Model Categories

- **DeepSeek**: `deepseek/deepseek-r1-*`
- **Qwen**: `qwen/qwen3-*`
- **GLM**: `zai-org/glm-*`, `thudm/glm-*`
- **LLaMA**: `meta-llama/llama-*`

### Recommended Parameters

- `temperature`: 0.6 (balances creativity and logic)
- `top_p`: 0.95 (nucleus sampling)
- `max_tokens`: 4096 (sufficient for complex moves)

## Error Handling

### Timeout Handling
- Per-model timeout: `timeout_seconds` parameter
- Default: 120 seconds
- Status: `"timeout"` in results

### Parse Errors
- Invalid JSON → `status: "parse_error"`
- Empty response → `status: "parse_error"`
- Includes error analysis tips

### API Errors
- HTTP errors → `status: "error"`
- Network errors → `status: "error"`
- Logs full response for debugging

### Judge Validation
- Invalid words → `judge_valid: False`
- Validation error → `status: "invalid"`
- Includes reason in `judge_reason`

## Testing

### Unit Tests
```bash
# Mark tests with @pytest.mark.novita
poetry run pytest -m novita

# Run with real API (requires NOVITA_API_KEY)
poetry run pytest tests/test_novita_client.py
```

### Manual Testing
1. Add API key to `.env`
2. Run app: `poetry run scrabgpt`
3. Start new game
4. Open Settings → AI Protivník
5. Select Novita AI mode
6. Configure models
7. Play game and observe results table

## Comparison: OpenRouter vs Novita

| Feature | OpenRouter | Novita |
|---------|-----------|--------|
| Model Count | 100+ | 15+ |
| Focus | General LLMs | Reasoning models |
| Special Field | - | `reasoning_content` |
| Pricing | Variable | Competitive |
| Context Window | Varies | 8K-131K |
| API Style | Custom | OpenAI-compatible |

## Troubleshooting

### Models Not Loading
- Check `NOVITA_API_KEY` in `.env`
- Verify API key is valid
- Check network connectivity
- See logs: Settings → View Log

### Empty Responses
- Check model availability
- Increase `max_tokens`
- Try different models
- Check Novita API status

### Timeout Issues
- Increase `AI_MOVE_TIMEOUT_SECONDS`
- Use faster models (8B variants)
- Check network latency

### Parse Errors
- Some models may not follow JSON format strictly
- Use Response Detail dialog to inspect raw output
- Report issues to model provider

## Future Enhancements

- [ ] Model performance tracking
- [ ] Cost estimation per model
- [ ] Reasoning content visualization
- [ ] Model recommendation engine
- [ ] Batch testing across models
- [ ] Custom model parameters per model

## References

- [Novita API Documentation](https://novita.ai/docs/guides/llm-reasoning)
- [DeepSeek R1 Paper](https://arxiv.org/abs/...)
- [OpenAI Chat Completions Spec](https://platform.openai.com/docs/api-reference/chat)

## Credits

Implemented by Factory Droid following the OpenRouter pattern.
