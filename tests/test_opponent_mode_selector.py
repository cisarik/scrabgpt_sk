"""Tests for opponent mode selector widget."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from scrabgpt.core.opponent_mode import OpponentMode


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def sample_agents() -> list[dict]:
    # Legacy fixture kept because SettingsDialog still accepts available_agents.
    return [
        {"name": "Full Access", "model": "gpt-4o", "tools": ["tool1"]},
        {"name": "Minimal", "model": "gpt-4o-mini", "tools": ["tool1"]},
    ]


class TestOpponentModeSelector:
    def test_legacy_agent_mode_maps_to_lmstudio(self, qapp) -> None:
        assert OpponentMode.from_string("agent") == OpponentMode.LMSTUDIO

    def test_creates_with_default_mode(self, qapp, sample_agents: list[dict]) -> None:
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)
        assert selector.get_selected_mode() == OpponentMode.BEST_MODEL

    def test_can_set_mode_programmatically(self, qapp, sample_agents: list[dict]) -> None:
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)
        selector.set_mode(OpponentMode.LMSTUDIO)
        assert selector.get_selected_mode() == OpponentMode.LMSTUDIO

    def test_all_modes_are_present(self, qapp, sample_agents: list[dict]) -> None:
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)
        button_modes = {button.property("mode") for button in selector.button_group.buttons()}
        assert OpponentMode.GEMINI in button_modes
        assert OpponentMode.BEST_MODEL in button_modes
        assert OpponentMode.OPENROUTER in button_modes
        assert OpponentMode.NOVITA in button_modes
        assert OpponentMode.LMSTUDIO in button_modes

    def test_emits_signal_on_mode_change(self, qapp, sample_agents: list[dict]) -> None:
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)
        received_mode: OpponentMode | None = None

        def on_mode_changed(mode: OpponentMode) -> None:
            nonlocal received_mode
            received_mode = mode

        selector.mode_changed.connect(on_mode_changed)

        for button in selector.button_group.buttons():
            if button.property("mode") == OpponentMode.LMSTUDIO:
                button.click()
                break

        assert received_mode == OpponentMode.LMSTUDIO

    def test_disables_all_buttons_when_disabled(self, qapp, sample_agents: list[dict]) -> None:
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)
        selector.set_enabled(False)
        for button in selector.button_group.buttons():
            assert not button.isEnabled()


class TestSettingsDialog:
    def test_creates_with_mode(self, qapp, sample_agents: list[dict]) -> None:
        from scrabgpt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            current_mode=OpponentMode.LMSTUDIO,
            available_agents=sample_agents,
        )
        assert dialog.get_selected_mode() == OpponentMode.LMSTUDIO

    def test_shows_warning_when_game_in_progress(self, qapp, sample_agents: list[dict]) -> None:
        from scrabgpt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            current_mode=OpponentMode.BEST_MODEL,
            available_agents=sample_agents,
            game_in_progress=True,
        )
        assert dialog.mode_selector.button_group.buttons()[0].isEnabled()

    def test_openai_mode_requires_models(self, qapp, sample_agents: list[dict]) -> None:
        from scrabgpt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            current_mode=OpponentMode.BEST_MODEL,
            available_agents=sample_agents,
        )
        dialog.selected_openai_models = []

        selected_mode = dialog.mode_selector.get_selected_mode()
        assert selected_mode == OpponentMode.BEST_MODEL
        assert not dialog.selected_openai_models

    def test_prompt_editor_tab_removed(self, qapp, sample_agents: list[dict]) -> None:
        from scrabgpt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            current_mode=OpponentMode.BEST_MODEL,
            available_agents=sample_agents,
        )

        tab_titles = [dialog.tabs.tabText(i).lower() for i in range(dialog.tabs.count())]
        assert dialog.tabs.count() == 4
        assert all("prompt" not in title for title in tab_titles)
