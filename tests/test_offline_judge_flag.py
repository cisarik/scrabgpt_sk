from __future__ import annotations

import importlib


def test_env_forces_offline(monkeypatch) -> None:
    monkeypatch.setenv("OFFLINE_JUDGE_ENABLED", "1")
    # reimport pre uplatnenie env v module
    if "scrabgpt.config" in list(importlib.sys.modules.keys()):
        del importlib.sys.modules["scrabgpt.config"]
    cfg = importlib.import_module("scrabgpt.config")
    assert cfg.effective_offline_judge(False) is True
    assert cfg.effective_offline_judge(True) is True


def test_env_zero_respects_ui(monkeypatch) -> None:
    monkeypatch.setenv("OFFLINE_JUDGE_ENABLED", "0")
    if "scrabgpt.config" in list(importlib.sys.modules.keys()):
        del importlib.sys.modules["scrabgpt.config"]
    cfg = importlib.import_module("scrabgpt.config")
    assert cfg.effective_offline_judge(False) is False
    assert cfg.effective_offline_judge(True) is True


def test_no_env_follows_ui(monkeypatch) -> None:
    monkeypatch.delenv("OFFLINE_JUDGE_ENABLED", raising=False)
    if "scrabgpt.config" in list(importlib.sys.modules.keys()):
        del importlib.sys.modules["scrabgpt.config"]
    cfg = importlib.import_module("scrabgpt.config")
    assert cfg.effective_offline_judge(False) is False
    assert cfg.effective_offline_judge(True) is True


