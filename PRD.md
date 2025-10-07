# ScrabGPT — Product Requirements Document (PRD)

**Projekt:** ScrabGPT  
**Cieľ:** Cross‑platform Python desktop aplikácia, v ktorej človek odohrá Scrabble partiu
proti AI tímom z OpenRoutera aj Novity. MVP demonštruje kvalitnú architektúru, TDD v doméne
bodovania, minimalistickú integráciu OpenAI (structured completions) a čistý UI/UX.

---

## 1) Kontext & ciele
- **Prečo:** Ukázať pokročilé Python zručnosti, schopnosť navrhnúť modulárnu architektúru, a porozumenie OpenAI API (structured JSON outputs).  
- **Hlavný výsledok (MVP):**  
  - Spustiteľná desktop app (Windows/macOS/Linux) s hernou doskou 15×15, so skórovaním a prémiovými políčkami (DL, TL, DW, TW).  
  - Hra **1v1**: hráč (človek) vs. **AI hráč (GPT‑5‑mini)**.  
  - **Rozhodca (GPT‑5‑mini)** overuje **platnosť anglických slov**.  
  - **TDD** testuje doménové pravidlá výpočtu skóre (vrátane prémií a krížových slov).  
  - **Deterministická náhoda** (seed) pre ťahanie kameňov, aby boli testy opakovateľné.
  - **Ukladanie/obnova hry (Save/Load)** do JSON s `schema_version`.
- **Rozšírené ciele (Q1 2025):**  
  - Multi-model konkurencia pre OpenRouter aj Novita s paralelnym volaním a výsledkovou
    tabuľkou.
  - Persistované tímové konfigurácie a uložený režim protivníka cez `TeamManager`.
  - Variant bootstrap agent generujúci jazykové podklady z Wikipédie.
  - UI bez blokujúcich alertov, logovanie stavov a detailná dokumentácia v `docs/`.

### 1.1 Demo scénar (akceptačný)
1. Spustím aplikáciu, zvolím **Nová hra**.  
2. Zobrazí sa prázdna doska, moje **7 písmen** (rack) a stav ťahu (človek/AI).  
3. **Ja** položím platné slovo cez stred (H8) a dám **„Potvrdiť ťah“**.  
4. Aplikácia:  
   - lokálne spočíta skóre (s prémiami),
   - zavolá **Rozhodcu** na **validáciu jedného nového hlavného slova** (cross‑words v MVP nevalidujeme samostatne – viď 3.3),
   - ak validné → aplikuje ťah (odoberie kocky z racku, doplní do 7, aktualizuje skóre a históriu ťahov).  
5. **AI ťah**: aplikácia odošle stav vybranému protivníckemu režimu (OpenRouter multi-model
   alebo Novita) a **AI** vráti **štruktúrovaný JSON s ťahom** (pozície, smer, slovo).
   Aplikácia ťah **overí a spočíta** a zobrazí.  
6. Striedame sa, až kým nedôjde na **MVP koniec** (keď jeden hráč klikne **„Ukončiť“** alebo
   **prázdny zásobník** a obaja pasujú 2×).  

---

## 2) Funkčné požiadavky
1. **Doska 15×15** s presnou mapou prémií:
   - **TW**: 8 polí (rohy a stredy okrajov),
   - **DW**: 17 polí (diagonály + stred H8),
   - **TL**: 12 polí,
   - **DL**: 24 polí.  
   Mapa bude uložená v `assets/premiums.json` a overená testami (počet + spot‑check súradníc).  
2. **Kameňová taška (tile bag)** – oficiálna EN distribúcia:  
   - A×9(1), B×2(3), C×2(3), D×4(2), E×12(1), F×2(4), G×3(2), H×2(4), I×9(1), J×1(8), K×1(5), L×4(1), M×2(3), N×6(1), O×8(1), P×2(3), Q×1(10), R×6(1), S×4(1), T×6(1), U×4(1), V×2(4), W×2(4), X×1(8), Y×2(4), Z×1(10), **Blank×2(0)**.  
   - **Deterministické ťahanie**: `RNG(seed)` pre testy a „Repro“ režim.  
