# Team Configuration Feature

## Overview

ScrabGPT now supports persistent "Team" configurations - saved selections of AI models from different providers that persist across app restarts.

## What is a Team?

A **Team** is a named configuration containing:
- **Provider** (e.g., "openrouter", "novita")
- **Models** - List of selected models with their settings
- **Timeout** - API call timeout for this team
- **Timestamps** - Created/updated timestamps

Teams are automatically saved to disk when you configure models in Settings.

## Storage Location

```
~/.scrabgpt/teams/
├── openrouter_team.json
├── novita_team.json
└── ... (future providers)
```

Each provider has its own JSON file that persists the configuration.

## How It Works

### 1. **Configuration** (User selects models)

```
Settings → AI Protivník → Select "Novita AI" → Click "Nastaviť"
→ Select models → Click OK
→ Team automatically saved to disk
```

### 2. **Persistence** (Team saved to JSON)

```json
{
  "name": "Novita Team",
  "provider": "novita",
  "models": [
    {"id": "deepseek/deepseek-r1", "name": "DeepSeek R1", "max_tokens": 4096},
    {"id": "qwen/qwen3-32b-fp8", "name": "Qwen3 32B", "max_tokens": 4096}
  ],
  "timeout_seconds": 120,
  "created_at": "2025-01-20T10:00:00",
  "updated_at": "2025-01-20T10:05:00"
}
```

### 3. **Automatic Loading** (On app startup)

```python
# In MainWindow.__init__()
self.team_manager = get_team_manager()
self._load_saved_teams()  # Loads all saved teams

# Now models are available immediately:
# - self.selected_novita_models (loaded from disk)
# - self.selected_ai_models (loaded from disk)
```

### 4. **Game Play** (Teams ready to use)

```
Start new game → AI turn → Uses loaded team
→ Results table shows all models
→ Competition happens automatically
```

## Architecture

### Core Module: `team_config.py`

```python
from scrabgpt.core.team_config import TeamManager, TeamConfig

# Create manager
tm = TeamManager()

# Save team
tm.save_provider_models("novita", models_list, timeout=120)

# Load team
result = tm.load_provider_models("novita")
if result:
    models, timeout = result
    # Use models...

# List all teams
teams = tm.list_teams()

# Delete team
tm.delete_team("novita")
```

### Key Classes

#### `TeamConfig`
```python
@dataclass
class TeamConfig:
    name: str                     # "Novita Team"
    provider: str                 # "novita"
    models: list[dict[str, Any]]  # Model configurations
    timeout_seconds: int          # 120
    created_at: str              # ISO timestamp
    updated_at: str              # ISO timestamp
```

#### `TeamManager`
```python
class TeamManager:
    def save_team(team: TeamConfig) -> None
    def load_team(provider: str) -> TeamConfig | None
    def delete_team(provider: str) -> None
    def list_teams() -> list[TeamConfig]
    
    # Convenience methods
    def save_provider_models(...) -> TeamConfig
    def load_provider_models(...) -> tuple[models, timeout] | None
```

## Integration Points

### 1. **App Startup** (`app.py`)

```python
class MainWindow:
    def __init__(self):
        # Initialize team manager
        self.team_manager = get_team_manager()
        
        # Initialize empty model lists
        self.selected_ai_models = []
        self.selected_novita_models = []
        
        # Load saved teams (populates model lists)
        self._load_saved_teams()
```

### 2. **Settings Dialog** (`app.py` → `on_opponent_settings_accepted`)

```python
# When user clicks OK after configuring models:
if novita_models:
    self.selected_novita_models = novita_models
    
    # SAVE TO DISK
    self.team_manager.save_provider_models(
        "novita",
        novita_models,
        self.ai_move_timeout_seconds,
    )
    
    log.info("Novita models updated and saved: %d models", len(novita_models))
```

### 3. **AI Turn** (`app.py` → `_start_ai_turn`)

```python
# Models already loaded from disk on startup
if self.opponent_mode == OpponentMode.NOVITA and self.selected_novita_models:
    # Use the loaded models
    selected_models = self.selected_novita_models
    # ... start multi-model competition
```

## Benefits

### ✅ **Persistence**
- Models saved once, available forever
- No need to reconfigure on every startup
- Survives app crashes/restarts

### ✅ **Modularity**
- Each provider has separate configuration
- Easy to add new providers (just use `save_provider_models("new_provider", ...)`)
- No hardcoded provider logic

### ✅ **User Experience**
- Configure once, use many times
- Quick testing iterations
- Team configurations can be shared (copy JSON files)

### ✅ **Debugging**
- Teams visible in filesystem
- JSON format easy to inspect/edit
- Clear separation between providers

## Usage Examples

### Example 1: Configure Novita Team

