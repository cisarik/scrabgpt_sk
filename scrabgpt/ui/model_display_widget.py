"""Widget for displaying current OpenAI model with styling."""

from __future__ import annotations

import logging
import os
from typing import Optional

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtGui import QFont

log = logging.getLogger("scrabgpt.ui.model_display")


class ModelDisplayWidget(QWidget):
    """Widget that displays current OpenAI model with bold green styling.
    
    Shows: "Current AI Model: <model>" (in bold green)
    
    Also provides a "Check for Best" button to manually trigger agent check.
    """
    
    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize model display widget.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        
        self._setup_ui()
        self._update_display()
    
    def _setup_ui(self) -> None:
        """Setup UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)
        
        # Label text
        self.label_text = QLabel("Aktuálny AI Model:")
        self.label_text.setStyleSheet(
            "color: #b6e0bd; font-size: 11px;"
        )
        layout.addWidget(self.label_text)
        
        # Model name (bold green)
        self.label_model = QLabel("loading...")
        font = QFont()
        font.setBold(True)
        font.setPointSize(11)
        self.label_model.setFont(font)
        self.label_model.setStyleSheet(
            "color: #4caf50; font-weight: bold;"
        )
        layout.addWidget(self.label_model)
        
        layout.addStretch()
        
        # "Nastavit Model" button
        self.btn_check = QPushButton("⚙️ Nastaviť Model")
        self.btn_check.setStyleSheet(
            "QPushButton { "
            "background: #2a3a4a; color: #c8c8c8; border: 1px solid #404040; "
            "border-radius: 4px; padding: 6px 12px; font-size: 11px; "
            "} "
            "QPushButton:hover { background: #3a4a5a; border-color: #5a9fd4; } "
            "QPushButton:pressed { background: #1a2a3a; }"
        )
        self.btn_check.clicked.connect(self._on_check_clicked)
        self.btn_check.setToolTip(
            "Otvoriť inteligentný výber modelu s agentom"
        )
        layout.addWidget(self.btn_check)
    
    def _update_display(self) -> None:
        """Update display with current model from environment."""
        selected_models = [
            model.strip()
            for model in os.getenv("OPENAI_MODELS", "").split(",")
            if model.strip()
        ]
        if not selected_models:
            selected_models = ["gpt-5.2"]

        primary = selected_models[0]
        suffix = f" (+{len(selected_models) - 1})" if len(selected_models) > 1 else ""
        self.label_model.setText(f"{primary}{suffix}")
        
        # Update tooltip with details
        auto_update = os.getenv("OPENAI_BEST_MODEL_AUTO_UPDATE", "false")
        tooltip = f"Aktuálne OpenAI modely: {', '.join(selected_models)}\n"
        tooltip += f"Auto-update: {auto_update}"
        self.label_model.setToolTip(tooltip)
    
    def _on_check_clicked(self) -> None:
        """Handle model setup button click."""
        from .model_selector_dialog import ModelSelectorDialog
        
        log.info("Model selector dialog requested")
        
        # Open model selector dialog
        dialog = ModelSelectorDialog(parent=self)
        
        if dialog.exec() == ModelSelectorDialog.DialogCode.Accepted:
            selected_model = dialog.get_selected_model()
            
            if selected_model:
                # Update .env file
                from scrabgpt.ai.model_auto_updater import update_env_file
                
                if update_env_file(selected_model):
                    from PySide6.QtWidgets import QMessageBox
                    
                    QMessageBox.information(
                        self,
                        "Model Nastavený",
                        f"Model bol nastavený na:\n{selected_model}\n\n"
                        "Zmeny sa prejavia po reštarte aplikácie."
                    )
                    self._update_display()
                else:
                    from PySide6.QtWidgets import QMessageBox
                    
                    QMessageBox.warning(
                        self,
                        "Chyba",
                        "Nepodarilo sa aktualizovať .env súbor."
                    )
    
    def refresh(self) -> None:
        """Refresh display (call after model change)."""
        self._update_display()
