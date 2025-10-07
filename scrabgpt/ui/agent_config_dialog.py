"""Agent configuration dialog for selecting AI agent."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QWidget, QFrame,
)

log = logging.getLogger("scrabgpt.ui")


class AgentConfigDialog(QDialog):
    """Dialog for selecting AI agent with tool configuration."""
    
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        available_agents: list[dict] | None = None,
        current_agent_name: Optional[str] = None,
    ) -> None:
        """Initialize agent configuration dialog.
        
        Args:
            parent: Parent widget
            available_agents: List of available agent configurations
            current_agent_name: Currently selected agent name
        """
        super().__init__(parent)
        
        self.available_agents = available_agents or []
        self.current_agent_name = current_agent_name
        self.selected_agent_name: Optional[str] = None
        
        self.setWindowTitle("Nastavenie Agenta")
        self.setModal(True)
        self.resize(600, 400)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup UI components."""
        self.setStyleSheet(
            "QDialog { background-color: #0f1a12; color: #e8f5e9; }"
            "QLabel { color: #e8f5e9; }"
        )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Title
        title = QLabel("🤖 Nastavenie AI Agenta")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #e8f5e9; "
            "padding: 8px 0px;"
        )
        layout.addWidget(title)
        
        # Info box - moved from main settings
        info = QLabel(
            "💡 Tip: Agent mód je experimentálny. Agent sa sám rozhoduje, "
            "ktoré nástroje použije na návrh svojho ťahu. Rôzni agenti majú "
            "prístup k rôznym nástrojom - experimentujte a porovnajte výkon."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background: #1a2f1f; color: #e8f5e9; padding: 12px; "
            "border: 1px solid #2f5c39; border-radius: 6px; font-size: 11px;"
        )
        layout.addWidget(info)
        
        # Agent selector section
        selector_frame = QFrame()
        selector_frame.setStyleSheet(
            "QFrame { "
            "background: #0a0a0a; border: 1px solid #2f5c39; border-radius: 6px; "
            "padding: 16px; "
            "}"
        )
        
        selector_layout = QVBoxLayout(selector_frame)
        selector_layout.setSpacing(12)
        
        # Label
        label = QLabel("Vyber agenta:")
        label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #e8f5e9;"
        )
        selector_layout.addWidget(label)
        
        # Agent dropdown
        self.agent_combo = QComboBox()
        self.agent_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.agent_combo.setStyleSheet(
            "QComboBox { "
            "font-size: 13px; color: #e8f5e9; padding: 8px 12px; "
            "background: #0f1a12; border: 1px solid #2f5c39; border-radius: 4px; "
            "} "
            "QComboBox::drop-down { border: none; width: 24px; } "
            "QComboBox QAbstractItemView { "
            "font-size: 13px; background: #0f1a12; color: #e8f5e9; "
            "selection-background-color: #295c33; border: 1px solid #2f5c39; "
            "}"
        )
        
        selector_layout.addWidget(self.agent_combo)
        
        # Agent details - CREATE BEFORE populating combo (to avoid signal errors)
        self.agent_details = QLabel()
        self.agent_details.setWordWrap(True)
        self.agent_details.setStyleSheet(
            "font-size: 11px; color: #9ad0a2; padding: 8px; "
            "background: #0a0a0a; border-radius: 4px;"
        )
        selector_layout.addWidget(self.agent_details)
        
        # Populate with available agents AFTER creating details widget
        if self.available_agents:
            for agent in self.available_agents:
                name = agent.get("name", "Unknown")
                tool_count = len(agent.get("tools", []))
                model = agent.get("model", "unknown")
                self.agent_combo.addItem(f"{name} ({tool_count} nástrojov, {model})")
            
            # Select current agent if specified
            if self.current_agent_name:
                for i, agent in enumerate(self.available_agents):
                    if agent.get("name") == self.current_agent_name:
                        self.agent_combo.setCurrentIndex(i)
                        self.selected_agent_name = self.current_agent_name
                        break
            
            # Set default selection
            if not self.current_agent_name and self.available_agents:
                self.selected_agent_name = self.available_agents[0].get("name")
        else:
            self.agent_combo.addItem("Žiadne agenty nenájdené")
            self.agent_combo.setEnabled(False)
        
        # Connect signal AFTER populating to avoid initial trigger issues
        self.agent_combo.currentTextChanged.connect(self._on_agent_changed)
        
        # Update details for current selection
        self._update_agent_details()
        
        layout.addWidget(selector_frame)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        
        button_layout.addStretch()
        
        cancel_btn = QPushButton("✗ Zrušiť")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(
            "QPushButton { "
            "padding: 10px 20px; font-size: 13px; border-radius: 6px; "
            "background-color: #182c1d; color: #b6e0bd; border: 1px solid #2f5c39; "
            "} "
            "QPushButton:hover { background-color: #213f29; border-color: #4caf50; } "
            "QPushButton:pressed { background-color: #152820; }"
        )
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("✓ Použiť")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setStyleSheet(
            "QPushButton { "
            "padding: 10px 20px; font-size: 13px; font-weight: bold; border-radius: 6px; "
            "background-color: #2e7d32; color: #e8f5e9; border: 2px solid #4caf50; "
            "} "
            "QPushButton:hover { background-color: #388e3c; } "
            "QPushButton:pressed { background-color: #1b5e20; }"
        )
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
    
    def _on_agent_changed(self, text: str) -> None:
        """Handle agent selection change.
        
        Args:
            text: Selected combo box text
        """
        if not self.available_agents:
            return
        
        # Extract agent name from combo text (before the parentheses)
        agent_name = text.split(" (")[0] if " (" in text else text
        
        # Find agent config
        for agent in self.available_agents:
            if agent.get("name") == agent_name:
                self.selected_agent_name = agent_name
                self._update_agent_details()
                log.info("Selected agent: %s", agent_name)
                break
    
    def _update_agent_details(self) -> None:
        """Update agent details display."""
        if not self.selected_agent_name or not self.available_agents:
            self.agent_details.setText("Vyberte agenta...")
            return
        
        # Find selected agent
        selected_agent = None
        for agent in self.available_agents:
            if agent.get("name") == self.selected_agent_name:
                selected_agent = agent
                break
        
        if not selected_agent:
            self.agent_details.setText("")
            return
        
        # Build details text
        description = selected_agent.get("description", "")
        tools = selected_agent.get("tools", [])
        model = selected_agent.get("model", "unknown")
        
        details_html = f"<b>Model:</b> {model}<br>"
        details_html += f"<b>Počet nástrojov:</b> {len(tools)}<br>"
        if description:
            details_html += f"<b>Popis:</b> {description}<br>"
        
        # Show some tools
        if tools:
            tools_preview = ", ".join(tools[:5])
            if len(tools) > 5:
                tools_preview += f" + {len(tools) - 5} ďalších"
            details_html += f"<b>Nástroje:</b> {tools_preview}"
        
        self.agent_details.setText(details_html)
    
    def get_selected_agent_name(self) -> Optional[str]:
        """Get selected agent name.
        
        Returns:
            Selected agent name or None
        """
        return self.selected_agent_name
