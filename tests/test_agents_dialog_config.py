import pytest

from scrabgpt.ui.agents_dialog import normalize_llm_config, load_env_llm_defaults


def test_normalize_llm_config_trims_and_clamps() -> None:
    cfg = normalize_llm_config(" http://127.0.0.1:1234 ", " qwen3-vl-8b ", 40000, 2)
    assert cfg["base_url"] == "http://127.0.0.1:1234"
    assert cfg["model"] == "qwen3-vl-8b"
    assert cfg["max_tokens"] == 20000  # clamp
    assert cfg["timeout"] == 5  # clamp


def test_normalize_llm_config_requires_fields() -> None:
    with pytest.raises(ValueError):
        normalize_llm_config("", "model")
    with pytest.raises(ValueError):
        normalize_llm_config("http://localhost", "")


def test_load_env_llm_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("OPENAI_MODELS", "qwen3,qwen3-vl")
    monkeypatch.setenv("AI_MOVE_MAX_OUTPUT_TOKENS", "30000")
    monkeypatch.setenv("AI_MOVE_TIMEOUT_SECONDS", "2")
    
    cfg = load_env_llm_defaults()
    assert cfg is not None
    assert cfg["base_url"] == "http://127.0.0.1:1234/v1"
    assert cfg["model"] == "qwen3"
    assert cfg["max_tokens"] == 20000  # clamped
    assert cfg["timeout"] == 5  # clamped
