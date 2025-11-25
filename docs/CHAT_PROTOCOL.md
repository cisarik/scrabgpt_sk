# Chat Protocol - OpenRouter Context Session

## Prehľad

Nový protokol komunikácie medzi hráčom a AI v Scrabble hre založený na:
- **Delta updates** - posielame len zmeny, nie celý stav dosky
- **Context session** - jednoduchá konverzácia, nie zero-shot
- **MCP tools** - AI má prístup k validačným funkciám
- **OpenRouter default** - všetky ťahy cez OpenRouter API

## Výhody

✅ **80-90% úspora tokenov** - delta namiesto plného stavu  
✅ **Prirodzený chat** - user môže priamo komunikovať s AI  
✅ **MCP validácie** - AI kontroluje svoje ťahy  
✅ **História kontextu** - AI pamätá predchádzajúce ťahy  
✅ **Multi-model ready** - funguje s OpenRouter aj Novita  

## Formát Správ

### 1. System Prompt (raz na začiatku hry)

```
Hráš Scrabble v jazyku {language}. Používaj MCP tools na validáciu ťahov.

=== PRAVIDLÁ ===
- Prvý ťah musí pokrývať stred dosky (7,7)
- Políčka musia byť v jednom riadku (ACROSS/DOWN) bez medzier
- Musia sa pripojiť k existujúcim písmenám (po prvom ťahu)
- Všetky vytvorené slová musia byť platné v jazyku {language}

=== BODOVÉ HODNOTY PÍSMEN ===
{tile_summary}

=== PRÉMIOVÉ POLÍČKA ===
* = TW (slovo ×3)
~ = DW (slovo ×2)  
$ = TL (písmeno ×3)
^ = DL (písmeno ×2)

Použité prémiá sa už nepočítajú.

=== DOSTUPNÉ MCP TOOLS ===

1. **validate_word_{language}(word: str)**
   - Validuje slovo v slovníku
   - Vracia: {valid: bool, reason: str, tier: int}
   - Príklad: validate_word_slovak("KOT") → {valid: true, reason: "Found in local dictionary"}

2. **validate_move_legality(board_grid: list[str], placements: list[dict], is_first_move: bool)**
   - Kontroluje legalitu ťahu (riadok, prepojenie, medzery, stred)
   - Vracia: {valid: bool, checks: dict, reason: str}
   - Príklad: validate_move_legality([...], [{row:7,col:7,letter:"K"}], true)

3. **calculate_move_score(board_grid: list[str], premium_grid: list, placements: list[dict])**
   - Počíta skóre pre ťah vrátane prémií
   - Vracia: {total_score: int, breakdowns: list, words: list}
   - Príklad: calculate_move_score([...], [...], [{row:7,col:7,letter:"K"}])

4. **rules_extract_all_words(board_grid: list[str], placements: list[dict])**
   - Extrahuje všetky slová vytvorené ťahom (hlavné + krížové)
   - Vracia: {words: list[{word: str, cells: list}]}

=== FORMÁT ODPOVEDE ===

Odpovedaj **VŽDY** JSON objektom:

```json
{
  "start": {"row": 7, "col": 7},
  "direction": "ACROSS",
  "placements": [
    {"row": 7, "col": 7, "letter": "K"},
    {"row": 7, "col": 8, "letter": "O"},
    {"row": 7, "col": 9, "letter": "T"}
  ],
  "word": "KOT"
}
```

Ak nie je možný žiadny ťah, odpovedz:
```json
{"pass": true}
```

**DÔLEŽITÉ:** Políčko `word` musí obsahovať výsledné hlavné slovo na doske (vrátane existujúcich písmen).
```

### 2. User Message - Prvý Ťah (prázdna doska)

```
=== NOVÁ HRA ===

Začínaš. Doska je prázdna.

Tvoj rack: [A, E, I, K, L, O, T]

Prémiové políčka:
* (TW): (0,0), (0,7), (0,14), (7,0), (7,14), (14,0), (14,7), (14,14)
~ (DW): (1,1), (2,2), (3,3), (4,4), (10,10), (11,11), (12,12), (13,13)
$ (TL): (1,5), (1,9), (5,1), (5,5), (5,9), (5,13), (9,1), (9,5), (9,9), (9,13), (13,5), (13,9)
^ (DL): (0,3), (0,11), (2,6), (2,8), (3,0), (3,7), (3,14), (6,2), (6,6), (6,8), (6,12), (7,3), (7,11), (8,2), (8,6), (8,8), (8,12), (11,0), (11,7), (11,14), (12,6), (12,8), (14,3), (14,11)

Pripomenutie: Prvý ťah musí pokryť stred (7,7).
```

### 3. Assistant Response - Prvý Ťah

