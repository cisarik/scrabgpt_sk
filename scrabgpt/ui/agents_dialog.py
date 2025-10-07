"""Agents Activity Dialog - Shows agent thinking, status, and responses.

This dialog provides visibility into agent operations without exposing MCP
terminology to end users. Each agent gets its own tab showing real-time activity.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Any
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QTextCursor, QCloseEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTabWidget, QWidget, QTextEdit, QProgressBar,
    QListWidget, QDialogButtonBox,
)

log = logging.getLogger("scrabgpt.ui.agents")


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
    
    def __init__(self, agent_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.agent_name = agent_name
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
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Status bar
        status_layout = QHBoxLayout()

        self.status_label = QLabel("Pripravený")
        self.status_label.setStyleSheet(
            "color: #b6e0bd; font-weight: bold; font-size: 13px;"
        )
        status_layout.addWidget(self.status_label)
        
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
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #2e7d32, stop:1 #4caf50); "
            "border-radius: 3px; "
            "}"
        )
        status_layout.addWidget(self.progress_bar, stretch=2)  # Give it more space
        
        layout.addLayout(status_layout)
        
        # Activity log (thinking + status)
        activity_label = QLabel("🧠 Aktivita:")
        activity_label.setStyleSheet("color: #b6e0bd; font-weight: bold; font-size: 13px;")
        layout.addWidget(activity_label)
        
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

    def add_html_snippet(self, label: str, raw_html: str, summary: str) -> None:
        snippet = {
            "label": label,
            "raw": raw_html,
            "summary": summary,
        }
        self._html_snippets.append(snippet)
        self.html_snippet_button.setEnabled(True)
        self.html_snippet_button.setText(f"Zobraziť HTML ({label})")

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
        
        # Info label
        info_label = QLabel(
            "Tu môžete sledovať, čo agenti robia. Každý agent má vlastnú záložku."
        )
        info_label.setStyleSheet(
            "color: white; font-size: 14px; font-style: italic; "
            "padding: 4px 0px;"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
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
        
        widget = AgentActivityWidget(agent_name, parent=self)
        self.agent_tabs[agent_name] = widget
        
        tab_label = display_name or agent_name
        self.tabs.addTab(widget, tab_label)
        
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