3. **Umiestňovanie písmen**: drag‑and‑drop z racku na dosku; smer **ACROSS/DOWN** sa určuje podľa prvej dvojice; prichytenie na mriežku; návrat do racku.  
4. **Validácia ťahu (lokálna):**
   - Slovo je v jednej rovine, bez dier, nadväzuje na existujúce písmená (po prvom ťahu),
   - **prvý ťah** prechádza **H8** (DW),
   - **skóre** sa spočíta lokálne (aj všetky nové krížové slová),
   - **Online mód:** Rozhodca validuje **iba hlavné slovo**; krížové slová **neposielame** na validáciu (zníženie latencie/ceny).  
5. **AI ťah (GPT‑5‑mini):** Aplikácia pošle **stav** (doska + vlastný rack AI + história) a dostane **štruktúrovaný JSON** s návrhom ťahu.  
6. **Rozhodca (GPT‑5‑mini):** Endpoint na **validáciu hlavného slova** → true/false + stručný dôvod.  
7. **Skóre & história:** pravý panel so skóre hráča/AI, posledný ťah, tlačidlo **„Undo (1× späť)“** len pre ľudský ťah pred potvrdením.  
8. **Nastavenia:** seed (voliteľne), prepínač „**Low‑latency judge**“ (skip validačného hovoru pri slove ≥2 a ≤15 s ASCII písmenami → **len lokálne pravidlá**; experimentálny režim pre demo).
9. **Multi-provider AI:** nastavenia musia podporovať OpenRouter aj Novita, výber až 10 modelov,
   paralelné volanie, výsledkovú tabuľku a detailný log stavu.
10. **Reasoning field podpora:** parser musí zvládnuť `content`, `reasoning_content` aj fallback
    rozbor cez GPT, vrátane ukladania kompletných odpovedí.
11. **Persistované tímy:** konfigurácie modelov a timeoutov sa ukladajú do
    `~/.scrabgpt/teams/<provider>_team.json` a nahrávajú sa pri štarte.
12. **Persistovaný režim protivníka:** posledný zvolený `OpponentMode` sa uloží do
    `~/.scrabgpt/config.json` a aplikuje pri spustení hry.
13. **Variant bootstrap pipeline:** automatizovaný agent generuje jazykové súhrny zo
    `wikipedia_scrabble_cache.html` a ukladá ich do `assets/variants/lang_summarizations/`.

---

## 3) Nefunkčné požiadavky
- **Cross‑platform:** Python 3.10+, **PySide6** UI; balenie neskôr (PyInstaller), mimo MVP.  
- **Kvalita:** ruff, mypy (strict), pytest; **UI testy na CI skip**.  
- **Testovanie:**
  - **Doménové testy** (core/): offline, bez mocks, deterministické
  - **Integračné testy** (ai/, ui/): môžu volať real API (označené markermi)
  - **Pytest markers:**
    - `@pytest.mark.internet` - testy vyžadujúce internet (httpx, API calls)
    - `@pytest.mark.openai` - testy volajúce OpenAI API
    - `@pytest.mark.openrouter` - testy volajúce OpenRouter API  
    - `@pytest.mark.stress` - stress testy / IQ testy pre AI validáciu
    - `@pytest.mark.ui` - testy vyžadujúce Qt UI
  - **CI/CD:** GitHub workflow skipuje testy s markermi `internet`, `openai`, `openrouter`, `ui`
  - **Lokálny vývoj:** všetky testy sa spúšťajú s real API calls (ak sú nastavené API keys v `.env`)
  - **Conftest:** `tests/conftest.py` načíta `.env` pre API keys
- **Bezpečnosť:** `.env` s `OPENAI_API_KEY`, `OPENROUTER_API_KEY`; nikdy necommitovať do gitu.  
- **Konfigurácia poskytovateľov:** `.env` dopĺňa `NOVITA_API_KEY`, `NOVITA_MAX_TOKENS`,
  `NOVITA_TIMEOUT_SECONDS`; hodnoty majú defaulty a sú validované v UI.  
- **Perzistencia konfigurácií:**
  - globálny súbor `~/.scrabgpt/config.json` drží `opponent_mode`,
  - priečinok `~/.scrabgpt/teams/` obsahuje JSON pre každý provider,
  - cache HTML (`wikipedia_scrabble_cache.html`) žije v `assets/variants/`.  
- **Telemetria:** žiadna.  

---

