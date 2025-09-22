"""Centralizovaná inicializácia logovania pre ScrabGPT.

- Konfiguruje Rich konzolový handler a rotujúci súborový handler.
- Zabráni duplicitným handlerom pri opakovaných importoch.
- Poskytuje `TRACE_ID_VAR` pre propagáciu trace-id cez ContextVar.
"""
from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

# Kontextové ID ťahu, dostupné pre UI a AI moduly
TRACE_ID_VAR: ContextVar[str] = ContextVar("trace_id", default="-")


class _TraceIdFilter(logging.Filter):
    """Filter doplní `trace_id` do každého záznamu z ContextVar.

    Pozn.: Použitý na konzolovom aj súborovom handleri.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.trace_id = TRACE_ID_VAR.get()
        except Exception:  # noqa: BLE001
            record.trace_id = "-"
        return True


def default_log_path() -> str:
    """Určí predvolenú cestu k log súboru.

    Behavior-preserving: predvolene používa koreň repozitára (`scrabgpt.log`).
    Možno prepísať premennou prostredia `SCRABGPT_LOG_PATH`.
    """

    env = os.getenv("SCRABGPT_LOG_PATH")
    if env:
        return env
    root_dir = Path(__file__).resolve().parents[2]
    return str(root_dir / "scrabgpt.log")


def configure_logging(*, log_path: str | None = None) -> logging.Logger:
    """Inicializuje logging iba raz a vráti projektový logger.

    - Rich na konzolu (prehľadné tracebacky)
    - Rotujúci súborový handler (≈1 MB, 5 záloh)
    - Formát zahŕňa `trace_id` z `TRACE_ID_VAR`
    """

    root = logging.getLogger()
    if root.handlers:
        return logging.getLogger("scrabgpt")

    root.setLevel(logging.INFO)
    trace_filter = _TraceIdFilter()

    # Konzola
    ch = RichHandler(rich_tracebacks=True)
    ch.setLevel(logging.INFO)
    ch.addFilter(trace_filter)
    ch.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(ch)

    # Súbor s rotáciou
    try:
        path = log_path or default_log_path()
        fh = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.addFilter(trace_filter)
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [trace=%(trace_id)s] %(message)s"
            )
        )
        root.addHandler(fh)
    except Exception:  # noqa: BLE001
        # Bez súboru pokračuj aspoň s konzolou
        pass

    return logging.getLogger("scrabgpt")


