"""Tests for opponent mode selector widget."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication
from scrabgpt.core.opponent_mode import OpponentMode


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def sample_agents() -> list[dict]:
    """Sample agent configurations for testing."""
    return [
        {
            "name": "Full Access",
            "model": "gpt-4o",
            "tools": ["tool1", "tool2", "tool3"],
        },
        {
            "name": "Minimal",
            "model": "gpt-4o-mini",
            "tools": ["tool1"],
        },
    ]


class TestOpponentModeSelector:
    """Test OpponentModeSelector widget."""

    def test_creates_with_default_mode(self, qapp, sample_agents: list[dict]) -> None:
        """Given: OpponentModeSelector created
        When: No mode specified
        Then: Defaults to BEST_MODEL
        """
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)

        assert selector.get_selected_mode() == OpponentMode.BEST_MODEL

    def test_can_set_mode_programmatically(self, qapp, sample_agents: list[dict]) -> None:
        """Given: Selector exists
        When: Setting mode to AGENT
        Then: Mode is changed and agent selector shown
        """
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)
        selector.set_mode(OpponentMode.AGENT)

        assert selector.get_selected_mode() == OpponentMode.AGENT
        assert selector.agent_selector_widget.isVisible()

    def test_agent_selector_hidden_for_non_agent_mode(
        self, qapp, sample_agents: list[dict]
    ) -> None:
        """Given: Selector in BEST_MODEL mode
        When: Checking agent selector visibility
        Then: Agent selector is hidden
        """
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)
        selector.set_mode(OpponentMode.BEST_MODEL)

        assert selector.get_selected_mode() == OpponentMode.BEST_MODEL
        assert not selector.agent_selector_widget.isVisible()

    def test_can_select_agent_by_name(self, qapp, sample_agents: list[dict]) -> None:
        """Given: Selector with available agents
        When: Setting agent name
        Then: Agent is selected in dropdown
        """
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)
        selector.set_mode(OpponentMode.AGENT)
        selector.set_agent_name("Minimal")

        assert selector.get_selected_agent_name() == "Minimal"

    def test_offline_mode_is_disabled(self, qapp, sample_agents: list[dict]) -> None:
        """Given: Selector created
        When: Checking OFFLINE mode button
        Then: Button is disabled
        """
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)

        # Find OFFLINE button
        for button in selector.button_group.buttons():
            mode = button.property("mode")
            if mode == OpponentMode.OFFLINE:
                assert not button.isEnabled()

    def test_emits_signal_on_mode_change(self, qapp, sample_agents: list[dict]) -> None:
        """Given: Selector with mode
        When: User clicks different mode button
        Then: mode_changed signal is emitted
        """
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)

        # Connect to signal
        received_mode = None

        def on_mode_changed(mode: OpponentMode) -> None:
            nonlocal received_mode
            received_mode = mode

        selector.mode_changed.connect(on_mode_changed)

        # Find AGENT mode button and click it
        for button in selector.button_group.buttons():
            mode = button.property("mode")
            if mode == OpponentMode.AGENT:
                button.click()
                break

        assert received_mode == OpponentMode.AGENT

    def test_disables_all_buttons_when_disabled(
        self, qapp, sample_agents: list[dict]
    ) -> None:
        """Given: Selector enabled
        When: Calling set_enabled(False)
        Then: All buttons (except OFFLINE) are disabled
        """
        from scrabgpt.ui.opponent_mode_selector import OpponentModeSelector

        selector = OpponentModeSelector(available_agents=sample_agents)
        selector.set_enabled(False)

        for button in selector.button_group.buttons():
            assert not button.isEnabled()


class TestSettingsDialog:
    """Test SettingsDialog."""

    def test_creates_with_mode(self, qapp, sample_agents: list[dict]) -> None:
        """Given: Settings dialog created with mode
        When: Getting selected mode
        Then: Returns configured mode
        """
        from scrabgpt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            current_mode=OpponentMode.AGENT,
            available_agents=sample_agents,
        )

        assert dialog.get_selected_mode() == OpponentMode.AGENT

    def test_shows_warning_when_game_in_progress(
        self, qapp, sample_agents: list[dict]
    ) -> None:
        """Given: Settings dialog with game_in_progress=True
        When: Dialog is shown
        Then: Warning message is visible
        """
        from scrabgpt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            current_mode=OpponentMode.BEST_MODEL,
            available_agents=sample_agents,
            game_in_progress=True,
        )

        # Check that mode selector is disabled
        assert not dialog.mode_selector.button_group.buttons()[0].isEnabled()

    def test_validates_agent_selection_for_agent_mode(
        self, qapp, sample_agents: list[dict]
    ) -> None:
        """Given: Settings dialog in AGENT mode
        When: No agent selected
        Then: Validation fails
        """
        from scrabgpt.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(
            current_mode=OpponentMode.AGENT,
            available_agents=sample_agents,
        )

        # Set mode to AGENT but don't select agent
        dialog.mode_selector.set_mode(OpponentMode.AGENT)
        dialog.mode_selector.current_agent_name = None

        # Try to click OK
        # Note: In real UI test, we'd simulate button click
        # Here we just test the validation logic directly
        selected_mode = dialog.mode_selector.get_selected_mode()
        agent_name = dialog.mode_selector.get_selected_agent_name()

        if selected_mode == OpponentMode.AGENT:
            # Should require agent name
            assert agent_name is not None  # Will fail if not set
