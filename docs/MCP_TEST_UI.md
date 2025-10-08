# MCP Testovacie Rozhranie

## Prehľad

MCP Testovacie rozhranie je nové UI pre testovanie MCP serverov a nástrojov v ScrabGPT. Poskytuje kompletné prostredie pre vývojárov na testovanie MCP funkcionality pred jej integráciou do agentov.

## Funkcie

### 🔌 Správa Serverov
- **Pseudo toolbar**: Dropdown s uloženými MCP servermi v štýle "Potvrdiť ťah"
- **Pridávanie serverov**: Dialóg pre pridanie nových MCP serverov
- **Typy pripojenia**: Podpora pre Command a URL+Port pripojenia
- **Mazanie/Premenovanie**: Správa uložených serverov
- **Načítanie konfigurácie**: Automatické načítanie zo `scrabble_mcp.json`
- **Zobrazenie stavu**: Tabuľka pripojených serverov s počtom nástrojov

### 🔧 Testovanie Nástrojov
- **Výber nástroja**: Dropdown s dostupnými nástrojmi z pripojených serverov
- **Parametre**: Dynamická tabuľka pre zadávanie parametrov nástrojov
- **Typy parametrov**: Podpora pre string, number, boolean, array
- **Testovanie**: Spustenie nástroja s vlastnými parametrami
- **Výsledky**: JSON formátovaný výstup výsledkov

### 📋 Logovanie
- **Clickable status bar**: Kliknite na status bar pre otvorenie logov
- **Samostatné okno**: Logy v samostatnom non-modal dialógu
- **Verbose logy**: Detailné logovanie všetkých operácií
- **Timestamp**: Každá správa má časovú značku
- **Auto-scroll**: Automatické posúvanie na najnovšie správy
- **Uloženie logov**: Export logov do textového súboru
- **Vymazanie**: Rýchle vymazanie logov

## Použitie

### Spustenie z hlavnej aplikácie
1. Otvorte ScrabGPT
2. Kliknite na **🔧 MCP Test** v toolbar
3. MCP testovacie okno sa otvorí

### Spustenie samostatne
```bash
python test_mcp_ui.py
```

### Pridávanie a pripájanie MCP servera
1. Kliknite **➕ Pridať MCP server** v pseudo toolbar
2. Vyplňte konfiguráciu:
   - **Názov servera**: `scrabble`
   - **Typ pripojenia**: `Príkaz (Command)`
   - **Príkaz**: `poetry`
   - **Argumenty**: `run, python, -m, scrabgpt.ai.mcp_server`
   - **Popis**: `ScrabGPT MCP Server`
3. Kliknite **Pridať**
4. Vyberte server z dropdown v pseudo toolbar
5. Kliknite **🔌 Pripojiť**

### Pridávanie URL+Port servera
1. Kliknite **➕ Pridať MCP server**
2. Vyplňte konfiguráciu:
   - **Názov servera**: `factory_droid`
   - **Typ pripojenia**: `URL + Port`
   - **URL**: `localhost`
   - **Port**: `8080`
   - **Popis**: `Factory Droid MCP Server`
3. Kliknite **Pridať**

### Testovanie nástroja
1. Prejdite na tab **🔧 Testovanie Nástrojov**
2. Vyberte server z dropdown
3. Vyberte nástroj (napr. `get_board_state`)
4. Upravte parametre v tabuľke
5. Kliknite **🚀 Spustiť test**
6. Výsledky sa zobrazia v textovom poli

### Zobrazenie logov
1. Kliknite na status bar (spodná časť okna)
2. Otvorí sa samostatné okno s logmi
3. Môžete vymazať, uložiť alebo nastaviť auto-scroll

## Dostupné Nástroje

ScrabGPT MCP server poskytuje 11 nástrojov:

