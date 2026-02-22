"""Opponent mode selector widget for Settings dialog."""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.opponent_mode import OpponentMode
from ..core.team_config import get_team_manager

log = logging.getLogger("scrabgpt.ui")


class OpponentModeSelector(QWidget):
    """Widget for selecting AI opponent mode with checkbox indicators."""

    mode_changed = Signal(OpponentMode)
    configure_google_requested = Signal()
    configure_openai_requested = Signal()
    configure_openrouter_requested = Signal()
    configure_novita_requested = Signal()
    configure_lmstudio_requested = Signal()
    configure_offline_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        available_agents: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(parent)
        # Legacy parameter retained for compatibility with callers/tests.
        del available_agents

        self.current_mode = OpponentMode.BEST_MODEL
        self.team_manager = get_team_manager()
        self.novita_desc_label: QLabel | None = None
        self.openrouter_desc_label: QLabel | None = None
        self.openai_desc_label: QLabel | None = None
        self._openai_models_preview: list[str] | None = None

        self._setup_ui()
        self.setVisible(True)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Režim AI Protivníka")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #e8f5e9; "
            "padding: 8px 0px;"
        )
        layout.addWidget(title)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(False)

        mode_order = [
            OpponentMode.GEMINI,
            OpponentMode.BEST_MODEL,
            OpponentMode.OPENROUTER,
            OpponentMode.NOVITA,
            OpponentMode.LMSTUDIO,
        ]
        for mode in mode_order:
            layout.addWidget(self._create_mode_option(mode))

        layout.addStretch()

    def _create_mode_option(self, mode: OpponentMode) -> QWidget:
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
        if mode == self.current_mode:
            checkbox.setChecked(True)

        self.button_group.addButton(checkbox)
        checkbox.toggled.connect(
            lambda checked, btn=checkbox: self._on_mode_toggled(btn, checked)
        )
        layout.addWidget(checkbox)

        desc_layout = QHBoxLayout()
        desc_layout.setSpacing(8)
        desc_layout.setContentsMargins(26, 0, 0, 0)

        if mode == OpponentMode.NOVITA:
            desc = QLabel()
            desc.setWordWrap(True)
            desc.setTextFormat(Qt.TextFormat.RichText)
            desc.setStyleSheet("font-size: 12px; color: #b6e0bd;")
            desc.setMinimumHeight(60)
            self.novita_desc_label = desc
            self._update_novita_description()
        elif mode == OpponentMode.OPENROUTER:
            desc = QLabel()
            desc.setWordWrap(True)
            desc.setTextFormat(Qt.TextFormat.RichText)
            desc.setStyleSheet("font-size: 12px; color: #b6e0bd;")
            desc.setMinimumHeight(60)
            self.openrouter_desc_label = desc
            self._update_openrouter_description()
        elif mode == OpponentMode.BEST_MODEL:
            desc = QLabel()
            desc.setWordWrap(True)
            desc.setTextFormat(Qt.TextFormat.RichText)
            desc.setStyleSheet("font-size: 12px; color: #b6e0bd;")
            desc.setMinimumHeight(60)
            self.openai_desc_label = desc
            self._update_openai_description()
        else:
            desc = QLabel(mode.description_sk)
            desc.setWordWrap(True)
            desc.setStyleSheet("font-size: 12px; color: #b6e0bd;")
            desc.setMinimumHeight(60)

        desc_layout.addWidget(desc, 1)

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
        elif mode == OpponentMode.BEST_MODEL:
            config_btn.clicked.connect(lambda: self.configure_openai_requested.emit())
        elif mode == OpponentMode.LMSTUDIO:
            config_btn.clicked.connect(lambda: self.configure_lmstudio_requested.emit())
        else:
            config_btn.clicked.connect(lambda: self.configure_google_requested.emit())

        desc_layout.addWidget(config_btn)
        layout.addLayout(desc_layout)

        return container

    def _on_mode_toggled(self, button: QCheckBox, checked: bool) -> None:
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
        self.mode_changed.emit(mode)
        log.info("Opponent mode changed to: %s", mode.value)

    def get_selected_mode(self) -> OpponentMode:
        return self.current_mode

    @staticmethod
    def _parse_openai_models(raw: str) -> list[str]:
        models: list[str] = []
        for item in raw.split(","):
            model_id = item.strip()
            if not model_id or model_id in models:
                continue
            models.append(model_id)
        return models

    def _update_novita_description(self) -> None:
        if self.novita_desc_label is None:
            return

        selection = self.team_manager.load_provider_selection("novita")
        model_ids = selection[0] if selection else []
        if model_ids:
            header_html = (
                '<span style="font-size: 14px; font-weight: bold; color: #ffffff;">'
                "Vybrané Novita modely</span>"
            )
            models_html = "<br/>".join(
                f'<span style="font-size: 11px; color: #9ad0a2;">• {model_id}</span>'
                for model_id in model_ids
            )
            self.novita_desc_label.setText(f"{header_html}<br/>{models_html}")
            return

        self.novita_desc_label.setText(
            '<span style="color: #b6e0bd;">Žiadne Novita modely nie sú nakonfigurované. '
            'Klikni na "Nastaviť" pre výber modelov.</span>'
        )

    def refresh_novita_team_info(self) -> None:
        self._update_novita_description()

    def _update_openrouter_description(self) -> None:
        if self.openrouter_desc_label is None:
            return

        selection = self.team_manager.load_provider_selection("openrouter")
        model_ids = selection[0] if selection else []
        if model_ids:
            header_html = (
                '<span style="font-size: 14px; font-weight: bold; color: #ffffff;">'
                "Vybrané OpenRouter modely</span>"
            )
            models_html = "<br/>".join(
                f'<span style="font-size: 11px; color: #9ad0a2;">• {model_id}</span>'
                for model_id in model_ids
            )
            self.openrouter_desc_label.setText(f"{header_html}<br/>{models_html}")
            return

        self.openrouter_desc_label.setText(
            '<span style="color: #b6e0bd;">Žiadne OpenRouter modely nie sú nakonfigurované. '
            'Klikni na "Nastaviť" pre výber modelov.</span>'
        )

    def refresh_openrouter_team_info(self) -> None:
        self._update_openrouter_description()

    def _update_openai_description(self) -> None:
        if self.openai_desc_label is None:
            return

        model_ids = list(self._openai_models_preview or [])
        if not model_ids:
            model_ids = self._parse_openai_models(os.getenv("OPENAI_MODELS", ""))

        if model_ids:
            header_html = (
                '<span style="font-size: 14px; font-weight: bold; color: #ffffff;">'
                "Vybrané OpenAI modely</span>"
            )
            models_html = "<br/>".join(
                f'<span style="font-size: 11px; color: #9ad0a2;">• {model_id}</span>'
                for model_id in model_ids
            )
            self.openai_desc_label.setText(f"{header_html}<br/>{models_html}")
            return

        self.openai_desc_label.setText(
            '<span style="color: #b6e0bd;">Žiadne OpenAI modely nie sú nakonfigurované. '
            'Klikni na "Nastaviť" pre výber modelov.</span>'
        )

    def set_openai_models_preview(self, models: list[str]) -> None:
        normalized = [
            model.strip()
            for model in models
            if isinstance(model, str) and model.strip()
        ]
        self._openai_models_preview = normalized or None
        self._update_openai_description()

    def refresh_openai_models_info(self) -> None:
        self._openai_models_preview = None
        self._update_openai_description()

    def set_mode(self, mode: OpponentMode) -> None:
        for button in self.button_group.buttons():
            button.blockSignals(True)
            button.setChecked(button.property("mode") == mode)
            button.blockSignals(False)
        self.current_mode = mode

    def set_enabled(self, enabled: bool) -> None:
        for button in self.button_group.buttons():
            mode = button.property("mode")
            button.setEnabled(enabled and mode.is_available)

    def get_selected_agent_name(self) -> str | None:
        # Legacy interface kept for compatibility with existing callers.
        return None

    def set_agent_name(self, agent_name: str) -> None:
        # Legacy no-op.
        del agent_name
