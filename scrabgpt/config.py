"""Konfigurácia a flagy pre ScrabGPT (offline/online rozhodca).

Pravidlá:
- OFFLINE_JUDGE_ENABLED='1' -> vždy zapni offline judge (override UI).
- OFFLINE_JUDGE_ENABLED='0' alebo chýba -> riadi to UI toggle.
"""
from __future__ import annotations

import os
from contextlib import suppress

# Preferuj python-dotenv, no nech je import bezpečný
try:  # pragma: no cover - vetvenie importu
    from dotenv import load_dotenv as _load_dotenv
except Exception:  # pragma: no cover
    _load_dotenv = None  # type: ignore[assignment]

# Načítaj .env veľmi skoro, ale nenahrádzaj už existujúce OS premenne
if _load_dotenv is not None and os.getenv("PYTEST_CURRENT_TEST") is None:
    # pragma: no cover - obranné vetvenie
    with suppress(Exception):
        _load_dotenv(override=False)

_TRUE = {"1", "true", "yes", "on", "y", "t"}
_FALSE = {"0", "false", "no", "off", "n", "f"}


def _parse_bool(val: str | None) -> bool | None:
    """Bezpečné parsovanie boolean reťazcov; None ak neznáme.

    Komentár (SK): Funkcia akceptuje viacero zápisov pravdy/nepravdy a vráti
    None, ak hodnota nie je rozpoznaná. Používa sa pre spoľahlivé čítanie
    konfiguračných premenných prostredia.
    """
    if val is None:
        return None
    v = val.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return None


def effective_offline_judge(ui_toggle: bool | None) -> bool:
    """Vráti výsledný stav offline-judga podľa .env a UI togglu.

    - .env == True  -> vždy True
    - .env == False -> podľa UI
    - .env == None  -> podľa UI

    Komentár (SK): Táto funkcia enkapsuluje prioritu konfigurácie. V prvom
    kroku zohľadní .env (ak je nastavené na pravdu, prepíše UI). V opačnom
    prípade sa použije hodnota prepínača z UI.
    """
    env_val = _parse_bool(os.getenv("OFFLINE_JUDGE_ENABLED"))
    if env_val is True:
        return True
    if env_val is False:
        return bool(ui_toggle)
    return bool(ui_toggle)