### Pravidlá validácie (5 nástrojov)
- `rules_first_move_must_cover_center` - Kontrola pokrytia stredového štvorca
- `rules_placements_in_line` - Kontrola umiestnenia v rade
- `rules_connected_to_existing` - Kontrola pripojenia k existujúcim písmenám
- `rules_no_gaps_in_line` - Kontrola medzier v rade
- `rules_extract_all_words` - Extrakcia všetkých slov

### Bodovanie (1 nástroj)
- `scoring_score_words` - Výpočet skóre slov

### Stav/Informácie (3 nástroje)
- `get_board_state` - Stav hracej dosky
- `get_rack_letters` - Písmená na racku
- `get_tile_values` - Hodnoty písmen

### Vysokúrovňové kompozitné (2 nástroje)
- `validate_move_legality` - Kompletná validácia ťahu
- `calculate_move_score` - Kompletný výpočet skóre

## Príklady testov

### Test get_board_state
```json
{
  "board": null
}
```

### Test rules_first_move_must_cover_center
```json
{
  "placements": [
    {"row": 7, "col": 7, "letter": "A"},
    {"row": 7, "col": 8, "letter": "B"}
  ]
}
```

### Test validate_move_legality
```json
{
  "board_grid": [
    "...............",
    "...............",
    "...............",
    "...............",
    "...............",
    "...............",
    "...............",
    ".......AB......",
    "...............",
    "...............",
    "...............",
    "...............",
    "...............",
    "...............",
    "..............."
  ],
  "placements": [
    {"row": 7, "col": 9, "letter": "C"}
  ],
  "is_first_move": false
}
```

## Dizajn

Rozhranie používa tmavý lesný dizajn konzistentný s ostatnými dialógmi ScrabGPT:

- **Pozadie**: `#0f1a12` (tmavá zelená)
- **Text**: `#e8f5e9` (svetlá zelená)
- **Rámce**: `#2f5c39` (stredná zelená)
- **Tlačidlá**: `#1a2f1f` s hover efektmi
- **Tabuľky**: Tmavé pozadie s zelenými akcentmi

## Technické detaily

### Worker thready
- **MCPConnectionWorker**: Asynchrónne pripájanie serverov
- **MCPToolTestWorker**: Asynchrónne testovanie nástrojov
- Thread-safe komunikácia cez Qt signály

### Logovanie
- **UI logy**: Zobrazenie v real-time v log tab
- **Konzolové logy**: Použitie Python logging modulu
- **Timestamp**: Automatické pridávanie časových značiek

### Konfigurácia
- **scrabble_mcp.json**: Automatické načítanie konfigurácie
- **JSON formát**: Štandardný MCP konfiguračný formát
- **Validácia**: Kontrola správnosti konfigurácie

## Rozšírenia

Rozhranie je navrhnuté pre ľahké rozšírenie:

1. **Nové servery**: Pridajte podporu pre ďalšie MCP servery
2. **Nové nástroje**: Automatické zisťovanie nástrojov z serverov
3. **Parametre**: Dynamické generovanie parametrov z tool schémy
4. **Validácia**: Rozšírenie validácie parametrov

## Troubleshooting

### Server sa nepripája
- Skontrolujte konfiguráciu príkazu a argumentov
- Overte, že MCP server beží
- Pozrite si logy pre detailné chybové správy

### Nástroj zlyhá
- Skontrolujte typy parametrov
- Overte správnosť JSON formátu pre array parametre
- Pozrite si logy pre detailné chybové správy

### UI neodpovedá
- Worker thready môžu byť zablokované
- Zatvorte a znovu otvorte dialóg
- Skontrolujte konzolové logy pre chyby

## Budúce vylepšenia

- **Real-time MCP**: Priame pripojenie k bežiacim MCP serverom
- **Schéma validácia**: Automatická validácia parametrov podľa JSON schémy
- **História testov**: Uloženie a načítanie predchádzajúcich testov
- **Batch testovanie**: Testovanie viacerých nástrojov naraz
- **Export výsledkov**: Uloženie výsledkov do JSON súborov