```bash
# 1. Start app
poetry run scrabgpt

# 2. Settings → AI Protivník → Novita AI → Nastaviť
# 3. Select 3 models → OK

# 4. Team saved automatically to:
# ~/.scrabgpt/teams/novita_team.json
```

### Example 2: Check Saved Teams

```bash
# List all teams
ls -la ~/.scrabgpt/teams/

# View Novita team
cat ~/.scrabgpt/teams/novita_team.json

# View OpenRouter team
cat ~/.scrabgpt/teams/openrouter_team.json
```

### Example 3: Verify Loading on Startup

```bash
# Start app with logging
poetry run scrabgpt

# Check logs for:
# [INFO] Loaded Novita team: 3 models
# [INFO] Loaded OpenRouter team: 5 models
```

### Example 4: Test Programmatically

```python
# tools/test_teams.py
from scrabgpt.core.team_config import TeamManager

tm = TeamManager()

# Save test team
models = [
    {"id": "model1", "name": "Model 1", "max_tokens": 4096},
    {"id": "model2", "name": "Model 2", "max_tokens": 4096},
]
tm.save_provider_models("novita", models, timeout_seconds=120)

# Load and verify
result = tm.load_provider_models("novita")
assert result is not None
models_loaded, timeout = result
assert len(models_loaded) == 2
print("✓ Team saved and loaded successfully!")
```

## Log Output

### Successful Configuration Save

```
[INFO] Settings dialog returned 3 Novita models
[INFO] Stored Novita models: ['DeepSeek R1', 'Qwen3 32B', 'GLM 4.5']
[INFO] Saved team 'Novita Team' for novita: 3 models
[INFO] Novita models updated and saved: 3 models
```

### Successful Load on Startup

```
[INFO] Team manager initialized: /home/user/.scrabgpt/teams
[INFO] Loaded team 'Novita Team' for novita: 3 models
[INFO] Loaded Novita team: 3 models
```

### AI Turn with Loaded Team

```
[INFO] AI turn: opponent_mode=OpponentMode.NOVITA
[INFO] Available: OpenRouter models=0, Novita models=3
[INFO] Using Novita with 3 models
[INFO] [Novita] Volám 3 modelov: DeepSeek R1, Qwen3 32B, GLM 4.5...
```

## Future Enhancements

### Named Teams
Allow multiple teams per provider:
```json
// ~/.scrabgpt/teams/novita_team_speed.json
{"name": "Speed Team", "models": ["fast-model-1", "fast-model-2"]}

// ~/.scrabgpt/teams/novita_team_quality.json
{"name": "Quality Team", "models": ["best-model-1", "best-model-2"]}
```

### Team Sharing
Export/import team configurations:
```bash
# Export
scrabgpt export-team novita > my_team.json

# Import
scrabgpt import-team my_team.json
```

### Team Statistics
Track team performance:
```json
{
  "name": "Novita Team",
  "stats": {
    "games_played": 42,
    "avg_score": 245,
    "best_model": "deepseek/deepseek-r1",
    "win_rate": 0.73
  }
}
```

## Troubleshooting

### Issue: "Available: ... Novita models=0"

**Cause:** Team not loaded on startup

**Solution:**
1. Check if team file exists: `ls ~/.scrabgpt/teams/novita_team.json`
2. If missing, reconfigure in Settings
3. Check logs for loading errors
4. Verify JSON format is valid

### Issue: Models disappear after restart

**Cause:** Team not being saved when configured

**Solution:**
1. Check logs for "Novita models updated and saved"
2. Verify write permissions: `ls -la ~/.scrabgpt/teams/`
3. Check for exceptions in logs
4. Try manual save: `poetry run python tools/test_teams.py`

### Issue: Wrong models loaded

**Cause:** Old team file from previous configuration

**Solution:**
1. Check team file: `cat ~/.scrabgpt/teams/novita_team.json`
2. If wrong, delete: `rm ~/.scrabgpt/teams/novita_team.json`
3. Reconfigure in Settings
4. Verify new file has correct models

## Testing

### Manual Test
```bash
# 1. Delete existing teams
rm -rf ~/.scrabgpt/teams/

# 2. Start app
poetry run scrabgpt

# 3. Configure Novita team (Settings → AI Protivník → Novita → Nastaviť)

# 4. Check team saved
cat ~/.scrabgpt/teams/novita_team.json

# 5. Restart app
# (Close and reopen)

# 6. Check logs
# Should see: "Loaded Novita team: N models"

# 7. Start game
# Results table should show N models
```

### Automated Test
```bash
poetry run python tools/test_teams.py
```

## Summary

The Team Configuration feature solves the persistence problem by:
1. ✅ Saving model selections to disk (JSON)
2. ✅ Loading teams automatically on startup
3. ✅ Providing modular API for any provider
4. ✅ Maintaining separate configs per provider
5. ✅ Making configurations human-readable and editable

**Result:** Configure once, play forever! 🎮✨
