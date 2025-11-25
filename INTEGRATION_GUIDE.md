# Chat Protocol - Integračný Návod

## 🎯 Čo Už Funguje

✅ **ChatDialog UI** - Dark green téma, animácie, bubliny  
✅ **propose_move_chat()** - OpenRouter + context session + delta  
✅ **Statusbar click handler** - Otvorí chat dialog  
✅ **GameContextSession** - Delta methods (add_human_move, add_ai_move, atď.)  

## 🔌 Čo Ešte Treba - Integrácia do Herného Loopu

### **Problém:**
Momentálne `_start_ai_turn()` používa:
- `build_ai_state_dict()` - plný stav dosky
- `propose_move()` - starý protokol (zero-shot)
- `ProposeWorker` - single-model OpenAI

### **Riešenie:**
Pridať nový **chat protocol mode** vedľa existujúcich režimov.

---

## 📝 Implementačný Plán

### **Krok 1: Pridaj Chat Protocol Mode**

Rozšír `OpponentMode` enum:

```python
# scrabgpt/core/opponent_mode.py

class OpponentMode(str, Enum):
    BEST_MODEL = "best_model"
    OPENROUTER = "openrouter"
    NOVITA = "novita"
    CHAT_PROTOCOL = "chat_protocol"  # ← NOVÉ
```

### **Krok 2: Pridaj ChatProtocolWorker**

V `app.py`, pridaj nový worker pre chat protokol:

```python
class ChatProtocolWorker(QThread):
    """Worker pre chat protocol AI ťahy (async OpenRouter)."""
    
    finished = Signal(dict)
    failed = Signal(Exception)
    
    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        board: Board,
        ai_rack: list[str],
        variant: VariantDefinition,
        model_id: str,
        is_first_move: bool,
    ):
        super().__init__()
        self.openrouter_client = openrouter_client
        self.board = board
        self.ai_rack = ai_rack
        self.variant = variant
        self.model_id = model_id
        self.is_first_move = is_first_move
    
    def run(self):
        """Run propose_move_chat in thread's event loop."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                from scrabgpt.ai.player import propose_move_chat
                
                move = loop.run_until_complete(
                    propose_move_chat(
                        openrouter_client=self.openrouter_client,
                        board=self.board,
                        ai_rack=self.ai_rack,
                        variant=self.variant,
                        model_id=self.model_id,
                        is_first_move=self.is_first_move,
                    )
                )
                
                self.finished.emit(move)
            finally:
                loop.close()
        
        except Exception as e:
            log.exception("ChatProtocolWorker failed: %s", e)
            self.failed.emit(e)
```

### **Krok 3: Upraviť _start_ai_turn()**

Pridaj vetvu pre chat protocol mode:

```python
def _start_ai_turn(self) -> None:
    # ... existing code ...
    
    # Check opponent mode
    if self.opponent_mode == OpponentMode.CHAT_PROTOCOL:
        # === NOVÝ CHAT PROTOCOL PATH ===
        self._start_ai_turn_chat()
        return
    
    # ... existing code for other modes ...
```

### **Krok 4: Implementuj _start_ai_turn_chat()**

```python
def _start_ai_turn_chat(self) -> None:
    """AI ťah cez chat protocol (OpenRouter + delta updates)."""
    
    # Initialize OpenRouter client
    if self.openrouter_client is None:
        self.openrouter_client = OpenRouterClient()
    
    # Check if first move
    from scrabgpt.ai.player import is_board_empty
    is_first = is_board_empty(self.board)
    
    # Model selection (TODO: UI picker)
    model_id = "openai/gpt-4o-mini"  # Default
    
    # Create worker
    self._chat_worker = ChatProtocolWorker(
        openrouter_client=self.openrouter_client,
        board=self.board,
        ai_rack=self.ai_rack,
        variant=self.variant_definition,
        model_id=model_id,
        is_first_move=is_first,
    )
    
    # Connect signals
    self._chat_worker.finished.connect(self._on_chat_protocol_move_done)
    self._chat_worker.failed.connect(self._on_chat_protocol_move_failed)
    
    # Start
    log.info("Starting chat protocol AI turn (model=%s, first=%s)", model_id, is_first)
    self._chat_worker.start()


def _on_chat_protocol_move_done(self, move: dict[str, Any]) -> None:
    """Handler pre dokončený chat protocol ťah."""
    
    self._stop_status_spinner()
    
    # Update context session
    from scrabgpt.ai.player import _ensure_context_session
    session = _ensure_context_session(self.variant_definition)
    
    # Pass?
    if move.get("pass"):
        log.info("[AI] chat protocol pass")
        self._register_scoreless_turn("AI")
        session.add_system_message("AI pasoval (nemal legálny ťah).")
        self._check_endgame()
        if not self._game_over:
            self._enable_human_inputs()
        return
    
    # Validate & apply move (existing logic)
    # ... use existing _process_ai_move() ...
    
    # After successful move:
    session.add_ai_move(move, score=total_score, board=self.board)
    
    # Enable human inputs
    self._enable_human_inputs()
    
    log.info("[AI] chat protocol move completed: %s", move.get("word", "?"))


def _on_chat_protocol_move_failed(self, error: Exception) -> None:
    """Handler pre zlyhanie chat protocol ťahu."""
    
    self._stop_status_spinner()
    
    log.error("[AI] chat protocol failed: %s", error)
    QMessageBox.critical(
        self,
        "AI Chyba",
        f"Chat protocol zlyhal: {error}\n\nAI bude pasovať."
    )
    
    # Pass
    self._register_scoreless_turn("AI")
    self._check_endgame()
    if not self._game_over:
        self._enable_human_inputs()
```

