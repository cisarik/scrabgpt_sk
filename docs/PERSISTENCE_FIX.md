# Persistence Fix: Models & Opponent Mode

## Problem

**Original Issues:**
1. ❌ Unwanted alert popup after configuring models
2. ❌ Models not persisting between app restarts
3. ❌ Opponent mode not persisting - always reset to `BEST_MODEL`
4. ❌ Even with models configured, app chose wrong mode

**Log Evidence:**
```
AI turn: opponent_mode=OpponentMode.BEST_MODEL  ← Wrong!
Available: OpenRouter models=0, Novita models=0  ← Models lost!
Using single-model mode  ← Should be multi-model!
```

## Root Causes

### Issue 1: Unwanted Alerts
- **Cause:** `QMessageBox.information()` dialogs in settings_dialog.py
- **Files:** `scrabgpt/ui/settings_dialog.py` lines 356-360, 372-376

### Issue 2: Models Not Persisting
- **Cause:** Team configurations saved but not loaded on startup
- **Fix:** Already implemented in previous iteration (team_config.py)
- **Status:** ✅ Working

### Issue 3: Opponent Mode Not Persisting
- **Cause:** Opponent mode never saved to disk
- **Impact:** Even if models loaded, wrong mode meant they weren't used
- **Fix:** Added opponent mode to config.json

## Solution Implemented

### 1. Removed Alert Popups ✅

**Before:**
```python
QMessageBox.information(
    self,
    "Novita Nastavené",
    f"Vybrané: {model_count} reasoning modelov pre Novita režim.",
)
```

**After:**
```python
log.info("Novita models configured: %d models", len(self.selected_novita_models))
```

**Result:** Silent confirmation in logs only, no UI interruption.

### 2. Added Opponent Mode Persistence ✅

**New Methods in `team_config.py`:**
```python
class TeamManager:
    def save_opponent_mode(self, mode: str) -> None:
        """Save opponent mode to ~/.scrabgpt/config.json"""
        
    def load_opponent_mode(self) -> str | None:
        """Load opponent mode from ~/.scrabgpt/config.json"""
```

**Config File Format** (`~/.scrabgpt/config.json`):
```json
{
  "opponent_mode": "novita"
}
```

### 3. Integrated Load/Save in App ✅

**On Startup** (`app.py` → `_load_saved_teams`):
```python
# Load saved opponent mode
saved_mode = self.team_manager.load_opponent_mode()
if saved_mode:
    try:
        self.opponent_mode = OpponentMode(saved_mode)
        log.info("Loaded opponent mode from config: %s", self.opponent_mode.value)
    except ValueError:
        log.warning("Invalid opponent mode in config: %s", saved_mode)
```

**On Save** (`app.py` → `on_opponent_settings_accepted`):
```python
# Save opponent mode to config
self.team_manager.save_opponent_mode(new_mode.value)
log.info("Saved opponent mode to config: %s", new_mode.value)
```

## Files Modified

### Core Module
- ✅ `scrabgpt/core/team_config.py`
  - Added `DEFAULT_CONFIG_FILE` constant
  - Added `config_file` parameter to `TeamManager.__init__`
  - Added `save_opponent_mode()` method
  - Added `load_opponent_mode()` method

### UI Module
- ✅ `scrabgpt/ui/settings_dialog.py`
  - Removed `QMessageBox.information()` for OpenRouter (line ~356)
  - Removed `QMessageBox.information()` for Novita (line ~372)
  - Replaced with `log.info()` calls

### Main Application
- ✅ `scrabgpt/ui/app.py`
  - Updated `_load_saved_teams()` to load opponent mode
  - Updated `on_opponent_settings_accepted()` to save opponent mode

### Documentation & Tests
- ✅ `tools/test_teams.py` - Added TEST 6 for opponent mode
- ✅ `docs/PERSISTENCE_FIX.md` - This document

## Storage Locations

```
~/.scrabgpt/
├── config.json              # Opponent mode + future global settings
├── teams/
│   ├── novita_team.json     # Novita model selections
│   └── openrouter_team.json # OpenRouter model selections
```

### Example Files

**config.json:**
```json
{
  "opponent_mode": "novita"
}
```

**novita_team.json:**
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

## Expected Behavior Now

### Configuration Flow

1. **User configures Novita:**
   ```
   Settings → AI Protivník → Novita AI (radio button) → Nastaviť
   → Select models → OK
   → NO ALERT POPUP!
   → Settings dialog closes
   ```

2. **Logs show:**
   ```
   [INFO] Novita models configured: 3 models
   [INFO] Stored Novita models: ['DeepSeek R1', 'Qwen3 32B', ...]
   [INFO] Saved team 'Novita Team' for novita: 3 models
   [INFO] Novita models updated and saved: 3 models
   [INFO] Saved opponent mode to config: novita  ← NEW!
   [INFO] Opponent mode changed to: novita
   ```

