#!/usr/bin/env python3
"""Test script pre MCP UI rozhranie."""

import sys
import os
from pathlib import Path

# Pridaj project root do Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication
from scrabgpt.ui.mcp_test_dialog import MCPTestDialog

def main():
    """Spusti test MCP UI."""
    app = QApplication(sys.argv)
    
    # Vytvor MCP testovací dialóg
    dialog = MCPTestDialog()
    dialog.show()
    
    print("🔧 MCP Testovacie rozhranie spustené!")
    print("📋 Funkcie:")
    print("  - Pripájanie/odpájanie MCP serverov")
    print("  - Testovanie nástrojov s vlastnými parametrami")
    print("  - Verbose logovanie do UI a konzoly")
    print("  - Tmavý lesný dizajn")
    print("  - Načítanie konfigurácie zo scrabble_mcp.json")
    
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())


