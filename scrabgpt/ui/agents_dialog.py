"""Agents Activity Dialog - Shows agent thinking, status, and responses."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QCloseEvent, QFont, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("scrabgpt.ui.agents")


def load_env_llm_defaults() -> dict[str, object] | None:
    """Načítaj implicitné LLM nastavenie z .env (OpenAI/LLMStudio)."""
    base = os.getenv("OPENAI_BASE_URL") or os.getenv("LLMSTUDIO_BASE_URL")
    model = ""
    for item in os.getenv("OPENAI_MODELS", "").split(","):
        candidate = item.strip()
        if candidate:
            model = candidate
            break
    if not model:
        model = (os.getenv("LLMSTUDIO_MODEL") or "").strip()
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
    """Widget showing profiling blocks for a single model/agent."""

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
        self._html_snippets: list[dict[str, str]] = []
        self._setup_ui()

    @staticmethod
    def _tile_style(active: bool) -> str:
        if active:
            return (
                "QLabel {"
                "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                "stop:0 #f8f8f8, stop:1 #e1e1e1);"
                "border:1px solid #9aa4a0;"
                "border-radius:7px;"
                "color:#1c3c1c;"
                "font-weight:700;"
                "font-size:19px;"
                "}"
            )
        return (
            "QLabel {"
            "background:#24452c;"
            "border:1px dashed #3c6544;"
            "border-radius:7px;"
            "color:#7ea686;"
            "font-size:15px;"
            "}"
        )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        tile_px = 44
        spacing_px = 6
        rack_padding_px = 6
        rack_width_px = (
            7 * tile_px
            + (7 - 1) * spacing_px
            + rack_padding_px * 2
        )
        rack_height_px = tile_px + rack_padding_px * 2

        self.status_label = QLabel("Pripravený")
        self.status_label.setStyleSheet(
            "color: #b6e0bd; font-weight: 700; font-size: 14px; padding: 2px 0;"
        )
        layout.addWidget(self.status_label)

        rack_title = QLabel("🎯 Rack AI:")
        rack_title.setStyleSheet("color:#cde7d1; font-weight:700; font-size:12px;")
        layout.addWidget(rack_title)

        self.rack_shell = QWidget(self)
        self.rack_shell.setStyleSheet(
            "QWidget {"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #1a8c1a, stop:0.6 #147414, stop:1 #0b3d0b);"
            "border:1px solid #083508;"
            "border-radius:14px;"
            "}"
        )
        self.rack_shell.setFixedSize(rack_width_px, rack_height_px)
        rack_shadow = QGraphicsOpacityEffect(self.rack_shell)
        rack_shadow.setOpacity(0.98)
        self.rack_shell.setGraphicsEffect(rack_shadow)
        rack_layout = QHBoxLayout(self.rack_shell)
        rack_layout.setContentsMargins(rack_padding_px, rack_padding_px, rack_padding_px, rack_padding_px)
        rack_layout.setSpacing(spacing_px)
        self._rack_tiles: list[QLabel] = []
        for _ in range(7):
            tile = QLabel("")
            tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tile.setFixedSize(tile_px, tile_px)
            tile.setStyleSheet(self._tile_style(active=False))
            rack_layout.addWidget(tile)
            self._rack_tiles.append(tile)
        layout.addWidget(self.rack_shell, alignment=Qt.AlignmentFlag.AlignLeft)

        self.tool_calls_log = self._create_log_section(
            layout,
            "🛠️ Tool calls",
            min_height=120,
        )
        self.word_validation_log = self._create_log_section(
            layout,
            "📚 Overovanie slov",
            min_height=120,
        )
        self.judge_log = self._create_log_section(
            layout,
            "⚖️ Judge",
            min_height=110,
        )

        output_label = QLabel("✅ Výstup modelu:")
        output_label.setStyleSheet("color:#cde7d1; font-weight:700; font-size:12px;")
        layout.addWidget(output_label)

        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        font = QFont("Monospace")
        font.setPointSize(10)
        self.response_text.setFont(font)
        self.response_text.setMaximumHeight(96)
        self.response_text.setStyleSheet(
            "QTextEdit {"
            "background:#0f1a12; color:#8ef0a7;"
            "border:1px solid #2f5c39; border-radius:6px; padding:10px;"
            "}"
        )
        layout.addWidget(self.response_text)

        clear_btn = QPushButton("🗑️ Vymazať")
        clear_btn.clicked.connect(self.clear_log)
        clear_btn.setStyleSheet(
            "QPushButton {"
            "padding:7px 14px; font-size:12px; border-radius:5px;"
            "background:#3d2a0f; color:#ffd54f; border:1px solid #8a6a4a;"
            "}"
            "QPushButton:hover { background:#4d3a1f; border-color:#ff9800; }"
        )
        layout.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # Backward-compat alias used in app helpers.
        self.activity_log = self.tool_calls_log

        if self.llm_config:
            self.set_llm_config(self.llm_config)

    def _create_log_section(
        self,
        layout: QVBoxLayout,
        title: str,
        *,
        min_height: int,
    ) -> QTextEdit:
        title_label = QLabel(title)
        title_label.setStyleSheet("color:#cde7d1; font-weight:700; font-size:12px;")
        layout.addWidget(title_label)

        editor = QTextEdit()
        editor.setReadOnly(True)
        editor.setAcceptRichText(True)
        editor.setMinimumHeight(min_height)
        editor.setStyleSheet(
            "QTextEdit {"
            "background:#060a07; color:#e8f5e9;"
            "border:1px solid #2f5c39; border-radius:6px; padding:10px;"
            "font-family:'Monospace', 'Courier New'; font-size:11px;"
            "}"
        )
        layout.addWidget(editor)
        return editor

    def _editor_for_section(self, section: str) -> QTextEdit:
        normalized = (section or "tool_calls").strip().lower()
        if normalized in {"word", "words", "word_validation", "validation"}:
            return self.word_validation_log
        if normalized in {"judge", "result", "final"}:
            return self.judge_log
        return self.tool_calls_log

    @staticmethod
    def _auto_section(prefix: str, message: str) -> str:
        text = f"{prefix} {message}".lower()
        if "overenie slova" in text or "validate_word" in text:
            return "word_validation"
        if "rozhodca" in text or "judge" in text or "⚖" in prefix:
            return "judge"
        return "tool_calls"

    def set_status(self, status: str, is_working: bool = False) -> None:
        marker = "🟢 " if is_working else "✅ "
        self.status_label.setText(f"{marker}{status}")

    def update_progress(self, percent: int | None) -> None:
        del percent

    def update_context_progress(self, percent: int | None) -> None:
        del percent

    def set_ai_rack(self, letters: list[str]) -> None:
        normalized = [str(ch).strip().upper() for ch in letters if str(ch).strip()][:7]
        for idx, tile in enumerate(self._rack_tiles):
            if idx < len(normalized):
                tile.setText(normalized[idx])
                tile.setStyleSheet(self._tile_style(active=True))
            else:
                tile.setText("")
                tile.setStyleSheet(self._tile_style(active=False))

    def append_activity(
        self,
        message: str,
        prefix: str = "ℹ️",
        color: str | None = None,
        *,
        section: str = "auto",
    ) -> None:
        target_section = section
        if section == "auto":
            target_section = self._auto_section(prefix, message)
        editor = self._editor_for_section(target_section)
        scrollbar = editor.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10

        timestamp = datetime.now().strftime("%H:%M:%S")
        if color:
            formatted = (
                f'<span style="color:#d9eadc;">[{timestamp}] {prefix}</span> '
                f'<span style="color:{color};">{message}</span>'
            )
            editor.append(formatted)
        else:
            editor.append(f"[{timestamp}] {prefix} {message}")

        if was_at_bottom:
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            editor.setTextCursor(cursor)
            scrollbar.setValue(scrollbar.maximum())

    def append_thinking(self, thought: str) -> None:
        self.append_activity(thought, prefix="💭", section="tool_calls")

    def append_status(self, status: str) -> None:
        self.append_activity(status, prefix="📊", section="tool_calls")

    def append_prompt(self, prompt: str) -> None:
        for line in prompt.split("\n"):
            if line.strip():
                self.append_activity(line, prefix="🧾", color="#8ef0a7", section="tool_calls")

    def add_html_snippet(self, label: str, raw_html: str, summary: str) -> None:
        self._html_snippets.append(
            {
                "label": label,
                "raw": raw_html,
                "summary": summary,
            }
        )
        self.append_activity(
            f"HTML snippet uložený: {label}",
            prefix="📎",
            color="#9ec8ff",
            section="tool_calls",
        )

    def set_llm_config(self, cfg: dict[str, object]) -> None:
        self.llm_config = cfg
        self.llm_config_changed.emit(cfg)

    def set_response(self, response: str) -> None:
        self.response_text.setPlainText(response.strip())

    def append_response(self, response: str) -> None:
        if not response:
            return
        current = self.response_text.toPlainText().strip()
        if not current:
            self.response_text.setPlainText(response.strip())
            return
        self.response_text.setPlainText(f"{current}\n{response.strip()}")

    def clear_log(self) -> None:
        self.tool_calls_log.clear()
        self.word_validation_log.clear()
        self.judge_log.clear()
        self.response_text.clear()
        self.set_status("Pripravený", is_working=False)
        self._html_snippets.clear()
        self.set_ai_rack([])


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
            widget = self.agent_tabs[agent_name]
            if display_name:
                idx = self.tabs.indexOf(widget)
                if idx >= 0 and self.tabs.tabText(idx) != display_name:
                    self.tabs.setTabText(idx, display_name)
            return widget
        
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