3. **Files created:**
   ```
   ~/.scrabgpt/config.json (opponent mode)
   ~/.scrabgpt/teams/novita_team.json (models)
   ```

### Restart Flow

1. **App starts:**
   ```
   [INFO] Team manager initialized: ~/.scrabgpt/teams
   [INFO] Loaded team 'Novita Team' for novita: 3 models
   [INFO] Loaded Novita team: 3 models
   [INFO] Loaded opponent mode from config: novita  ← NEW!
   ```

2. **State restored:**
   ```python
   self.selected_novita_models = [3 models]  # ✅ From novita_team.json
   self.opponent_mode = OpponentMode.NOVITA   # ✅ From config.json
   ```

3. **AI turn works:**
   ```
   [INFO] AI turn: opponent_mode=OpponentMode.NOVITA  ✅
   [INFO] Available: OpenRouter models=0, Novita models=3  ✅
   [INFO] Using Novita with 3 models  ✅
   [INFO] [Novita] Volám 3 modelov: ...  ✅
   ```

## Testing

### Automated Test

```bash
poetry run python tools/test_teams.py
```

**Expected output:**
```
TEST 1: Save Novita team
✓ Saved team: Novita Team

TEST 2: Load Novita team
✓ Loaded 3 models

TEST 3: Save OpenRouter team
✓ Saved team: Openrouter Team

TEST 4: List all teams
✓ Found 2 teams

TEST 5: Verify JSON files
✓ Files exist

TEST 6: Save and load opponent mode
✓ Saved opponent mode: novita
✓ Loaded opponent mode: novita

✓ All tests passed!
```

### Manual Test

1. **Clean slate:**
   ```bash
   rm -rf ~/.scrabgpt/
   ```

2. **Start app:**
   ```bash
   poetry run scrabgpt
   ```

3. **Configure Novita:**
   - Settings → AI Protivník → Novita AI → Nastaviť
   - Select 2-3 models → OK
   - Click OK on Settings dialog
   - **Verify:** No alert popup! ✅

4. **Check files:**
   ```bash
   cat ~/.scrabgpt/config.json
   # Should show: {"opponent_mode": "novita"}
   
   cat ~/.scrabgpt/teams/novita_team.json
   # Should show: 2-3 models
   ```

5. **Restart app:**
   ```bash
   # Close and reopen
   poetry run scrabgpt
   ```

6. **Check logs:**
   ```bash
   # Look for:
   # "Loaded Novita team: N models"
   # "Loaded opponent mode from config: novita"
   ```

7. **Start game:**
   - Click "Nová hra"
   - **Verify:** Results table shows N models ✅
   - **Verify:** Status bar shows "[Novita] Volám N modelov..." ✅

## Debugging

### Issue: Config file not created

**Check:**
```bash
ls -la ~/.scrabgpt/
```

**Fix:**
- Verify write permissions
- Check logs for "Failed to save opponent mode"

### Issue: Wrong mode loaded

**Check:**
```bash
cat ~/.scrabgpt/config.json
```

**Fix:**
- Manually edit if needed
- Or delete and reconfigure

### Issue: Models loaded but wrong mode

**Log signature:**
```
Available: ... Novita models=3
Using single-model mode (opponent_mode=OpponentMode.BEST_MODEL)
```

**Cause:** Config file missing or has wrong mode

**Fix:**
```bash
echo '{"opponent_mode": "novita"}' > ~/.scrabgpt/config.json
```

### Issue: Mode loaded but no models

**Log signature:**
```
Loaded opponent mode: novita
Available: ... Novita models=0
```

**Cause:** Team file missing

**Fix:**
```bash
# Reconfigure in Settings or run:
poetry run python tools/test_teams.py
```

## Summary of Changes

### Problems Fixed ✅
1. ✅ Removed annoying alert popups
2. ✅ Models persist across restarts (already working)
3. ✅ **Opponent mode now persists** (NEW)
4. ✅ App uses correct mode on startup

### User Experience
- **Before:** Configure → Alert → Restart → Lost → Repeat 😤
- **After:** Configure once → Works forever 🎉

### Developer Experience
- Clean separation: models in teams/, mode in config.json
- Extensible: config.json can hold future settings
- Testable: Automated tests verify persistence
- Debuggable: JSON files easy to inspect/edit

### Next Steps

1. **Add NOVITA_API_KEY to .env**
2. **Configure Novita team** (Settings → AI Protivník)
3. **Restart app** to verify persistence
4. **Play game** and watch results table!

The complete fix is implemented and tested. No more lost configurations! 🚀✨