## 4) Architektúra (moduly)
```
scrabgpt/
  core/                  # čistá doména (bez UI, bez siete)
    board.py             # model dosky, súradnice, prémiá, aplikácia ťahu
    rack.py              # model hráčovho stojanu (rack)
    tiles.py             # distribúcia, RNG, taška
    scoring.py           # výpočet skóre
    rules.py             # lokálne pravidlá ťahu
    types.py             # datatypy (Direction, Placement, Move…)
    team_config.py       # persistované tímy + opponent mode
  ai/
    client.py            # tenký klient pre OpenAI
    judge.py             # validácia hlavného slova
    player.py            # AI hráč (JSON schema návrhu ťahu)
    openrouter.py        # OpenRouter API klient (multi-model)
    multi_model.py       # OpenRouter orchestrácia + GPT fallback
    novita.py            # Novita API klient (OpenAI kompatibilný)
    novita_multi_model.py# Novita orchestrácia
    language_agent.py    # Async agent na získavanie jazykov
    variant_agent.py     # Bootstrap jazykových sumarizácií
    wiki_loader.py       # Wikipedia fetch + parsing
    schema.py            # Pydantic modely pre AI odpovede
  ui/
    app.py               # PySide6 hlavné okno
    board_view.py        # 2D mriežka, DnD, prémiá
    rack_view.py         # DnD kocky
    ai_config.py         # OpenRouter multi-model dialóg
    novita_config_dialog.py # Novita model browser
    model_results.py     # Tabuľka výsledkov multi-model súťaže
    response_detail.py   # Detail odpovedí modelov
    opponent_mode_selector.py # Prepínač poskytovateľov
    team_details_dialog.py    # Prehľad tímov a perzistencie
    settings_dialog.py   # Unifikovaný nastavovací dialóg
    agents_dialog.py     # Aktivita agentov (non-blocking)
    agent_status_widget.py # Toolbar widget s animáciou
  assets/
    premiums.json        # mapa prémií 15×15
    variants/
      wikipedia_scrabble_cache.html   # cached HTML
      lang_summarizations/            # generované súhrny (gitignored)
  docs/
    NOVITA_INTEGRATION.md
    NOVITA_QUICKSTART.md
    PERSISTENCE_FIX.md
    TEAMS_FEATURE.md
  tests/
    test_scoring.py
    test_rules.py
    test_premiums.py
    test_tiles.py
    test_variant_agent.py
    test_agent_player.py
    test_opponent_mode_selector.py
```
**Zásada:** `core/` nemá závislosť na `ai/` ani `ui/`. Všetky OpenAI hovory sa dajú **mockovať**.

---

## 5) UX / UI
- **Estetika:** moderné ploché UI (PySide6), jemné tiene, kontrastné farby prémií (TW=červená, DW=ružová, TL=tmavomodrá, DL=svetlomodrá), center **H8** so „★“.
- **Interakcie:**
  - DnD kameňov, snapping, zrušenie ťahu, zvýraznenie vzniknutého slova a jeho skóre „ghost preview“.  
  - Toolbar: **Nová hra**, **Potvrdiť ťah**, **Pasovať**, **Nastavenia**.  
  - Status‑bar: kto je na ťahu, posledný ťah + skóre.  

## 5.5) Agent System – Async Background Execution

ScrabGPT implementuje async agent system pre dlhé operácie (API calls, background tasks) s non-blocking UI.

### Architektúra
- **AsyncAgentWorker (QThread)**: Spúšťa async funkcie vo vlastnom event loop, emituje signály pre progress updates
- **AgentsDialog (non-modal)**: Zobrazuje real-time aktivitu agentov, možno zavrieť kedykoľvek – agenti pokračujú na pozadí
- **AgentStatusWidget**: OpenAI-style animácia v toolbar-e (fading text, animated dots)
- **Global dispatcher**: MainWindow vlastní `agent_workers` dict – workeri prežijú zatvorenie dialógov

### Thread Safety Pattern
❌ **WRONG**: Direct UI update z worker thread → UI freeze  
✅ **CORRECT**: Worker emituje signal → Qt ho doručí do main thread → slot updatne UI safely

```python
# Worker thread (background)
worker.progress_update.emit(update)  # Thread-safe signal

# Main thread (UI)  
def on_progress(update):
    widget.set_status(update.status)  # Safe!
worker.progress_update.connect(on_progress)
```

### Components

#### Language Agent (Example)
- Async/await pattern s `asyncio.to_thread()` pre blocking operations
- Progress callbacks: "Kontrolujem cache...", "Volám OpenAI API...", "Spracovávam odpoveď..."
- 1-hour caching pre efektívnosť
- Full implementation: `scrabgpt/ai/language_agent.py`

