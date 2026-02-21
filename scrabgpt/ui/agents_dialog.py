"""Agents Activity Dialog - Shows agent thinking, status, and responses."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("scrabgpt.ui.agents")


def load_env_llm_defaults() -> dict[str, object] | None:
    """Načítaj implicitné LLM nastavenie z .env (OpenAI/LLMStudio)."""
    base = os.getenv("OPENAI_BASE_URL") or os.getenv("LLMSTUDIO_BASE_URL")
    model = (
        os.getenv("OPENAI_MODEL")
        or os.getenv("OPENAI_PLAYER_MODEL")
        or os.getenv("LLMSTUDIO_MODEL")
    )
    max_tokens_env = os.getenv("AI_MOVE_MAX_OUTPUT_TOKENS")
    timeout_env = os.getenv("AI_MOVE_TIMEOUT_SECONDS")
    
    if not base and not model:
        return None
    
    def _to_int(value: str | None) -> int | None:
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None
    
    return {
        "base_url": base or "http://127.0.0.1:1234/v1",
        "model": model or "gpt-5.2",
        "max_tokens": max(500, min(20000, _to_int(max_tokens_env) or 4000)),
        "timeout": max(5, min(120, _to_int(timeout_env) or 30)),
    }


def normalize_llm_config(
    base_url: str,
    model: str,
    max_tokens: int | None = None,
    timeout: int | None = None,
) -> dict[str, object]:
    """Normalize LLM config input (strip, basic validation, clamping)."""
    base = (base_url or "").strip()
    mdl = (model or "").strip()
    if not base:
        raise ValueError("URL nesmie byť prázdne")
    if not mdl:
        raise ValueError("Model nesmie byť prázdny")
    
    def _clamp(value: int | None, min_v: int, max_v: int) -> int | None:
        if value is None:
            return None
        return max(min_v, min(max_v, value))
    
    return {
        "base_url": base,
        "model": mdl,
        "max_tokens": _clamp(max_tokens, 500, 20000),
        "timeout": _clamp(timeout, 5, 120),
    }


class AsyncAgentWorker(QThread):
    """QThread worker that runs async agent operations.
    
    This worker:
    1. Runs async function in a separate thread with its own event loop
    2. Emits progress updates via signals
    3. Handles errors gracefully
    4. Returns result or error
    
    Signals:
        progress_update(str, str): (status, thinking)
        agent_finished(object): Result from agent
        agent_error(str): Error message
    """
    
    progress_update = Signal(object)  # AgentProgress object
    agent_finished = Signal(object)  # result
    agent_error = Signal(str)  # error message
    
    def __init__(
        self,
        async_func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize worker.
        
        Args:
            async_func: Async function to run
            *args: Positional arguments for async_func
            **kwargs: Keyword arguments for async_func
            
        Note:
            If the async function accepts an 'on_progress' callback,
            this worker will inject a callback that emits the progress_update signal.
        """
        super().__init__()
        self.async_func = async_func
        self.args = args
        self.kwargs = kwargs
        
        # Inject progress callback that emits signal
        if 'on_progress' not in self.kwargs:
            self.kwargs['on_progress'] = self._emit_progress
    
    def _emit_progress(self, update: Any) -> None:
        """Emit progress update signal (called from worker thread)."""
        self.progress_update.emit(update)
    
    def run(self) -> None:
        """Run async function in thread's event loop."""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Run async function
                result = loop.run_until_complete(
                    self.async_func(*self.args, **self.kwargs)
                )
                
                # Emit success
                self.agent_finished.emit(result)
            finally:
                loop.close()
        
        except Exception as e:
            log.exception("Agent worker failed: %s", e)
            self.agent_error.emit(str(e))


