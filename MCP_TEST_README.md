# 🔧 MCP Testovacie Rozhranie

## Rýchle spustenie

### 1. Z hlavnej aplikácie ScrabGPT
```bash
poetry run python -m scrabgpt.ui.app
```
Potom kliknite na **🔧 MCP Test** v toolbar.

### 2. Samostatne
```bash
python test_mcp_ui.py
```

## Funkcie

✅ **Pseudo toolbar s dropdown serverov** (štýl "Potvrdiť ťah")  
✅ **Pridávanie MCP serverov** (Command + URL+Port typy)  
✅ **Mazanie/Premenovanie serverov**  
✅ **Testovanie nástrojov s vlastnými parametrami**  
✅ **Clickable status bar pre logy**  
✅ **Verbose logovanie do UI a konzoly**  
✅ **Tmavý lesný dizajn**  
✅ **Načítanie konfigurácie zo scrabble_mcp.json**  

## Príklad použitia

1. **Pridávanie ScrabGPT servera**:
   - Kliknite "➕ Pridať MCP server"
   - Názov: `scrabble`
   - Typ: `Príkaz (Command)`
   - Príkaz: `poetry`
   - Argumenty: `run, python, -m, scrabgpt.ai.mcp_server`

2. **Pridávanie URL+Port servera**:
   - Kliknite "➕ Pridať MCP server"
   - Názov: `factory_droid`
   - Typ: `URL + Port`
   - URL: `localhost`
   - Port: `8080`

3. **Testovanie nástroja**:
   - Vyberte server z dropdown
   - Vyberte nástroj a upravte parametre
   - Spustite test

4. **Pozrite si logy**: Kliknite na status bar

## Dostupné nástroje

ScrabGPT poskytuje **11 nástrojov**:
- 5 pravidiel validácie
- 1 bodovanie
- 3 stav/informácie  
- 2 vysokúrovňové kompozitné

## Dokumentácia

Podrobná dokumentácia: [docs/MCP_TEST_UI.md](docs/MCP_TEST_UI.md)

---

**Tip**: Rozhranie je navrhnuté pre testovanie MCP nástrojov pred ich integráciou do agentov. Ideálne pre vývojárov a testovanie nových funkcionalít.
