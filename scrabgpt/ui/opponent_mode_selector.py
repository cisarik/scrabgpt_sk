"""Opponent mode selector widget for Settings dialog."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox,
    QButtonGroup, QLabel, QFrame, QComboBox, QPushButton,
)

from ..core.opponent_mode import OpponentMode
from ..core.team_config import get_team_manager

log = logging.getLogger("scrabgpt.ui")


class OpponentModeSelector(QWidget):
    """Widget for selecting AI opponent mode with checkbox indicators."""
    
    mode_changed = Signal(OpponentMode)
    agent_changed = Signal(str)  # Agent name
    configure_google_requested = Signal()  # Request to configure Google model
    configure_openrouter_requested = Signal()  # Request to configure OpenRouter models
    configure_novita_requested = Signal()  # Request to configure Novita models
    configure_agent_requested = Signal()  # Request to configure AI agent
    configure_offline_requested = Signal()  # Deprecated - kept for compatibility
    
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        available_agents: list[dict[str, str]] | None = None,
    ) -> None:
        """Initialize opponent mode selector.
        
        Args:
            parent: Parent widget
            available_agents: List of agent configurations
        """
        super().__init__(parent)
        
        self.available_agents = available_agents or []
        self.current_mode = OpponentMode.BEST_MODEL
        self.current_agent_name: Optional[str] = None
        self.team_manager = get_team_manager()
        self.novita_desc_label: QLabel | None = None
        self.openrouter_desc_label: QLabel | None = None
        
        self._setup_ui()
        
        # Ensure widget is properly set up for visibility (needed for testing)
        self.setVisible(True)
    
    def _setup_ui(self) -> None:
        """Setup UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title = QLabel("Režim AI Protivníka")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #e8f5e9; "
            "padding: 8px 0px;"
        )
        layout.addWidget(title)
        
        # Button group for mode toggles
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(False)
        
        # Mode checkboxes - include Google/Gemini
        mode_order = [
            OpponentMode.GEMINI,
            OpponentMode.BEST_MODEL,
            OpponentMode.OPENROUTER,
            OpponentMode.NOVITA,
            OpponentMode.AGENT,
        ]
        
        for mode in mode_order:
            mode_widget = self._create_mode_option(mode)
            layout.addWidget(mode_widget)
        
        # Agent selector widget (shown only for AGENT mode)
        self.agent_selector_widget = self._create_agent_selector()
        layout.addWidget(self.agent_selector_widget)
        self._update_agent_selector_visibility()
        
        layout.addStretch()
    
    def _create_mode_option(self, mode: OpponentMode) -> QWidget:
        """Create a mode option with checkbox and description.
        
        Args:
            mode: Opponent mode
        
        Returns:
            Widget containing radio button and description
        """
        container = QFrame()
        container.setFrameShape(QFrame.Shape.StyledPanel)
        container.setStyleSheet(
            "QFrame { "
            "background: #0a0a0a; border: 1px solid #2f5c39; border-radius: 6px; "
            "padding: 10px; "
            "} "
            "QFrame:hover { background: #151515; border-color: #4caf50; }"
        )
        
        layout = QVBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Checkbox with mode name
        checkbox = QCheckBox(mode.display_name_sk)
        checkbox.setProperty("mode", mode)
        checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        checkbox.setStyleSheet(
            "QCheckBox { "
            "font-size: 13px; font-weight: bold; color: #e8f5e9; "
            "spacing: 8px; "
            "} "
            "QCheckBox::indicator { width: 18px; height: 18px; } "
            "QCheckBox::indicator:unchecked { "
            "border: 2px solid #4caf50; border-radius: 4px; background: #132418; "
            "} "
            "QCheckBox::indicator:checked { "
            "border: 2px solid #4caf50; border-radius: 4px; "
            "background: #4caf50; "
            "}"
        )
        checkbox.setToolTip(mode.description_sk)
        
        # Set default selection
        if mode == self.current_mode:
            checkbox.setChecked(True)

        self.button_group.addButton(checkbox)
        checkbox.toggled.connect(
            lambda checked, btn=checkbox: self._on_mode_toggled(btn, checked)
        )
        layout.addWidget(checkbox)
        
        # Description with optional button for OpenRouter, Novita, or Agent
        if mode in (OpponentMode.OPENROUTER, OpponentMode.NOVITA, OpponentMode.AGENT, OpponentMode.GEMINI):
            desc_layout = QHBoxLayout()
            desc_layout.setSpacing(8)
            desc_layout.setContentsMargins(26, 0, 0, 0)
            
            # For Novita and OpenRouter, show dynamic team info; for others, show static description
            if mode == OpponentMode.NOVITA:
                desc = QLabel()
                desc.setWordWrap(True)
                desc.setTextFormat(Qt.TextFormat.RichText)
                desc.setStyleSheet("font-size: 12px; color: #b6e0bd;")
                desc.setMinimumHeight(60)
                self.novita_desc_label = desc  # Store reference for updates
                self._update_novita_description()  # Set initial text
            elif mode == OpponentMode.OPENROUTER:
                desc = QLabel()
                desc.setWordWrap(True)
                desc.setTextFormat(Qt.TextFormat.RichText)
                desc.setStyleSheet("font-size: 12px; color: #b6e0bd;")
                desc.setMinimumHeight(60)
                self.openrouter_desc_label = desc  # Store reference for updates
                self._update_openrouter_description()  # Set initial text
            else:
                desc = QLabel(mode.description_sk)
                desc.setWordWrap(True)
                desc.setStyleSheet("font-size: 12px; color: #b6e0bd;")
                desc.setMinimumHeight(60)
            
            desc_layout.addWidget(desc, 1)
            
            # "Nastaviť" button
            config_btn = QPushButton("Nastaviť")
            config_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            config_btn.setStyleSheet(
                "QPushButton { "
                "background: #2e7d32; color: #e8f5e9; border: 1px solid #4caf50; "
                "border-radius: 4px; padding: 6px 12px; font-size: 11px; font-weight: bold; "
                "} "
                "QPushButton:hover { background: #388e3c; } "
                "QPushButton:pressed { background: #1b5e20; }"
            )
            
            if mode == OpponentMode.OPENROUTER:
                config_btn.clicked.connect(lambda: self.configure_openrouter_requested.emit())
            elif mode == OpponentMode.NOVITA:
                config_btn.clicked.connect(lambda: self.configure_novita_requested.emit())
            elif mode == OpponentMode.AGENT:
                config_btn.clicked.connect(lambda: self.configure_agent_requested.emit())
            else:  # GEMINI/Google
                config_btn.clicked.connect(lambda: self.configure_google_requested.emit())
            
            desc_layout.addWidget(config_btn)
            
            layout.addLayout(desc_layout)
        else:
            # Description - BIGGER font size
            desc = QLabel(mode.description_sk)
            desc.setWordWrap(True)
            desc.setStyleSheet(
                "font-size: 12px; color: #b6e0bd; padding-left: 26px;"
            )
            layout.addWidget(desc)
        
        return container
    
    def _create_agent_selector(self) -> QWidget:
        """Create agent selector dropdown.
        
        Returns:
            Widget containing agent selector
        """
        container = QFrame()
        container.setFrameShape(QFrame.Shape.StyledPanel)
        container.setStyleSheet(
            "QFrame { "
            "background: #0a0a0a; border: 1px solid #2f5c39; border-radius: 6px; "
            "padding: 10px; "
            "}"
        )
        
        layout = QVBoxLayout(container)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Label
        label = QLabel("Vyberte agenta:")
        label.setStyleSheet("font-size: 12px; font-weight: bold; color: #b6e0bd;")
        layout.addWidget(label)
        
        # Combo box for agent selection
        self.agent_combo = QComboBox()
        self.agent_combo.setStyleSheet(
            "QComboBox { "
            "background: #132418; color: #e8f5e9; border: 1px solid #4caf50; "
            "border-radius: 4px; padding: 6px; font-size: 12px; "
            "} "
            "QComboBox:hover { background: #1a3020; } "
            "QComboBox::drop-down { border: none; } "
            "QComboBox::down-arrow { "
            "image: none; border-left: 4px solid transparent; "
            "border-right: 4px solid transparent; border-top: 6px solid #4caf50; "
            "margin-right: 8px; "
            "}"
        )
        
        # Populate with available agents
        for agent in self.available_agents:
            self.agent_combo.addItem(agent["name"])
        
        # Set current agent if exists, otherwise select first if available
        if self.current_agent_name:
            index = self.agent_combo.findText(self.current_agent_name)
            if index >= 0:
                self.agent_combo.setCurrentIndex(index)
        elif self.available_agents:
            # Select first agent by default
            self.agent_combo.setCurrentIndex(0)
            self.current_agent_name = self.available_agents[0]["name"]
        
        # Connect change signal
        self.agent_combo.currentTextChanged.connect(self._on_agent_changed)
        
        layout.addWidget(self.agent_combo)
        
        return container
    
    def _update_agent_selector_visibility(self) -> None:
        """Update visibility of agent selector based on current mode."""
        is_agent_mode = self.current_mode == OpponentMode.AGENT
        if is_agent_mode:
            self.agent_selector_widget.show()
        else:
            self.agent_selector_widget.hide()
    
    def _on_agent_changed(self, agent_name: str) -> None:
        """Handle agent selection change.
        
        Args:
            agent_name: Selected agent name
        """
        self.current_agent_name = agent_name
        self.agent_changed.emit(agent_name)
        log.info("Agent changed to: %s", agent_name)
    
    def set_agent_name(self, agent_name: str) -> None:
        """Set agent name programmatically.
        
        Args:
            agent_name: Agent name to select
        """
        self.current_agent_name = agent_name
        
        # Update combo box if it exists
        if hasattr(self, 'agent_combo'):
            index = self.agent_combo.findText(agent_name)
            if index >= 0:
                self.agent_combo.setCurrentIndex(index)
    
    def _on_mode_toggled(self, button: QCheckBox, checked: bool) -> None:
        """Handle mode checkbox changes while keeping a single active mode."""
        mode = button.property("mode")
        if mode is None:
            return

        if not checked:
            if self.current_mode == mode:
                button.blockSignals(True)
                button.setChecked(True)
                button.blockSignals(False)
            return

        for other in self.button_group.buttons():
            if other is button:
                continue
            if other.isChecked():
                other.blockSignals(True)
                other.setChecked(False)
                other.blockSignals(False)

        self.current_mode = mode

        # Update agent selector visibility
        self._update_agent_selector_visibility()

        # Emit signal
        self.mode_changed.emit(mode)

        log.info("Opponent mode changed to: %s", mode.value)
    
    def get_selected_mode(self) -> OpponentMode:
        """Get currently selected opponent mode.
        
        Returns:
            Selected opponent mode
        """
        return self.current_mode
    
    def get_selected_agent_name(self) -> Optional[str]:
        """Get currently selected agent name (if AGENT mode).
        
        Returns:
            Agent name or None
        """
        if self.current_mode == OpponentMode.AGENT:
            # If combo box exists and has items, get current selection
            if hasattr(self, 'agent_combo') and self.agent_combo.count() > 0:
                current_text = self.agent_combo.currentText()
                if current_text:
                    return current_text
            return self.current_agent_name
        return None
    
    def _update_novita_description(self) -> None:
        """Update Novita description to show active team info."""
        if self.novita_desc_label is None:
            return
        
        # Load active team
        team = self.team_manager.load_active_team_config("novita")
        
        if team and team.model_ids:
            # Show team name in bold white, larger font
            team_name_html = f'<span style="font-size: 14px; font-weight: bold; color: #ffffff;">{team.name}</span>'
            
            # Show model IDs below in smaller gray text
            models_html = '<br/>'.join([
                f'<span style="font-size: 11px; color: #9ad0a2;">• {model_id}</span>'
                for model_id in team.model_ids
            ])
            
            full_html = f'{team_name_html}<br/>{models_html}'
            self.novita_desc_label.setText(full_html)
        else:
            # No team configured - show default message
            self.novita_desc_label.setText(
                '<span style="color: #b6e0bd;">Žiadny team nie je nakonfigurovaný. '
                'Klikni na "Nastaviť" pre výber modelov.</span>'
            )
    
    def refresh_novita_team_info(self) -> None:
        """Refresh Novita team info (call after team changes)."""
        self._update_novita_description()
    
    def _update_openrouter_description(self) -> None:
        """Update OpenRouter description to show active team info."""
        if self.openrouter_desc_label is None:
            return
        
        # Load active team
        team = self.team_manager.load_active_team_config("openrouter")
        
        if team and team.model_ids:
            # Show team name in bold white, larger font
            team_name_html = f'<span style="font-size: 14px; font-weight: bold; color: #ffffff;">{team.name}</span>'
            
            # Show model IDs below in smaller gray text
            models_html = '<br/>'.join([
                f'<span style="font-size: 11px; color: #9ad0a2;">• {model_id}</span>'
                for model_id in team.model_ids
            ])
            
            full_html = f'{team_name_html}<br/>{models_html}'
            self.openrouter_desc_label.setText(full_html)
        else:
            # No team configured - show default message
            self.openrouter_desc_label.setText(
                '<span style="color: #b6e0bd;">Žiadny team nie je nakonfigurovaný. '
                'Klikni na "Nastaviť" pre výber modelov.</span>'
            )
    
    def refresh_openrouter_team_info(self) -> None:
        """Refresh OpenRouter team info (call after team changes)."""
        self._update_openrouter_description()
    
    def set_mode(self, mode: OpponentMode) -> None:
        """Set opponent mode programmatically.
        
        Args:
            mode: Mode to set
        """
        for button in self.button_group.buttons():
            button.blockSignals(True)
            button.setChecked(button.property("mode") == mode)
            button.blockSignals(False)
        self.current_mode = mode
        self._update_agent_selector_visibility()
    

    
    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the selector.
        
        Args:
            enabled: Whether to enable the selector
        """
        for button in self.button_group.buttons():
            mode = button.property("mode")
            button.setEnabled(enabled and mode.is_available)
