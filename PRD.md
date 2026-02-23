# ScrabGPT — Product Requirements Document (Living)

Aktualizované: **23. február 2026**

## 1. Produkt v jednej vete

ScrabGPT je desktopová Scrabble aplikácia (PySide6), kde hráč súťaží proti AI režimom
(OpenAI, LMStudio, OpenRouter, Novita, Google/Vertex) s lokálnou validáciou pravidiel,
tool-calling workflow a transparentným profilovaním pokusov modelov.

## 2. Produktové ciele

1. Poskytnúť hrateľný Scrabble zážitok s robustnou lokálnou doménovou logikou.
2. Umožniť porovnávanie viacerých modelov paralelne, nie len „single call“ AI.
3. Zachovať auditovateľnosť AI rozhodnutí (tool calls, judge, pokusy, chybové stavy).
4. Udržať jednotné limity výkonu a ceny naprieč providermi.
5. Zachovať použiteľnosť pre vývojárov (testy, typovanie, logovanie, perzistencia konfigurácie).
6. Dlhodobý cieľ: vybudovať AI protihráča, ktorý je prakticky neporaziteľný pre človeka.

### 2.1 North Star kvality AI

- AI musí dlhodobo zlepšovať hernú silu cez prompt engineering, lepší candidate search
  a robustnejšie rozhodovanie cez nástroje.
- Každá zmena promptu/orchestrácie musí byť overiteľná benchmarkmi a nesmie znižovať
  legalitu ťahov.
- Projekt cieli na superhuman úroveň hry, nie len na „funkčný AI move generator“.

## 3. Primárni používatelia

- Hráč, ktorý chce hrať Scrabble proti AI.
- Prompt/LLM experimentátor porovnávajúci kvalitu modelov.
- Vývojár, ktorý potrebuje rozširovať providery, nástroje a varianty bez rozbitia jadra hry.

## 4. Scope (aktuálny stav)

### 4.1 Implementované

- Hracie jadro:
  - doska 15×15, prémiové políčka, bodovanie, legalita ťahov, tile bag, save/load.
- Opponent režimy (`OpponentMode`):
  - `BEST_MODEL` (OpenAI model competition)
  - `LMSTUDIO`
  - `OPENROUTER`
  - `NOVITA`
  - `GEMINI` (Google Vertex)
- Multi-model orchestration:
  - paralelné volania, priebežné statusy, retries, judge validácia, výber najlepšieho ťahu.
- Tool-calling architektúra:
  - interné Scrabble tools (`mcp_tools.py`)
  - OpenAI tool adapter + Gemini/Vertex adapter
  - workflow enforcement cez env prepínače.
- Konfiguračná perzistencia:
  - `~/.scrabgpt/config.json`
  - `~/.scrabgpt/teams/`
- Varianty:
  - `variant_store.py` + JSON variant súbory
  - Wikipedia bootstrap pipeline (`variant_agent.py`, `wiki_loader.py`)
- UI observabilita:
  - `AgentsDialog`, `AgentStatusWidget`, `ChatDialog`, `AIModelResultsTable`
  - detailný profiling sekcií (tool calls, validácia slov, judge, finalizácia)

### 4.2 Čiastočne implementované / experimentálne

- Chat s AI protihráčom:
  - UI existuje (`ChatDialog`), ale handler v `MainWindow._on_user_chat_message()` je placeholder.
- Agent profiles cez `.agent` konfigurácie:
  - `agent_config.py` je funkčný, ale `agent_player.py` je stále stub (`NotImplementedError`).

### 4.3 Out of scope (aktuálne)

- Multiplayer (human vs human online).
- Ranking/ladder backend.
- Telemetria do externých služieb.
- Mobile natívny klient.

## 5. Funkčné požiadavky

### FR-01 Herné pravidlá a bodovanie

- Aplikácia musí lokálne validovať legalitu ťahu.
- Aplikácia musí spočítať body vrátane prémií a krížových slov.
- Stav hry musí byť uložitelný/obnoviteľný zo JSON.

Stav: **Done**

### FR-02 AI ťah cez provider režimy

- Režim protivníka musí byť prepínateľný v nastaveniach.
- Každý režim musí vedieť navrhnúť ťah vo validovateľnom formáte.
- V multi-model režimoch sa musí vybrať najlepší legálny výsledok.

Stav: **Done**

### FR-03 Tool-calling workflow

- Modely majú používať lokálne nástroje na legalitu, scoring a slovníky.
- Pri enforce režime sa vyžaduje minimálny počet validácií/candidate scoringu.
- Výstup musí byť striktne JSON move payload alebo fallback (exchange/pass).

Stav: **Done**

### FR-04 Transparentnosť rozhodovania

- Používateľ musí vidieť priebeh pokusov modelov, statusy a chyby.
- Každý model musí mať vlastný profil aktivity počas ťahu.
- Pri parse fallbackoch sa musí zachovať raw odpoveď + analýza.

Stav: **Done**

### FR-05 Perzistencia konfigurácie

- Musí sa ukladať posledný režim protivníka.
- Musia sa ukladať provider model selections + timeout.
- Po reštarte sa musí stav načítať bez resetu na default.

