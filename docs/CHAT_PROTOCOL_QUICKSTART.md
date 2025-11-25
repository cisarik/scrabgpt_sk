# Chat Protocol - Quick Start Guide

## 🚀 5-minutový Setup

### 1. Predpoklady

```bash
# Python 3.10+ s poetry
python --version  # 3.10+
poetry --version

# Nainštalované dependencies
poetry install
```

### 2. API Keys

```bash
# Skopíruj .env.example
cp .env.example .env

# Edituj .env a pridaj:
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENAI_API_KEY=sk-your-openai-key-here  # Pre judge validácie
```

### 3. Spusti App

```bash
poetry run python -m scrabgpt.ui.app
```

### 4. Prvá Hra s Chat Protokolom

1. **Nová hra** → File > Nová hra
2. **Počkaj na AI ťah** → Logy ukážu:
   ```
   Chat protocol: initialized system prompt for Slovak
   Chat protocol: calling OpenRouter model=openai/gpt-4o-mini
   ```
3. **Klikni na statusbar** (dole v okne) → Otvorí sa chat dialog
4. **Napíš správu AI** → "Ahoj, ako sa máš?"
5. **Dummy odpoveď** → Zatiaľ len echo, plná funkcionalita bude po dokončení

## 🎨 Chat Dialog Features

### Loading Animation
```
⚙️ AI premýšľa.   (400ms cycle)
⚙️ AI premýšľa..
⚙️ AI premýšľa...
```

### Typing Effect
```
Áno, viem hrať...▋  (20ms/8 chars)
```

### Chat Bubliny
```
┌──────────────────────────┐
│ [10:15:30]              │  AI (green gradient)
│ Ahoj! Vieš hrať?        │
└──────────────────────────┘

            ┌──────────────────┐
            │ [10:15:45]      │  User (blue gradient)
            │ Áno, zahrajme!  │
            └──────────────────┘
```

## 📊 Token Savings

Po 5 ťahoch:

| Starý protokol | Nový protokol | Úspora |
|----------------|---------------|--------|
| 6000 tokens    | 1650 tokens   | **72.5%** |

## 🔧 Konfigurácia

### Default Model

Chat protokol defaultne používa `openai/gpt-4o-mini`. Pre zmenu edituj v kóde:

```python
# scrabgpt/ui/app.py - _start_ai_turn()
move = await propose_move_chat(
    ...,
    model_id="anthropic/claude-3.5-sonnet",  # Zmeniť tu
)
```

### Token Limits

```bash
# .env
AI_MOVE_MAX_OUTPUT_TOKENS=3600  # Max tokens per move
AI_MOVE_TIMEOUT_SECONDS=30      # Timeout per API call
```

## 🐛 Troubleshooting

### "OpenRouter API key not found"
```bash
# Skontroluj .env
cat .env | grep OPENROUTER_API_KEY
```

### "Context session not initialized"
```bash
# Reštartuj hru (File > Nová hra)
# Context session sa vytvorí pri prvom ťahu
```

### Chat dialog sa neotvorí
```bash
# Skontroluj logy
poetry run python -m scrabgpt.ui.app 2>&1 | grep -i chat

# Klikni PRIAMO na statusbar (sivý pruh dole)
```

## 📖 Ďalšie Čítanie

- [Plná dokumentácia](CHAT_PROTOCOL_IMPLEMENTATION.md)
- [Chat Protocol Spec](CHAT_PROTOCOL.md)
- [MCP Tools API](../scrabgpt/ai/mcp_tools.py)

## 🎯 Next Steps

1. Zahraj 5 ťahov → Pozoruj token savings v logoch
2. Otvor chat dialog → Vyskúšaj animácie
3. Prečítaj plnú dokumentáciu → Pochop architektúru
4. Experimentuj s inými modelmi → `model_id` parameter

---

Ak máš otázky, otvor issue alebo kontaktuj autora. Enjoy! 🎉