```json
{
  "start": {"row": 7, "col": 7},
  "direction": "ACROSS",
  "placements": [
    {"row": 7, "col": 7, "letter": "K"},
    {"row": 7, "col": 8, "letter": "O"},
    {"row": 7, "col": 9, "letter": "T"}
  ],
  "word": "KOT"
}
```

System zapamätá tento ťah do kontextu.

### 4. User Message - Ďalší Ťah (delta update)

```
=== ŤAH #2 ===

Hráč zahral: "MAČKA" za 18 bodov
Políčka: (6,7,M), (7,7,A), (8,7,Č), (9,7,K), (10,7,A)

Doska teraz (len obsadené):
(6,7)=M  (7,7)=K  (7,8)=O  (7,9)=T
(8,7)=Č  (9,7)=K  (10,7,=A

Tvoj rack: [A, E, I, L, N, R, S]

Voľné prémiá (nepoužité):
~ (DW): (1,1), (2,2), (10,10)
$ (TL): (1,5), (5,5), (9,9)
^ (DL): (3,7), (6,6), (8,8)

Je na tebe.
```

**Vysvetlenie delta formátu:**
- Posielame len **obsadené políčka** namiesto celej 15×15 matice
- Voľné prémiá - len tie čo sú **ešte aktívne** (nepoužité)
- História - implicitne v context session

### 5. Assistant Response - Ďalší Ťah

```json
{
  "start": {"row": 7, "col": 10},
  "direction": "DOWN",
  "placements": [
    {"row": 7, "col": 10, "letter": "S"}
  ],
  "word": "KOTS"
}
```

### 6. User Message - Chat od Užívateľa

```
Prečo si zahral KOTS? To je validné slovo?
```

### 7. Assistant Response - Voľná Odpoveď

```
Áno, KOTS je validné slovenské slovo (plurál od KOT). Získal som 12 bodov:
- K (1) + O (1) + T (1) + S (1) = 4 body × DW (×2) = 8 bodov
- Pripojil som sa k tvojmu slovu MAČKA.

Chceš pokračovať v hre?
```

### 8. Systémová Správa - Validácia

Keď AI udá nevalidný ťah, system vracia chybovú správu:

```
=== CHYBA VALIDÁCIE ===

Tvoj ťah bol zamietnutý:
Dôvod: Slovo "KOTX" nie je platné v slovenskom jazyku.

Skús prosím iný ťah.

Stav dosky (bez zmeny):
(6,7)=M  (7,7)=K  (7,8)=O  (7,9)=T
(8,7)=Č  (9,7)=K  (10,7)=A

Tvoj rack (stále): [A, E, I, L, N, R, S]
```

## Implementačné Detaily

### GameContextSession API

```python
class GameContextSession:
    def add_human_move(
        self, 
        word: str, 
        score: int, 
        placements: list[Placement]
    ) -> None:
        """Pridá ťah hráča do kontextu ako user message."""
    
    def add_ai_move(
        self, 
        move: dict[str, Any],
        score: int
    ) -> None:
        """Pridá vlastný ťah AI ako assistant message."""
    
    def add_user_message(self, message: str) -> None:
        """Pridá chat správu od užívateľa."""
    
    def add_system_message(self, message: str) -> None:
        """Pridá systémovú správu (napr. chyba validácie)."""
    
    def get_compact_delta(
        self, 
        board: Board, 
        rack: list[str], 
        premiums: list[tuple[int, int, str]]
    ) -> str:
        """Vygeneruje kompaktnú delta správu s aktuálnym stavom."""
```

### Kompaktný Delta Formát - Detailná Špecifikácia

#### Obsadené Políčka

Namiesto:
```
grid:
...............
...............
.......M.......
.......KOT.....
...............
```

Použijeme:
```
Doska (obsadené):
(6,7)=M (7,7)=K (7,8)=O (7,9)=T (8,7)=Č (9,7)=K (10,7)=A
```

**Úspora:** ~225 znakov → ~60 znakov (75% menej)

#### Prémiá

Namiesto:
```
premium_grid: [
  [TW, None, None, DL, ...],
  [None, DW, None, None, ...],
  ...
]
```

Použijeme:
```
Voľné prémiá:
~ (DW): (1,1), (2,2)
$ (TL): (5,5), (9,9)
```

**Úspora:** ~400 znakov → ~80 znakov (80% menej)

## Porovnanie: Starý vs Nový Protokol

### Starý Protokol (zero-shot, plný stav)

```
You are an expert Scrabble player...

Given this compact state:
grid:
...............
...............
.......M.......
.......KOT.....
.......Č.......
.......K.......
.......A.......
...............
ai_rack: AEILNRS
human_score: 18
ai_score: 12
turn: AI

Premium legend: *=TW, ~=DW, $=TL, ^=DL
...
```