#### Variant Bootstrap Agent
- Načítava a cache-uje Wikipedia HTML cez `wiki_loader.py`.
- Parsuje jazykové sekcie, generuje sumarizácie a ukladá ich do assets.
- Streamuje postup cez `VariantBootstrapProgress` (HTML snippet, stav, percento).
- Implementácia: `scrabgpt/ai/variant_agent.py`, testy v `tests/test_variant_agent.py`.

#### Settings Dialog (Unified)
4 taby v zelenej téme:
1. **Všeobecné**: Variant, Jazyky (tlačidlo "Aktualizovať"), Repro mód, Auto-show agents checkbox
2. **AI Protivník**: Opponent mode (budúcnosť)
3. **Nastavenia API**: OpenAI/OpenRouter keys, max tokens
4. **Upraviť prompt**: Embedded prompt editor

**Clickable status bar**: Klik v settings otvára Agents dialog (aj keď settings modal).

### Environment Variables
```bash
SHOW_AGENT_ACTIVITY_AUTO='true'  # Auto-show agents dialog when agent starts
OPENROUTER_MAX_TOKENS='8000'     # Max tokens per OpenRouter move
```

### Key Benefits
- ✅ UI nikdy nezmrzne (thread-safe signály)
- ✅ Dialógy možno zavrieť kedykoľvek
- ✅ Agenti pokračujú na pozadí
- ✅ Real-time progress tracking
- ✅ OpenAI-style animácie


---

## 6) OpenAI integrácia (minimalistická, structured completions)
### 6.1 Modely
- **`gpt-5-mini`** použitý pre **AI hráča** aj **Rozhodcu** (single-model režim).
- **OpenRouter API** pre multi-model režim – top týždenné modely (GPT-4, Claude, Gemini, DeepSeek, atď.).
- **GPT-5-mini** použitý aj pre GPT fallback parser (extrakcia ťahov z non-JSON responses).

### 6.2 Kontrakty (JSON Schema – log výstupu)
**A) Rozhodca – `judge_word`**  
**Vstup (prompt context):** hlavné slovo (UPPERCASE A‑Z), krátky opis kontextu (jazyk: EN), „You are a strict Scrabble referee. Answer JSON only.“  
**Výstup (JSON):**
```json
{
  "valid": true,
  "reason": "standard English word in general dictionaries"
}
```

**B) AI hráč – `propose_move`**  
**Vstup (prompt context):** serializovaný stav (doska 15×15 s písmenami/blank symbolmi, rack AI, zostatok tašky – voliteľné, skóre, kto je na ťahu), „Play to win. Return JSON only.“  
**Výstup (JSON):**
```json
{
  "placements": [ {"row": 8, "col": 8, "letter": "C"}, {"row": 8, "col": 9, "letter": "A"}, {"row": 8, "col": 10, "letter": "T"} ],
  "direction": "ACROSS",
  "word": "CAT",
  "exchange": [],
  "pass": false
}
```
> **Pozn.:** Výstup je **bez reťazenia myšlienok**; model odovzdá iba dáta.

### 6.3 Klient (pseudokontrakt)
- Metódy: `call_judge(word: str) -> JudgeResult`, `call_ai(state: GameState) -> MoveProposal`.  
- JSON/„function‑calling“ režim (strict), timeout/reties, jednoduchý rate‑limit.  
- **Žiadne** volania z testov – v testoch sa **mockuje**.

### 6.4 Multi-Model Klient (OpenRouter)
- `fetch_models()` – Načíta dostupné modely z OpenRouter API (top týždenné).
- `call_model_async(model_id, prompt)` – Asynchrónne volanie jedného modelu.
- `propose_move_multi_model(models, state)` – Volá všetky modely súčasne, validuje paralelne, vráti najlepší ťah + všetky výsledky.
- Podpora pre `reasoning` field (GLM-4.6 a podobné modely).
- Graceful error handling pre empty/invalid responses.


---

## 7) Pravidlá bodovania (lokálne)
- **Základ:** súčet bodov písmen (blank = 0).  
- **DL/TL:** aplikujú sa **len** na novo položené písmená.  
- **DW/TW:** násobí sa **celé slovo**; viac násobičov sa kumuluje (napr. DW×TW = ×6).  
- **Krížové slová:** Každé novo vytvorené krížové slovo sa spočíta rovnako (s DL/TL len na nových písmenách).  
- **Bingo (7 kameňov):** +50 (ak položené v jednom ťahu).  

---

