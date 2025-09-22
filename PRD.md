# ScrabGPT — Product Requirements Document (PRD)

**Projekt:** ScrabGPT  
**Cieľ:** Cross‑platform Python desktop aplikácia, v ktorej človek odohrá Scrabble partiu proti AI (GPT‑5‑mini). MVP demonštruje kvalitnú architektúru, TDD v doméne bodovania, minimalistickú integráciu OpenAI (structured completions) a čistý UI/UX.

---

## 1) Kontext & ciele
- **Prečo:** Ukázať pokročilé Python zručnosti, schopnosť navrhnúť modulárnu architektúru, a porozumenie OpenAI API (structured JSON outputs).  
- **Hlavný výsledok (MVP):**  
  - Spustiteľná desktop app (Windows/macOS/Linux) s hernou doskou 15×15, so skórovaním a prémiovými políčkami (DL, TL, DW, TW).  
  - Hra **1v1**: hráč (človek) vs. **AI hráč (GPT‑5‑mini)**.  
  - **Rozhodca (GPT‑5‑mini)** overuje **platnosť anglických slov**; dostupný je voliteľný **Offline judge (ENABLE)** (default OFF).  
  - **TDD** testuje doménové pravidlá výpočtu skóre (vrátane prémií a krížových slov).  
  - **Deterministická náhoda** (seed) pre ťahanie kameňov, aby boli testy opakovateľné.
  - **Ukladanie/obnova hry (Save/Load)** do JSON s `schema_version`.

### 1.1 Demo scénar (akceptačný)
1. Spustím aplikáciu, zvolím **Nová hra**.  
2. Zobrazí sa prázdna doska, moje **7 písmen** (rack) a stav ťahu (človek/AI).  
3. **Ja** položím platné slovo cez stred (H8) a dám **„Potvrdiť ťah“**.  
4. Aplikácia:  
   - lokálne spočíta skóre (s prémiami),
   - zavolá **Rozhodcu** na **validáciu jedného nového hlavného slova** (cross‑words v MVP nevalidujeme samostatne – viď 3.3),
   - ak validné → aplikuje ťah (odoberie kocky z racku, doplní do 7, aktualizuje skóre a históriu ťahov).  
5. **AI ťah**: aplikácia odošle AI hráčovi (GPT‑5‑mini) **aktualizovaný stav** a **AI** vráti **štruktúrovaný JSON s ťahom** (pozície, smer, slovo). Aplikácia ťah **overí a spočíta** a zobrazí.  
6. Striedame sa, až kým nedôjde na **MVP koniec** (keď jeden hráč klikne **„Ukončiť“** alebo **prázdny zásobník** a obaja pasujú 2×).  

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
   - **Offline mód (ENABLE):** všetky nové slová (**hlavné + krížové**) sa overujú **offline** (bez OpenAI).  
5. **AI ťah (GPT‑5‑mini):** Aplikácia pošle **stav** (doska + vlastný rack AI + história) a dostane **štruktúrovaný JSON** s návrhom ťahu.  
6. **Rozhodca (GPT‑5‑mini):** Endpoint na **validáciu hlavného slova** → true/false + stručný dôvod.  
7. **Skóre & história:** pravý panel so skóre hráča/AI, posledný ťah, tlačidlo **„Undo (1× späť)“** len pre ľudský ťah pred potvrdením.  
8. **Nastavenia:** seed (voliteľne), prepínač „**Low‑latency judge**“ (skip validačného hovoru pri slove ≥2 a ≤15 s ASCII písmenami → **len lokálne pravidlá**; experimentálny režim pre demo).

9. **Offline judge (ENABLE):**
   - Prepínač v **Nastaveniach**.
   - Pri prvom zapnutí sa zobrazí **modal** s **QProgressBar** a percentami; po dosiahnutí **100 %** sa modal **automaticky zavrie**.
   - Wordlist sa uloží do cache (napr. `~/.scrabgpt/wordlists/enable1.txt`) a režim sa aktivuje.
   - V offline móde sa **ľudské aj AI** slová validujú **offline** a status‑bar **nezobrazuje** „Rozhoduje rozhodca…“. Pri vypnutom offline móde sa používa **online** rozhodca ako doteraz.

