# Novita AI Quick Start Guide

## Step-by-Step Instructions

### 1. Add API Key

Edit `.env` file and add your Novita API key:

```bash
NOVITA_API_KEY='your-novita-api-key-here'
```

Get your API key from: https://novita.ai/

### 2. Start the Game

```bash
poetry run scrabgpt
```

### 3. Configure Novita Mode

1. Click **Nastavenia** (Settings) button in toolbar
2. Go to **AI Protivník** tab
3. Select **Novita AI** radio button
4. Click the **Nastaviť** button next to the Novita description
5. In the dialog that opens:
   - Browse available models (DeepSeek, Qwen, GLM, LLaMA)
   - Use search box to filter models
   - Select up to 10 models by clicking checkboxes
   - Click **OK**
6. You should see a confirmation message: "Vybrané: N reasoning modelov pre Novita režim"
7. Click **OK** to close Settings dialog

### 4. Start a New Game

1. Click **Nová hra** (New Game)
2. The AI will use the selected Novita models
3. Watch the **Results Table** (below the rack) populate with:
   - Model names
   - Proposed moves
   - Scores
   - Judge validation (✓/✗)
   - Status

### 5. Verify It's Working

**Expected Behavior:**
- Status bar shows: `[Novita] Volám N modelov: Model1, Model2, ...`
- Results table shows rows for each model
- As each model completes, its row updates with move and score
- Winner gets 🥇 medal
- Status bar updates: `✓ Víťaz: ModelName - WORD (score bodov)`

**Troubleshooting:**

If you see empty table or just "Hra AI":

1. **Check logs:**
   - Settings → View Log
   - Look for lines like:
     ```
     AI turn: opponent_mode=OpponentMode.NOVITA
     Available: OpenRouter models=0, Novita models=5
     Using Novita with 5 models
     ```

2. **Verify models were saved:**
   - Look for: `Stored Novita models: ['Model1', 'Model2', ...]`
   - If this is missing, models weren't selected properly

3. **Check API key:**
   - Make sure `NOVITA_API_KEY` is in `.env`
   - No quotes around the actual key value
   - Key should start with a valid prefix

4. **Restart app:**
   - Close ScrabGPT completely
   - Reopen: `poetry run scrabgpt`
   - Reconfigure Novita models

### Debug Checklist

```python
# In logs, you should see:
[INFO] Settings dialog returned N Novita models  # When you click OK in config
[INFO] Stored Novita models: [...]              # Confirms storage
[INFO] Opponent mode changed to: novita         # When you select Novita radio
[INFO] AI turn: opponent_mode=OpponentMode.NOVITA  # When AI starts turn
[INFO] Available: OpenRouter models=0, Novita models=N  # Shows model counts
[INFO] Using Novita with N models               # Confirms provider selection
[INFO] [novita-call-1] Calling Novita model...  # API calls starting
```

### Common Issues

**Issue: "Settings dialog returned 0 Novita models"**
- You clicked OK without selecting any models
- Solution: Reopen config dialog and select models

**Issue: "opponent_mode=OpponentMode.BEST_MODEL"**
- Novita mode wasn't selected or didn't persist
- Solution: In Settings → AI Protivník, click Novita AI radio button, then OK

**Issue: "Using single-model mode"**
- Either opponent_mode is not NOVITA, or selected_novita_models is empty
- Solution: Follow steps 3-4 again carefully

**Issue: API errors in logs**
- Check NOVITA_API_KEY is correct
- Verify API key has sufficient credits
- Check Novita service status

### Example Log Output (Success)

```
[INFO] Settings dialog returned 3 Novita models
[INFO] Stored Novita models: ['Deepseek R1 0528', 'Qwen3 32B Fp8', 'Glm 4.5']
[INFO] Opponent mode changed to: novita
[INFO] [AI] start turn
[INFO] AI turn: opponent_mode=OpponentMode.NOVITA
[INFO] Available: OpenRouter models=0, Novita models=3
[INFO] Using Novita with 3 models
[INFO] [Novita] Volám 3 modelov: Deepseek R1 0528, Qwen3 32B...
[INFO] [novita-call-1] Calling Novita model: deepseek/deepseek-r1-0528
[INFO] [novita-call-2] Calling Novita model: qwen/qwen3-32b-fp8
[INFO] [novita-call-3] Calling Novita model: zai-org/glm-4.5
[INFO] Novita finished for deepseek/deepseek-r1-0528 status=ok...
[INFO] Partial result from Deepseek R1 0528 status=ok score=24
...
[INFO] ✓ Víťaz: Deepseek R1 0528 - SLOVO (24 bodov)
```

## Testing Individual Components

### Test Model Fetching

```python
# Run in Python console
import asyncio
from scrabgpt.ai.novita import NovitaClient
import os

async def test_fetch():
    client = NovitaClient(os.getenv("NOVITA_API_KEY"))
    models = await client.fetch_models()
    print(f"Fetched {len(models)} models")
    for m in models[:5]:
        print(f"  - {m['id']}: {m['name']}")
    await client.close()

asyncio.run(test_fetch())
```

### Test Model Selection Dialog

```python
# In app, add debug print in novita_config_dialog.py _on_ok:
def _on_ok(self) -> None:
    selected_ids = [model_id for model_id, checked in self._selection_state.items() if checked]
    print(f"DEBUG: Selected {len(selected_ids)} models: {selected_ids}")
    ...
```

## Support

If issues persist:
1. Share the full log output (Settings → View Log → copy all)
2. Describe exact steps you took
3. Include screenshot of empty table
4. Check if OpenRouter mode works (to isolate Novita-specific issue)