## 8) TDD plán testov
### 8.1 Prémiové polia
- Over počty: TW=8, DW=17, TL=12, DL=24.  
- Spot‑check: `A1, A8, A15, H1, H15, O1, O8, O15 = TW`; `H8 = DW`; `B2,C3,D4,E5,K11,L12,M13,N14 = DW`; `B14,C13,D12,E11,K5,L4,M3,N2 = DW`.  

### 8.2 Skórovanie (unit tests)
- **Bez prémii:** `CAT` (C=3,A=1,T=1) → 5.  
- **DL:** `CAT` s `A` na DL → 6.  
- **TL:** `CAT` s `C` na TL → 8.  
- **DW:** `CAT` cez H8 → 10.  
- **TW:** `CAT` s T na TW → 15.  
- **Kombinácie:** `AXE` kde `X` na TL a celé na DW → (1 + 8*3 + 1)×2 = 60.  
- **Krížové slová:** položené `TO`, vznikne kríž `AT` cez DL pod `A` → obidve slová sa spočítajú.  
- **Bingo:** ľubovoľné validné 7‑písmenové nové slovo → +50.  
- **Regres:** prémie sa neuplatnia 2× pri prechode cez to isté pole v ďalších ťahoch.

### 8.3 Pravidlá ťahu
- **Prvý ťah** musí prejsť H8.  
- **Spojitosť:** po prvom ťahu každé nové slovo sa dotýka existujúcich písmen.  
- **Jedna línia:** bez dier.  

---

## 9) Dátové modely (skratka)
```python
Placement = {"row": int, "col": int, "letter": "A"|...|"Z"|"?"}
Move = {"placements": [Placement], "direction": "ACROSS"|"DOWN"}
WordScore = {"word": str, "base": int, "letter_bonus": int, "word_multiplier": int, "total": int}
GameState = {"board": [[" ",...]], "rack_human": str, "rack_ai": str, "scores": {"human": int, "ai": int}}
```

---

## 10) Riziká & mitigácie
- **Latencia API:** minimalizujeme payload (kompaktý stav), používanie rozhodcu len na hlavné slovo; dočasný „Low‑latency“ prepínač.  
- **Halucinácie AI ťahu:** prísny JSON schema + validácia ťahu v `core.rules`.  
- **Reprodukovateľnosť:** seedované ťahanie + „Repro“ mód.  
- **UX robustnosť:** Undo pred potvrdením; zreteľný highlight nových písmen a skóre.  

---

## 11) Akceptačné kritériá MVP (DoD)
- `pytest -q` prejde: `test_scoring.py`, `test_premiums.py`, `test_rules.py`, `test_tiles.py`.  
- Manuálne demo podľa **1.1**: odohrám min. 3 ťahy človek/AI; skóre na UI sedí s logom v konzole.  
- OpenAI volania sú izolované v `ai/` a konfigurované cez `.env`; testy **bez siete**.

**Multi-model akceptačné kritériá (Splnené):**
- Konfiguračný dialóg načíta modely z OpenRouter a zobrazí ich s cenami.
- Používateľ môže vybrať 1-10 modelov, nastaviť max_tokens pre každý.
- Real-time odhad maximálnej ceny za ťah sa zobrazuje správne.
- Pri AI ťahu sa zavolajú všetky vybrané modely súčasne.
- Tabuľka výsledkov zobrazí všetky modely s ranking, skóre, validáciou.
- Víťazný model (najvyšší score + validný) sa aplikuje na dosku.
- Paralelná validácia prebehne v <5s pre 5+ modelov.
- GPT fallback parser extrahuje ťahy z non-JSON responses.
- Response detail dialóg zobrazí raw odpoveď + GPT analýzu pri kliku.
- UI zostane responzívne počas multi-model operácií.
- Všetky error stavy (empty response, parse error, API error) sú správne zobrazené.

---

## 12) Multi‑Model AI Support (Implementované)

ScrabGPT teraz podporuje **súčasné volanie viacerých AI modelov** cez OpenRouter API s automatickým výberom najlepšieho ťahu.

### 12.1 Funkčnosť
- **OpenRouter integrácia**: Volanie top týždenných modelov z OpenRouter.ai
- **Konkurencia modelov**: Až 10 modelov súčasne navrhuje ťahy
- **Automatický výber**: Najvyšší skóre + platný ťah od Rozhodcu = víťaz
- **Konfiguračný dialóg**: Vizuálny výber modelov, nastavenie max_tokens, real‑time odhad ceny
- **Tabuľka výsledkov**: Zobrazenie všetkých návrhov s rankingom (🥇🥈🥉), skóre, validáciou
- **Sledovanie modelov**: Status bar zobrazuje ktorý model navrhol ktorý ťah