---

## 3) Nefunkčné požiadavky
- **Cross‑platform:** Python 3.10+, **PySide6** UI; balenie neskôr (PyInstaller), mimo MVP.  
- **Kvalita:** ruff, mypy (strict), pytest; **UI testy na CI skip**.  
- **Deterministickosť:** všetky doménové testy bez siete; OpenAI volania sa **mockujú**.  
- **Bezpečnosť:** `.env` s `OPENAI_API_KEY`; sieť len pri interakcii **AI**/**Rozhodca** v runtime.  
- **Telemetria:** žiadna.  

---

## 4) Architektúra (moduly)
```
scrabgpt/
  core/            # čistá doména (bez UI, bez siete)
    board.py      # model dosky, súradnice, prémiá, aplikácia ťahu
    rack.py       # model hráčovho stojanu (rack)
    tiles.py      # distribúcia, RNG, taška
    scoring.py    # výpočet skóre (DL/TL/DW/TW, krížové slová)
    rules.py      # lokálne pravidlá ťahu (stred, spojitosť…)
    types.py      # datatypy (Direction, Placement, Move, WordScore…)
  ai/
    client.py     # tenký klient pre OpenAI (minimálny)
    judge.py      # validácia hlavného slova (JSON schema)
    player.py     # AI hráč (JSON schema návrhu ťahu)
  ui/
    app.py        # PySide6 hlavné okno
    board_view.py # 2D mriežka, DnD, zvýraznenia prémií
    rack_view.py  # DnD kocky
    dialogs.py    # nastavenia, upozornenia
  assets/
    premiums.json # mapa prémií 15×15
  tests/
    test_scoring.py
    test_rules.py
    test_premiums.py
    test_tiles.py
```
**Zásada:** `core/` nemá závislosť na `ai/` ani `ui/`. Všetky OpenAI hovory sa dajú **mockovať**.

---

## 5) UX / UI
- **Estetika:** moderné ploché UI (PySide6), jemné tiene, kontrastné farby prémií (TW=červená, DW=ružová, TL=tmavomodrá, DL=svetlomodrá), center **H8** so „★“.
- **Interakcie:**
  - DnD kameňov, snapping, zrušenie ťahu, zvýraznenie vzniknutého slova a jeho skóre „ghost preview“.  
  - Toolbar: **Nová hra**, **Potvrdiť ťah**, **Pasovať**, **Nastavenia**.  
  - Status‑bar: kto je na ťahu, posledný ťah + skóre.  

---

## 6) OpenAI integrácia (minimalistická, structured completions)
### 6.1 Modely
- **`gpt-5-mini`** použitý pre **AI hráča** aj **Rozhodcu**.

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

- **Pozn.:** Pri zapnutom **offline móde** sa volania na **validáciu slov** do OpenAI **nepoužívajú** (Rozhodca sa nevolá).

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

- **Pokrytie offline slovníkom:** nie je to oficiálny Scrabble zoznam → možnosť prepnúť späť na **online** rozhodcu.  
- **Disk/pamäť pre wordlist:** nároky sú mierne; sťahovanie prebehne **iba raz** a s progres barom.

---

## 11) Akceptačné kritériá MVP (DoD)
- `pytest -q` prejde: `test_scoring.py`, `test_premiums.py`, `test_rules.py`, `test_tiles.py`.  
- Manuálne demo podľa **1.1**: odohrám min. 3 ťahy človek/AI; skóre na UI sedí s logom v konzole.  
- OpenAI volania sú izolované v `ai/` a konfigurované cez `.env`; testy **bez siete**.  

- **Offline mód:** Zapnutie **Offline judge (ENABLE)** zobrazí **QProgressBar** s percentami a po stiahnutí sa validuje **bez OpenAI**; manuálne demo prejde s **offline validáciou**.

---

## 12) Post‑MVP (len poznámky)
- Overovanie **všetkých** krížových slov u Rozhodcu (batched).  
- Vyhľadávanie najlepšieho ťahu lokálne (rack solver) + AI ako komentátor.  
- Export PNG skóre tabuľky, PyInstaller balíčky.  

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
