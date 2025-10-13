# Vylepšenia JSON Parsingu

## Prehľad

Modely často vracajú okrem JSON aj iný text (reasoning, vysvetlenia), čo spôsobovalo parsing chyby. Implementovali sme robustné fallback riešenie s transparentným informovaním používateľa.

## Problém

**Pred opravou:**
- Claude Sonnet 4.5 vrátil reasoning text pred JSON blokom
- Parser zlyhal s `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`
- Validný JSON bol prítomný v ```` ```json ... ``` ```` bloku, ale nebol extrahovaný
- Používateľovi sa zobrazila chyba "parse_error" aj keď JSON bol v odpovedi

**Príklad zlyhávajúcej odpovede:**
```
Let me play ORAL across at row 8, using existing letters if any:
ORAL at (8,6) going across: O(8,6), R(8,7), A(8,8), L(8,9)
This intersects with I at (7,7)... no, (8,7) is below (7,7).

Playing FLORA down from (4,7): F(4,7), L(5,7), O(6,7), R(7,7), A(8,7)
But (7,7) has 'I' not 'R'.

Let me play a separate word: FLORA at row 8 starting at column 2:
F(8,2), L(8,3), O(8,4), R(8,5), A(8,6)

```json
{"start":{"row":8,"col":2},"direction":"ACROSS","placements":[...]}
```
```

## Riešenie

### 1. Inteligentné Fallback Parso vanie

**Stratégia parsingu v `schema.py`:**

1. **Pokus 1 - Priamy parsing:**
   - Odstráni markdown bloky na začiatku/konci (```` ```json ... ``` ````)
   - Skúsi parsovať JSON priamo
   - Ak úspešné → `parse_method = "direct"`

2. **Pokus 2 - Markdown extraction:**
   - Ak priamy parsing zlyhá, hľadá JSON vo vnútri textu
   - Používa regex patterns na nájdenie ```` ```json ... ``` ```` blokov
   - Podporuje viaceré varianty (s/bez newline, s/bez `json` markeru)
   - Ak úspešné → `parse_method = "markdown_extraction"`

3. **Pokus 3 - Vyhodenie chyby:**
   - Ak všetky fallbacky zlyhajú, vyhodí pôvodnú `JSONDecodeError`
   - Umožňuje ďalšie fallbacky (napr. GPT-5-mini parser v budúcnosti)

### 2. Tracking Parse Metódy

**Zmeny v `parse_ai_move()`:**

```python
# Pred:
def parse_ai_move(text: str) -> MoveModel:
    ...
    return MoveModel.model_validate(obj)

# Po:
def parse_ai_move(text: str) -> tuple[MoveModel, str]:
    ...
    return MoveModel.model_validate(obj), "direct"  # alebo "markdown_extraction"
```

**Parse metódy:**
- `"direct"` - JSON parsovaný priamo (s odstránením markdown na okrajoch)
- `"markdown_extraction"` - JSON extrahovaný z markdown bloku vo vnútri textu
- (rezervované pre budúcnosť) `"gpt_fallback"` - JSON extrahovaný cez GPT-5-mini

### 3. Integrácia do Multi-Model Flow

**Zmeny v `multi_model.py` a `novita_multi_model.py`:**

```python
# Parse s tracking metódy
model_obj, parse_method = parse_ai_move(stripped)
move = to_move_payload(model_obj)

# Log informácie o extraction
if parse_method == "markdown_extraction":
    log.info("✓ Model %s: JSON extrahovaný z markdown bloku", model_id)

# Pridanie parse_method do result dict
return await _notify({
    "model": model_id,
    "status": "ok",
    "move": move,
    "parse_method": parse_method,  # ← nové pole
    ...
})
```

### 4. UI Transparencia

**Zmeny v `response_detail.py`:**

Názov sekcie sa dynamicky mení podľa použitej metódy:

| Podmienka | Názov sekcie | Farba pozadia |
|-----------|--------------|----------------|
| `gpt_analysis` prítomné | "🤖 GPT-5-mini Fallback Analysis" | `#1a3a4d` (modrá) |
| `parse_method == "markdown_extraction"` | "📋 Detaily ťahu (JSON extrahovaný z markdown)" | `#2a4d2a` (zelená) |
| Inak | "📋 Detaily ťahu" | `#2a2a2a` (šedá) |

**Benefit:**
- Používateľ vidí **ako** bol JSON parsovaný
- Zelená farba signalizuje úspešný fallback
- Modrá by signalizovala použitie GPT fallbacku (zatiaľ neimplementované)

## Implementácia

### Zmenené súbory:

1. **`scrabgpt/ai/schema.py`**
   - ✅ Pridaná `_extract_json_from_markdown()` helper funkcia
   - ✅ `parse_ai_move()` teraz vracia `tuple[MoveModel, str]`
   - ✅ Implementovaný fallback parsing s regex
   - ✅ Loguje úspešnosť každého pokusu

