# AI Config Dialog UX Improvements

## Issues Fixed

Based on user feedback from `ui_error.png`, the following issues were addressed:

### 1. **Font Too Small**
- **Before**: Model names at 11px, details at 9px
- **After**: Model names at 12px, details included in same line, more readable

### 2. **Model Name Not Visible**
- **Before**: Model name on first line, tiny gray text on second line (not clear what model it is)
- **After**: Full model name + pricing info all on same line in one readable text

### 3. **Poor Layout - Multiple Lines Per Model**
- **Before**: 
  - Line 1: Checkbox with just model name
  - Line 2: Gray pricing info (too small)
  - Line 3: "Tokens:" label + spinbox
- **After**: Everything on ONE line:
  - `[✓] 1. Model Name (32K ctx, $0.10‱ prompt, $0.30‱ completion) ................. Max. tokenov na ťah: [3600]`

### 4. **Slovak Translation Missing**
- **Before**: "Tokens:"
- **After**: "Max. tokenov na ťah:"

### 5. **Limited to 10 Models Only**
- **Before**: Only showed top 10 models (filtered by `get_top_models(limit=10)`)
- **After**: Shows ALL weekly trending models from OpenRouter API
- **Limit**: User can select maximum 10 models (enforced with warning dialog)

### 6. **Info Banner Not Prominent**
- **Before**: Light blue background, small font (11px)
- **After**: Dark background (#2c3e50), white text, larger font (13px, bold)

## New Layout Design

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                       🤖 Top Weekly AI Modely                                │
├──────────────────────────────────────────────────────────────────────────────┤
│  Vyber modely pre konkurenčné hranie (max. 10).                            │
│  Najlepší ťah (najvyššie skóre) sa použije.                                │
│  (Dark background, white text, bold, 13px)                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│ [✓] 1. GPT-4 Turbo (32K ctx, $0.10‱ prompt, $0.30‱ completion) ... Max. tokenov na ťah: [3600] │
│ [ ] 2. Claude 3 Opus (200K ctx, $0.15‱ prompt, $0.45‱ completion) .. Max. tokenov na ťah: [3600] │
│ [✓] 3. Gemini Pro (128K ctx, $0.05‱ prompt, $0.15‱ completion) .... Max. tokenov na ťah: [3600] │
│ ... (scrollable, all models visible)                                         │
├──────────────────────────────────────────────────────────────────────────────┤
│ ✓ 2 modelov vybraných | 💰 Maximálna cena za ťah: $0.001234                │
├──────────────────────────────────────────────────────────────────────────────┤
│              [✗ Zrušiť]                      [✓ Použiť vybrané modely]      │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Key Changes

### Single-Line Layout
Each model now uses a horizontal layout (`QHBoxLayout`) instead of grid:
- Checkbox with full info text (model name + pricing)
- Stretch spacer
- Label: "Max. tokenov na ťah:"
- SpinBox (90px width)

### Max Selection Enforcement
New `_on_checkbox_changed()` method:
- Counts currently selected models
- If exceeding 10, blocks the selection and shows warning
- User-friendly Slovak message: "Môžeš vybrať maximálne 10 modelov."

### Show All Models
```python
# Before:
self.models = get_top_models(models, limit=10)

# After:
self.models = models  # All models from API (already sorted by order=week)
```

### Improved Visibility
Info banner styling:
```python
"padding: 10px; background: #2c3e50; border-radius: 4px; "
"color: white; font-size: 13px; font-weight: bold;"
```

### Slovak Translation
- "Tokens:" → "Max. tokenov na ťah:"
- "Vyber modely pre..." message now includes "(max. 10)"

## Window Size
- **Before**: 700×600
- **After**: 800×650 (more width for longer model names and info)

## Implementation Details

### File: `scrabgpt/ui/ai_config.py`

**Key Methods**:
1. `_populate_models()`: Creates single-line layout per model
2. `_on_checkbox_changed()`: Enforces max 10 selection limit
3. `_setup_ui()`: Improved info banner styling

**Data Flow**:
1. Fetch all models from OpenRouter (sorted by `order=week`)
2. Display all models in scrollable list
3. User can select up to 10 models
4. If trying to select 11th, show warning and uncheck

### Checkbox Text Format
```python
checkbox_text = (
    f"{idx}. {model_name}  "
    f"({context_length//1000}K ctx, "
    f"${prompt_price*1000:.2f}‱ prompt, "
    f"${completion_price*1000:.2f}‱ completion)"
)
```

This creates readable text like:
> "1. GPT-4 Turbo (32K ctx, $0.10‱ prompt, $0.30‱ completion)"

## User Experience Improvements

### Before
- ❌ Model names barely visible (tiny gray text)
- ❌ Unclear what each model costs
- ❌ Takes 3 lines per model (wasteful vertical space)
- ❌ Only 10 models shown (can't browse more)
- ❌ English labels ("Tokens:")
- ❌ Info text hard to see

### After
- ✅ Model names clear and readable (12px, on same line as checkbox)
- ✅ All pricing info visible immediately
- ✅ One line per model (efficient use of space)
- ✅ All weekly trending models visible (can scroll through hundreds)
- ✅ Slovak labels ("Max. tokenov na ťah:")
- ✅ Info text prominent on dark background

## Testing

All linting and type checking passes:
- `poetry run ruff check` ✓
- `poetry run mypy` ✓
- Max selection enforcement tested
- Layout renders correctly with long model names

## Future Enhancements

Possible improvements:
1. Search/filter models by name or provider
2. Sort options (by price, context length, etc.)
3. Save/load model configurations
4. Show model descriptions/capabilities on hover
5. Group models by provider