class AgentActivityWidget(QWidget):
    """Widget showing activity for a single agent."""
    
    llm_config_changed = Signal(dict)
    
    def __init__(
        self,
        agent_name: str,
        parent: QWidget | None = None,
        default_llm_config: dict[str, object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.agent_name = agent_name
        self.llm_config: dict[str, object] | None = default_llm_config
        self._reasoning_anim: QPropertyAnimation | None = None
        self._reasoning_effect: QGraphicsOpacityEffect | None = None
        self._setup_ui()
        
    def _setup_ui(self) -> None:
        """Setup UI components."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        button_layout = QHBoxLayout()
        self.html_snippet_button = QPushButton("Zobraziť HTML snippety", self)
        self.html_snippet_button.setEnabled(False)
        self.html_snippet_button.clicked.connect(self._show_html_snippet_dialog)
        button_layout.addWidget(self.html_snippet_button)
        
        self.add_llm_button = QPushButton("➕ Pridať LLM", self)
        self.add_llm_button.clicked.connect(self._open_llm_dialog)
        self.add_llm_button.setToolTip("Pridať/aktualizovať hlavný LLM (URL, model, limity)")
        self.add_llm_button.setStyleSheet(
            "QPushButton { padding: 6px 10px; border-radius: 6px; "
            "background: #1d2c22; color: #b6e0bd; border: 1px solid #2f5c39; } "
            "QPushButton:hover { background: #243a2a; }"
        )
        button_layout.addWidget(self.add_llm_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Status bar
        status_layout = QHBoxLayout()

        self.status_label = QLabel("Pripravený")
        self.status_label.setStyleSheet(
            "color: #b6e0bd; font-weight: bold; font-size: 13px;"
        )
        status_layout.addWidget(self.status_label)
        
        self.context_label = QLabel("Context: --")
        self.context_label.setStyleSheet(
            "color: #96a28f; font-size: 11px; font-family: 'Fira Sans';"
        )
        status_layout.addWidget(self.context_label)
        
        status_layout.addStretch()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumWidth(200)
        self.progress_bar.setStyleSheet(
            "QProgressBar { "
            "background: #0f1a12; color: #e8f5e9; "
            "border: 1px solid #2f5c39; border-radius: 4px; "
            "text-align: center; height: 20px; "
            "} "
            "QProgressBar::chunk { "
            "background: #4b7d5d; "
            "border-radius: 3px; "
            "}"
        )
        status_layout.addWidget(self.progress_bar, stretch=2)  # Give it more space
        
        layout.addLayout(status_layout)
        
        # Activity log (thinking + status)
        activity_label = QLabel("🧠 Aktivita:")
        activity_label.setStyleSheet("color: #b6e0bd; font-weight: bold; font-size: 13px;")
        layout.addWidget(activity_label)
        
        # Reasoning flash (fade in/out)
        self.reasoning_flash = QLabel("")
        self.reasoning_flash.setWordWrap(True)
        self.reasoning_flash.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.reasoning_flash.setStyleSheet(
            "background: #050805; color: #8cd9a0; border: 1px solid #1f2f23; "
            "border-radius: 6px; padding: 8px; font-family: 'Fira Code', 'Consolas'; "
            "font-size: 11px; opacity: 0;"
        )
        self._reasoning_effect = QGraphicsOpacityEffect(self.reasoning_flash)
        self._reasoning_effect.setOpacity(0.0)
        self.reasoning_flash.setGraphicsEffect(self._reasoning_effect)
        layout.addWidget(self.reasoning_flash)
        
        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setAcceptRichText(True)  # Enable HTML formatting
        font = QFont("Monospace")
        font.setPointSize(10)
        self.activity_log.setFont(font)
        self.activity_log.setStyleSheet(
            "QTextEdit { "
            "background: #000000; color: #e8f5e9; "
            "border: 2px solid #2f5c39; border-radius: 6px; "
            "padding: 12px; font-family: 'Monospace', 'Courier New'; "
            "} "
            "QTextEdit:focus { border-color: #4caf50; }"
        )
        layout.addWidget(self.activity_log, 2)  # Stretch factor 2
        
        # Response output
        response_label = QLabel("✅ Odpoveď:")
        response_label.setStyleSheet("color: #b6e0bd; font-weight: bold; font-size: 13px;")
        layout.addWidget(response_label)
        
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setFont(font)
        self.response_text.setStyleSheet(
            "QTextEdit { "
            "background: #0f1a12; color: #4caf50; "
            "border: 2px solid #2f5c39; border-radius: 6px; "
            "padding: 12px; font-family: 'Monospace', 'Courier New'; "
            "} "
            "QTextEdit:focus { border-color: #4caf50; }"
        )
        layout.addWidget(self.response_text, 1)  # Stretch factor 1

        # Clear button
        clear_btn = QPushButton("🗑️ Vymazať log")
        clear_btn.clicked.connect(self.clear_log)
        clear_btn.setStyleSheet(
            "QPushButton { "
            "padding: 8px 16px; font-size: 12px; border-radius: 4px; "
            "background-color: #3d2a0f; color: #ffd54f; border: 1px solid #8a6a4a; "
            "} "
            "QPushButton:hover { background-color: #4d3a1f; border-color: #ff9800; }"
        )
        layout.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignLeft)
       
        self._html_snippets: list[dict[str, str]] = []
        self._current_progress: int = 0
        
        # Ak je predvyplnený LLM, zobraz ho v stave
        if self.llm_config:
            self.set_llm_config(self.llm_config)
        
    def set_status(self, status: str, is_working: bool = False) -> None:
        """Update status label and progress bar."""
        self.status_label.setText(status)
        self.progress_bar.setVisible(is_working)

    def update_progress(self, percent: int | None) -> None:
        if percent is None:
            return
        clamped = max(0, min(100, percent))
        self._current_progress = clamped
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(clamped)
        self.context_label.setText(f"Context: {clamped}%")

    def update_context_progress(self, percent: int | None) -> None:
        """Alias na update_progress pre jasnejší význam."""
        self.update_progress(percent)

    def append_activity(self, message: str, prefix: str = "ℹ️", color: str | None = None) -> None:
        """Append message to activity log with timestamp.
        
        Args:
            message: Message text
            prefix: Emoji prefix
            color: Optional color for message (HTML color)
        """
        # Check if user has manually scrolled up before appending
        scrollbar = self.activity_log.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10  # Within 10px of bottom
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if color:
            # Use HTML formatting for colored text
            formatted = f'<span style="color: white;">[{timestamp}] {prefix}</span> <span style="color: {color};">{message}</span>'
            self.activity_log.append(formatted)
        else:
            formatted = f"[{timestamp}] {prefix} {message}"
            self.activity_log.append(formatted)
        
        # Auto-scroll to bottom ONLY if user was already at bottom
        # This allows manual scrolling without being forced back down
        if was_at_bottom:
            cursor = self.activity_log.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.activity_log.setTextCursor(cursor)
            scrollbar.setValue(scrollbar.maximum())
    
    def append_thinking(self, thought: str) -> None:
        """Append agent thinking to activity log."""
        self.append_activity(thought, prefix="💭")
        self._show_reasoning_flash(thought)
    
    def append_status(self, status: str) -> None:
        """Append status update to activity log."""
        self.append_activity(status, prefix="📊")
    
    def append_prompt(self, prompt: str) -> None:
        """Append prompt text in green color."""
        # Split prompt into lines for better readability
        lines = prompt.split('\n')
        for line in lines:
            if line.strip():
                self.append_activity(line, prefix="  ", color="#4caf50")

    def _show_reasoning_flash(self, text: str) -> None:
        """Zobraz krátky fade-in/out blok s reasoning obsahom."""
        effect = self._reasoning_effect
        if effect is None:
            return
        self.reasoning_flash.setText(text)
        effect.setOpacity(0.0)
        
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim.start()
        self._reasoning_anim = anim
        
        def _fade_out() -> None:
            out_anim = QPropertyAnimation(effect, b"opacity", self)
            out_anim.setDuration(350)
            out_anim.setStartValue(1.0)
            out_anim.setEndValue(0.0)
            out_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            out_anim.start()
            self._reasoning_anim = out_anim
        
        QTimer.singleShot(1200, _fade_out)

    def add_html_snippet(self, label: str, raw_html: str, summary: str) -> None:
        snippet = {
            "label": label,
            "raw": raw_html,
            "summary": summary,
        }
        self._html_snippets.append(snippet)
        self.html_snippet_button.setEnabled(True)
        self.html_snippet_button.setText(f"Zobraziť HTML ({label})")
    
    def set_llm_config(self, cfg: dict[str, object]) -> None:
        """Ulož LLM config a emituj signál."""
        self.llm_config = cfg
        self.llm_config_changed.emit(cfg)
        short_model = str(cfg.get("model", ""))[:32]
        self.status_label.setText(f"LLM: {short_model}")

    def set_response(self, response: str) -> None:
        """Set response text (replacing previous)."""
        self.response_text.setPlainText(response)

    def append_response(self, response: str) -> None:
        """Append to response text."""
        self.response_text.append(response)
    
    def clear_log(self) -> None:
        """Clear activity log and response."""
        self.activity_log.clear()
        self.response_text.clear()
        self.set_status("Pripravený", is_working=False)
        self._html_snippets.clear()
        self.html_snippet_button.setEnabled(False)
        self.html_snippet_button.setText("Zobraziť HTML snippety")
        self._current_progress = 0
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        if self._reasoning_effect:
            self._reasoning_effect.setOpacity(0.0)

    def _open_llm_dialog(self) -> None:
        """Dialog pre nastavenie hlavného LLM (URL, model, limity)."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Hlavný LLM")
        form = QFormLayout(dialog)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)
        cfg_map = self.llm_config or {}

        def _cfg_int(key: str, default: int) -> int:
            raw = cfg_map.get(key, default)
            if isinstance(raw, bool):
                return default
            if isinstance(raw, int):
                return raw
            if isinstance(raw, float):
                return int(raw)
            if isinstance(raw, str):
                try:
                    return int(raw)
                except ValueError:
                    return default
            return default
        
        url_edit = QLineEdit(dialog)
        url_edit.setPlaceholderText("http://127.0.0.1:1234")
        url_edit.setText(
            str(cfg_map.get("base_url", "http://127.0.0.1:1234"))
        )
        form.addRow("Server URL:", url_edit)
        
        model_edit = QLineEdit(dialog)
        model_edit.setPlaceholderText("gpt-5.2")
        model_edit.setText(str(cfg_map.get("model", "")))
        form.addRow("Model:", model_edit)
        
        max_tokens_spin = QSpinBox(dialog)
        max_tokens_spin.setRange(500, 20000)
        max_tokens_spin.setValue(_cfg_int("max_tokens", 4000))
        form.addRow("Max tokens:", max_tokens_spin)
        
        timeout_spin = QSpinBox(dialog)
        timeout_spin.setRange(5, 120)
        timeout_spin.setSuffix(" s")
        timeout_spin.setValue(_cfg_int("timeout", 30))
        form.addRow("Timeout:", timeout_spin)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                cfg = normalize_llm_config(
                    url_edit.text(),
                    model_edit.text(),
                    max_tokens_spin.value(),
                    timeout_spin.value(),
                )
            except ValueError as exc:
                QMessageBox.warning(self, "LLM nastavenie", str(exc))
                return
            
            self.set_llm_config(cfg)
            self.append_status(
                f"Nastavený LLM: {cfg['model']} @ {cfg['base_url']} "
                f"(max_tokens={cfg['max_tokens']}, timeout={cfg['timeout']}s)"
            )

    def _show_html_snippet_dialog(self) -> None:
        if not self._html_snippets:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("HTML snippety")
        dialog.resize(900, 700)

        layout = QVBoxLayout(dialog)
        list_widget = QListWidget(dialog)
        for snippet in self._html_snippets:
            list_widget.addItem(snippet["label"])
        layout.addWidget(QLabel("Vyber snippet:"))
        layout.addWidget(list_widget)

        summary_edit = QTextEdit(dialog)
        summary_edit.setReadOnly(True)
        summary_edit.setFont(QFont("Monospace"))
        layout.addWidget(QLabel("Sumarizovaný text:"))
        layout.addWidget(summary_edit, stretch=1)

        raw_edit = QTextEdit(dialog)
        raw_edit.setReadOnly(True)
        raw_edit.setFont(QFont("Monospace"))
        layout.addWidget(QLabel("Čisté HTML:"))
        layout.addWidget(raw_edit, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        def update(index: int) -> None:
            if index < 0 or index >= len(self._html_snippets):
                return
            data = self._html_snippets[index]
            summary_edit.setPlainText(data.get("summary", ""))
            raw_edit.setPlainText(data.get("raw", ""))

        list_widget.currentRowChanged.connect(update)
        list_widget.setCurrentRow(len(self._html_snippets) - 1)
        dialog.exec()


class AgentsDialog(QDialog):
    """Dialog showing agent activities in tabs.
    
    Each agent gets its own tab where users can see:
    - Current status
    - Thinking process
    - Status updates
    - Final response
    """
    
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        
        self.agent_tabs: dict[str, AgentActivityWidget] = {}
        self.default_llm_config = load_env_llm_defaults()
        
        self.setWindowTitle("⚙️ Agenti")
        self.setModal(False)  # Non-modal so it can stay open
        self.resize(900, 700)
        
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
        title = QLabel("⚙️ Aktivita agentov")
        title.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #e8f5e9; "
            "padding: 8px 0px;"
        )
        layout.addWidget(title)
        
        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("✓ Zavrieť")
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet(
            "QPushButton { "
            "padding: 10px 20px; font-size: 13px; font-weight: bold; border-radius: 6px; "
            "background-color: #2e7d32; color: #e8f5e9; border: 2px solid #4caf50; "
            "} "
            "QPushButton:hover { background-color: #388e3c; } "
            "QPushButton:pressed { background-color: #1b5e20; }"
        )
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def get_or_create_agent_tab(self, agent_name: str, display_name: str | None = None) -> AgentActivityWidget:
        """Get existing or create new agent activity tab.
        
        Args:
            agent_name: Internal agent identifier
            display_name: User-facing display name (defaults to agent_name)
        
        Returns:
            AgentActivityWidget for the agent
        """
        if agent_name in self.agent_tabs:
            return self.agent_tabs[agent_name]
        
        widget = AgentActivityWidget(
            agent_name,
            parent=self,
            default_llm_config=self.default_llm_config,
        )
        self.agent_tabs[agent_name] = widget
        
        tab_label = display_name or agent_name
        self.tabs.addTab(widget, tab_label)
        
        return widget

    def show_agent_tab(self, agent_name: str, display_name: str | None = None) -> AgentActivityWidget:
        """Open dialog and focus given agent tab (create if missing)."""
        widget = self.get_or_create_agent_tab(agent_name, display_name)
        self.show()
        self.raise_()
        self.activateWindow()
        idx = self.tabs.indexOf(widget)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
        return widget
    
    def remove_agent_tab(self, agent_name: str) -> None:
        """Remove agent tab."""
        if agent_name not in self.agent_tabs:
            return
        
        widget = self.agent_tabs[agent_name]
        index = self.tabs.indexOf(widget)
        if index >= 0:
            self.tabs.removeTab(index)
        
        del self.agent_tabs[agent_name]
    
    def should_auto_show(self) -> bool:
        """Check if dialog should auto-show when agent starts.
        
        Returns:
            True if auto-show is enabled (reads from environment)
        """
        import os
        value = os.getenv("SHOW_AGENT_ACTIVITY_AUTO", "true").lower()
        return value in ("true", "1", "yes", "on")
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle dialog close - allow closing even when agents are running."""
        # Don't stop agents, they continue in background (owned by MainWindow)
        # Just hide the dialog
        event.accept()
        self.hide()
    
    def reject(self) -> None:
        """Handle ESC key or X button - same as close button."""
        # Allow closing/hiding the dialog
        self.hide()
