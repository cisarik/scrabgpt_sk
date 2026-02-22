from __future__ import annotations

from scrabgpt.ai.player import _build_prompt, _load_prompt_template
from scrabgpt.core.variant_store import VariantDefinition


def _variant() -> VariantDefinition:
    return VariantDefinition(slug="test", language="Slovak", letters=tuple())


def test_prompt_template_is_unified_for_all_modes() -> None:
    chat_template = _load_prompt_template(use_chat_protocol=True)
    legacy_template = _load_prompt_template(use_chat_protocol=False)

    assert chat_template == legacy_template
    assert "elite tournament Scrabble engine" in chat_template
    assert "Use blank adaptively, never by a fixed points threshold." in chat_template


def test_build_prompt_ignores_legacy_prompt_file_env(monkeypatch) -> None:
    monkeypatch.setenv("AI_PROMPT_FILE", "/tmp/does-not-exist.txt")
    monkeypatch.setenv("AI_PROMPT_FILE_CHAT", "/tmp/does-not-exist-chat.txt")

    compact_state = "ai_rack: A,B,?,R,O,T,S\n"
    prompt = _build_prompt(compact_state, _variant())

    assert "elite tournament Scrabble engine for Slovak" in prompt
    assert "CURRENT STATE:" in prompt
    assert "/tmp/does-not-exist" not in prompt


def test_build_prompt_contains_strict_output_contract() -> None:
    prompt = _build_prompt("ai_rack: A,E,I,O,U,S,T\n", _variant())

    assert "=== STRICT OUTPUT CONTRACT ===" in prompt
    assert "For a scoring move, include: start, direction, placements, word." in prompt
    assert "Use pass=true only as absolute last resort when exchange is impossible." in prompt
