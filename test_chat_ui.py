#!/usr/bin/env python3
"""Test script pre ChatDialog UI - animácie a téma.

Spustí ChatDialog samostatne aby si mohol otestovať:
- Dark green tému
- Loading animation
- Typing effect
- Chat bubliny (user vs AI)
- Input field + send button
"""

import sys
from PySide6.QtWidgets import QApplication
from scrabgpt.ui.chat_dialog import ChatDialog


def main():
    app = QApplication(sys.argv)
    
    # Vytvor dialog
    dialog = ChatDialog()
    
    # Pridaj testovacie správy
    dialog.add_user_message("Ahoj AI, vieš hrať Scrabble?")
    
    # Zobraz loading animation na 2 sekundy
    dialog._show_loading_animation()
    
    # Po 2 sekundách pridaj AI odpoveď s typing efektom
    from PySide6.QtCore import QTimer
    QTimer.singleShot(2000, lambda: _add_ai_response(dialog))
    
    # Otvor dialog
    dialog.show()
    
    sys.exit(app.exec())


def _add_ai_response(dialog):
    """Pridá AI odpoveď s typing animáciou."""
    dialog.add_ai_message(
        "Ahoj! Áno, viem hrať Scrabble. Som expertný hráč v slovenčine. "
        "Chceš si zahrať? Môžem ti pomôcť s ťahmi alebo vysvetliť stratégiu.",
        use_typing_effect=True
    )


if __name__ == "__main__":
    main()
