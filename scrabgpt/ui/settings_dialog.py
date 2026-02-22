"""Settings dialog for game configuration."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Sequence, TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .app import MainWindow

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIntValidator, QMouseEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTabWidget, QWidget, QMessageBox, QFormLayout,
    QLineEdit, QCheckBox, QComboBox, QSpinBox, QDialogButtonBox,
)

from ..core.opponent_mode import OpponentMode
from ..core.variant_store import (
    VariantDefinition,
    get_active_variant_slug,
    list_installed_variants,
    load_variant,
    set_active_variant_slug,
)
from ..ai.variants import (
    LanguageInfo,
    get_languages_for_ui,
    match_language,
)
from ..ai.client import OpenAIClient
from ..ai.variant_agent import (
    BootstrapResult,
    VariantBootstrapAgent,
    VariantBootstrapProgress,
)
from .agents_dialog import AsyncAgentWorker, AgentActivityWidget
from .settings_dialog_helper import update_lang_status_animation
from .opponent_mode_selector import OpponentModeSelector
from .ai_config import AIConfigDialog

log = logging.getLogger("scrabgpt.ui")

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = str(ROOT_DIR / ".env")
EUR_PER_TOKEN = 0.00000186  # 1 token ≈ 0.00000186 EUR


class ClickableLabel(QLabel):
    """Label that emits clicked signal when clicked."""
    
    clicked = Signal()
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press event."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SettingsDialog(QDialog):
    """Settings dialog for game configuration."""
    
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        current_mode: OpponentMode | None = None,
        current_agent_name: Optional[str] = None,
        available_agents: list[dict[str, Any]] | None = None,
        game_in_progress: bool = False,
        ai_move_max_tokens: int = 3600,
        ai_tokens_from_env: bool = False,
        user_defined_ai_tokens: bool = False,
        repro_mode: bool = False,
        repro_seed: int = 0,
        active_tab_index: int = 0,
    ) -> None:
        """Initialize settings dialog.
        
        Args:
            parent: Parent widget
            current_mode: Current opponent mode
            current_agent_name: Legacy field (unused in LMStudio mode)
            available_agents: Legacy list (unused in LMStudio mode)
            game_in_progress: Whether a game is currently in progress
            ai_move_max_tokens: Max tokens for AI moves
            ai_tokens_from_env: Whether tokens from env
            user_defined_ai_tokens: Whether user defined tokens
        """
        super().__init__(parent)
        
        self.current_mode = current_mode or OpponentMode.BEST_MODEL
        self.current_agent_name = current_agent_name
        self.available_agents = available_agents or []
        self.game_in_progress = game_in_progress
        self.ai_move_max_tokens = ai_move_max_tokens
        self.ai_tokens_from_env = ai_tokens_from_env
        self.user_defined_ai_tokens = user_defined_ai_tokens
        self.repro_mode = repro_mode
        self.repro_seed = repro_seed
        self.active_tab_index = active_tab_index
        
        # Store OpenRouter config from nested dialog
        self.selected_openrouter_models: list[dict[str, Any]] = []
        self.openrouter_tokens: int = ai_move_max_tokens
        
        # Store Novita config from nested dialog
        self.selected_novita_models: list[dict[str, Any]] = []
        self.novita_tokens: int = ai_move_max_tokens

        # Store OpenAI model selection(s) for OpenAI mode
        self.selected_openai_models = self._load_openai_models_from_env()
        
        # Store Google model selection(s) for GEMINI mode
        self.selected_google_models = self._load_google_models_from_env()
        self.selected_google_model: str = self.selected_google_models[0]
        
        # API settings state
        self.selected_variant_slug = get_active_variant_slug()
        self._installed_variants: list[VariantDefinition] = []
        self._languages: list[LanguageInfo] = []
        
        # Language fetch animation state
        self._lang_dot_count = 0
        self._lang_status_timer: QTimer | None = None
        self._lang_current_status = ""
        
        self.setWindowTitle("⚙️ Nastavenia Hry")
        self.setModal(False)  # Non-modal - allow interaction with Agents dialog
        self.resize(700, 600)
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup UI components."""
        self.setStyleSheet(
            "QDialog { background-color: #0f1a12; color: #e8f5e9; }"
            "QLabel { color: #e8f5e9; }"
            "QTabWidget::pane { border: 1px solid #2f5c39; background: #0f1a12; }"
            "QTabBar::tab { "
            "background: #1a2f1f; color: #b6e0bd; padding: 8px 16px; "
            "border: 1px solid #2f5c39; margin-right: 2px; "
            "} "
            "QTabBar::tab:selected { "
            "background: #295c33; color: #e8f5e9; font-weight: bold; "
            "border-bottom: 2px solid #4caf50; "
            "} "
            "QTabBar::tab:hover { background: #213f29; }"
        )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Title
        title = QLabel("⚙️ Nastavenia Hry")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #e8f5e9; "
            "padding: 8px 0px;"
        )
        layout.addWidget(title)
        
        # Tab widget
        self.tabs = QTabWidget()
        
        # General tab (most important settings)
        general_tab = self._create_general_tab()
        self.tabs.addTab(general_tab, "🎮 Všeobecné")
        
        # AI Opponent tab
        ai_tab = self._create_ai_tab()
        self.tabs.addTab(ai_tab, "🤖 AI Protivník")
        
        # API Settings tab
        api_tab = self._create_api_tab()
        self.tabs.addTab(api_tab, "⚡ Nastavenia API")
        
        # Set active tab (safety clamp for stale indices from older builds)
        max_index = max(0, self.tabs.count() - 1)
        self.tabs.setCurrentIndex(max(0, min(self.active_tab_index, max_index)))
        
        layout.addWidget(self.tabs)
        
        # Agent status bar at bottom (hidden by default, clickable)
        self.lang_fetch_status = ClickableLabel("")
        self.lang_fetch_status.clicked.connect(self._on_status_bar_clicked)
        self.lang_fetch_status.setStyleSheet(
            "QLabel { "
            "color: #4caf50; font-size: 14px; font-weight: bold; "
            "padding: 12px 16px; background: #000000; "
            "border-top: 1px solid #2f5c39; "
            "} "
            "QLabel:hover { background: #0a0a0a; cursor: pointer; }"
        )
        self.lang_fetch_status.setVisible(False)
        self.lang_fetch_status.setWordWrap(True)
        self.lang_fetch_status.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.lang_fetch_status.setToolTip("Kliknite pre otvorenie okna s aktivitou agentov")
        layout.addWidget(self.lang_fetch_status)
        
        # Warning if game in progress
        if self.game_in_progress:
            warning = QLabel(
                "⚠️ Hra je v priebehu. Zmeny sa uplatnia až v novej hre."
            )
            warning.setWordWrap(True)
            warning.setStyleSheet(
                "background: #3d2a0f; color: #ffd54f; padding: 10px; "
                "border: 2px solid #ff9800; border-radius: 6px; font-weight: bold;"
            )
            layout.addWidget(warning)
        
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
        
        ok_btn = QPushButton("✓ Uložiť")
        ok_btn.clicked.connect(self._on_ok_clicked)
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
    
    def _create_ai_tab(self) -> QWidget:
        """Create AI opponent configuration tab.
        
        Returns:
            Widget with AI opponent settings
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Opponent mode selector
        self.mode_selector = OpponentModeSelector(
            parent=widget,
            available_agents=self.available_agents,
        )
        
        # Set current mode
        self.mode_selector.set_mode(self.current_mode)
        
        # Connect configuration signals
        self.mode_selector.configure_google_requested.connect(self._configure_google)
        self.mode_selector.configure_openai_requested.connect(self._configure_openai)
        self.mode_selector.configure_openrouter_requested.connect(self._configure_openrouter)
        self.mode_selector.configure_novita_requested.connect(self._configure_novita)
        self.mode_selector.configure_lmstudio_requested.connect(self._configure_offline)
        self.mode_selector.configure_offline_requested.connect(self._configure_offline)
        self.mode_selector.set_openai_models_preview(self.selected_openai_models)
        
        layout.addWidget(self.mode_selector)
        
        layout.addStretch()
        
        return widget
    
    def _on_ok_clicked(self) -> None:
        """Handle OK button click."""
        # Validate configuration
        selected_mode = self.mode_selector.get_selected_mode()
        if selected_mode == OpponentMode.BEST_MODEL and not self.selected_openai_models:
            QMessageBox.warning(
                self,
                "Chyba",
                "Prosím vyberte aspoň jeden OpenAI model.",
            )
            return
        # Accept dialog
        self.accept()
    
    def get_selected_mode(self) -> OpponentMode:
        """Get selected opponent mode.
        
        Returns:
            Selected opponent mode
        """
        return self.mode_selector.get_selected_mode()
    
    def get_selected_agent_name(self) -> Optional[str]:
        """Legacy getter kept for compatibility.
        
        Returns:
            Always None (Agent mode was replaced by LMStudio mode)
        """
        return self.mode_selector.get_selected_agent_name()
    
    def get_selected_openrouter_models(self) -> list[dict[str, Any]]:
        """Get selected OpenRouter models (if configured).
        
        Returns:
            List of selected model dicts
        """
        return self.selected_openrouter_models
    
    def get_selected_novita_models(self) -> list[dict[str, Any]]:
        """Get selected Novita models (if configured)."""
        return self.selected_novita_models

    def get_selected_openai_models(self) -> list[str]:
        """Get selected OpenAI models for OpenAI mode."""
        return list(self.selected_openai_models)

    def get_openrouter_tokens(self) -> int:
        """Get OpenRouter token limit (if configured).
        
        Returns:
            Token limit
        """
        return self.openrouter_tokens
    
    def get_novita_tokens(self) -> int:
        """Get Novita token limit (if configured)."""
        return self.novita_tokens
    
    def get_selected_google_model(self) -> str:
        """Get selected Google Gemini model for GEMINI mode."""
        if self.selected_google_models:
            return self.selected_google_models[0]
        return self.selected_google_model

    def get_selected_google_models(self) -> list[str]:
        """Get selected Google Gemini models for GEMINI mode."""
        return list(self.selected_google_models)

    @staticmethod
    def _parse_google_models(raw: str) -> list[str]:
        parsed: list[str] = []
        for item in raw.split(","):
            model = item.strip()
            if not model or model in parsed:
                continue
            parsed.append(model)
        return parsed

    def _load_google_models_from_env(self) -> list[str]:
        raw_models = (
            os.getenv("GEMINI_MODELS")
            or os.getenv("GOOGLE_GEMINI_MODELS")
            or ""
        ).strip()
        parsed = self._parse_google_models(raw_models)
        if parsed:
            return parsed

        fallback = (
            os.getenv("GEMINI_MODEL")
            or os.getenv("GOOGLE_GEMINI_MODEL")
            or "gemini-2.5-pro"
        ).strip()
        return [fallback or "gemini-2.5-pro"]

    @staticmethod
    def _parse_openai_models(raw: str) -> list[str]:
        parsed: list[str] = []
        for item in raw.split(","):
            model = item.strip()
            if not model or model in parsed:
                continue
            parsed.append(model)
        return parsed

    def _load_openai_models_from_env(self) -> list[str]:
        raw_models = (os.getenv("OPENAI_MODELS") or "").strip()
        parsed = self._parse_openai_models(raw_models)
        if parsed:
            return parsed
        return ["gpt-5.2"]
    
    def _configure_google(self) -> None:
        """Open Google Gemini model configuration dialog (multi-select)."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Google Modely")
        form = QFormLayout(dialog)
        form.setContentsMargins(14, 14, 14, 14)
        form.setSpacing(10)

        known_models: list[tuple[str, str]] = [
            ("Gemini 3.1 Pro (preview)", "gemini-3.1-pro-preview"),
            ("Gemini 3 Pro (preview)", "gemini-3-pro-preview"),
            ("Gemini 3 Flash (preview)", "gemini-3-flash-preview"),
            ("Gemini 2.5 Pro", "gemini-2.5-pro"),
            ("Gemini 2.5 Flash", "gemini-2.5-flash"),
        ]

        checks_container = QWidget(dialog)
        checks_layout = QVBoxLayout(checks_container)
        checks_layout.setContentsMargins(0, 0, 0, 0)
        checks_layout.setSpacing(8)

        model_checks: list[tuple[str, QCheckBox]] = []
        selected_set = set(self.selected_google_models)
        for label, model_id in known_models:
            check = QCheckBox(label, checks_container)
            check.setProperty("model_id", model_id)
            check.setChecked(model_id in selected_set)
            check.setToolTip(model_id)
            checks_layout.addWidget(check)
            model_checks.append((model_id, check))

        form.addRow("Modely:", checks_container)

        info = QLabel(
            "Môžeš vybrať viac modelov. Vybrané modely sa volajú paralelne a použije sa\n"
            "najlepší legálny ťah podľa skóre."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #b6e0bd; font-size: 11px;")
        form.addRow("", info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        form.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = [
                model_id
                for model_id, check in model_checks
                if check.isChecked()
            ]
            if not selected:
                QMessageBox.warning(
                    self,
                    "Google modely",
                    "Vyber aspoň jeden Google/Gemini model.",
                )
                return

            self.selected_google_models = selected
            self.selected_google_model = selected[0]
            log.info("Google models configured: %s", selected)

    def _configure_openai(self) -> None:
        """Open OpenAI model configuration dialog (multi-select)."""
        dialog = QDialog(self)
        dialog.setWindowTitle("OpenAI Modely")
        form = QFormLayout(dialog)
        form.setContentsMargins(14, 14, 14, 14)
        form.setSpacing(10)

        known_models: list[tuple[str, str]] = [
            ("gpt-5.2", "gpt-5.2"),
            ("gpt-5-mini", "gpt-5-mini"),
            ("gpt-4.1", "gpt-4.1"),
        ]

        checks_container = QWidget(dialog)
        checks_layout = QVBoxLayout(checks_container)
        checks_layout.setContentsMargins(0, 0, 0, 0)
        checks_layout.setSpacing(8)

        model_checks: list[tuple[str, QCheckBox]] = []
        selected_set = set(self.selected_openai_models)
        for label, model_id in known_models:
            check = QCheckBox(label, checks_container)
            check.setProperty("model_id", model_id)
            check.setChecked(model_id in selected_set)
            check.setToolTip(model_id)
            checks_layout.addWidget(check)
            model_checks.append((model_id, check))

        form.addRow("Modely:", checks_container)

        info = QLabel(
            "Môžeš vybrať viac modelov. Vybrané modely sa volajú paralelne a použije sa\n"
            "najlepší legálny ťah podľa skóre."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #b6e0bd; font-size: 11px;")
        form.addRow("", info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        form.addRow(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = [
                model_id
                for model_id, check in model_checks
                if check.isChecked()
            ]
            if not selected:
                QMessageBox.warning(
                    self,
                    "OpenAI modely",
                    "Vyber aspoň jeden OpenAI model.",
                )
                return

            self.selected_openai_models = selected
            if hasattr(self, "mode_selector") and self.mode_selector:
                self.mode_selector.set_openai_models_preview(selected)
            log.info("OpenAI models configured: %s", selected)
    
    def _configure_openrouter(self) -> None:
        """Open OpenRouter model configuration dialog."""
        # Use unified AI_MOVE_MAX_OUTPUT_TOKENS (prefer in-dialog value)
        ai_tokens = self._current_ai_tokens_value()
        
        dialog = AIConfigDialog(
            parent=self,
            default_tokens=ai_tokens,
            lock_default=False,  # Token limit managed in settings
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Store selected models for parent to retrieve
            self.selected_openrouter_models = dialog.get_selected_models()
            self.openrouter_tokens = dialog.get_shared_tokens_value()
            # Sync shared token limit back to settings field for consistency
            self.ai_tokens_edit.setText(str(self.openrouter_tokens))
            log.info("OpenRouter models configured: %d models", len(self.selected_openrouter_models))
            
            # Refresh model info display in mode selector
            if hasattr(self, 'mode_selector') and self.mode_selector:
                self.mode_selector.refresh_openrouter_team_info()
    
    def _configure_novita(self) -> None:
        """Open Novita model configuration dialog."""
        from .novita_config_dialog import NovitaConfigDialog
        
        # Use unified AI_MOVE_MAX_OUTPUT_TOKENS (prefer in-dialog value)
        ai_tokens = self._current_ai_tokens_value()
        dialog = NovitaConfigDialog(
            parent=self,
            default_tokens=ai_tokens,
            use_env_default=False,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Store selected models for parent to retrieve
            self.selected_novita_models = dialog.get_selected_models()
            self.novita_tokens = dialog.get_shared_tokens_value()
            # Sync shared token limit back to settings field for consistency
            self.ai_tokens_edit.setText(str(self.novita_tokens))
            log.info("Novita models configured: %d models", len(self.selected_novita_models))
            
            # Refresh model info display in mode selector
            if hasattr(self, 'mode_selector') and self.mode_selector:
                self.mode_selector.refresh_novita_team_info()

    def _configure_offline(self) -> None:
        """Open dialog to configure LMStudio/OpenAI-compatible local server."""
        dialog = QDialog(self)
        dialog.setWindowTitle("LMStudio")
        form = QFormLayout(dialog)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        current_url = (
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("LLMSTUDIO_BASE_URL")
            or "http://127.0.0.1:1234/v1"
        ).strip()
        parsed_current = urlparse(current_url if "://" in current_url else f"http://{current_url}")
        current_scheme = parsed_current.scheme or "http"
        current_host = parsed_current.hostname or "127.0.0.1"
        current_port = parsed_current.port or 1234

        host_edit = QLineEdit(dialog)
        host_edit.setPlaceholderText("http://127.0.0.1")
        host_edit.setText(f"{current_scheme}://{current_host}")
        form.addRow("URL:", host_edit)

        port_spin = QSpinBox(dialog)
        port_spin.setRange(1, 65535)
        port_spin.setValue(int(current_port))
        form.addRow("Port:", port_spin)
        
        model = QLineEdit(dialog)
        model.setPlaceholderText("gpt-5.2")
        openai_models = self._parse_openai_models(os.getenv("OPENAI_MODELS", ""))
        model.setText((os.getenv("LLMSTUDIO_MODEL") or (openai_models[0] if openai_models else "")).strip())
        form.addRow("Model:", model)
        
        tokens = QSpinBox(dialog)
        tokens.setRange(500, 20000)
        tokens.setValue(int(os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS", "3600") or 3600))
        form.addRow("Max tokens:", tokens)
        
        timeout = QSpinBox(dialog)
        timeout.setRange(5, 120)
        timeout.setSuffix(" s")
        timeout.setValue(int(os.getenv("AI_MOVE_TIMEOUT_SECONDS", "30") or 30))
        form.addRow("Timeout:", timeout)
        
        buttons_layout = QHBoxLayout()
        save_btn = QPushButton("Uložiť", dialog)
        cancel_btn = QPushButton("Zrušiť", dialog)
        buttons_layout.addWidget(save_btn)
        buttons_layout.addWidget(cancel_btn)
        form.addRow(buttons_layout)
        
        def _save() -> None:
            host_val = host_edit.text().strip()
            model_val = model.text().strip()
            if not host_val or not model_val:
                QMessageBox.warning(dialog, "LMStudio", "Vyplňte URL aj model.")
                return
            if "://" not in host_val:
                host_val = f"http://{host_val}"
            parsed_host = urlparse(host_val)
            hostname = (parsed_host.hostname or "").strip()
            if not hostname:
                QMessageBox.warning(dialog, "LMStudio", "Neplatná URL adresa.")
                return
            scheme = (parsed_host.scheme or "http").strip() or "http"
            port_val = int(port_spin.value())
            url_val = f"{scheme}://{hostname}:{port_val}/v1"
            tokens_val = str(tokens.value())
            timeout_val = str(timeout.value())
            
            os.environ["OPENAI_BASE_URL"] = url_val
            os.environ["LLMSTUDIO_MODEL"] = model_val
            os.environ["AI_MOVE_MAX_OUTPUT_TOKENS"] = tokens_val
            os.environ["AI_MOVE_TIMEOUT_SECONDS"] = timeout_val
            
            try:
                from dotenv import set_key as _set_key
                _set_key(ENV_PATH, "OPENAI_BASE_URL", url_val)
                _set_key(ENV_PATH, "LLMSTUDIO_MODEL", model_val)
                _set_key(ENV_PATH, "AI_MOVE_MAX_OUTPUT_TOKENS", tokens_val)
                _set_key(ENV_PATH, "AI_MOVE_TIMEOUT_SECONDS", timeout_val)
            except Exception:
                pass
            
            # Sync AI tokens field so main dialog shares limit
            if hasattr(self, "ai_tokens_edit"):
                self.ai_tokens_edit.setText(tokens_val)
            
            dialog.accept()
        
        save_btn.clicked.connect(_save)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec()
    
    def _create_general_tab(self) -> QWidget:
        """Create general game settings tab.
        
        Returns:
            Widget with general settings
        """
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Variant selection
        self.variant_combo = QComboBox(widget)
        self.variant_combo.setEditable(False)
        self.variant_combo.currentIndexChanged.connect(self._on_variant_changed)
        self.variant_combo.setStyleSheet(
            "QComboBox { "
            "background: #000000; color: #e8f5e9; padding: 6px; "
            "border: 1px solid #2f5c39; border-radius: 4px; "
            "} "
            "QComboBox:hover { border-color: #4caf50; background: #0a0a0a; } "
            "QComboBox:focus { border-color: #4caf50; } "
            "QComboBox::drop-down { border: none; width: 20px; } "
            "QComboBox QAbstractItemView { "
            "background: #000000; color: #e8f5e9; "
            "selection-background-color: #295c33; "
            "}"
        )
        layout.addRow(
            self._styled_label("Aktívny Scrabble variant:"),
            self.variant_combo,
        )
        
        # Languages with buttons
        self.languages_combo = QComboBox(widget)
        self.languages_combo.setEditable(False)
        self.languages_combo.setStyleSheet(self.variant_combo.styleSheet())
        lang_row = QHBoxLayout()
        lang_row.addWidget(self.languages_combo, 2)
        self.refresh_languages_btn = QPushButton("Aktualizovať jazyky", widget)
        self.refresh_languages_btn.clicked.connect(self._refresh_languages)
        self.refresh_languages_btn.setStyleSheet(
            "QPushButton { "
            "padding: 6px 12px; font-size: 11px; border-radius: 4px; "
            "background-color: #182c1d; color: #b6e0bd; border: 1px solid #2f5c39; "
            "} "
            "QPushButton:hover { background-color: #213f29; }"
        )
        lang_row.addWidget(self.refresh_languages_btn)
        self.new_variant_btn = QPushButton("Nový variant", widget)
        self.new_variant_btn.clicked.connect(self._on_new_variant)
        self.new_variant_btn.setStyleSheet(self.refresh_languages_btn.styleSheet())
        lang_row.addWidget(self.new_variant_btn)
        lang_container = QWidget(widget)
        lang_container.setLayout(lang_row)
        layout.addRow(
            self._styled_label("Jazyky:"),
            lang_container,
        )
        
        # Repro mode
        self.repro_check = QCheckBox("Repro mód (deterministický seed)", widget)
        self.repro_check.setChecked(self.repro_mode)
        self.repro_check.setStyleSheet("QCheckBox { color: #e8f5e9; }")
        layout.addRow(self.repro_check)
        
        # Seed
        self.seed_edit = QLineEdit(widget)
        self.seed_edit.setValidator(QIntValidator(0, 2_147_483_647, widget))
        self.seed_edit.setText(str(self.repro_seed))
        self.seed_edit.setStyleSheet(
            "QLineEdit { "
            "background: #000000; color: #e8f5e9; padding: 8px; "
            "border: 1px solid #2f5c39; border-radius: 4px; "
            "} "
            "QLineEdit:hover { border-color: #4caf50; } "
            "QLineEdit:focus { border-color: #4caf50; background: #0a0a0a; }"
        )
        layout.addRow(
            self._styled_label("Seed:"),
            self.seed_edit,
        )
        
        # Agent activity auto-show
        self.agent_auto_show_check = QCheckBox(
            "Zobrazovať automaticky aktivitu agentov",
            widget
        )
        self.agent_auto_show_check.setChecked(self._load_agent_auto_show())
        self.agent_auto_show_check.setStyleSheet("QCheckBox { color: #e8f5e9; }")
        layout.addRow(self.agent_auto_show_check)
        
        # Load variants and languages
        self._load_installed_variants(select_slug=self.selected_variant_slug)
        self._init_languages()
        
        return widget
    
    def _create_api_tab(self) -> QWidget:
        """Create API and game settings tab.
        
        Returns:
            Widget with API settings
        """
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Load .env to prefill API key
        try:
            from dotenv import load_dotenv as _load_dotenv
            _load_dotenv(ENV_PATH, override=False)
        except Exception:
            pass
        
        # OpenAI API key
        self.key_edit = QLineEdit(widget)
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setText(os.getenv("OPENAI_API_KEY", ""))
        self.key_edit.setStyleSheet(
            "QLineEdit { "
            "background: #000000; color: #e8f5e9; padding: 8px; "
            "border: 1px solid #2f5c39; border-radius: 4px; "
            "} "
            "QLineEdit:hover { border-color: #4caf50; } "
            "QLineEdit:focus { border-color: #4caf50; background: #0a0a0a; }"
        )
        layout.addRow(
            self._styled_label("OpenAI API kľúč:"),
            self.key_edit,
        )
        
        # AI tokens with cost
        self.ai_tokens_edit = QLineEdit(widget)
        self.ai_tokens_edit.setValidator(QIntValidator(1, 1_000_000, widget))
        self.ai_tokens_edit.setText(os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS", "3600"))
        self.ai_tokens_edit.setStyleSheet(self.key_edit.styleSheet())
        self.ai_tokens_cost = QLabel("")
        self.ai_tokens_cost.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.ai_tokens_cost.setStyleSheet("color: #ffd54f; font-size: 12px;")
        ai_row = QHBoxLayout()
        ai_row.addWidget(self.ai_tokens_edit, 2)
        ai_row.addWidget(self.ai_tokens_cost, 1)
        ai_row_w = QWidget(widget)
        ai_row_w.setLayout(ai_row)
        layout.addRow(
            self._styled_label("AI ťah — max výstupných tokenov:"),
            ai_row_w,
        )
        
        # Judge tokens with cost
        self.judge_tokens_edit = QLineEdit(widget)
        self.judge_tokens_edit.setValidator(QIntValidator(1, 1_000_000, widget))
        self.judge_tokens_edit.setText(os.getenv("JUDGE_MAX_OUTPUT_TOKENS", "800"))
        self.judge_tokens_edit.setStyleSheet(self.key_edit.styleSheet())
        self.judge_tokens_cost = QLabel("")
        self.judge_tokens_cost.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.judge_tokens_cost.setStyleSheet("color: #ffd54f; font-size: 12px;")
        j_row = QHBoxLayout()
        j_row.addWidget(self.judge_tokens_edit, 2)
        j_row.addWidget(self.judge_tokens_cost, 1)
        j_row_w = QWidget(widget)
        j_row_w.setLayout(j_row)
        layout.addRow(
            self._styled_label("Rozhodca — max výstupných tokenov:"),
            j_row_w,
        )
        
        # Test connection button
        self.test_btn = QPushButton("🔌 Testovať pripojenie", widget)
        self.test_btn.clicked.connect(self._test_connection)
        self.test_btn.setStyleSheet(
            "QPushButton { "
            "padding: 8px 16px; font-size: 12px; border-radius: 4px; "
            "background-color: #182c1d; color: #b6e0bd; border: 1px solid #2f5c39; "
            "} "
            "QPushButton:hover { background-color: #213f29; border-color: #4caf50; }"
        )
        layout.addRow("", self.test_btn)
        
        # Connect cost updates
        self.ai_tokens_edit.textChanged.connect(self._update_costs)
        self.judge_tokens_edit.textChanged.connect(self._update_costs)
        self._update_costs()
        
        return widget
    
    def _styled_label(self, text: str) -> QLabel:
        """Create a styled label for form rows.
        
        Args:
            text: Label text
            
        Returns:
            Styled label
        """
        label = QLabel(text)
        label.setStyleSheet("color: #b6e0bd; font-weight: bold;")
        return label
    
    def _update_costs(self) -> None:
        """Update cost estimates for token fields."""
        def fmt(tokens_text: str) -> str:
            try:
                t = int(tokens_text)
                if t <= 0:
                    return ""
                eur = t * EUR_PER_TOKEN
                if eur < 0.01:
                    return f"≈ {eur:.6f} €"
                return f"≈ {eur:.2f} €"
            except ValueError:
                return ""
        
        self.ai_tokens_cost.setText(fmt(self.ai_tokens_edit.text()))
        self.judge_tokens_cost.setText(fmt(self.judge_tokens_edit.text()))
    
    @staticmethod
    def _parse_positive_int(value: Any) -> int | None:
        """Return positive integer parsed from value, otherwise None."""

        if value is None:
            return None
        try:
            tokens = int(str(value))
        except (TypeError, ValueError):
            return None
        return tokens if tokens > 0 else None

    def _current_ai_tokens_value(self) -> int:
        """Resolve the current AI token cap from the input or environment."""

        text_value = self.ai_tokens_edit.text().strip()
        field_tokens = self._parse_positive_int(text_value)
        if field_tokens is not None:
            return field_tokens

        env_tokens = self._parse_positive_int(os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS"))
        if env_tokens is not None:
            return env_tokens

        return 3600
    
    def _load_installed_variants(self, *, select_slug: str | None = None) -> None:
        """Load installed variants into combo box."""
        variants = sorted(list_installed_variants(), key=lambda v: v.language.lower())
        self._installed_variants = variants
        slug_to_select = select_slug or self.selected_variant_slug
        
        self.variant_combo.blockSignals(True)
        self.variant_combo.clear()
        for variant in variants:
            label = f"{variant.language} ({variant.slug})"
            self.variant_combo.addItem(label, variant.slug)
        self.variant_combo.blockSignals(False)
        
        if slug_to_select:
            idx = self.variant_combo.findData(slug_to_select)
            if idx >= 0:
                self.variant_combo.setCurrentIndex(idx)
        if self.variant_combo.count() and self.variant_combo.currentIndex() < 0:
            self.variant_combo.setCurrentIndex(0)
        
        data = self.variant_combo.currentData()
        if isinstance(data, str):
            self.selected_variant_slug = data
        self._sync_language_with_variant(self.selected_variant_slug)
    
    def _init_languages(self) -> None:
        """Initialize languages combo box."""
        languages = get_languages_for_ui()
        self._set_languages(languages)
        self._sync_language_with_variant(self.selected_variant_slug)
    
    def _set_languages(self, languages: Sequence[LanguageInfo], *, keep_selection: bool = False) -> None:
        """Set languages in combo box."""
        previous = self._current_language() if keep_selection else None
        self._languages = list(languages)
        self.languages_combo.blockSignals(True)
        self.languages_combo.clear()
        for lang in self._languages:
            self.languages_combo.addItem(lang.display_label(), lang)
        self.languages_combo.blockSignals(False)
        if previous:
            idx = self._index_for_language(previous)
            if idx >= 0:
                self.languages_combo.setCurrentIndex(idx)
                return
        if self.languages_combo.count():
            self.languages_combo.setCurrentIndex(0)
    
    def _current_language(self) -> LanguageInfo | None:
        """Get currently selected language."""
        data = self.languages_combo.currentData()
        return data if isinstance(data, LanguageInfo) else None
    
    def _index_for_language(self, language: LanguageInfo) -> int:
        """Find index for language in combo box."""
        for idx in range(self.languages_combo.count()):
            data = self.languages_combo.itemData(idx)
            if not isinstance(data, LanguageInfo):
                continue
            if data.name.casefold() == language.name.casefold():
                code_a = (data.code or "").casefold()
                code_b = (language.code or "").casefold()
                if code_a == code_b or not code_b:
                    return idx
        return -1
    
    def _on_variant_changed(self, index: int) -> None:
        """Handle variant selection change."""
        data = self.variant_combo.itemData(index)
        if isinstance(data, str):
            self.selected_variant_slug = data
            self._sync_language_with_variant(data)
    
    def _sync_language_with_variant(self, slug: str | None) -> None:
        """Sync language selection with variant."""
        if not slug:
            return
        try:
            variant = load_variant(slug)
        except Exception:
            return
        match = match_language(variant.language, self._languages)
        if match:
            idx = self._index_for_language(match)
            if idx >= 0:
                self.languages_combo.setCurrentIndex(idx)
                return
        new_lang = LanguageInfo(name=variant.language, code=None)
        self._languages.append(new_lang)
        self.languages_combo.addItem(new_lang.display_label(), new_lang)
        self.languages_combo.setCurrentIndex(self.languages_combo.count() - 1)
    
    def _refresh_languages(self) -> None:
        """Refresh languages list from OpenAI using async agent."""
        # Get main window to access agents dialog
        from .app import MainWindow
        main_window_qobj = self.parent()
        while main_window_qobj and not isinstance(main_window_qobj, MainWindow):
            main_window_qobj = main_window_qobj.parent()
        
        if not isinstance(main_window_qobj, MainWindow):
            QMessageBox.warning(
                self,
                "Chyba",
                "Nemôžem nájsť hlavné okno pre zobrazenie aktivity agenta."
            )
            return
        
        main_window: MainWindow = main_window_qobj
        
        # Get or create agents dialog
        agents_dialog = main_window.get_agents_dialog()
        agent_widget = agents_dialog.get_or_create_agent_tab(
            agent_name="language_fetcher",
            display_name="🌍 Získavanie jazykov",
        )
        
        # Show agents dialog only if auto-show is enabled
        # But always show toolbar animation
        if agents_dialog.should_auto_show():
            agents_dialog.show()
            agents_dialog.raise_()
        
        # Clear previous log
        agent_widget.clear_log()
        agent_widget.set_status("Spúšťam...", is_working=True)
        agent_widget.append_activity("Spúšťam bootstrap variantov z Wikipédie a LLM...")

        # Create agent
        try:
            agent = VariantBootstrapAgent()
        except Exception as exc:
            agent_widget.set_status(f"Chyba: {exc}", is_working=False)
            agent_widget.append_activity(f"Inicializácia zlyhala: {exc}", prefix="❌")
            # Error shown in agent widget - no modal alert needed
            return
        
        # Get main window for toolbar animation
        toolbar_widget = None
        if main_window and hasattr(main_window, 'agent_status_widget'):
            toolbar_widget = main_window.agent_status_widget
            toolbar_widget.show_agent_activity("Jazyky", "Získavam")
        
        # Create worker thread and store in MainWindow so it continues even if dialog closes
        worker = AsyncAgentWorker(agent.bootstrap, force_refresh=True)
        main_window.agent_workers['language_fetcher'] = worker
        
        # Define progress handler (runs in main thread via signal/slot)
        def on_progress_update(update: VariantBootstrapProgress) -> None:
            """Handle progress updates from agent - RUNS IN MAIN THREAD."""
            agent_widget.set_status(update.status, is_working=True)
            if update.detail:
                agent_widget.append_activity(update.detail)
            if update.prompt:
                agent_widget.append_prompt(update.prompt)
            if update.html_snippet_raw:
                agent_widget.add_html_snippet(
                    update.html_snippet_label or "HTML snippet",
                    update.html_snippet_raw,
                    update.html_snippet_text or "",
                )
            agent_widget.update_progress(update.progress_percent)

            # Update inline status in settings dialog
            self._lang_current_status = update.status

            # Update toolbar animation
            if toolbar_widget:
                # Extract short status for toolbar
                short_status = update.status.split("...")[0] if "..." in update.status else update.status
                toolbar_widget.update_status(short_status)
        
        # Connect signals (these run in main thread)
        worker.progress_update.connect(on_progress_update)
        worker.agent_finished.connect(
            lambda result: self._on_languages_bootstrapped(result, agent_widget)
        )
        worker.agent_error.connect(
            lambda error: self._on_language_fetch_error(error, agent_widget)
        )
        
        # Start worker
        worker.start()
        
        # Disable refresh button and show status while working
        self.refresh_languages_btn.setEnabled(False)
        self.lang_fetch_status.setVisible(True)
        self.lang_fetch_status.setText("🤖 Získavam jazyky...")
        
        # Start animation timer for dots
        self._lang_dot_count = 0
        self._lang_status_timer = QTimer(self)
        self._lang_status_timer.timeout.connect(self._update_lang_status_animation)
        self._lang_status_timer.start(500)  # Update every 500ms
    
    def _on_languages_bootstrapped(
        self,
        result: BootstrapResult,
        agent_widget: AgentActivityWidget,
    ) -> None:
        """Handle successful bootstrap completion."""
        languages = result.languages
        summaries = result.summaries

        agent_widget.set_status(f"Hotovo! ({len(languages)} jazykov)", is_working=False)
        agent_widget.append_status(
            f"Úspešne vytvorených {len(summaries)} sumarizácií"
        )

        response_lines = ["Načítané jazyky:", ""]
        for lang in languages[:10]:
            response_lines.append(f"• {lang.display_label()}")
        if len(languages) > 10:
            response_lines.append(f"\n... a ďalších {len(languages) - 10} jazykov")

        if summaries:
            response_lines.append("\nUložené sumarizácie:")
            for summary in summaries[:10]:
                response_lines.append(f"• {summary.file_path.name}")
            if len(summaries) > 10:
                response_lines.append(f"\n... a ďalších {len(summaries) - 10} súborov")

        agent_widget.set_response("\n".join(response_lines))

        self._set_languages(languages, keep_selection=True)
        self._sync_language_with_variant(self.selected_variant_slug)

        # Stop animation timer
        if self._lang_status_timer:
            self._lang_status_timer.stop()

        # Hide status and re-enable button
        self.lang_fetch_status.setVisible(False)
        self.refresh_languages_btn.setEnabled(True)
        
        # Hide toolbar animation and cleanup worker
        main_window = self.parent()
        while main_window and not hasattr(main_window, 'agent_status_widget'):
            main_window = main_window.parent()
        if main_window and hasattr(main_window, 'agent_status_widget'):
            main_window.agent_status_widget.hide_agent_activity(delay_ms=2000)
        
        # Cleanup worker from MainWindow
        if main_window and hasattr(main_window, 'agent_workers'):
            main_window.agent_workers.pop('language_fetcher', None)
        
        # Success - no modal alert needed, agent widget shows the status
    
    def _on_language_fetch_error(
        self,
        error: str,
        agent_widget: AgentActivityWidget,
    ) -> None:
        """Handle language fetch error."""
        agent_widget.set_status(f"Chyba: {error}", is_working=False)
        agent_widget.append_activity(f"Zlyhalo: {error}", prefix="❌")
        agent_widget.set_response(f"Chyba:\\n{error}")
        
        # Stop animation timer
        if self._lang_status_timer:
            self._lang_status_timer.stop()
        
        # Show error in status
        self.lang_fetch_status.setText(f"❌ Chyba: {error}")
        self.lang_fetch_status.setStyleSheet(
            "QLabel { "
            "color: #ff5252; font-size: 14px; font-weight: bold; "
            "padding: 12px 16px; background: #000000; "
            "border-top: 1px solid #5c2f2f; "
            "} "
            "QLabel:hover { background: #0a0a0a; cursor: pointer; }"
        )
        
        # Re-enable button
        self.refresh_languages_btn.setEnabled(True)
        
        # Hide toolbar animation and cleanup worker
        main_window = self.parent()
        while main_window and not hasattr(main_window, 'agent_status_widget'):
            main_window = main_window.parent()
        if main_window and hasattr(main_window, 'agent_status_widget'):
            main_window.agent_status_widget.hide_agent_activity(delay_ms=0)
        
        # Cleanup worker from MainWindow
        if main_window and hasattr(main_window, 'agent_workers'):
            main_window.agent_workers.pop('language_fetcher', None)
        
        # Error shown in agent widget and status bar - no modal alert needed

    def _on_new_variant(self) -> None:
        """Handle new variant creation."""
        # Import dialog locally to avoid circular dependency
        from .app import NewVariantDialog
        
        current_lang = self._current_language()
        dialog = NewVariantDialog(self, self._languages or get_languages_for_ui(), current_lang)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        summary = dialog.selected_summary
        if summary is None:
            QMessageBox.warning(self, "Nová sumarizácia", "Žiadna sumarizácia nebola vytvorená.")
            return

        if not match_language(summary.language.name, self._languages):
            new_language = LanguageInfo(name=summary.language.name, code=summary.language.code)
            self._languages.append(new_language)
            self.languages_combo.addItem(new_language.display_label(), new_language)

        QMessageBox.information(
            self,
            "Nová sumarizácia",
            f"Sumarizácia pre jazyk '{summary.language.name}' bola uložená do:\n{summary.file_path}",
        )
    
    def _test_connection(self) -> None:
        """Test OpenAI connection."""
        k = self.key_edit.text().strip()
        if not k:
            QMessageBox.warning(self, "Test", "Zadaj API key.")
            return
        os.environ["OPENAI_API_KEY"] = k
        try:
            _ = OpenAIClient()
            QMessageBox.information(
                self,
                "Test",
                "Kľúč uložený do prostredia. Reálne volanie sa vykoná počas hry.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Test zlyhal", str(e))
    
    def _load_agent_auto_show(self) -> bool:
        """Load agent auto-show setting from environment.
        
        Returns:
            True if auto-show enabled (default: True)
        """
        value = os.getenv("SHOW_AGENT_ACTIVITY_AUTO", "true").lower()
        return value in ("true", "1", "yes", "on")
    
    def _update_lang_status_animation(self) -> None:
        """Update language fetch status with animated dots."""
        update_lang_status_animation(self)
    
    def _on_status_bar_clicked(self) -> None:
        """Handle status bar click - open agents dialog."""
        # Get main window
        from .app import MainWindow
        main_window_qobj = self.parent()
        while main_window_qobj and not isinstance(main_window_qobj, MainWindow):
            main_window_qobj = main_window_qobj.parent()
        
        if isinstance(main_window_qobj, MainWindow):
            main_window: MainWindow = main_window_qobj
            agents_dialog = main_window.get_agents_dialog()
            agents_dialog.show()
            agents_dialog.raise_()
            agents_dialog.activateWindow()
    
    def accept(self) -> None:
        """Handle accept - save API settings to .env."""
        # Save API key
        key_str = self.key_edit.text().strip()
        try:
            if not os.path.exists(ENV_PATH):
                Path(ENV_PATH).open("a", encoding="utf-8").close()
        except Exception:
            pass
        if key_str:
            os.environ["OPENAI_API_KEY"] = key_str
            try:
                from dotenv import set_key as _set_key
                _set_key(ENV_PATH, "OPENAI_API_KEY", key_str)
            except Exception:
                pass
        
        # Save token limits
        ai_tokens = self.ai_tokens_edit.text().strip() or "3600"
        judge_tokens = self.judge_tokens_edit.text().strip() or "800"
        os.environ["AI_MOVE_MAX_OUTPUT_TOKENS"] = ai_tokens
        os.environ["JUDGE_MAX_OUTPUT_TOKENS"] = judge_tokens
        try:
            from dotenv import set_key as _set_key2
            _set_key2(ENV_PATH, "AI_MOVE_MAX_OUTPUT_TOKENS", ai_tokens)
            _set_key2(ENV_PATH, "JUDGE_MAX_OUTPUT_TOKENS", judge_tokens)
        except Exception:
            pass

        # Save OpenAI parallel model list
        openai_models = [
            model.strip()
            for model in self.selected_openai_models
            if isinstance(model, str) and model.strip()
        ]
        if not openai_models:
            openai_models = ["gpt-5.2"]
        openai_models_csv = ",".join(openai_models)
        os.environ["OPENAI_MODELS"] = openai_models_csv
        try:
            from dotenv import set_key as _set_key_models
            _set_key_models(ENV_PATH, "OPENAI_MODELS", openai_models_csv)
        except Exception:
            pass
        
        # Save variant
        slug_data = self.variant_combo.currentData()
        if isinstance(slug_data, str) and slug_data:
            try:
                variant = set_active_variant_slug(slug_data)
                self.selected_variant_slug = variant.slug
                from dotenv import set_key as _set_key_variant
                _set_key_variant(ENV_PATH, "SCRABBLE_VARIANT", variant.slug)
            except Exception:
                os.environ["SCRABBLE_VARIANT"] = slug_data
        
        # Save agent auto-show setting
        agent_auto_show = "true" if self.agent_auto_show_check.isChecked() else "false"
        os.environ["SHOW_AGENT_ACTIVITY_AUTO"] = agent_auto_show
        try:
            from dotenv import set_key as _set_key_agent
            _set_key_agent(ENV_PATH, "SHOW_AGENT_ACTIVITY_AUTO", agent_auto_show)
        except Exception:
            pass
        
        # Reload provider model selections and refresh UI in main window after saving settings
        if hasattr(self, 'parent') and self.parent():
            main_window = self.parent()
            if hasattr(main_window, '_load_saved_teams'):
                main_window._load_saved_teams()
            if hasattr(main_window, '_refresh_model_results_table'):
                main_window._refresh_model_results_table()
            if hasattr(main_window, '_update_mode_status_label'):
                main_window._update_mode_status_label()
        
        # Call parent accept
        super().accept()
