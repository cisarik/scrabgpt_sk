# Multi-Model AI Configuration UI Improvements

## Summary of Changes

The AI configuration dialog has been significantly improved to be more compact and user-friendly, with better cost visibility.

## Key Improvements

### 1. **Top Weekly Models**
- Now fetches "Top Weekly" models from OpenRouter (same as their website)
- Uses `order=week` parameter in API call
- Window title updated to "Nastaviť AI Modely (Top Weekly)"

### 2. **Compact Layout**
- Reduced window size: 700x600 (from 800x700)
- Tighter spacing and margins throughout
- Smaller font sizes (11px for model names, 9-10px for details)
- More efficient use of space

### 3. **Better Cost Visibility**
- **Prominent separator line** before cost label
- **Large, bordered cost display** at the bottom
- Shows "⚠️ Vyber aspoň jeden model" when nothing selected (yellow)
- Shows "✓ N modelov vybraných | 💰 Maximálna cena za ťah: $X" when selected (green with border)
- Smart formatting: Shows 4, 6, or 8 decimal places depending on cost magnitude
- **Maximum possible cost** calculated correctly (all models with max completion tokens)

### 4. **Improved Model Cards**
- Changed from `QGroupBox` to `QFrame` for lighter styling
- Numbered models (1., 2., 3., etc.)
- Compact pricing display using ‱ (basis points):
  - Example: "$0.02‱" means $0.00002 per token
  - Format: `{context}K ctx | ${price}‱ prompt | ${price}‱ completion`
- Smaller spinbox (80px width) for max tokens
- Hover effect changes background to light gray

### 5. **Visual Hierarchy**
```
┌─────────────────────────────────────┐
│   🤖 Top Weekly AI Modely           │  ← Title (15px, bold)
│   Info about concurrent models      │  ← Info (11px)
├─────────────────────────────────────┤
│ ╔═════════════════════════════════╗ │
│ ║  [✓] 1. GPT-4 Turbo            ║ │  ← Model cards (compact)
│ ║  32K ctx | $0.10‱ | $0.30‱     ║ │
│ ║  Tokens: [3600▼]               ║ │
│ ╚═════════════════════════════════╝ │
│ ... more models ...                 │
├─────────────────────────────────────┤  ← Separator line
│ ✓ 3 modelov | 💰 Max: $0.001234   │  ← Cost (13px, bold, bordered)
├─────────────────────────────────────┤
│    [✗ Zrušiť]    [✓ Použiť]       │  ← Buttons
└─────────────────────────────────────┘
```

### 6. **Cost Calculation Details**
The "Maximálna cena za ťah" is calculated as:
```python
total_cost = sum(
    (prompt_tokens / 1_000_000) * model.prompt_price +
    (max_completion_tokens / 1_000_000) * model.completion_price
    for model in selected_models
)
```

Where:
- `prompt_tokens = 2000` (estimated)
- `max_completion_tokens = max(m["max_tokens"] for m in selected_models)`

This represents the **maximum possible cost** for one AI turn.

## Design Philosophy

1. **Information Density**: Pack more info in less space without sacrificing readability
2. **Visual Hierarchy**: Most important info (cost) is most prominent
3. **Progressive Disclosure**: Details visible but not overwhelming
4. **Immediate Feedback**: Cost updates instantly as you change selections
5. **Clear Affordances**: Buttons, checkboxes, and spinboxes clearly interactive

## Font Sizes Used

| Element | Size | Purpose |
|---------|------|---------|
| Title | 15px | Dialog title |
| Info | 11px | Instructional text |
| Model name | 11px | Primary identifier |
| Model details | 9px | Secondary info (context, pricing) |
| Token label | 10px | Spinbox label |
| Cost label | 13px | **Most important** - always visible |
| Buttons | 12px | Action buttons |

## Color Scheme

- **Yellow (#fff3cd)**: Warning - no selection
- **Green (#d4edda)**: Success - models selected
- **Blue (#e3f2fd)**: Info banner
- **White (#ffffff)**: Model cards background
- **Light gray (#f8f9fa)**: Hover state

## Before vs After

### Before:
- 800x700 window
- Large model cards with lots of padding
- Generic font sizes (13-14px)
- Cost not very prominent
- Used full model names with verbose pricing

### After:
- 700x600 window (saves ~23% space)
- Compact model cards with minimal padding
- Smaller fonts (9-11px for details)
- **Cost has separator + border + emojis**
- Numbered models with compact pricing (‱ notation)
- Shows "Maximálna cena" (maximum possible cost)

## Technical Implementation

- `order="week"` parameter added to `fetch_models()` API call
- Pricing displayed in basis points (×1000 for display)
- Context length shown in thousands (÷1000)
- Smart decimal formatting based on magnitude
- Cost updates on every checkbox or spinbox change
