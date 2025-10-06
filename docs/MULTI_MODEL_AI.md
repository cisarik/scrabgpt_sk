# Multi-Model AI Configuration

ScrabGPT now supports using multiple AI models concurrently via OpenRouter, allowing the game to select the best move from multiple AI systems.

## Features

- **Concurrent API Calls**: Call multiple AI models simultaneously
- **Best Move Selection**: Automatically selects the move with the highest score
- **Cost Estimation**: Shows estimated cost per move based on selected models
- **Top Model Selection**: Automatically ranks and presents the top 10 models

## Setup

### 1. Get OpenRouter API Key

1. Sign up at [https://openrouter.ai/](https://openrouter.ai/)
2. Get your API key from the dashboard
3. Add it to your `.env` file:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
```

### 2. Configure Models

1. Launch ScrabGPT: `poetry run scrabgpt`
2. Click the **🤖 Nastaviť AI** button in the toolbar
3. The dialog will load the top 10 recommended models
4. Select one or more models you want to use
5. Adjust `max_tokens` for each model (default: 3600)
6. View the estimated cost per move at the bottom
7. Click **✓ Použiť vybrané modely**

## How It Works

### Model Selection

The system automatically ranks models based on:
- **Context length** (prioritizes 4000+ tokens)
- **Provider reputation** (OpenAI, Anthropic, Google, Meta, etc.)
- **Pricing** (balances cost and quality)

### Concurrent Execution

When the AI's turn comes:
1. The game state is sent to all selected models concurrently
2. Each model proposes a move
3. Each move is scored using the game's scoring rules
4. The move with the highest score is selected
5. That move is played

### Cost Calculation

Estimated cost is calculated as:
```
Total Cost = Σ(model_prompt_price × prompt_tokens + model_completion_price × max_completion_tokens)
```

Prices are per 1 million tokens.

## Model Configuration Format

Each selected model includes:
```python
{
    "id": "openai/gpt-4-turbo",
    "name": "GPT-4 Turbo",
    "context_length": 128000,
    "prompt_price": 0.01,        # per 1M tokens
    "completion_price": 0.03,    # per 1M tokens
    "max_tokens": 3600           # user-configured
}
```

## Usage Examples

### Single Model (Default)
If no models are configured, the system uses the default `gpt-5-mini` via OpenAI.

### Multiple Models
Select 3-5 models for best results. More models = more cost but potentially better moves.

**Recommended combinations:**
- **Balanced**: GPT-4 Turbo + Claude 3.5 Sonnet + Gemini Pro
- **Budget**: GPT-3.5 Turbo + Llama 3 + Mistral
- **Premium**: GPT-4 + Claude 3 Opus + Gemini Ultra

## Logging

Multi-model execution logs include:
- Number of models called
- Which model provided the best move
- Individual model scores
- Any errors or failures

Example log output:
```
[AI] Multi-model: 3 models, best score from GPT-4 Turbo
  GPT-4 Turbo: score=45
  Claude 3.5 Sonnet: score=42
  Gemini Pro: score=38
```

## Fallback Behavior

If multi-model execution fails:
1. The system falls back to single-model (GPT-5-mini)
2. An error message is logged
3. The game continues normally

## Performance

- **Latency**: Concurrent calls complete in ~same time as single call
- **Cost**: Proportional to number of models selected
- **Quality**: Generally improves with more diverse models

## Troubleshooting

### "OPENROUTER_API_KEY not set"
Add the API key to your `.env` file in the project root.

### "No models returned valid moves"
Check:
1. API key is valid
2. You have credits in your OpenRouter account
3. Selected models support the required features

### High costs
Reduce:
1. Number of selected models
2. `max_tokens` value
3. Or use cheaper models (Llama, Mistral)

## Technical Details

### Files
- `scrabgpt/ai/openrouter.py` - OpenRouter client
- `scrabgpt/ai/multi_model.py` - Multi-model orchestration
- `scrabgpt/ui/ai_config.py` - Configuration dialog

### Key Functions
- `propose_move_multi_model()` - Calls multiple models concurrently
- `get_top_models()` - Ranks and filters models
- `calculate_estimated_cost()` - Estimates move cost

### Dependencies
- `httpx` - Async HTTP client
- `asyncio` - Concurrent execution
- Existing OpenAI client for fallback