Stav: **Done**

### FR-06 Variant bootstrap

- Aplikácia musí vedieť načítať/cachovať Wikipedia zdroj.
- Musí vedieť získať jazykové fragmenty a uložiť sumarizácie.

Stav: **Done**

### FR-07 User chat s AI mimo herného protokolu

- Používateľská správa má ísť do AI kontextu a vrátiť AI reply.

Stav: **Planned / Partial UI only**

### FR-08 Agent profile (.agent) gameplay mode

- Agent nakonfigurovaný cez `.agent` má vedieť kompletne odohrať ťah cez tool loop.

Stav: **Planned / Stub implementation**

## 6. Nefunkčné požiadavky

### NFR-01 Kvalita kódu

- Type hints a strict mypy (`tool.mypy.strict = true`).
- Ruff linting.
- Modulárne oddelenie core vs provider vs UI.

### NFR-02 Výkon a rozpočet

- Jednotný budget pre všetky AI move cally:
  - `AI_MOVE_MAX_OUTPUT_TOKENS`
  - `AI_MOVE_TIMEOUT_SECONDS`
- Budget musí byť clampovaný pred API volaním.

### NFR-03 Robustnosť pri chybách providerov

- Graceful error statusy (timeout/error/parse_error/invalid).
- Žiadny crash hlavného UI pri zlyhaní jedného modelu.
- Retry/fallback cesta pri parse problémoch.

### NFR-04 Thread safety (Qt)

- Dlhé operácie musia bežať mimo UI thread.
- UI update len cez Qt signal/slot.

## 7. Architektúra (aktuálna)

Detailné runtime flow diagramy sú v `ARCHITECTURE.md`.

### 7.1 Core (`scrabgpt/core/`)

- `board.py`, `rules.py`, `scoring.py`, `tiles.py`, `rack.py`, `state.py`, `game.py`
- `variant_store.py` (variant persistence + active variant)
- `team_config.py` (provider selections, teams, opponent mode persistence)

### 7.2 AI (`scrabgpt/ai/`)

- Klienti: `client.py`, `openai_tools_client.py`, `openrouter.py`, `novita.py`, `vertex.py`
- Orchestrácia: `multi_model.py`, `novita_multi_model.py`
- Tools: `mcp_tools.py`, `tool_adapter.py`, `mcp_adapter.py`, `tool_schemas.py`
- Variant/agents: `variant_agent.py`, `wiki_loader.py`, `language_agent.py`
- Experimental: `agent_player.py` (stub), `model_selector_agent.py`, `model_auto_updater.py`

### 7.3 UI (`scrabgpt/ui/`)

- Hlavné okno + game loop: `app.py`
- Nastavenia: `settings_dialog.py` (+ selector/config dialogs)
- Profiling: `agents_dialog.py`, `agent_status_widget.py`, `model_results.py`, `response_detail.py`
- Chat/protocol vizualizácia: `chat_dialog.py`

Poznámka: `app.py` je stále veľký monolit a obsahuje aj legacy interné widget triedy.

## 8. Dáta a perzistencia

- Config: `~/.scrabgpt/config.json`
- Team/provider files: `~/.scrabgpt/teams/*.json`
- Variant assets: `scrabgpt/assets/variants/*.json`
- Wikipedia cache: `scrabgpt/assets/variants/wikipedia_scrabble_cache.html`
- Generované sumarizácie: `scrabgpt/assets/variants/lang_summarizations/`

## 9. Test stratégia

- Doménové testy: pravidlá, scoring, tiles, save/load, variant store.
- Integračné testy: multi-model, tool klient, variant/bootstrap, benchmark testy.
- Marker stratégia: `network/openai/google/openrouter/internet/stress/ui`.
- `tests/conftest.py` automaticky označuje API/network testy markerom `internet`.

## 10. KPI / úspech

1. Multi-model ťah sa vyhodnotí bez UI freeze.
2. Zlyhanie jednotlivého modelu nespôsobí pád celého kola.
3. Persistované nastavenia sa obnovia po reštarte.
4. V benchmark scenároch je vysoká miera legálnych skórujúcich ťahov.
5. Dlhodobý trend benchmarkov a self-play musí ukazovať rast hernej sily AI.

## 11. Známé riziká a dlh

1. `agent_player.py` ešte nie je produkčne zapojený.
2. Chat handler v `app.py` je placeholder.
3. `model_fetcher.py` má statické pricing tabuľky (nie live API).
4. `app.py` potrebuje ďalšiu dekompozíciu na menšie UI moduly.

## 12. Najbližší roadmap backlog

1. Dokončiť plnohodnotný chat loop do AI kontext session.
2. Doviesť `.agent` gameplay mód z „stub“ do produkčnej path.
3. Rozdeliť `MainWindow` workflow do menších servisných/UI tried.
4. Pridať smoke/integration test matrix pre všetky režimy protivníka.
5. Zaviesť prompt-engineering pipeline (A/B prompt verzie + leaderboard výsledkov).
6. Doplniť self-play eval režim pre meranie rastu hernej sily medzi verziami.
