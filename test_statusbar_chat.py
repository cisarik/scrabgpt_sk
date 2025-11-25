#!/usr/bin/env python3
"""Test statusbar click handler - otvorí chat dialog.

Tento script spustí MainWindow a otestuje:
- Statusbar click handler
- Otvorenie chat dialogu
- Dummy chat odpovede
"""

import sys
import logging
from PySide6.QtWidgets import QApplication
from scrabgpt.ui.app import MainWindow
from scrabgpt.logging_setup import configure_logging

# Setup logging
configure_logging()
logging.getLogger().setLevel(logging.INFO)

def main():
    app = QApplication(sys.argv)
    
    # Vytvor main window
    window = MainWindow()
    window.show()
    
    # Nastav statusbar message s hintom
    window.status.showMessage(
        "👆 Klikni tu pre otvorenie chatu s AI (alebo stlač F1)",
        5000  # 5 sekúnd
    )
    
    # Info v console
    print("\n" + "="*60)
    print("TESTOVANIE CHAT DIALOGU")
    print("="*60)
    print("1. Klikni KDEKOĽVEK na statusbar (sivý pruh dole)")
    print("2. Otvorí sa chat dialog")
    print("3. Napíš správu a stlač Enter alebo Odoslať")
    print("4. Uvidíš dummy odpoveď s typing efektom")
    print("="*60 + "\n")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
