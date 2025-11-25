"""LMStudio helper utilities with safe fallbacks."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Iterable

log = logging.getLogger("scrabgpt.ai.lmstudio")


try:  # Optional dependency
    import lmstudio as _lms  # type: ignore
except Exception:  # pragma: no cover - optional
    _lms = None  # type: ignore[misc]


def _default_model_key() -> str | None:
    """Pick model key from env if present."""
    return os.getenv("OPENAI_MODEL") or os.getenv("LLMSTUDIO_MODEL")


@lru_cache(maxsize=2)
def _load_model(model_key: str):
    if _lms is None:
        raise RuntimeError("lmstudio SDK nie je nainštalované")
    return _lms.llm(model_key)


def get_context_stats(messages: Iterable[str], model_key: str | None = None) -> tuple[int, int, float]:
    """Return (tokens_used, context_length, percent) with graceful fallback."""
    msgs = list(messages)
    if not msgs:
        return 0, 0, 0.0
    key = model_key or _default_model_key()
    if not key:
        return 0, 0, 0.0
    try:
        model = _load_model(key)
        context_len = int(model.get_context_length())
        tokens_used = int(len(model.tokenize("\n\n".join(msgs))))
        if context_len <= 0:
            return tokens_used, 0, 0.0
        percent = min(100.0, (tokens_used / context_len) * 100.0)
        return tokens_used, context_len, percent
    except Exception as exc:  # pragma: no cover - relies on optional SDK
        log.debug("LMStudio context stats failed: %s", exc)
        return 0, 0, 0.0


def get_context_length(model_key: str | None = None) -> int:
    """Return context length for model, or 0 on failure."""
    key = model_key or _default_model_key()
    if not key or _lms is None:
        return 0
    try:
        model = _load_model(key)
        return int(model.get_context_length())
    except Exception as exc:  # pragma: no cover - optional
        log.debug("LMStudio context length failed: %s", exc)
        return 0