**Token count:** ~1200 tokenov

### Nový Protokol (context session, delta)

**Prvý ťah:**
```
System: [Pravidlá + MCP tools] (600 tokenov, raz)
User: [Prázdna doska + rack] (200 tokenov)
Assistant: [JSON odpoveď] (50 tokenov)
```

**Ďalšie ťahy:**
```
User: [Delta: nové políčka + rack] (100 tokenov)
Assistant: [JSON odpoveď] (50 tokenov)
```

**Token count po 5 ťahoch:**
- Starý: 1200 × 5 = **6000 tokenov**
- Nový: 600 + 200 + (100+50) × 4 = **1400 tokenov**

**Úspora: 77%** 🎉

## MCP Tools Integration

AI môže volať tools priamo v svojej odpovedi (pseudo-code):

```
User: Tvoj rack: [K,O,T,A,Ř,E,N]

Assistant (thinking):
Skúsim slovo KÔŇ na (7,7) ACROSS...
[internal: validate_word_slovak("KOŇ") → valid=true]
[internal: calculate_move_score(...) → 8 bodov]
OK, zahrám KOŇ.

Assistant (response):
{
  "start": {"row": 7, "col": 7},
  "direction": "ACROSS",
  "placements": [...],
  "word": "KOŇ"
}
```

**Poznámka:** Tools nebudú explicitne volané v odpovedi (to by zvýšilo tokeny). AI ich používa **implicitne** počas reasoning fázy (deepseek-r1 thinking channel).

## Migračný Plán

### Fáza 1: Backward Compatible

1. Zachovať starý `propose_move()` ako `propose_move_legacy()`
2. Vytvoriť nový `propose_move_chat()` s context session
3. Prepínač v Settings: "Použiť chat protokol (beta)"

### Fáza 2: Full Migration

1. Odstrániť legacy metódu
2. Všetky hry defaultne cez OpenRouter + chat
3. ChatDialog ako hlavné rozhranie

### Fáza 3: Advanced Features

1. User môže písať AI počas hry
2. AI vysvetľuje svoje ťahy (reasoning)
3. História sa ukladá do súboru

## Testovanie

### Unit Testy

```python
def test_compact_delta_occupied_only():
    """Delta obsahuje len obsadené políčka."""
    board = Board(...)
    board.cells[7][7].letter = "K"
    delta = get_compact_delta(board, [...])
    assert "(7,7)=K" in delta
    assert "." not in delta  # žiadne prázdne

def test_compact_delta_premiums_unused_only():
    """Delta obsahuje len nepoužité prémiá."""
    board.cells[1][1].premium = Premium.DW
    board.cells[1][1].premium_used = True  # použité
    delta = get_compact_delta(board, [...])
    assert "(1,1)" not in delta  # neuvádza použité
```

### Integračné Testy

```python
@pytest.mark.openrouter
async def test_openrouter_context_session():
    """Celá hra cez OpenRouter s context session."""
    client = OpenRouterClient()
    session = GameContextSession("slovak")
    
    # Prvý ťah
    messages = session.prepare_messages(system_prompt, first_turn_state)
    response = await client.call_model("gpt-4", messages)
    session.remember_response(response)
    
    # Druhý ťah (delta)
    delta = get_compact_delta(board, rack, premiums)
    session.add_human_move("MAČKA", 18, [...])
    messages = session.prepare_messages(system_prompt, delta)
    response = await client.call_model("gpt-4", messages)
    
    assert "start" in response
    assert "placements" in response
```

## Bezpečnosť & Performance

### Rate Limiting

- OpenRouter: 60 requestov/minútu (dostatočné pre gameplay)
- Cache validácií: 1 hodina TTL
- Timeout: 30s per request

### Cost Optimization

| Metóda | Tokens/ťah | Cost (GPT-4) |
|--------|-----------|--------------|
| Zero-shot full state | 1200 | $0.012 |
| Context session delta | 150 | $0.0015 |
| **Úspora** | **87.5%** | **87.5%** |

### Error Handling

```python
try:
    response = await client.call_model(model_id, messages)
except TimeoutException:
    return {"pass": true, "reason": "AI timeout"}
except HTTPError as e:
    log.error("OpenRouter error: %s", e)
    return {"pass": true, "reason": "API error"}
```

## Záver

Nový chat protokol poskytuje:
- ✅ **Masívnu úsporu tokenov** (80-90%)
- ✅ **Prirodzenejšiu konverzáciu**
- ✅ **MCP tools validácie**
- ✅ **Multi-model support**
- ✅ **User chat interakciu**

Všetko pri zachovaní plnej funkčnosti a spätnej kompatibility.