### **Krok 5: Update Human Move Handler**

Po úspešnom human ťahu, pridaj do context session:

```python
def _commit_placements(self) -> None:
    # ... existing validation & scoring ...
    
    # After successful move:
    if self.opponent_mode == OpponentMode.CHAT_PROTOCOL:
        from scrabgpt.ai.player import _ensure_context_session
        from scrabgpt.core.types import Placement
        
        session = _ensure_context_session(self.variant_definition)
        
        # Convert placements
        placements_objs = [
            Placement(row=p["row"], col=p["col"], letter=p["letter"])
            for p in validated_move["placements"]
        ]
        
        # Add to context
        session.add_human_move(
            word=validated_move["word"],
            score=total_score,
            placements=placements_objs,
            board=self.board
        )
        
        log.info("Human move added to chat context: %s (%d pts)", 
                 validated_move["word"], total_score)
    
    # ... existing code ...
```

### **Krok 6: Settings Dialog - Pridaj Chat Protocol Option**

V `SettingsDialog`, pridaj radio button:

```python
# Opponent mode group
opponent_group = QButtonGroup(self)
...
chat_radio = QRadioButton("Chat Protocol (OpenRouter)")
opponent_group.addButton(chat_radio)
opponent_layout.addWidget(chat_radio)

if opponent_mode == OpponentMode.CHAT_PROTOCOL:
    chat_radio.setChecked(True)
```

---

## 🧪 Testovací Workflow

### **1. Zapni Chat Protocol Mode**

```python
# V .env alebo settings dialog
DEFAULT_OPPONENT_MODE='chat_protocol'
```

### **2. Nová Hra**

```bash
poetry run python -m scrabgpt.ui.app
```

**Očakávaný flow:**
1. File > Nová hra
2. AI začína → Zavolá `propose_move_chat()` s `is_first_move=True`
3. Logy: "Chat protocol: initialized system prompt for Slovak"
4. Logy: "Chat protocol: calling OpenRouter model=openai/gpt-4o-mini (messages=2)"
5. AI zahá KOT na (7,7) → covers center ✅
6. Rack sa aktualizuje

### **3. Hráč Zahá**

1. Postav slovo na dosku (napr. MAČKA)
2. Klikni "Uložiť"
3. Logy: "Human move added to chat context: MAČKA (18 pts)"
4. AI ťah začne

### **4. AI Druhý Ťah (Delta)**

1. Zavolá `propose_move_chat()` s `is_first_move=False`
2. Logy: "Chat protocol: calling OpenRouter (messages=4, first_move=False)"
3. **Token count:** ~250 namiesto 1200 → **79% úspora** ✅
4. AI zahá word

### **5. Chat Interakcia**

1. Klikni na statusbar
2. Napíš: "Prečo si zahral toto slovo?"
3. AI odpovie (zatiaľ dummy, plná implementácia v Krok 7)

---

## 📊 Metrics Tracking

Pridaj logging pre token tracking:

```python
def _on_chat_protocol_move_done(self, move: dict[str, Any]) -> None:
    # ... existing code ...
    
    # Log token usage
    if hasattr(self, '_chat_worker'):
        # Extract from OpenRouter response
        prompt_tokens = move.get('_prompt_tokens', 0)
        completion_tokens = move.get('_completion_tokens', 0)
        
        log.info(
            "Chat protocol tokens: prompt=%d, completion=%d, total=%d",
            prompt_tokens,
            completion_tokens,
            prompt_tokens + completion_tokens
        )
```

---

## 🎯 Priority Order

1. **Krok 1-2** (OpponentMode + Worker) → 30 min
2. **Krok 3-4** (\_start_ai_turn integrácia) → 1 hodina
3. **Krok 5** (Human move context update) → 15 min
4. **Testovanie** (5 ťahov hry) → 30 min
5. **Krok 6** (Settings UI) → 30 min
6. **Metrics tracking** → 15 min

**Celkový čas:** ~3 hodiny práce

---

## 🚀 Quick Integration (Bez UI)

Ak nechceš hneď settings dialog, môžeš to hard-code:

```python
# app.py - __init__()
self.opponent_mode = OpponentMode.CHAT_PROTOCOL  # Force chat protocol

# _start_ai_turn()
if True:  # Always chat protocol
    self._start_ai_turn_chat()
    return
```

Potom:
```bash
poetry run python -m scrabgpt.ui.app
# → Automaticky použije chat protocol
```

---

## 📖 Ďalšie Kroky Po Integrácii

### **Fáza 3.1: Plný User Chat**

Implementuj `_on_user_chat_message()`:

```python
async def _on_user_chat_message(self, message: str):
    session = _ensure_context_session(self.variant_definition)
    session.add_user_message(message)
    
    # Show loading
    self.chat_dialog._show_loading_animation()
    
    # Call OpenRouter
    messages = session._reasoning_context
    response = await self.openrouter_client.call_model(
        model_id="openai/gpt-4o-mini",
        messages=messages,
        max_tokens=500,
    )
    
    # Display response
    ai_text = response.get('content', 'Ospravedlňujem sa, nemohol som odpovedať.')
    self.chat_dialog.add_ai_message(ai_text, use_typing_effect=True)
```

### **Fáza 3.2: Model Picker**

Pridaj combo box na výber modelu:
- gpt-4o-mini (default, lacný)
- gpt-4o (drahší, lepší)
- claude-3.5-sonnet (Anthropic)
- deepseek-chat (lacný, reasoning)

---

Potrebuješ pomoc s implementáciou niektorého kroku? 🚀
