# How to Run and Test the New UI

## 🚀 Start the Application

```bash
poetry run python -m scrabgpt.ui.app
```

## 🧪 Test the Integration

### 1. Test Settings Dialog

1. **Click "🤖 Nastaviť AI"** in the toolbar
2. You should see:
   - ✓ Settings dialog opens
   - ✓ Radio buttons for 4 modes
   - ✓ Slovak descriptions next to each
   - ✓ "OpenAI API call" selected by default
3. **Try selecting "OpenAI Agent"**:
   - ✓ Agent dropdown appears
   - ✓ Shows available agents
4. **Click "Uložiť"**:
   - ✓ Dialog closes
   - ✓ Status bar shows "AI Režim: ..."

### 2. Test Game State Lock

1. **Start a new game** (click "Nová hra")
2. **Click "🤖 Nastaviť AI"** again
3. You should see:
   - ✓ Warning message: "⚠️ Hra je v priebehu..."
   - ✓ Radio buttons are disabled
   - ✓ Can't change settings
4. **End the game** (complete it or start new)
5. **Click "🤖 Nastaviť AI"** again
6. You should see:
   - ✓ Warning gone
   - ✓ Radio buttons enabled

### 3. Test OpenRouter Button

1. **Click "🏁 Nastaviť OpenRouter"** in toolbar
2. You should see:
   - ✓ Multi-model config dialog opens (existing AIConfigDialog)
   - ✓ Can select models and configure tokens

## ✅ Expected Results

- **Toolbar**: Two buttons visible (Nastaviť AI, Nastaviť OpenRouter)
- **Settings**: Opens correctly with all 4 modes
- **Descriptions**: Match user requirements exactly
- **Game lock**: Works as expected
- **Status bar**: Updates when settings change

## 🐛 If Something Doesn't Work

### UI doesn't open
```bash
# Check for errors
poetry run python -m scrabgpt.ui.app 2>&1 | grep -i error
```

### Import errors
```bash
# Verify all components
poetry run python -c "from scrabgpt.ui.app import MainWindow; print('OK')"
```

### Agent list empty
```bash
# Check agents directory
ls -la agents/
# Should show: full_access.agent, minimal.agent, etc.
```

## 📝 What Works Now

✅ Settings dialog opens from toolbar
✅ Radio button selection
✅ Agent dropdown
✅ Game state locking
✅ Status bar updates
✅ OpenRouter separate button

## 🔜 What Still Needs Work

⚠️ **Agent mode** - Requires OpenAI function calling implementation
⚠️ **Best model mode** - Needs model parameter added to player.py
⚠️ **Settings persistence** - Save/load to file

See QUICK_START_AGENTS.md for next steps!
