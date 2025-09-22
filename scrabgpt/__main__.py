"""Vstupný bod pre spustenie: `python -m scrabgpt`.

Deleguje na `scrabgpt.ui.app.main()`.
"""

from __future__ import annotations

from .ui.app import main as _main


def main() -> None:
    """Spustí PySide6 aplikáciu.

    Pozn.: Oddelené kvôli peknému entry pointu v Poetry.
    """

    _main()


if __name__ == "__main__":
    main()