2. **`scrabgpt/ai/multi_model.py`**
   - ✅ Aktualizované volanie `parse_ai_move()` na tuple unpacking
   - ✅ Pridaný log pre markdown extraction
   - ✅ `parse_method` pridaný do result dict

3. **`scrabgpt/ai/novita_multi_model.py`**
   - ✅ Rovnaké zmeny ako v `multi_model.py`

4. **`scrabgpt/ai/player.py`**
   - ✅ Aktualizované na tuple unpacking (ignore `_parse_method`)

5. **`scrabgpt/ui/response_detail.py`**
   - ✅ Dynamický názov sekcie podľa `parse_method`
   - ✅ Farebné rozlíšenie (zelená/modrá/šedá)
   - ✅ Transparentná komunikácia k používateľovi

6. **`tests/test_ai_schema_parser.py`**
   - ✅ Pridané testy pre markdown extraction
   - ✅ Test pre reasoning text pred JSON blokom
   - ✅ Test pre viaceré markdown bloky (použije prvý)
   - ✅ Všetky existujúce testy aktualizované na tuple unpacking

## Testovanie

### Nové testy:

```python
def test_parse_json_with_reasoning_text_before():
    """Test parsovania JSON keď pred ním je reasoning text (ako na screenshote)"""
    response = """Let me play ORAL...
    
    ```json
    {"start":{"row":8,"col":2},...}
    ```"""
    
    m, method = parse_ai_move(response)
    assert method == "markdown_extraction"  # ✓ Extrahované z markdown
    assert can["word"] == "FLORA"
```

### Výsledky:

```bash
$ poetry run pytest tests/test_ai_schema_parser.py -v
✅ 11 passed in 0.06s

$ poetry run mypy scrabgpt/ai/schema.py ...
✅ No errors found
```

## Data Flow

```
Model Response with reasoning text
    ↓
parse_ai_move(text)
    ↓
Pokus 1: Priamy parse (strip markdown na okrajoch)
    ↓
    Zlyhalo (reasoning text pred JSON)
    ↓
Pokus 2: Hľadaj ```json ... ``` blok
    ↓
    ✓ Našiel! Extrahuj obsah
    ↓
    ✓ Parse úspešný → return (model, "markdown_extraction")
    ↓
multi_model.py: Pridaj parse_method do result
    ↓
response_detail.py: Zobraz "📋 Detaily ťahu (JSON extrahovaný z markdown)" 🟢
    ↓
Používateľ vidí transparentnú informáciu o parsing metóde
```

## Benefits

### Pre používateľov:
- ✅ **Viac úspešných ťahov**: Modely s reasoning textom už nie sú zamietnuté
- ✅ **Transparencia**: Vidia ako bol JSON parsovaný
- ✅ **Dôvera**: Vedia, že systém inteligentne spracoval odpoveď

### Pre vývojárov:
- ✅ **Robustnosť**: Zvláda rôzne formáty odpovedí
- ✅ **Debugging**: Parse metóda je tracked v result dict
- ✅ **Extensibilita**: Pripravené na GPT fallback parser

## Známe obmedzenia

1. **Regex patterns môžu zlyhať pri exotických formátoch:**
   - Riešenie: Pridať viac patterns alebo GPT fallback

2. **CHEAUP bug (videné na screenshote):**
   - Toto je separátny bug v word extraction/scoring
   - Nie je súčasťou tejto úpravy
   - Potrebuje vlastné vyšetrovanie

3. **GPT-5-mini fallback parser nie je implementovaný:**
   - Dokumentácia v `docs/GPT_FALLBACK_PARSER.md` ho popisuje
   - Ale aktuálny kód ho neimplementuje
   - Pridať v budúcej iterácii ak markdown extraction nestačí

## Budúce vylepšenia

1. **GPT-5-mini fallback parser** (posled ná možnosť):
   ```python
   # Pokus 3: Ak markdown extraction zlyhá A má content > 50 znakov
   if len(text) > 50:
       return _gpt_extract_json(text), "gpt_fallback"
   ```

2. **Štatistiky parsing metód**:
   - Trackuj koľkokrát sa použil každý fallback
   - Zobraz v UI alebo logoch

3. **Custom error messages pre konkrétne zlyhania**:
   - Lepšie hints pre používateľa v error_analysis

## Commity

```bash
git add scrabgpt/ai/schema.py
git add scrabgpt/ai/multi_model.py scrabgpt/ai/novita_multi_model.py scrabgpt/ai/player.py
git add scrabgpt/ui/response_detail.py
git add tests/test_ai_schema_parser.py
git add docs/JSON_PARSING_IMPROVEMENTS.md
git commit -m "Vylepšené JSON parsing s markdown extraction fallback

- Pridaná markdown extraction pre odpovede s reasoning textom
- Parse metóda tracked v result dict (direct/markdown_extraction)
- UI zobrazuje transparentne ako bol JSON parsovaný
- 11/11 testov prešlo, žiadne type errors
"
```

## Autori

- Úprava: 2025-01-08
- Request: Používateľ chcel lepšie spracovanie LLM odpovedí s reasoning textom
- Implementácia: AI asistent

