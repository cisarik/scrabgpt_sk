# Agent Configuration UX Update - Complete ✅

## What Changed

Based on ux2.png feedback, I've restructured the agent configuration to use a separate dialog (like OpenRouter), improving usability and readability.

### 🎯 Changes Made

#### 1. **New AgentConfigDialog** (`scrabgpt/ui/agent_config_dialog.py`)

Created a dedicated dialog for agent selection with:
- ✅ **"Vyber agenta:"** label and dropdown
- ✅ **Tip message** moved from main settings (agent-specific info)
- ✅ **Agent details** showing model, tool count, description, tool list
- ✅ **Dark theme** matching the app style
- ✅ **✓ Použiť** button (not "Uložiť" since it's nested)

#### 2. **OpponentModeSelector Updated**

- ✅ Removed inline "Vyber agenta:" section
- ✅ Removed inline agent dropdown
- ✅ Removed tip message (moved to agent dialog)
- ✅ Added **"Nastaviť" button** next to OpenAI Agent description
- ✅ Increased minimum height (60px) for OpenAI Agent description box
- ✅ Both OpenRouter and Agent now have "Nastaviť" buttons

#### 3. **SettingsDialog Updated**

- ✅ Removed general tip message
- ✅ Connected `configure_agent_requested` signal
- ✅ Opens AgentConfigDialog when "Nastaviť" clicked
- ✅ Shows confirmation after agent selection

#### 4. **Visual Improvements**

- ✅ **Black backgrounds** (#0a0a0a) for all mode containers
- ✅ **Bigger description text** (12px)
- ✅ **Increased height** for Agent/OpenRouter descriptions (60px minimum)
- ✅ **White tip text** (no blue) - matches dark+green theme
- ✅ **Mode order**: Offline AI → OpenAI API call → OpenRouter → OpenAI Agent

---

## 🎨 New UI Flow

### Main Settings Dialog

```
┌─────────────────────────────────────────────────────┐
│ ⚙️ Nastavenia Hry                                   │
├─────────────────────────────────────────────────────┤
│ [🤖 AI Protivník]                                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ○ Offline AI                                       │
│   Hrať offline proti Vášmu PC                      │
│                                                     │
│ ● OpenAI API call                                  │
│   Hrať oproti najlepšiemu <GPT5> modelu           │
│                                                     │
│ ○ OpenRouter                       [Nastaviť]     │
│   Paralelné volanie modelov ktoré sú              │
│   nastavené pomocou funkcie                        │
│   'Nastaviť OpenRouter'                           │
│   (taller box - text readable)                     │
│                                                     │
│ ○ OpenAI Agent                     [Nastaviť]     │  ← NEW!
│   Hrať proti agentovi ktorý sa sám rozhoduje     │
│   čo a kedy použije (aké nástroje=funkcie si     │
│   podľa potreby zavolá) na to aby navrhol        │
│   svoj ťah                                         │
│   (taller box - text readable)                     │
│                                                     │
├─────────────────────────────────────────────────────┤
│                [✗ Zrušiť]  [✓ Uložiť]              │
└─────────────────────────────────────────────────────┘
```

### Agent Configuration Dialog (NEW)

```
┌─────────────────────────────────────────────────────┐
│ 🤖 Nastavenie AI Agenta                             │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 💡 Tip: Agent mód je experimentálny. Agent sa      │
│ sám rozhoduje, ktoré nástroje použije na návrh    │
│ svojho ťahu. Rôzni agenti majú prístup k rôznym   │
│ nástrojom - experimentujte a porovnajte výkon.    │
│                                                     │
│ ┌─────────────────────────────────────────────┐   │
│ │ Vyber agenta:                                │   │
│ │                                              │   │
│ │ [Plný Prístup (13 nástrojov, gpt-4o)    ▼]  │   │
│ │                                              │   │
│ │ Model: gpt-4o                                │   │
│ │ Počet nástrojov: 13                          │   │
│ │ Popis: Agent s prístupom ku všetkým...       │   │
│ │ Nástroje: rules_first_move_must_cover_ce...  │   │
│ └─────────────────────────────────────────────┘   │
│                                                     │
├─────────────────────────────────────────────────────┤
│                [✗ Zrušiť]  [✓ Použiť]              │
└─────────────────────────────────────────────────────┘
```

---

## 📝 User Experience Improvements

### Before

- ❌ "Vyber agenta:" shown inline - not visible when window small
- ❌ Agent dropdown always visible (cluttering UI)
- ❌ Tip message generic for all modes
- ❌ Description text cut off/unreadable
- ❌ Toolbar had separate "Nastaviť OpenRouter" button

### After

- ✅ Clean main settings - only mode radio buttons
- ✅ "Nastaviť" buttons for both OpenRouter and Agent
- ✅ Agent-specific tip in dedicated dialog
- ✅ All text readable (increased height)
- ✅ Toolbar simplified - only "Nastaviť AI"
- ✅ Consistent pattern: click "Nastaviť" to configure

---

## 🧪 Testing

```bash
poetry run python -m scrabgpt.ui.app
```

Then:

1. **Click "🤖 Nastaviť AI"** in toolbar
2. **Select "OpenAI Agent"** mode
3. **Click "Nastaviť"** button next to description
4. **Agent dialog opens**:
   - Select agent from dropdown
   - See agent details update
   - Click "✓ Použiť"
5. **Confirmation shows**: "Vybraný agent: [name]"
6. **Click "✓ Uložiť"** in main settings
7. **Done!** Agent configured

---

## 🎯 Key Benefits

### 1. **Cleaner Main Settings**
- No inline agent selector cluttering the view
- All modes look consistent
- More space for readable descriptions

### 2. **Better Discoverability**
- "Nastaviť" button clearly indicates configuration available
- Same pattern for both OpenRouter and Agent
- Users understand what to expect

### 3. **Agent-Specific Context**
- Tip message focused on agents (not generic)
- Agent details show immediately
- Tool list preview helps users understand differences

### 4. **Responsive Design**
- No "Vyber agenta:" visibility issues on small windows
- Description boxes tall enough to read full text
- Dialog can be sized independently

### 5. **Consistent Architecture**
- OpenRouter config → separate dialog
- Agent config → separate dialog
- Same user flow for both features

---

## 🔧 Technical Details

### Files Created

- `scrabgpt/ui/agent_config_dialog.py` (233 lines)

### Files Modified

- `scrabgpt/ui/opponent_mode_selector.py`:
  - Removed inline agent selector
  - Added "Nastaviť" button for Agent mode
  - Added `configure_agent_requested` signal
  - Increased description height to 60px
  - Cleaned up unused code

- `scrabgpt/ui/settings_dialog.py`:
  - Removed tip message
  - Added `_configure_agent()` method
  - Imported `AgentConfigDialog`
  - Connected agent config signal

- `scrabgpt/ui/app.py`:
  - Removed "Nastaviť OpenRouter" from toolbar (already done)
  - All OpenRouter config now in settings dialog

### Code Removed

- `_create_agent_selector()` method (~60 lines)
- `_on_agent_changed()` method (~20 lines)
- References to `agent_combo`, `agent_label`, `agent_info`

---

## ✅ Verification Checklist

- [x] Agent dialog opens from "Nastaviť" button
- [x] Agent dropdown populated correctly
- [x] Agent details update on selection
- [x] Tip message shows in agent dialog
- [x] Confirmation message after selection
- [x] Settings properly stored and passed to main window
- [x] OpenAI Agent description readable (60px height)
- [x] OpenRouter description readable (60px height)
- [x] No more inline agent selector in main settings
- [x] Toolbar simplified (only "Nastaviť AI")
- [x] No import errors or unused code warnings

---

## 📊 Summary Statistics

**Before:**
- 1 toolbar button: "Nastaviť AI"
- 1 toolbar button: "Nastaviť OpenRouter"
- Inline agent selector (always visible)
- Generic tip message
- ~326 lines in opponent_mode_selector.py

**After:**
- 1 toolbar button: "Nastaviť AI" (consolidated)
- "Nastaviť" buttons in settings (OpenRouter + Agent)
- Separate AgentConfigDialog (233 lines)
- Agent-specific tip in dialog
- ~240 lines in opponent_mode_selector.py (cleaner)

**Net Result:**
- ✅ Simpler toolbar
- ✅ Cleaner main settings
- ✅ Better UX consistency
- ✅ Improved readability
- ✅ More maintainable code

---

## 🎉 Ready to Use!

The agent configuration now follows the same pattern as OpenRouter, making it intuitive and consistent. Users can easily discover and configure agents without cluttering the main settings dialog!