### 12.2 GPT Fallback Parser
- **Automatická extrakcia**: Keď model vráti text+JSON alebo len text, GPT‑5‑mini analyzuje a extrahuje ťah
- **Response Detail Dialog**: Klik na riadok → zobrazí raw odpoveď + GPT analýzu
- **Transparentnosť**: Používateľ vidí presne čo model odpovedal a ako to GPT interpretoval

### 12.3 Error Handling & Performance
- **Paralelná validácia**: Všetky modely sa validujú súčasne (3‑5× rýchlejšie)
- **Žiadne zamrznutie**: UI zostáva responzívne aj s 10 modelmi
- **Graceful errors**: Prázdne odpovede, parse errors, API errors sa zobrazia user‑friendly
- **Reasoning field support**: Modely ako GLM‑4.6 ktoré vracajú content v `reasoning` poli
- **GPT‑5 podpora**: Správne parametre pre GPT‑5 modely (`max_completion_tokens`)

### 12.4 UI/UX
- **Dark mode**: Všetky nové komponenty v tmavej téme
- **Kompaktný layout**: Efektívne využitie priestoru, väčšie písmo (12‑13px)
- **Cost visibility**: Výrazné zobrazenie max. ceny za ťah
- **Model tracking**: `[Model Name]` prefix v status bare
- **Clear on retry**: Tabuľka sa vyčistí pri retry, žiadne staré dáta

### 12.5 Technické detaily
**Nové súbory:**
- `scrabgpt/ai/openrouter.py` – OpenRouter klient
- `scrabgpt/ai/multi_model.py` – Multi‑model orchestrácia, GPT fallback parser
- `scrabgpt/ui/ai_config.py` – Konfiguračný dialóg
- `scrabgpt/ui/model_results.py` – Tabuľka výsledkov
- `scrabgpt/ui/response_detail.py` – Detail dialóg pre odpovede

**Kľúčové funkcie:**
- `propose_move_multi_model()` – Volá modely asynchrónne, validuje paralelne
- `_analyze_response_with_gpt()` – GPT fallback pre non‑JSON odpovede
- `judge_words()` – Paralelná validácia všetkých modelov
- `get_top_models()` – Načíta top týždenné modely z OpenRouter

**Dátové štruktúry:**
```python
MultiModelResult = {
    "model": str,              # Model ID
    "model_name": str,         # Display name
    "status": "ok"|"invalid"|"error"|"parse_error",
    "move": Move | None,
    "score": int,
    "words": list[str],
    "judge_valid": bool,
    "judge_reason": str,
    "error": str | None,
    "raw_response": str,       # Pre response detail
    "gpt_analysis": str | None # GPT fallback analýza
}
```

---

## 13) Post‑MVP (len poznámky)
- Overovanie **všetkých** krížových slov u Rozhodcu (batched).  
- Vyhľadávanie najlepšieho ťahu lokálne (rack solver) + AI ako komentátor.  
- Export PNG skóre tabuľky, PyInstaller balíčky.
- Model performance tracking a štatistiky (success rate, avg score)
- Model filtering (skryť/zobraziť nespoľahlivé modely)
- Batch GPT analysis (analyzovať všetky failed responses v jednom calle)

---

## 13) Pseudoprompt – Rozhodca (anglicky)
```
System: You are a strict Scrabble referee for EN words. Reply with JSON only.
User: Is this a valid English word for Scrabble play? Return {"valid": boolean, "reason": string}.
Word: "{WORD}"
Constraints: No explanations beyond the JSON.
```

## 14) Pseudoprompt – AI hráč (anglicky)
```
System: You are an expert Scrabble player. Play to win. Reply with JSON only.
User: Given the board (15x15), your rack, and whose turn it is, propose exactly one move.
Return schema: {"placements":[{"row":int,"col":int,"letter":A..Z|?}], "direction":"ACROSS"|"DOWN", "word":string, "exchange":string[], "pass":boolean}
Board: <compact representation>
Your rack: <letters>
```

*Pozn.: Mapa prémií bude zapracovaná z referencie; v testoch sa overí počet a niekoľko kanonických súradníc (A1/H8/O15 …).*
